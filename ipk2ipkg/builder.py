"""Build iKuai 4.0 `.ipkg` archives (tar.gz with top-level app directory)."""

from __future__ import annotations

import json
import re
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

from .icon import make_app_icon_png


KNOWN_PORTS: dict[str, int] = {
    "adguardhome": 3000,
    "alist": 5244,
    "aria2": 6800,
    "caddy": 80,
    "clash": 9090,
    "clash-meta": 9090,
    "ddns-go": 9876,
    "emby": 8096,
    "filebrowser": 8080,
    "frps": 7000,
    "heimdall": 80,
    "homeassistant": 8123,
    "homebox": 5173,
    "homepage": 3000,
    "jellyfin": 8096,
    "lucky": 16601,
    "mihomo": 9090,
    "minio": 9000,
    "mosquitto": 1883,
    "navidrome": 4533,
    "nezha": 8008,
    "nginx": 80,
    "ninjadesktop": 9190,
    "ninjadesktop-lite": 9190,
    "nikki": 9090,
    "openclash": 9090,
    "openlist": 5244,
    "plex": 32400,
    "portainer": 9000,
    "qbittorrent": 8080,
    "shellcrash": 9090,
    "sing-box": 9090,
    "subconverter": 25500,
    "sun-panel": 3002,
    "syncthing": 8384,
    "transmission": 9091,
    "uptime-kuma": 3001,
    "v2raya": 2017,
    "vaultwarden": 80,
    "webdav": 8080,
}


def sanitize_name(name: str) -> str:
    raw = (name or "app").strip().lower()
    for prefix in ("luci-i18n-", "luci-app-", "luci-theme-", "luci-", "lib"):
        if raw.startswith(prefix) and len(raw) > len(prefix) + 1:
            raw = raw[len(prefix) :]
            break
    cleaned = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if not cleaned:
        cleaned = "app"
    if cleaned[0].isdigit():
        cleaned = "app_" + cleaned
    return cleaned[:32]


def normalize_version(version: str) -> str:
    text = (version or "").strip().lstrip("vV")
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if match:
        return f"{int(match.group(1))}.{int(match.group(2))}.{int(match.group(3))}"
    match = re.search(r"(\d+)\.(\d+)", text)
    if match:
        return f"{int(match.group(1))}.{int(match.group(2))}.0"
    match = re.search(r"(\d+)", text)
    if match:
        return f"{int(match.group(1))}.0.0"
    return "1.0.0"


def guess_port(package: str, files: list[str] | None = None) -> int:
    key = (package or "").lower()
    for name, port in KNOWN_PORTS.items():
        if name in key:
            return port
    if files:
        joined = "\n".join(files).lower()
        found = re.findall(r":(\d{2,5})\b", joined)
        for item in found:
            value = int(item)
            if 80 <= value <= 65535 and value not in {22, 53, 123}:
                return value
    return 8080


def pick_command(package: str, executables: list[str]) -> str:
    if not executables:
        return ""
    pkg = sanitize_name(package)
    scored: list[tuple[int, str]] = []
    for rel in executables:
        norm = rel.replace("\\", "/").lstrip("./")
        base = Path(norm).name.lower()
        score = 0
        if base == pkg or base.replace("-", "_") == pkg:
            score += 50
        if pkg and pkg in base:
            score += 20
        if any(norm.startswith(prefix) for prefix in ("usr/bin/", "usr/sbin/", "bin/", "sbin/")):
            score += 10
        if base.endswith(".sh"):
            score -= 5
        if "luci" in base:
            score -= 20
        scored.append((score, norm))
    scored.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    rel = scored[0][1]
    return f"/opt/pkg/{rel}"


@dataclass
class IpkgSpec:
    name: str
    display_name: str
    version: str
    description: str = ""
    maintainer: str = "ipk2ipkg"
    maintainer_url: str = ""
    distributor: str = "ipk2ipkg"
    distributor_url: str = ""
    image: str = "alpine:3.20"
    command: str = ""
    host_port: int = 8080
    container_port: int = 8080
    protocol: str = "tcp"
    host_network: bool = False
    extra_args: str = ""
    memory: str = "128MB"
    storage: str = "100MB"
    os_min_version: str = "3.7.0"
    changelog: str = ""
    readme: str = ""
    extra_env: dict[str, str] = field(default_factory=dict)


def _yaml_quote(value: str) -> str:
    if value == "":
        return '""'
    if re.search(r'[:#{}[\],&*?|!<>=%@"\'\n]', value) or value.strip() != value:
        return json.dumps(value, ensure_ascii=False)
    return value


def render_compose(spec: IpkgSpec) -> str:
    service = spec.name
    extra = spec.extra_args.strip()
    command_line = spec.command.strip()
    if extra:
        command_line = f"{command_line} {extra}".strip()
    if not command_line:
        command_line = "sleep infinity"

    lines = [
        "services:",
        f"  {service}:",
        f"    image: {spec.image}",
        f"    container_name: {service}-${{NAME_NONCE}}",
        "    deploy:",
        "      resources:",
        "        limits:",
        "          cpus: ${CPUS_LIMIT}",
        "          memory: ${MEMORY_LIMIT}",
        "    restart: ${RESTART}",
        "    working_dir: /opt/pkg",
        "    environment:",
        "      - PATH=/opt/pkg/usr/sbin:/opt/pkg/usr/bin:/opt/pkg/sbin:/opt/pkg/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "      - LD_LIBRARY_PATH=/opt/pkg/lib:/opt/pkg/usr/lib",
        "    volumes:",
        "      - ./rootfs:/opt/pkg:ro",
        "      - ./data:/opt/pkg/data",
        "    command: " + _yaml_quote(command_line),
        "    env_file:",
        "      - ./environment",
        "    logging:",
        '      driver: "json-file"',
        "      options:",
        '        max-size: "10m"',
        '        max-file: "3"',
    ]
    if spec.host_network:
        lines.append("    network_mode: host")
    else:
        proto = spec.protocol.lower() if spec.protocol.lower() in {"tcp", "udp"} else "tcp"
        lines.append("    ports:")
        lines.append(f"      - ${{HOST_IP}}:${{APP_PORT_WEB}}:{spec.container_port}/{proto}")
        lines.append("    networks:")
        lines.append("      - doc_app_default")
    lines.append("    labels:")
    lines.append(f'      createdBy: "{spec.display_name}"')
    if not spec.host_network:
        lines.extend(
            [
                "",
                "networks:",
                "  doc_app_default:",
                "    external: true",
                "    name: doc_app_default",
            ]
        )
    return "\n".join(lines) + "\n"


def render_option_json(spec: IpkgSpec) -> str:
    options = [
        {
            "default": spec.host_port,
            "attrname": "APP_PORT_WEB",
            "label": {"en": "Web Port", "zh": "Web 端口"},
            "required": True,
            "scope": "config",
            "type": "integer",
            "min": 1,
            "max": 65535,
            "description": {"zh": f"映射到容器 {spec.container_port} 端口"},
        }
    ]
    return json.dumps(options, ensure_ascii=False, indent=2) + "\n"


def render_manifest(spec: IpkgSpec) -> str:
    payload = {
        "name": spec.name,
        "version": spec.version,
        "display_name": spec.display_name,
        "image": spec.image,
        "description": spec.description or spec.display_name,
        "type": "1",
        "maintainer": spec.maintainer or "ipk2ipkg",
        "maintainer_url": spec.maintainer_url or "",
        "distributor": spec.distributor or "ipk2ipkg",
        "distributor_url": spec.distributor_url or "",
        "requirements": {
            "memory": spec.memory,
            "storage": spec.storage,
            "os_min_version": spec.os_min_version,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def default_readme(spec: IpkgSpec) -> str:
    return (
        f"# {spec.display_name}\n\n"
        f"{spec.description or spec.display_name}\n\n"
        "## 安装\n"
        "爱快 4.0：高级应用 → 应用市场 → 本地安装，上传本 `.ipkg`。\n"
        "需要已启用 Docker。\n\n"
        f"## 访问\n"
        f"默认端口：`{spec.host_port}`\n"
        f"启动命令：`{spec.command or '（未指定）'}`\n\n"
        "本包由 ipk2ipkg 从 OpenWrt IPK 转换生成。\n"
    )


def write_ipkg_tree(dest_root: Path, spec: IpkgSpec, rootfs: Path | None = None, icon_png: bytes | None = None) -> Path:
    app_dir = dest_root / spec.name
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "app").mkdir(exist_ok=True)
    (app_dir / "ui" / "ico").mkdir(parents=True, exist_ok=True)
    (app_dir / "app" / "data").mkdir(exist_ok=True)
    (app_dir / "app" / "rootfs").mkdir(exist_ok=True)

    (app_dir / "manifest.json").write_text(render_manifest(spec), encoding="utf-8")
    (app_dir / "changelog").write_text(spec.changelog or f"{spec.version} - converted from IPK\n", encoding="utf-8")
    (app_dir / "readme").write_text(spec.readme or default_readme(spec), encoding="utf-8")
    (app_dir / "app" / "docker-compose.yaml").write_text(render_compose(spec), encoding="utf-8")
    (app_dir / "app" / "option.json").write_text(render_option_json(spec), encoding="utf-8")

    env_lines = [f"APP_PORT_WEB={spec.host_port}"]
    for key, value in spec.extra_env.items():
        env_lines.append(f"{key}={value}")
    (app_dir / "app" / ".env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    (app_dir / "app" / "environment").write_text("TZ=Asia/Shanghai\n", encoding="utf-8")

    icon = icon_png or make_app_icon_png(spec.display_name or spec.name)
    (app_dir / "ui" / "ico" / "app.png").write_bytes(icon)

    if rootfs and rootfs.exists():
        _copy_tree(rootfs, app_dir / "app" / "rootfs")

    return app_dir


def pack_ipkg(app_dir: Path, output_file: Path) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()
    with tarfile.open(output_file, "w:gz") as tf:
        tf.add(app_dir, arcname=app_dir.name)
    return output_file


def _copy_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dest / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())
            try:
                target.chmod(item.stat().st_mode)
            except OSError:
                pass
