"""Create a synthetic OpenWrt IPK and convert it, to verify the pipeline."""

from __future__ import annotations

import gzip
import io
import tarfile
import tempfile
from pathlib import Path


def _tar_gz(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith("demo") else 0o644
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def make_ipk(path: Path) -> Path:
    control = (
        "Package: demo-app\n"
        "Version: 1.2.3-1\n"
        "Architecture: x86_64\n"
        "Maintainer: Test <test@example.com>\n"
        "Section: net\n"
        "Description: Demo service for ipk2ipkg tests\n"
    ).encode("utf-8")
    control_tar = _tar_gz({"control": control})
    data_tar = _tar_gz(
        {
            "usr/bin/demo": b"#!/bin/sh\necho demo\n",
            "etc/demo.conf": b"port=8080\n",
        }
    )
    debian = b"2.0\n"
    outer = io.BytesIO()
    with tarfile.open(fileobj=outer, mode="w:gz") as tf:
        for name, data in (
            ("debian-binary", debian),
            ("control.tar.gz", control_tar),
            ("data.tar.gz", data_tar),
        ):
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    path.write_bytes(outer.getvalue())
    return path


def make_ar_ipk(path: Path) -> Path:
    def ar_header(name: str, size: int) -> bytes:
        header = (
            name.ljust(16).encode("ascii")
            + b"0".ljust(12)
            + b"0".ljust(6)
            + b"0".ljust(6)
            + b"100644".ljust(8)
            + str(size).encode("ascii").ljust(10)
            + b"`\n"
        )
        return header

    control = (
        "Package: ar-demo\n"
        "Version: 4.5\n"
        "Architecture: x86_64\n"
        "Maintainer: Test\n"
        "Description: AR packaged demo\n"
    ).encode("utf-8")
    control_tar = _tar_gz({"control": control})
    data_tar = _tar_gz({"usr/sbin/ar-demo": b"\x7fELF" + b"\x00" * 16})
    debian = b"2.0\n"
    parts = [(b"debian-binary", debian), (b"control.tar.gz", control_tar), (b"data.tar.gz", data_tar)]
    blob = bytearray(b"!<arch>\n")
    for name, data in parts:
        blob.extend(ar_header(name.decode(), len(data)))
        blob.extend(data)
        if len(data) % 2 == 1:
            blob.append(0)
    path.write_bytes(bytes(blob))
    return path


def main() -> None:
    from ipk2ipkg.convert import convert_ipks
    from ipk2ipkg.parser import load_ipk

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ipk = make_ipk(tmp_path / "demo-app_1.2.3-1_x86_64.ipk")
        pkg = load_ipk(ipk)
        assert pkg.control.package == "demo-app", pkg.control
        assert pkg.control.architecture == "x86_64"
        assert any(name.endswith("usr/bin/demo") or name == "usr/bin/demo" for name in pkg.executables), pkg.executables

        ar_ipk = make_ar_ipk(tmp_path / "ar-demo_4.5_x86_64.ipk")
        ar_pkg = load_ipk(ar_ipk)
        assert ar_pkg.control.package == "ar-demo"
        assert ar_pkg.kind == "openwrt-ipk"

        out = tmp_path / "out"
        result = convert_ipks([ipk], out)
        assert result.output.exists(), result
        assert result.output.suffix == ".ipkg"
        assert result.spec.version == "1.2.3"
        assert result.spec.name == "demo_app"
        import tarfile
        with tarfile.open(result.output, "r:gz") as tf:
            compose = tf.extractfile("demo_app/app/docker-compose.yaml").read().decode()
            entry = tf.extractfile("demo_app/app/entrypoint.sh").read().decode()
        assert "./data:/data" in compose
        assert "/opt/pkg/data" not in compose
        assert "./rootfs:/opt/pkg:ro" in compose
        assert "entrypoint.sh" in compose
        assert "APP_COMMAND" in compose
        assert "link_dir" in entry
        print("OK", result.output)
        print("version", result.spec.version)
        print("command", result.spec.command)


if __name__ == "__main__":
    main()
