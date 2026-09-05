"""Command-line entry for converting IPK files without the GUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __app_name__, __version__
from .builder import IpkgSpec, normalize_version, sanitize_name
from .convert import convert_ipks, suggest_spec
from .parser import IpkError, load_ipk


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ipk2ipkg",
        description="将 OpenWrt IPK 转换为爱快 4.0 应用市场 IPKG",
    )
    parser.add_argument("ipk", nargs="*", help="一个或多个 .ipk 文件")
    parser.add_argument("-o", "--output", help="输出目录，默认与第一个 IPK 同目录")
    parser.add_argument("--name", help="应用内部名称")
    parser.add_argument("--display-name", help="显示名称")
    parser.add_argument("--version", help="版本号（爱快要求 x.y.z）")
    parser.add_argument("--image", default="alpine:3.20", help="Docker 镜像，默认 alpine:3.20")
    parser.add_argument("--command", help="容器启动命令")
    parser.add_argument("--port", type=int, help="Web 端口")
    parser.add_argument("--container-port", type=int, help="容器内部端口")
    parser.add_argument("--host-network", action="store_true", help="使用 host 网络")
    parser.add_argument("--inspect", action="store_true", help="只解析 IPK，不打包")
    parser.add_argument("-v", "--version-tool", action="version", version=f"{__app_name__} {__version__}")
    return parser


def print_inspect(path: Path) -> int:
    pkg = load_ipk(path)
    c = pkg.control
    print(f"文件: {pkg.path}")
    print(f"类型: {pkg.kind}")
    print(f"包名: {c.package}")
    print(f"版本: {c.version}")
    print(f"架构: {c.architecture}")
    print(f"维护: {c.maintainer}")
    print(f"依赖: {c.depends}")
    print(f"描述: {c.description}")
    if pkg.warning:
        print(f"警告: {pkg.warning}")
    print(f"可执行文件 ({len(pkg.executables)}):")
    for name in pkg.executables[:30]:
        print(f"  {name}")
    if len(pkg.executables) > 30:
        print("  ...")
    print(f"文件数: {len(pkg.files)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.ipk:
        parser.print_help()
        return 2
    paths = [Path(p) for p in args.ipk]
    for path in paths:
        if not path.is_file():
            print(f"找不到文件: {path}", file=sys.stderr)
            return 1
    try:
        if args.inspect:
            code = 0
            for path in paths:
                code = print_inspect(path) or code
                print()
            return code
        packages = [load_ipk(p) for p in paths]
        spec = suggest_spec(packages)
        if args.name:
            spec.name = sanitize_name(args.name)
        if args.display_name:
            spec.display_name = args.display_name
        if args.version:
            spec.version = normalize_version(args.version)
        spec.image = args.image
        if args.command:
            spec.command = args.command
        if args.port:
            spec.host_port = args.port
            if not args.container_port:
                spec.container_port = args.port
        if args.container_port:
            spec.container_port = args.container_port
        spec.host_network = args.host_network
        output_dir = Path(args.output) if args.output else paths[0].parent
        result = convert_ipks(paths, output_dir, spec=spec)
        for warning in result.warnings:
            print(f"警告: {warning}")
        print(f"已生成: {result.output}")
        return 0
    except IpkError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
