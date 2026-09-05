"""Convert one or more OpenWrt IPK files into an iKuai 4.0 IPKG."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .builder import (
    IpkgSpec,
    guess_port,
    normalize_version,
    pack_ipkg,
    pick_command,
    sanitize_name,
    write_ipkg_tree,
)
from .parser import IpkError, IpkPackage, extract_data_tree, load_ipk


@dataclass
class ConvertResult:
    output: Path
    spec: IpkgSpec
    packages: list[IpkPackage]
    warnings: list[str]


def suggest_spec(packages: list[IpkPackage]) -> IpkgSpec:
    if not packages:
        raise IpkError("没有可转换的 IPK")
    primary = next((p for p in packages if not p.control.is_luci), packages[0])
    others = [p for p in packages if p is not primary]
    all_exec = []
    all_files = []
    for pkg in packages:
        all_exec.extend(pkg.executables)
        all_files.extend(pkg.files)

    name = sanitize_name(primary.control.package or primary.path.stem)
    display = primary.control.package or name
    version = normalize_version(primary.control.version)
    desc_parts = [primary.control.description.strip()] if primary.control.description.strip() else []
    if others:
        extra = "、".join(p.control.package or p.path.name for p in others)
        desc_parts.append(f"合并包: {extra}")
    description = "\n".join(desc_parts) or display
    port = guess_port(primary.control.package, all_files)
    command = pick_command(primary.control.package, all_exec)
    maintainer = primary.control.maintainer.split("<")[0].strip() if primary.control.maintainer else "ipk2ipkg"
    extra_env: dict[str, str] = {}
    cap_add: list[str] = []
    need_tun = False
    memory = "128MB"
    pkg_key = (primary.control.package or "").lower()
    if "ninja" in pkg_key:
        extra_env["NINJA_LISTEN"] = "0.0.0.0"
        extra_env["NINJA_PORT"] = str(port)
        cap_add = ["NET_ADMIN", "NET_RAW"]
        need_tun = True
        memory = "512MB"
    return IpkgSpec(
        name=name,
        display_name=display,
        version=version,
        description=description.replace("\n", " ").strip(),
        maintainer=maintainer or "ipk2ipkg",
        command=command,
        host_port=port,
        container_port=port,
        extra_env=extra_env,
        cap_add=cap_add,
        need_tun=need_tun,
        memory=memory,
        changelog=f"{version} - converted from {primary.path.name}\n",
    )


def convert_ipks(
    ipk_paths: list[str | Path],
    output_dir: str | Path,
    spec: IpkgSpec | None = None,
    keep_work: bool = False,
) -> ConvertResult:
    packages: list[IpkPackage] = []
    warnings: list[str] = []
    for path in ipk_paths:
        pkg = load_ipk(path)
        packages.append(pkg)
        if pkg.warning:
            warnings.append(f"{pkg.path.name}: {pkg.warning}")
        if pkg.kind == "ikuai3-encrypted":
            raise IpkError(pkg.warning)
        if pkg.kind == "ikuai4-ipkg":
            # already an ipkg tarball; copy/rename
            dest = Path(output_dir)
            dest.mkdir(parents=True, exist_ok=True)
            out = dest / (Path(path).stem + ".ipkg")
            shutil.copy2(path, out)
            dummy = spec or IpkgSpec(name=Path(path).stem, display_name=Path(path).stem, version="1.0.0")
            return ConvertResult(output=out, spec=dummy, packages=packages, warnings=warnings)

    merged = spec or suggest_spec(packages)
    merged.name = sanitize_name(merged.name)
    merged.version = normalize_version(merged.version)
    if not merged.display_name:
        merged.display_name = merged.name
    if merged.host_port <= 0:
        merged.host_port = 8080
    if merged.container_port <= 0:
        merged.container_port = merged.host_port

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="ipk2ipkg-"))
    try:
        rootfs = work / "rootfs"
        rootfs.mkdir(parents=True, exist_ok=True)
        for pkg in packages:
            if pkg.kind == "openwrt-ipk":
                extract_data_tree(pkg, rootfs)
        app_dir = write_ipkg_tree(work / "tree", merged, rootfs=rootfs)
        output = output_dir / f"{merged.name}-{merged.version}.ipkg"
        pack_ipkg(app_dir, output)
        return ConvertResult(output=output, spec=merged, packages=packages, warnings=warnings)
    finally:
        if not keep_work:
            shutil.rmtree(work, ignore_errors=True)


def convert_one(ipk_path: str | Path, output_dir: str | Path, **kwargs) -> ConvertResult:
    spec = kwargs.pop("spec", None)
    return convert_ipks([ipk_path], output_dir, spec=spec, **kwargs)
