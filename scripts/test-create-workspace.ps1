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
$helper = Join-Path $repositoryRoot 'skills\dia-new-data-analysis-workspace\scripts\create_workspace.ps1'
$pwsh = Join-Path $PSHOME 'pwsh.exe'
$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase "dia-new-workspace-$([System.Guid]::NewGuid().ToString('N'))"
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
$safePrefix = $temporaryBase.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $resolvedTestRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Test root '$resolvedTestRoot' is outside '$temporaryBase'."
}

try {
    New-Item -ItemType Directory -Path $resolvedTestRoot | Out-Null
    $parent = Join-Path $resolvedTestRoot 'Projects'
    New-Item -ItemType Directory -Path $parent | Out-Null

    $workspaceRoot = Join-Path $parent 'Example Analysis'
    $commonArguments = @(
        '-Root', $parent,
        '-WorkspaceName', 'Example Analysis',
        '-Description', 'A temporary workspace used to test the DIA data-analysis standard.',
        '-DataSources', 'Excel exports from the example system.'
    )

    $plan = Invoke-WorkspaceHelper -Arguments $commonArguments
    Assert-True ($plan.action -eq 'planned') 'A new workspace did not produce a plan.'
    Assert-True ($plan.valid -eq $false) 'A plan with missing paths was reported as valid.'
    Assert-True (-not (Test-Path -LiteralPath $workspaceRoot)) 'Planning created the workspace folder.'

    $created = Invoke-WorkspaceHelper -Arguments ($commonArguments + '-Apply')
    Assert-True ($created.action -eq 'created') 'Apply did not report a created workspace.'
    Assert-True ($created.valid -eq $true) 'Apply did not report a valid workspace.'

    $requiredDirectories = @(
        'data\raw',
        'data\output',
        'scripts',
        'reports',
        'docs\presentations',
        'docs\transcripts',
        'scratch'
    )
    foreach ($relativeDirectory in $requiredDirectories) {
        Assert-True (Test-Path -LiteralPath (Join-Path $workspaceRoot $relativeDirectory) -PathType Container) "Missing directory: $relativeDirectory"
    }
    foreach ($relativeFile in @('README.md', 'AGENTS.md', 'scripts\README.md', 'docs\data-dictionary.md')) {
        Assert-True (Test-Path -LiteralPath (Join-Path $workspaceRoot $relativeFile) -PathType Leaf) "Missing file: $relativeFile"
    }

    $readme = Get-Content -Raw -LiteralPath (Join-Path $workspaceRoot 'README.md')
    Assert-True (-not $readme.Contains('{{')) 'README contains an unreplaced template token.'
    Assert-True ($readme.Contains('Example Analysis')) 'README workspace name is missing.'
    Assert-True ($readme.Contains('Excel exports from the example system.')) 'README data sources are missing.'

    $valid = Invoke-WorkspaceHelper -Arguments $commonArguments
    Assert-True ($valid.action -eq 'valid') 'A second run did not report a valid workspace.'
    Assert-True ($valid.changes.Count -eq 0) 'A second run proposed unexpected changes.'

    $customReadme = "# Team-owned workspace description`r`n"
    Set-Content -LiteralPath (Join-Path $workspaceRoot 'README.md') -Value $customReadme -NoNewline
    $preserved = Invoke-WorkspaceHelper -Arguments ($commonArguments + '-Apply')
    Assert-True ($preserved.valid -eq $true) 'A workspace with an edited README did not remain valid.'
    Assert-True ((Get-Content -Raw -LiteralPath (Join-Path $workspaceRoot 'README.md')) -eq $customReadme) 'Apply overwrote the existing README.'

    $partialRoot = Join-Path $parent 'Partial Workspace'
    New-Item -ItemType Directory -Path $partialRoot | Out-Null
    $partialReadme = '# Existing workspace notes'
    Set-Content -LiteralPath (Join-Path $partialRoot 'README.md') -Value $partialReadme -NoNewline
    $partialArguments = @(
        '-Root', $parent,
        '-WorkspaceName', 'Partial Workspace',
        '-Description', 'A partially initialized workspace.',
        '-DataSources', 'Excel exports.',
        '-Apply'
    )
    $partial = Invoke-WorkspaceHelper -Arguments $partialArguments
    Assert-True ($partial.valid -eq $true) 'A partial workspace could not be completed safely.'
    Assert-True ((Get-Content -Raw -LiteralPath (Join-Path $partialRoot 'README.md')) -eq $partialReadme) 'Partial setup overwrote an existing README.'

    $collisionRoot = Join-Path $parent 'Directory Collision'
    New-Item -ItemType Directory -Path $collisionRoot | Out-Null
    Set-Content -LiteralPath (Join-Path $collisionRoot 'data') -Value 'not a directory'
    $collisionArguments = @(
        '-Root', $parent,
        '-WorkspaceName', 'Directory Collision',
        '-Description', 'A workspace with a file collision.',
        '-DataSources', 'Excel exports.',
        '-Apply'
    )
    $collision = Invoke-WorkspaceHelper -Arguments $collisionArguments -ExpectedExitCode 2
    Assert-True ($collision.action -eq 'conflict') 'A directory collision was not rejected.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $collisionRoot 'reports'))) 'Collision handling changed the folder before stopping.'

    $missingParentArguments = @(
        '-Root', (Join-Path $resolvedTestRoot 'Does Not Exist'),
        '-WorkspaceName', 'Orphan Workspace',
        '-Description', 'A workspace without a parent.',
        '-DataSources', 'Excel exports.',
        '-Apply'
    )
    $missingParent = Invoke-WorkspaceHelper -Arguments $missingParentArguments -ExpectedExitCode 2
    Assert-True ($missingParent.action -eq 'conflict') 'A missing parent directory was not rejected.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $resolvedTestRoot 'Does Not Exist'))) 'Missing-parent handling created a parent directory.'

    $invalidNameArguments = @(
        '-Root', $parent,
        '-WorkspaceName', 'Invalid<Name>',
        '-Description', 'A workspace with an invalid name.',
        '-DataSources', 'Excel exports.',
        '-Apply'
    )
    $invalidName = Invoke-WorkspaceHelper -Arguments $invalidNameArguments -ExpectedExitCode 2
    Assert-True ($invalidName.action -eq 'conflict') 'An invalid workspace name was not rejected.'

    Write-Host 'Workspace helper tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

exit 0
