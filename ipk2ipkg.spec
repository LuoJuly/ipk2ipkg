"""
iKuai IPK → IPKG 转换工具
打包成 Windows 单文件 exe。
"""

from pathlib import Path

root = Path(SPECPATH)
entry = str(root / "run_app.py")
icon = root / "assets" / "app.ico"

a = Analysis(
    [entry],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "ipk2ipkg",
        "ipk2ipkg.gui",
        "ipk2ipkg.cli",
        "ipk2ipkg.parser",
        "ipk2ipkg.builder",
        "ipk2ipkg.convert",
        "ipk2ipkg.icon",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="IPK2IPKG",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon) if icon.exists() else None,
)
