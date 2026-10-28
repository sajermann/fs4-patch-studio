# Builds the desktop app: interface (Vite) -> packaged backend (PyInstaller) -> Tauri installer (NSIS) -> portable zip.
# Needs Node, Rust (MSVC) and a Python with backend/requirements-build.txt installed (pass it with -Python).
# Output in desktop/release/: the installer (.exe) and the portable zip.
param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
if (Test-Path $Python) { $Python = (Resolve-Path $Python).Path }  # relative path: the script changes folders
# Rust installed after this terminal (or the app that opened it) started: PATH does not have cargo yet
if (-not (Get-Command cargo -ErrorAction SilentlyContinue) -and (Test-Path "$env:USERPROFILE\.cargo\bin\cargo.exe")) {
  $env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
}
$desktop = $PSScriptRoot
$root = Split-Path $desktop -Parent

function Run($exe, [string[]]$arguments) {
  # warnings on stderr are not failures (Windows PowerShell turns them into errors when output is redirected)
  $ErrorActionPreference = 'Continue'
  & $exe @arguments
  if ($LASTEXITCODE -ne 0) { throw "$exe $($arguments -join ' ') failed ($LASTEXITCODE)" }
}

Push-Location "$root\frontend"
if (-not (Test-Path node_modules)) { Run npm @('ci') }
Run npm @('run', 'build')
Pop-Location

Push-Location "$root\backend"
Run $Python @('-m', 'PyInstaller', '--noconfirm', 'fs4-backend.spec')
Pop-Location

Push-Location $desktop
if (-not (Test-Path node_modules)) { Run npm @('ci') }
Run npx @('tauri', 'build')
Pop-Location

$version = (Get-Content "$desktop\src-tauri\tauri.conf.json" -Raw | ConvertFrom-Json).version
$target = "$desktop\src-tauri\target\release"
$release = "$desktop\release"
New-Item -ItemType Directory -Force $release | Out-Null
Get-ChildItem $release | Remove-Item -Recurse -Force
Copy-Item "$target\bundle\nsis\*.exe" $release

# portable copy: same files the installer puts in place (data goes to data\ beside the executable)
$name = "FS4-Patch-Studio_${version}_portable"
$staging = "$release\$name"
New-Item -ItemType Directory -Force $staging | Out-Null
Copy-Item "$target\fs4-patch-studio.exe" $staging
Copy-Item "$target\backend" $staging -Recurse
Copy-Item "$root\LICENSE", "$root\NOTICE" $staging
Compress-Archive -Path "$staging\*" -DestinationPath "$release\$name.zip"
Remove-Item $staging -Recurse -Force
Get-ChildItem $release | Format-Table Name, Length
