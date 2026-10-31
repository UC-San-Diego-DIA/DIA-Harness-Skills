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

function Invoke-WorkspaceHelper {
    param(
        [string[]]$Arguments,
        [int]$ExpectedExitCode = 0
    )

    $output = & $pwsh -NoProfile -File $helper @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $outputText = $output -join [Environment]::NewLine
    if ($exitCode -ne $ExpectedExitCode) {
        throw "Workspace helper exited $exitCode instead of $ExpectedExitCode. Output: $outputText"
    }

    return $outputText | ConvertFrom-Json
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$helper = Join-Path $repositoryRoot 'skills\dia-new-simple-workspace\scripts\create_simple_workspace.ps1'
$pwsh = Join-Path $PSHOME 'pwsh.exe'
$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase "dia-new-simple-workspace-$([System.Guid]::NewGuid().ToString('N'))"
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
$safePrefix = $temporaryBase.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $resolvedTestRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Test root '$resolvedTestRoot' is outside '$temporaryBase'."
}

try {
    New-Item -ItemType Directory -Path $resolvedTestRoot | Out-Null

    $folderRoot = Join-Path $resolvedTestRoot 'Example Work'
    $commonArguments = @('-Root', $folderRoot)

    $plan = Invoke-WorkspaceHelper -Arguments $commonArguments
    Assert-True ($plan.action -eq 'planned') 'A new folder did not produce a plan.'
    Assert-True ($plan.valid -eq $false) 'A plan with missing paths was reported as valid.'
    Assert-True (-not (Test-Path -LiteralPath $folderRoot)) 'Planning created the working folder.'

    $created = Invoke-WorkspaceHelper -Arguments ($commonArguments + '-Apply')
    Assert-True ($created.action -eq 'created') 'Apply did not report a created working folder.'
    Assert-True ($created.valid -eq $true) 'Apply did not report a valid working folder.'

    foreach ($relativeDirectory in @('Scripts', 'Inputs', 'Outputs')) {
        Assert-True (Test-Path -LiteralPath (Join-Path $folderRoot $relativeDirectory) -PathType Container) "Missing directory: $relativeDirectory"
    }
    foreach ($relativeFile in @('README.md', 'AGENTS.md')) {
        Assert-True (Test-Path -LiteralPath (Join-Path $folderRoot $relativeFile) -PathType Leaf) "Missing file: $relativeFile"
    }

    $readme = Get-Content -Raw -LiteralPath (Join-Path $folderRoot 'README.md')
    Assert-True (-not $readme.Contains('{{')) 'README contains an unreplaced template token.'
    Assert-True ($readme.Contains('Example Work')) 'README folder name is missing.'

    $agents = Get-Content -Raw -LiteralPath (Join-Path $folderRoot 'AGENTS.md')
    Assert-True ($agents.Contains('Inputs')) 'AGENTS file does not describe the folder responsibilities.'

    $valid = Invoke-WorkspaceHelper -Arguments $commonArguments
    Assert-True ($valid.action -eq 'valid') 'A second run did not report a valid working folder.'
    Assert-True ($valid.changes.Count -eq 0) 'A second run proposed unexpected changes.'

    $customReadme = "# Team-owned working notes`r`n"
    Set-Content -LiteralPath (Join-Path $folderRoot 'README.md') -Value $customReadme -NoNewline
    $preserved = Invoke-WorkspaceHelper -Arguments ($commonArguments + '-Apply')
    Assert-True ($preserved.valid -eq $true) 'A folder with an edited README did not remain valid.'
    Assert-True ((Get-Content -Raw -LiteralPath (Join-Path $folderRoot 'README.md')) -eq $customReadme) 'Apply overwrote the existing README.'

    $partialRoot = Join-Path $resolvedTestRoot 'Partial Work'
    New-Item -ItemType Directory -Path $partialRoot | Out-Null
    $partialReadme = '# Existing working notes'
    Set-Content -LiteralPath (Join-Path $partialRoot 'README.md') -Value $partialReadme -NoNewline
    $partial = Invoke-WorkspaceHelper -Arguments (@('-Root', $partialRoot) + '-Apply')
    Assert-True ($partial.valid -eq $true) 'A partially initialized folder could not be completed safely.'
    Assert-True (Test-Path -LiteralPath (Join-Path $partialRoot 'Outputs') -PathType Container) 'Partial setup did not create the missing directories.'
    Assert-True ((Get-Content -Raw -LiteralPath (Join-Path $partialRoot 'README.md')) -eq $partialReadme) 'Partial setup overwrote an existing README.'

    $collisionRoot = Join-Path $resolvedTestRoot 'Collision Work'
    New-Item -ItemType Directory -Path $collisionRoot | Out-Null
    Set-Content -LiteralPath (Join-Path $collisionRoot 'Inputs') -Value 'not a directory'
    $collision = Invoke-WorkspaceHelper -Arguments (@('-Root', $collisionRoot) + '-Apply') -ExpectedExitCode 2
    Assert-True ($collision.action -eq 'conflict') 'A directory collision was not rejected.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $collisionRoot 'Outputs'))) 'Collision handling changed the folder before stopping.'

    $relative = Invoke-WorkspaceHelper -Arguments @('-Root', 'relative-folder') -ExpectedExitCode 2
    Assert-True ($relative.action -eq 'conflict') 'A relative path was not rejected.'

    Write-Host 'Workspace helper tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

exit 0
