$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python desktop/verify.py @args
exit $LASTEXITCODE
