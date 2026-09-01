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

function Invoke-ProjectFolderHelper {
    param(
        [string[]]$Arguments,
        [int]$ExpectedExitCode = 0
    )

    $output = & $pwsh -NoProfile -File $helper @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $outputText = $output -join [Environment]::NewLine
    if ($exitCode -ne $ExpectedExitCode) {
        throw "Project-folder helper exited $exitCode instead of $ExpectedExitCode. Output: $outputText"
    }

    return $outputText | ConvertFrom-Json
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$helper = Join-Path $repositoryRoot 'skills\setup-project-folder\scripts\setup_project_folder.ps1'
$pwsh = Join-Path $PSHOME 'pwsh.exe'
$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase "dia-project-folder-$([System.Guid]::NewGuid().ToString('N'))"
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
$safePrefix = $temporaryBase.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $resolvedTestRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Test root '$resolvedTestRoot' is outside '$temporaryBase'."
}

try {
    New-Item -ItemType Directory -Path $resolvedTestRoot | Out-Null

    $projectRoot = Join-Path $resolvedTestRoot 'Example Business Insights'
    $commonArguments = @(
        '-Root', $projectRoot,
        '-ProjectName', 'Example Business Insights',
        '-Description', 'A temporary project used to test the DIA folder standard.',
        '-WorkspaceId', '100001',
        '-SpaceId', '200002',
        '-FolderId', '300003',
        '-TaskListId', '400004',
        '-DocId', 'abcde-12345',
        '-PageId', 'abcde-67890'
    )

    $plan = Invoke-ProjectFolderHelper -Arguments $commonArguments
    Assert-True ($plan.action -eq 'planned') 'A new project did not produce a plan.'
    Assert-True ($plan.valid -eq $false) 'A plan with missing paths was reported as valid.'
    Assert-True (-not (Test-Path -LiteralPath $projectRoot)) 'Planning created the project folder.'

    $created = Invoke-ProjectFolderHelper -Arguments ($commonArguments + '-Apply')
    Assert-True ($created.action -eq 'created') 'Apply did not report a created project folder.'
    Assert-True ($created.valid -eq $true) 'Apply did not report a valid project folder.'

    $requiredDirectories = @(
        'transcripts\inbox',
        'transcripts\processed',
        'source-data',
        'analysis',
        'deliverables\data-products',
        'deliverables\presentations',
        'working'
    )
    foreach ($relativeDirectory in $requiredDirectories) {
        Assert-True (Test-Path -LiteralPath (Join-Path $projectRoot $relativeDirectory) -PathType Container) "Missing directory: $relativeDirectory"
    }
    foreach ($relativeFile in @('project.yaml', 'README.md', 'AGENTS.md')) {
        Assert-True (Test-Path -LiteralPath (Join-Path $projectRoot $relativeFile) -PathType Leaf) "Missing file: $relativeFile"
    }

    $readme = Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'README.md')
    Assert-True (-not $readme.Contains('{{')) 'README contains an unreplaced template token.'
    Assert-True ($readme.Contains('Example Business Insights')) 'README project name is missing.'

    $manifest = Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'project.yaml')
    Assert-True ($manifest.Contains('schema_version: 1')) 'Manifest schema version is missing.'
    Assert-True ($manifest.Contains('folder_id: "300003"')) 'Folder ID was not written as a quoted identifier.'
    Assert-True ($manifest.Contains('type: "business-insights"')) 'Project type is missing.'

    $valid = Invoke-ProjectFolderHelper -Arguments $commonArguments
    Assert-True ($valid.action -eq 'valid') 'A second run did not report a valid project folder.'
    Assert-True ($valid.changes.Count -eq 0) 'A second run proposed unexpected changes.'

    $customReadme = "# Team-owned project description`r`n"
    Set-Content -LiteralPath (Join-Path $projectRoot 'README.md') -Value $customReadme -NoNewline
    $preserved = Invoke-ProjectFolderHelper -Arguments ($commonArguments + '-Apply')
    Assert-True ($preserved.valid -eq $true) 'A project with an edited README did not remain valid.'
    Assert-True ((Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'README.md')) -eq $customReadme) 'Apply overwrote the existing README.'

    $partialRoot = Join-Path $resolvedTestRoot 'Partial Project'
    New-Item -ItemType Directory -Path $partialRoot | Out-Null
    $partialReadme = '# Existing project notes'
    Set-Content -LiteralPath (Join-Path $partialRoot 'README.md') -Value $partialReadme -NoNewline
    $partialArguments = @(
        '-Root', $partialRoot,
        '-ProjectName', 'Partial Project',
        '-Description', 'A partially initialized project.',
        '-WorkspaceId', '100001',
        '-SpaceId', '200002',
        '-FolderId', '300005',
        '-TaskListId', '400006',
        '-DocId', 'abcde-22222',
        '-PageId', 'abcde-33333',
        '-Apply'
    )
    $partial = Invoke-ProjectFolderHelper -Arguments $partialArguments
    Assert-True ($partial.valid -eq $true) 'A partial project could not be completed safely.'
    Assert-True ((Get-Content -Raw -LiteralPath (Join-Path $partialRoot 'README.md')) -eq $partialReadme) 'Partial setup overwrote an existing README.'

    $conflictRoot = Join-Path $resolvedTestRoot 'Conflicting Project'
    New-Item -ItemType Directory -Path $conflictRoot | Out-Null
    Set-Content -LiteralPath (Join-Path $conflictRoot 'project.yaml') -Value "schema_version: 99`n" -NoNewline
    $conflictArguments = @(
        '-Root', $conflictRoot,
        '-ProjectName', 'Conflicting Project',
        '-Description', 'A project with a conflicting manifest.',
        '-WorkspaceId', '100001',
        '-SpaceId', '200002',
        '-FolderId', '300007',
        '-TaskListId', '400008',
        '-DocId', 'abcde-44444',
        '-PageId', 'abcde-55555',
        '-Apply'
    )
    $conflict = Invoke-ProjectFolderHelper -Arguments $conflictArguments -ExpectedExitCode 2
    Assert-True ($conflict.action -eq 'conflict') 'A conflicting manifest was not rejected.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $conflictRoot 'analysis'))) 'Conflict handling changed the folder before stopping.'

    $collisionRoot = Join-Path $resolvedTestRoot 'Directory Collision'
    New-Item -ItemType Directory -Path $collisionRoot | Out-Null
    Set-Content -LiteralPath (Join-Path $collisionRoot 'analysis') -Value 'not a directory'
    $collisionArguments = @(
        '-Root', $collisionRoot,
        '-ProjectName', 'Directory Collision',
        '-Description', 'A project with a file collision.',
        '-WorkspaceId', '100001',
        '-SpaceId', '200002',
        '-FolderId', '300009',
        '-TaskListId', '400010',
        '-DocId', 'abcde-66666',
        '-PageId', 'abcde-77777',
        '-Apply'
    )
    $collision = Invoke-ProjectFolderHelper -Arguments $collisionArguments -ExpectedExitCode 2
    Assert-True ($collision.action -eq 'conflict') 'A directory collision was not rejected.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $collisionRoot 'transcripts'))) 'Directory collision handling changed the folder before stopping.'

    $mismatchRoot = Join-Path $resolvedTestRoot 'Local Name'
    $mismatchArguments = @(
        '-Root', $mismatchRoot,
        '-ProjectName', 'ClickUp Name',
        '-Description', 'A project whose local and ClickUp names differ.',
        '-WorkspaceId', '100001',
        '-SpaceId', '200002',
        '-FolderId', '300011',
        '-TaskListId', '400012',
        '-DocId', 'abcde-88888',
        '-PageId', 'abcde-99999',
        '-Apply'
    )
    $mismatch = Invoke-ProjectFolderHelper -Arguments $mismatchArguments -ExpectedExitCode 2
    Assert-True ($mismatch.action -eq 'conflict') 'A local and ClickUp folder-name mismatch was not rejected.'
    Assert-True (-not (Test-Path -LiteralPath $mismatchRoot)) 'Name-mismatch handling created a project folder.'

    Write-Host 'Project-folder helper tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
