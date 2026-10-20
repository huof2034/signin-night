$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root '.desktop-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .desktop-venv and install requirements-desktop.txt first.' }
foreach ($wallpaperDependency in @('wallpaper-api\node.exe','repkg\RePKG.exe','capture\windows_capture.pyd')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot ('vendor\' + $wallpaperDependency)))) {
        throw 'Run desktop\setup_wallpaper_deps.py --node <node.exe> before building.'
    }
}
Push-Location $root
try {
    & $python -B -m PyInstaller --noconfirm --workpath (Join-Path $root '.desktop-build') --distpath (Join-Path $root 'dist') (Join-Path $PSScriptRoot 'app.spec')
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
    & $python -B (Join-Path $PSScriptRoot 'package.py')
    if ($LASTEXITCODE -ne 0) { throw 'Desktop packaging failed.' }
} finally { Pop-Location }
