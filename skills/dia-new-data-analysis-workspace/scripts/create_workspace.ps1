[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [Parameter(Mandatory = $true)]
    [string]$WorkspaceName,

    [Parameter(Mandatory = $true)]
    [string]$Description,

    [string]$DataSources = 'To be described.',

    [switch]$Apply
)

$ErrorActionPreference = 'Stop'

function ConvertTo-NormalizedText {
    param([string]$Text)

    return ($Text -replace "`r`n", "`n").TrimEnd()
}

function New-Result {
    param(
        [string]$Action,
        [bool]$Valid,
        [string]$ResolvedRoot,
        [System.Collections.Generic.List[string]]$Changes,
        [System.Collections.Generic.List[string]]$Preserved,
        [System.Collections.Generic.List[string]]$Conflicts
    )

    return [ordered]@{
        action = $Action
        valid = $Valid
        root = $ResolvedRoot
        changes = @($Changes)
        preserved = @($Preserved)
        conflicts = @($Conflicts)
    }
}

function Write-Result {
    param(
        [System.Collections.IDictionary]$Result,
        [int]$ExitCode
    )

    $Result | ConvertTo-Json -Depth 5
    exit $ExitCode
}

$changes = [System.Collections.Generic.List[string]]::new()
$preserved = [System.Collections.Generic.List[string]]::new()
$conflicts = [System.Collections.Generic.List[string]]::new()

if (-not [System.IO.Path]::IsPathFullyQualified($Root)) {
    $conflicts.Add("Root must be an absolute path: $Root")
    Write-Result (New-Result 'conflict' $false $Root $changes $preserved $conflicts) 2
}

$resolvedParent = [System.IO.Path]::GetFullPath($Root).TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)

if ([string]::IsNullOrWhiteSpace($WorkspaceName)) {
    $conflicts.Add('WorkspaceName cannot be blank.')
}
else {
    $invalidNameCharacters = [System.IO.Path]::GetInvalidFileNameChars()
    if ($WorkspaceName.IndexOfAny($invalidNameCharacters) -ge 0 -or $WorkspaceName -match '[\x00-\x1F]') {
        $conflicts.Add("WorkspaceName is not a valid Windows directory name: $WorkspaceName")
    }
    if ($WorkspaceName.EndsWith(' ') -or $WorkspaceName.EndsWith('.')) {
        $conflicts.Add('WorkspaceName cannot end with a space or period.')
    }
    $reservedNames = @('CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9')
    $baseName = $WorkspaceName.Split('.')[0].ToUpperInvariant()
    if ($reservedNames -contains $baseName) {
        $conflicts.Add("WorkspaceName is reserved by Windows: $WorkspaceName")
    }
}

if ([string]::IsNullOrWhiteSpace($Description) -or $Description -match '[\r\n]') {
    $conflicts.Add('Description must be one non-empty line.')
}

if ([string]::IsNullOrWhiteSpace($DataSources) -or $DataSources -match '[\r\n]') {
    $conflicts.Add('DataSources must be one non-empty line.')
}

$resolvedRoot = Join-Path $resolvedParent $WorkspaceName
if ($conflicts.Count -eq 0 -and -not (Test-Path -LiteralPath $resolvedParent -PathType Container)) {
    $conflicts.Add("Parent directory does not exist: $resolvedParent")
}

if (Test-Path -LiteralPath $resolvedRoot -PathType Leaf) {
    $conflicts.Add("Workspace root is an existing file: $resolvedRoot")
}

$skillRoot = Split-Path -Parent $PSScriptRoot
$templateFiles = [ordered]@{
    'README.md'            = 'assets\workspace-README.md'
    'AGENTS.md'            = 'assets\workspace-AGENTS.md'
    'scripts\README.md'    = 'assets\scripts-README.md'
    'docs\data-dictionary.md' = 'assets\data-dictionary.md'
}
foreach ($entry in $templateFiles.GetEnumerator()) {
    $templatePath = Join-Path $skillRoot $entry.Value
    if (-not (Test-Path -LiteralPath $templatePath -PathType Leaf)) {
        $conflicts.Add("Installed skill is missing required asset: $templatePath")
    }
}

$requiredDirectories = @(
    'data',
    'data\raw',
    'data\output',
    'scripts',
    'reports',
    'docs',
    'docs\presentations',
    'docs\transcripts',
    'scratch'
)

foreach ($relativeDirectory in $requiredDirectories) {
    $directoryPath = Join-Path $resolvedRoot $relativeDirectory
    if (Test-Path -LiteralPath $directoryPath -PathType Leaf) {
        $conflicts.Add("Expected directory is an existing file: $directoryPath")
    }
    elseif (-not (Test-Path -LiteralPath $directoryPath -PathType Container)) {
        $changes.Add("Create directory: $directoryPath")
    }
    else {
        $preserved.Add("Existing directory: $directoryPath")
    }
}

foreach ($entry in $templateFiles.GetEnumerator()) {
    $targetPath = Join-Path $resolvedRoot $entry.Key
    if (Test-Path -LiteralPath $targetPath -PathType Container) {
        $conflicts.Add("Expected file is an existing directory: $targetPath")
    }
    elseif (Test-Path -LiteralPath $targetPath -PathType Leaf) {
        $preserved.Add("Existing file: $targetPath")
    }
    else {
        $changes.Add("Create file: $targetPath")
    }
}

if ($conflicts.Count -gt 0) {
    Write-Result (New-Result 'conflict' $false $resolvedRoot $changes $preserved $conflicts) 2
}

if (-not $Apply) {
    $action = if ($changes.Count -eq 0) { 'valid' } else { 'planned' }
    Write-Result (New-Result $action ($changes.Count -eq 0) $resolvedRoot $changes $preserved $conflicts) 0
}

$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path -LiteralPath $resolvedRoot -PathType Container)) {
    [System.IO.Directory]::CreateDirectory($resolvedRoot) | Out-Null
}
foreach ($relativeDirectory in $requiredDirectories) {
    $directoryPath = Join-Path $resolvedRoot $relativeDirectory
    if (-not (Test-Path -LiteralPath $directoryPath -PathType Container)) {
        [System.IO.Directory]::CreateDirectory($directoryPath) | Out-Null
    }
}

$plainTemplateEntries = @('AGENTS.md', 'scripts\README.md', 'docs\data-dictionary.md')
foreach ($relativeFile in $plainTemplateEntries) {
    $targetPath = Join-Path $resolvedRoot $relativeFile
    if (-not (Test-Path -LiteralPath $targetPath)) {
        $templateText = Get-Content -Raw -LiteralPath (Join-Path $skillRoot $templateFiles[$relativeFile])
        [System.IO.File]::WriteAllText($targetPath, (ConvertTo-NormalizedText $templateText) + [Environment]::NewLine, $utf8WithoutBom)
    }
}

$readmePath = Join-Path $resolvedRoot 'README.md'
if (-not (Test-Path -LiteralPath $readmePath)) {
    $readmeText = Get-Content -Raw -LiteralPath (Join-Path $skillRoot $templateFiles['README.md'])
    $readmeText = $readmeText.Replace('{{PROJECT_NAME}}', $WorkspaceName).Replace('{{PROJECT_DESCRIPTION}}', $Description).Replace('{{DATA_SOURCES}}', $DataSources)
    [System.IO.File]::WriteAllText($readmePath, (ConvertTo-NormalizedText $readmeText) + [Environment]::NewLine, $utf8WithoutBom)
}

$postApplyConflicts = [System.Collections.Generic.List[string]]::new()
foreach ($relativeDirectory in $requiredDirectories) {
    $directoryPath = Join-Path $resolvedRoot $relativeDirectory
    if (-not (Test-Path -LiteralPath $directoryPath -PathType Container)) {
        $postApplyConflicts.Add("Required directory is missing after apply: $directoryPath")
    }
}
foreach ($relativeFile in $templateFiles.Keys) {
    $filePath = Join-Path $resolvedRoot $relativeFile
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
        $postApplyConflicts.Add("Required file is missing after apply: $filePath")
    }
}

if ($postApplyConflicts.Count -gt 0) {
    Write-Result (New-Result 'conflict' $false $resolvedRoot $changes $preserved $postApplyConflicts) 2
}

$finalAction = if ($changes.Count -eq 0) { 'valid' } else { 'created' }
Write-Result (New-Result $finalAction $true $resolvedRoot $changes $preserved $postApplyConflicts) 0
