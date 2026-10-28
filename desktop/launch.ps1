$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$exe = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'dist/win-unpacked/Research OS.exe')).Path
# This is an explicit interactive launch, separate from every isolated smoke test.
$process = Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe -Parent) -PassThru -WindowStyle Normal
$deadline = [DateTime]::UtcNow.AddSeconds(60)
do {
    Start-Sleep -Milliseconds 250
    $process.Refresh()
    if ($process.HasExited) { throw "Application exited before showing its window (code $($process.ExitCode))." }
} while (($process.MainWindowHandle -eq 0 -or $process.MainWindowTitle -notmatch 'Research OS') -and [DateTime]::UtcNow -lt $deadline)
if ($process.MainWindowHandle -eq 0) { throw 'Application did not show a window within 60 seconds.' }
Start-Sleep -Seconds 2
$process.Refresh()
if ($process.HasExited) { throw 'Application stopped after opening its window.' }
$state = @{running=$true;pid=$process.Id;executable=$exe;title=$process.MainWindowTitle}
$state | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $repo '.desktop-build/launched-app.json') -Encoding utf8
$state | ConvertTo-Json
