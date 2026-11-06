<#
Post-release step: bring the developer's editable checkout (the one `pip install -e .` points at, and so the one agent
clients' `ros mcp` runs) up to the release, so a release is also a release of the MCP server.

  powershell -File desktop/update-checkout.ps1 [-Checkout <folder>] [-Ref <tag-or-branch>] [-Python <python.exe>]

-Checkout  the checkout to update; default: $env:ROS_CHECKOUT. Nothing is assumed about where it is.
-Ref       what to fast-forward to; default: the newest tag reachable on the remote's main, else origin/main.
-Python    the interpreter that owns the editable install; default: python.

It only fast-forwards, and only when the checkout has no uncommitted changes to tracked files; otherwise it says what to
do and exits 1 without touching anything. Then it runs `pip install --user -e . --no-deps` there. Running `ros mcp`
servers need no restart: each notices the new VERSION within about 10 seconds and replaces its own worker.
#>
param([string]$Checkout = $env:ROS_CHECKOUT, [string]$Ref = '', [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
if (-not $Checkout) { Write-Host 'Give -Checkout <folder> or set ROS_CHECKOUT to the editable checkout.'; exit 1 }
if (-not (Test-Path (Join-Path $Checkout '.git'))) { Write-Host "$Checkout is not a git checkout."; exit 1 }
Push-Location $Checkout
try {
  git fetch --tags origin
  if ($LASTEXITCODE) { Write-Host 'git fetch failed; nothing changed.'; exit 1 }
  if (-not $Ref) {
    $Ref = (git describe --tags --abbrev=0 origin/main 2>$null)
    if (-not $Ref) { $Ref = 'origin/main' }
  }
  if (git status --porcelain --untracked-files=no) {
    Write-Host "$Checkout has uncommitted changes to tracked files. Commit or stash them, then run: git merge --ff-only $Ref ; $Python -m pip install --user -e . --no-deps"
    exit 1
  }
  git merge --ff-only $Ref
  if ($LASTEXITCODE) {
    Write-Host "$Checkout cannot fast-forward to $Ref (its branch has its own commits). Switch to main or rebase, then run: git merge --ff-only $Ref ; $Python -m pip install --user -e . --no-deps"
    exit 1
  }
  & $Python -m pip install --user -e . --no-deps
  if ($LASTEXITCODE) { Write-Host 'pip install failed; the checkout is updated but the install is not.'; exit 1 }
  Write-Host ("Checkout is at " + (Get-Content VERSION).Trim() + ". Running ros mcp servers pick it up on their own.")
} finally { Pop-Location }
