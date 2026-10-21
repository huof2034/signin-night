$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$compiler = Join-Path $root '.desktop-tools\nsis-3.13\makensis.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $tools = Join-Path $root '.desktop-tools'
    New-Item -ItemType Directory -Path $tools -Force | Out-Null
    $archive = Join-Path $tools 'nsis-3.13.zip'
    try {
        Invoke-WebRequest 'https://downloads.sourceforge.net/project/nsis/NSIS%203/3.13/nsis-3.13.zip' -OutFile $archive
        $expected = 'ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8'
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'NSIS checksum mismatch.' }
        Expand-Archive -LiteralPath $archive -DestinationPath $tools -Force
    } finally {
        if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive }
    }
}
Push-Location $PSScriptRoot
try {
    & $compiler /V2 'installer.nsi'
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
    $installer = Join-Path $root 'dist\AHUTSignIn-Setup-1.5.0-x64.exe'
    $digest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText((Join-Path $root 'dist\SHA256SUMS.txt'), "$digest  AHUTSignIn-Setup-1.5.0-x64.exe`n", [Text.UTF8Encoding]::new($false))
    Write-Output "Installer built: $installer"
} finally { Pop-Location }
