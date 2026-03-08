$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m pip install -r requirements.txt
python -m pip install PyInstaller
python -m playwright install chromium
pyinstaller --noconfirm --clean packaging/aiautomouse.spec
