<#
.SYNOPSIS
    Deploy the working copy on P: to the ordinary installation on C:.

.DESCRIPTION
    P:\IA\Tools\C4D\rs-material-bridge is the editable source of truth.
    Cinema 4D and Houdini load the tool from C: instead, exactly as any
    user's machine would -- no dependency on pCloud being mounted, and the
    same setup the installer produces for a customer.

    This script refreshes that C: deployment from P: and re-runs the
    installer, which rewrites the Houdini package and the copies inside
    the Cinema 4D preference folders.

    Run it after changing the code on P:. Nothing edits the C: copy
    directly: it is a build output, not a second workshop.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File `
        "P:\IA\Tools\C4D\rs-material-bridge\tools\deploy_to_c.ps1"
#>
[CmdletBinding()]
param(
    [string]$Source = "P:\IA\Tools\C4D\rs-material-bridge",
    [string]$Target = "C:\IA\Tools\C4D\rs-material-bridge-deploy"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Source)) {
    throw "Source not found: $Source (is P: mounted?)"
}

Write-Host "Deploying $Source -> $Target"

# /XJ so junctions are never traversed; .git and generated textures are not
# part of what a user installs. No /MIR, /PURGE or /MOVE: this never
# deletes anything outside the files it writes.
robocopy $Source $Target /E /COPY:DAT /DCOPY:DAT /R:2 /W:2 /XJ `
    /XD "$Source\.git" "$Source\c4d\textures" "$Source\houdini\textures" `
    /XF ".gitignore" /NFL /NDL /NP | Out-Null
$code = $LASTEXITCODE
if ($code -ge 8) {
    throw "robocopy failed with exit code $code"
}
Write-Host "  copy ok (robocopy exit $code)"

# The installer points Houdini at the folder it is run from, and copies the
# Cinema 4D side into the preference folders -- so it has to run from the
# deployment, never from P:.
$python = $null
foreach ($candidate in @("py", "python")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
}
if (-not $python) {
    $hython = Get-ChildItem "$env:ProgramFiles\Side Effects Software\Houdini*\bin\hython.exe" `
        -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
    if ($hython) { $python = $hython.FullName }
}
if (-not $python) {
    Write-Warning "No Python found; run install.py inside $Target by hand."
    return
}

Push-Location $Target
try {
    & $python "$Target\install.py" --cli
} finally {
    Pop-Location
}
Write-Host "Deployed. Restart Cinema 4D / Houdini to load the new build."
