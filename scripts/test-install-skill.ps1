[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase "dia-harness-skills-$([System.Guid]::NewGuid().ToString('N'))"
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
$safePrefix = $temporaryBase.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $resolvedTestRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Test root '$resolvedTestRoot' is outside '$temporaryBase'."
}

$installer = Join-Path $PSScriptRoot 'install-skill.ps1'
$destination = Join-Path $resolvedTestRoot 'installed-skills'
$whatIfDestination = Join-Path $resolvedTestRoot 'what-if-skills'

try {
    & $installer -Skill connect-clickup -Destination $destination -Force

    $installedSkill = Join-Path $destination 'connect-clickup'
    $installedEntry = Join-Path $installedSkill 'SKILL.md'
    Assert-True (Test-Path -LiteralPath $installedEntry -PathType Leaf) 'Fresh install did not copy SKILL.md.'

    $marker = 'installer-backup-test-marker'
    Set-Content -LiteralPath $installedEntry -Value $marker

    & $installer -Skill connect-clickup -Destination $destination -Force

    $currentText = Get-Content -Raw -LiteralPath $installedEntry
    Assert-True (-not $currentText.Contains($marker)) 'Replacement did not install the source copy.'

    $backups = @(Get-ChildItem -LiteralPath $destination -Directory -Filter 'connect-clickup.backup-*')
    Assert-True ($backups.Count -eq 1) 'Replacement did not create exactly one backup.'

    $backupText = Get-Content -Raw -LiteralPath (Join-Path $backups[0].FullName 'SKILL.md')
    Assert-True ($backupText.Contains($marker)) 'Backup does not contain the replaced copy.'

    & $installer -Skill connect-clickup -Destination $whatIfDestination -Force -WhatIf
    Assert-True (-not (Test-Path -LiteralPath $whatIfDestination)) 'WhatIf created a destination directory.'

    Write-Host 'Installer tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
