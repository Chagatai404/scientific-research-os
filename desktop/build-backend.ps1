$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONPATH = (Join-Path (Get-Location) '.desktop-build/python-packages') + [IO.Path]::PathSeparator + (Get-Location).Path
python -m PyInstaller --noconfirm --distpath desktop/backend --workpath .desktop-build/frozen desktop/backend.spec
if ($LASTEXITCODE -ne 0) {throw 'Backend packaging failed'}
