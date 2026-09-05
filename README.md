# ipk2ipkg

Windows tool that converts **OpenWrt `.ipk`** packages into **iKuai 4.0 App Market `.ipkg`** files.

iKuai 4.0 local apps are not opkg archives. They are gzip tarballs that contain `manifest.json`, `docker-compose.yaml`, and UI metadata. This converter unpacks an IPK, reads its control data, and wraps the files as a Docker-based iKuai app.

[简体中文](README_ZH.md)

## Features

- Windows GUI (`IPK2IPKG.exe`) and a Python CLI
- Parses both Debian `ar` and `tar.gz` IPK layouts
- Reads package name, version, architecture, and executables
- Can merge several IPKs into one iKuai app
- Normalizes versions to `x.y.z` (required by iKuai)
- Warns on LuCI plugins and encrypted iKuai 3.x packages

## Install on iKuai

1. Build or download `IPK2IPKG.exe` and convert your `.ipk`
2. On the router: **Advanced Apps → App Market → Local Install**
3. Upload the generated `.ipkg`

The router must be **64-bit iKuai 4.0** with **Docker** enabled, and it must be able to pull `alpine:3.20` (or whatever image you set in the GUI).

## GUI

Run `dist\IPK2IPKG.exe` (or `python -m ipk2ipkg`):

1. Add one or more `.ipk` files
2. Check name, version, ports, and the start command
3. Click **Start conversion**
4. Install the `.ipkg` on iKuai as above

The convert bar stays at the bottom when the window is short. The right-hand form scrolls.

## CLI

```text
python -m ipk2ipkg --inspect app.ipk
python -m ipk2ipkg app.ipk -o D:\out
python -m ipk2ipkg app.ipk --port 16601 --command "/opt/pkg/usr/bin/lucky"
```

Flags such as `--inspect`, `--name`, `--version`, `--image`, `--command`, `--port`, and `--host-network` are also available. See `python -m ipk2ipkg --help`.

## What the `.ipkg` contains

```text
appname/
  manifest.json
  changelog
  readme
  app/
    docker-compose.yaml
    option.json
    environment
    .env
    rootfs/          # files extracted from the IPK
  ui/ico/app.png
```

By default the container is `alpine:3.20`, the payload is mounted at `/opt/pkg`, and iKuai injects `HOST_IP`, `NAME_NONCE`, `CPUS_LIMIT`, `MEMORY_LIMIT`, and `RESTART`.

## Limitations

- **LuCI** plugins need the OpenWrt LuCI UI. They will not run as iKuai Docker apps.
- **iKuai 3.x encrypted `.ipk`** files cannot be converted without the plugin key.
- OpenWrt init scripts, `uci`, firewall, and dnsmasq hooks are not replayed on iKuai. Use the app’s own web UI / proxy ports.
- Binaries that hard-code `/usr/bin` or `/etc/...` may need a custom start command or image.
- Architecture should be `x86_64` or `aarch64` for typical iKuai hardware.

## Build the Windows exe

```powershell
python -m pip install -r requirements-build.txt
powershell -File .\build.ps1
```

Output: `dist\IPK2IPKG.exe`

Python 3.12+ is enough to run from source:

```powershell
python -m ipk2ipkg
```

## Tests

```powershell
$env:PYTHONPATH = (Get-Location)
python tests\selftest.py
```

## License

Use and modify freely for personal or local packaging. You are responsible for the packages you convert and install on your own router.
