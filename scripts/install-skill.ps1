[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]+(?:-[a-z0-9]+)*$')]
    [string]$Skill,

    [string]$Destination = (Join-Path $env:USERPROFILE '.tritonai-harness\codex\skills'),

    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $repositoryRoot 'skills'
$sourceSkill = Join-Path $sourceRoot $Skill

if (-not (Test-Path -LiteralPath (Join-Path $sourceSkill 'SKILL.md') -PathType Leaf)) {
    throw "Source skill '$Skill' does not exist at '$sourceSkill'."
}

$destinationRoot = [System.IO.Path]::GetFullPath($Destination)
$targetSkill = [System.IO.Path]::GetFullPath((Join-Path $destinationRoot $Skill))
$expectedPrefix = $destinationRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $targetSkill.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Resolved target '$targetSkill' is outside destination '$destinationRoot'."
}

Write-Host "Source:      $sourceSkill"
Write-Host "Destination: $targetSkill"

$targetExists = Test-Path -LiteralPath $targetSkill
if ($targetExists -and -not $Force) {
    $replace = $PSCmdlet.ShouldContinue(
        "Replace '$targetSkill' and keep the current copy as a timestamped backup?",
        "Replace installed skill '$Skill'"
    )
    if (-not $replace) {
        Write-Host 'Installation cancelled. No files changed.'
        return
    }
}

if (-not $PSCmdlet.ShouldProcess($targetSkill, "Install source skill '$Skill'")) {
    return
}

New-Item -ItemType Directory -Path $destinationRoot -Force | Out-Null

$stagingSkill = Join-Path $destinationRoot ".$Skill.install-$([System.Guid]::NewGuid().ToString('N'))"
$backupSkill = $null

try {
    Copy-Item -LiteralPath $sourceSkill -Destination $stagingSkill -Recurse

    if (-not (Test-Path -LiteralPath (Join-Path $stagingSkill 'SKILL.md') -PathType Leaf)) {
        throw "Staged skill is missing SKILL.md at '$stagingSkill'."
    }

    if ($targetExists) {
        $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
        $backupSkill = Join-Path $destinationRoot "$Skill.backup-$timestamp"
        Move-Item -LiteralPath $targetSkill -Destination $backupSkill
    }

    Move-Item -LiteralPath $stagingSkill -Destination $targetSkill
}
catch {
    if ($backupSkill -and (Test-Path -LiteralPath $backupSkill) -and -not (Test-Path -LiteralPath $targetSkill)) {
        Move-Item -LiteralPath $backupSkill -Destination $targetSkill
    }
    throw
}

Write-Host "Installed '$Skill' at '$targetSkill'."
if ($backupSkill) {
    Write-Host "Previous copy: $backupSkill"
}
Write-Host 'Restart TritonAI Harness to reload the skill catalog.'
