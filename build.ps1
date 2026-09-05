# 生成图标并打包单文件 exe
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$py = "C:\Users\luojuly\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}

& $py -m pip install -r requirements-build.txt
New-Item -ItemType Directory -Force -Path assets | Out-Null
& $py -c "from pathlib import Path; from ipk2ipkg.icon import make_exe_icon_ico; Path('assets').mkdir(exist_ok=True); Path('assets/app.ico').write_bytes(make_exe_icon_ico())"
& $py tests\selftest.py
& $py -m PyInstaller --noconfirm ipk2ipkg.spec
Write-Host "输出: $root\dist\IPK2IPKG.exe"
