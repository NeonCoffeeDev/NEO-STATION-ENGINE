# Activate the Neon Coffee PS1 toolchain for this shell only.
#   . .\env.ps1
# Nothing is written to your global PATH or user environment.

$NC_ROOT = $PSScriptRoot
$SDK = Join-Path $NC_ROOT "toolchain\psn00bsdk"

if (-not (Test-Path $SDK)) {
    Write-Error "PSn00bSDK not found at $SDK. See docs/ROADMAP.md M0."
    return
}

$env:PSN00BSDK_LIBS = Join-Path $SDK "lib\libpsn00b"
$env:NC_ROOT = $NC_ROOT

$bin = Join-Path $SDK "bin"
if ($env:PATH -notlike "*$bin*") { $env:PATH = "$bin;$env:PATH" }

Write-Host "Neon Coffee PS1 toolchain active." -ForegroundColor Green
Write-Host "  PSN00BSDK_LIBS = $env:PSN00BSDK_LIBS"
