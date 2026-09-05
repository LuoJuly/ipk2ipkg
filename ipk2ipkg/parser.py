"""Parse OpenWrt / ipkg `.ipk` archives and iKuai 3.x encrypted blobs."""

from __future__ import annotations

import gzip
import io
import lzma
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


class IpkError(ValueError):
    pass


@dataclass
class Control:
    package: str = ""
    version: str = ""
    architecture: str = ""
    maintainer: str = ""
    description: str = ""
    depends: str = ""
    section: str = ""
    source: str = ""
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def is_luci(self) -> bool:
        name = self.package.lower()
        return name.startswith("luci-") or self.section.lower() in {"luci", "luci-app"}


@dataclass
class IpkPackage:
    path: Path
    kind: str
    control: Control
    files: list[str] = field(default_factory=list)
    executables: list[str] = field(default_factory=list)
    data: bytes = b""
    scripts: dict[str, str] = field(default_factory=dict)

    @property
    def warning(self) -> str:
        if self.kind == "ikuai3-encrypted":
            return "这是爱快 3.x 加密插件包，无法直接转为 4.0 IPKG（缺少解密密钥）。"
        if self.kind == "ikuai4-ipkg":
            return "这已经是爱快 4.0 IPKG 结构，将按原样重新打包。"
        if self.control.is_luci:
            return "这是 OpenWrt LuCI 插件，依赖 OpenWrt 后台，无法在爱快应用市场以 Docker 方式运行。"
        arch = self.control.architecture.lower()
        if arch and arch not in {"all", "x86_64", "amd64", "aarch64", "arm64", "aarch64_generic"}:
            return f"架构 {self.control.architecture} 可能与爱快软路由不匹配（常见为 x86_64 / aarch64）。"
        return ""


def parse_control_text(text: str) -> Control:
    fields: dict[str, str] = {}
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            continue
        if line[:1] in {" ", "\t"} and current:
            fields[current] = fields[current] + "\n" + line.strip()
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current = key.strip()
        fields[current] = value.strip()

    def get(*names: str) -> str:
        for name in names:
            for k, v in fields.items():
                if k.lower() == name.lower():
                    return v
        return ""

    desc = get("Description")
    return Control(
        package=get("Package"),
        version=get("Version"),
        architecture=get("Architecture"),
        maintainer=get("Maintainer"),
        description=desc,
        depends=get("Depends"),
        section=get("Section"),
        source=get("Source"),
        fields={k: v for k, v in fields.items()},
    )


def _read_ar_members(data: bytes) -> dict[str, bytes]:
    if not data.startswith(b"!<arch>\n"):
        raise IpkError("不是 ar 归档")
    pos = 8
    members: dict[str, bytes] = {}
    n = len(data)
    while pos + 60 <= n:
        header = data[pos : pos + 60]
        pos += 60
        if header[58:60] not in (b"`\n", b"`\r"):
            break
        name = header[0:16].decode("ascii", "replace").strip()
        size_s = header[48:58].decode("ascii", "replace").strip()
        try:
            size = int(size_s)
        except ValueError:
            break
        payload = data[pos : pos + size]
        pos += size
        if size % 2 == 1:
            pos += 1
        if name.startswith("#1/"):
            try:
                namelen = int(name[3:])
            except ValueError:
                namelen = 0
            name = payload[:namelen].rstrip(b"\x00").decode("ascii", "replace").strip()
            payload = payload[namelen:]
        name = name.strip("/").strip()
        members[name] = payload
    if not members:
        raise IpkError("ar 归档为空")
    return members


def _open_tar(blob: bytes) -> tarfile.TarFile:
    bio = io.BytesIO(blob)
    try:
        return tarfile.open(fileobj=bio, mode="r:*")
    except tarfile.TarError as exc:
        raise IpkError(f"无法解开 tar: {exc}") from exc


def _decompress_named(name: str, blob: bytes) -> bytes:
    lower = name.lower()
    if lower.endswith(".gz") or lower.endswith(".gzip"):
        return gzip.decompress(blob)
    if lower.endswith(".xz") or lower.endswith(".lzma"):
        return lzma.decompress(blob)
    if lower.endswith(".bz2") or lower.endswith(".bzip2"):
        import bz2

        return bz2.decompress(blob)
    return blob


def _tar_member_bytes(tf: tarfile.TarFile, names: Iterable[str]) -> bytes | None:
    wanted = {n.lower() for n in names}
    for member in tf.getmembers():
        base = Path(member.name).name.lower()
        if base in wanted and member.isfile():
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            return extracted.read()
    return None


def _extract_control_and_data(members: dict[str, bytes]) -> tuple[bytes, bytes]:
    control_blob = None
    data_blob = None
    for name, blob in members.items():
        base = Path(name).name.lower()
        if base.startswith("control.tar"):
            control_blob = blob
        elif base.startswith("data.tar"):
            data_blob = blob
    if control_blob is None or data_blob is None:
        raise IpkError("IPK 中缺少 control.tar.* 或 data.tar.*")
    return control_blob, data_blob


def _parse_control_tar(blob: bytes) -> tuple[Control, dict[str, str]]:
    tf = _open_tar(blob)
    try:
        control_text = ""
        scripts: dict[str, str] = {}
        for member in tf.getmembers():
            if not member.isfile():
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            raw = extracted.read()
            name = Path(member.name).name
            if name == "control":
                control_text = raw.decode("utf-8", "replace")
            elif name in {"preinst", "postinst", "prerm", "postrm"}:
                scripts[name] = raw.decode("utf-8", "replace")
        if not control_text:
            raise IpkError("control.tar 中没有 control 文件")
        return parse_control_text(control_text), scripts
    finally:
        tf.close()


def _is_executable_member(member: tarfile.TarInfo, payload: bytes) -> bool:
    name = member.name.replace("\\", "/").lstrip("./")
    if member.isdir() or name.endswith("/"):
        return False
    if payload.startswith(b"\x7fELF") or payload.startswith(b"#!"):
        return True
    mode = member.mode or 0
    if mode & 0o111 and not name.endswith((".so", ".so.0", ".so.1")):
        base = Path(name).name
        if "." not in base or base.endswith(".sh"):
            return True
    return False


def _parse_data_tar(blob: bytes) -> tuple[list[str], list[str]]:
    tf = _open_tar(blob)
    files: list[str] = []
    executables: list[str] = []
    try:
        for member in tf.getmembers():
            name = member.name.replace("\\", "/").lstrip("./")
            if not name or name.endswith("/"):
                continue
            files.append(name)
            if not member.isfile():
                continue
            extracted = tf.extractfile(member)
            payload = extracted.read() if extracted is not None else b""
            if _is_executable_member(member, payload):
                executables.append(name)
    finally:
        tf.close()
    files.sort()
    executables.sort()
    return files, executables


def _looks_like_ipkg_tar(blob: bytes) -> bool:
    try:
        tf = _open_tar(blob)
    except IpkError:
        return False
    try:
        names = [m.name.replace("\\", "/").lstrip("./") for m in tf.getmembers()]
    finally:
        tf.close()
    return any(n.endswith("manifest.json") or n == "manifest.json" for n in names)


def _members_from_ipk_tar(blob: bytes) -> dict[str, bytes]:
    tf = _open_tar(blob)
    members: dict[str, bytes] = {}
    try:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            members[Path(member.name).name] = extracted.read()
    finally:
        tf.close()
    return members


def sniff_kind(data: bytes) -> str:
    if data.startswith(b"Salted__"):
        return "ikuai3-encrypted"
    if data.startswith(b"!<arch>"):
        return "ar"
    if data.startswith(b"\x1f\x8b"):
        return "gzip"
    if data.startswith(b"\xfd7zXZ"):
        return "xz"
    if data[257:262] == b"ustar":
        return "tar"
    return "unknown"


def load_ipk(path: str | Path) -> IpkPackage:
    path = Path(path)
    data = path.read_bytes()
    kind = sniff_kind(data)

    if kind == "ikuai3-encrypted":
        return IpkPackage(path=path, kind=kind, control=Control(package=path.stem), data=data)

    if kind == "ar":
        members = _read_ar_members(data)
        control_blob, data_blob = _extract_control_and_data(members)
        control, scripts = _parse_control_tar(control_blob)
        files, executables = _parse_data_tar(data_blob)
        return IpkPackage(
            path=path,
            kind="openwrt-ipk",
            control=control,
            files=files,
            executables=executables,
            data=data,
            scripts=scripts,
        )

    # gzip / xz / tar
    if kind in {"gzip", "xz", "tar", "unknown"}:
        blob = data
        if _looks_like_ipkg_tar(blob):
            control = Control(package=path.stem, version="1.0.0", description="已是爱快 IPKG")
            return IpkPackage(path=path, kind="ikuai4-ipkg", control=control, data=data)
        try:
            members = _members_from_ipk_tar(blob)
            if any(n.startswith("control.tar") for n in members) and any(
                n.startswith("data.tar") for n in members
            ):
                control_blob, data_blob = _extract_control_and_data(members)
                control, scripts = _parse_control_tar(control_blob)
                files, executables = _parse_data_tar(data_blob)
                return IpkPackage(
                    path=path,
                    kind="openwrt-ipk",
                    control=control,
                    files=files,
                    executables=executables,
                    data=data,
                    scripts=scripts,
                )
        except IpkError:
            pass
        if _looks_like_ipkg_tar(blob):
            return IpkPackage(
                path=path,
                kind="ikuai4-ipkg",
                control=Control(package=path.stem),
                data=data,
            )

    raise IpkError(f"无法识别的 IPK 格式: {path.name} ({kind})")


def extract_data_tree(ipk: IpkPackage, dest_dir: Path) -> None:
    """Extract data.tar.* contents into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    kind = sniff_kind(ipk.data)
    if kind == "ar":
        members = _read_ar_members(ipk.data)
    else:
        members = _members_from_ipk_tar(ipk.data)
    _, data_blob = _extract_control_and_data(members)
    tf = _open_tar(data_blob)
    try:
        try:
            tf.extractall(dest_dir, filter="data")
        except TypeError:
            tf.extractall(dest_dir)
    finally:
        tf.close()
