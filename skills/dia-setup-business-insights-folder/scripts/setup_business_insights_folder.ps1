[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [Parameter(Mandatory = $true)]
    [string]$ProjectName,

    [Parameter(Mandatory = $true)]
    [string]$Description,

    [Parameter(Mandatory = $true)]
    [string]$WorkspaceId,

    [Parameter(Mandatory = $true)]
    [string]$SpaceId,

    [Parameter(Mandatory = $true)]
    [string]$FolderId,

    [Parameter(Mandatory = $true)]
    [string]$TaskListId,

    [Parameter(Mandatory = $true)]
    [string]$DocId,

    [Parameter(Mandatory = $true)]
    [string]$PageId,

    [switch]$Apply
)

$ErrorActionPreference = 'Stop'

function ConvertTo-NormalizedText {
    param([string]$Text)

    return ($Text -replace "`r`n", "`n").TrimEnd()
}

function ConvertTo-YamlDoubleQuoted {
    param([string]$Value)

    $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
    $escaped = $escaped.Replace("`t", '\t').Replace("`r", '\r').Replace("`n", '\n')
    return '"' + $escaped + '"'
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

$resolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)
$pathRoot = [System.IO.Path]::GetPathRoot($resolvedRoot).TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)

if ($resolvedRoot.Equals($pathRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    $conflicts.Add("Root cannot be a filesystem root: $resolvedRoot")
}

if ([string]::IsNullOrWhiteSpace($ProjectName)) {
    $conflicts.Add('ProjectName cannot be blank.')
}
else {
    $invalidNameCharacters = [System.IO.Path]::GetInvalidFileNameChars()
    if ($ProjectName.IndexOfAny($invalidNameCharacters) -ge 0 -or $ProjectName -match '[\x00-\x1F]') {
        $conflicts.Add("ProjectName is not a valid Windows directory name: $ProjectName")
    }
    if ($ProjectName.EndsWith(' ') -or $ProjectName.EndsWith('.')) {
        $conflicts.Add('ProjectName cannot end with a space or period.')
    }
    $reservedNames = @('CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9')
    $baseName = $ProjectName.Split('.')[0].ToUpperInvariant()
    if ($reservedNames -contains $baseName) {
        $conflicts.Add("ProjectName is reserved by Windows: $ProjectName")
    }
}

$rootName = [System.IO.Path]::GetFileName($resolvedRoot)
if (-not $rootName.Equals($ProjectName, [System.StringComparison]::Ordinal)) {
    $conflicts.Add("Local folder name '$rootName' must exactly match ClickUp Folder name '$ProjectName'.")
}

if ([string]::IsNullOrWhiteSpace($Description) -or $Description -match '[\r\n]') {
    $conflicts.Add('Description must be one non-empty line.')
}

$numericIds = [ordered]@{
    WorkspaceId = $WorkspaceId
    SpaceId = $SpaceId
    FolderId = $FolderId
    TaskListId = $TaskListId
}
foreach ($entry in $numericIds.GetEnumerator()) {
    if ($entry.Value -notmatch '^\d+$') {
        $conflicts.Add("$($entry.Key) must contain only digits.")
    }
}

$opaqueIds = [ordered]@{
    DocId = $DocId
    PageId = $PageId
}
foreach ($entry in $opaqueIds.GetEnumerator()) {
    if ($entry.Value -notmatch '^[A-Za-z0-9-]+$') {
        $conflicts.Add("$($entry.Key) must contain only letters, digits, or hyphens.")
    }
}

if (Test-Path -LiteralPath $resolvedRoot -PathType Leaf) {
    $conflicts.Add("Project root is an existing file: $resolvedRoot")
}
elseif (-not (Test-Path -LiteralPath $resolvedRoot -PathType Container)) {
    $parent = [System.IO.Directory]::GetParent($resolvedRoot)
    if ($null -eq $parent -or -not (Test-Path -LiteralPath $parent.FullName -PathType Container)) {
        $conflicts.Add("Parent directory does not exist: $($parent.FullName)")
    }
    else {
        $changes.Add("Create directory: $resolvedRoot")
    }
}

$skillRoot = Split-Path -Parent $PSScriptRoot
$readmeTemplatePath = Join-Path $skillRoot 'assets\project-README.md'
$agentsTemplatePath = Join-Path $skillRoot 'assets\project-AGENTS.md'
foreach ($templatePath in @($readmeTemplatePath, $agentsTemplatePath)) {
    if (-not (Test-Path -LiteralPath $templatePath -PathType Leaf)) {
        $conflicts.Add("Installed skill is missing required asset: $templatePath")
    }
}

$manifest = @"
# DIA project manifest schema 1
schema_version: 1

project:
  name: $(ConvertTo-YamlDoubleQuoted $ProjectName)
  type: "business-insights"

clickup:
  workspace_id: $(ConvertTo-YamlDoubleQuoted $WorkspaceId)
  space_id: $(ConvertTo-YamlDoubleQuoted $SpaceId)
  folder_id: $(ConvertTo-YamlDoubleQuoted $FolderId)
  task_list_id: $(ConvertTo-YamlDoubleQuoted $TaskListId)
  project_hub:
    doc_id: $(ConvertTo-YamlDoubleQuoted $DocId)
    page_id: $(ConvertTo-YamlDoubleQuoted $PageId)
"@

$requiredDirectories = @(
    'transcripts',
    'transcripts\inbox',
    'transcripts\processed',
    'source-data',
    'analysis',
    'deliverables',
    'deliverables\data-products',
    'deliverables\presentations',
    'working'
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

$manifestPath = Join-Path $resolvedRoot 'project.yaml'
if (Test-Path -LiteralPath $manifestPath -PathType Container) {
    $conflicts.Add("Expected file is an existing directory: $manifestPath")
}
elseif (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    $existingManifest = Get-Content -Raw -LiteralPath $manifestPath
    if ((ConvertTo-NormalizedText $existingManifest) -ne (ConvertTo-NormalizedText $manifest)) {
        $conflicts.Add("Existing project manifest does not exactly match schema 1 and the verified project values: $manifestPath")
    }
    else {
        $preserved.Add("Existing file: $manifestPath")
    }
}
else {
    $changes.Add("Create file: $manifestPath")
}

$boilerplateFiles = [ordered]@{
    'README.md' = $readmeTemplatePath
    'AGENTS.md' = $agentsTemplatePath
}
foreach ($entry in $boilerplateFiles.GetEnumerator()) {
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
    if (-not (Test-Path -LiteralPath $directoryPath)) {
        [System.IO.Directory]::CreateDirectory($directoryPath) | Out-Null
    }
}

if (-not (Test-Path -LiteralPath $manifestPath)) {
    [System.IO.File]::WriteAllText($manifestPath, (ConvertTo-NormalizedText $manifest) + [Environment]::NewLine, $utf8WithoutBom)
}

$readmeText = $null
$agentsText = $null
if (-not (Test-Path -LiteralPath (Join-Path $resolvedRoot 'README.md'))) {
    $readmeText = Get-Content -Raw -LiteralPath $readmeTemplatePath
    $readmeText = [regex]::Replace(
        $readmeText,
        '\{\{PROJECT_NAME\}\}|\{\{PROJECT_DESCRIPTION\}\}',
        {
            param($templateMatch)
            if ($templateMatch.Value -eq '{{PROJECT_NAME}}') {
                return $ProjectName
            }
            return $Description
        }
    )
    [System.IO.File]::WriteAllText((Join-Path $resolvedRoot 'README.md'), (ConvertTo-NormalizedText $readmeText) + [Environment]::NewLine, $utf8WithoutBom)
}
if (-not (Test-Path -LiteralPath (Join-Path $resolvedRoot 'AGENTS.md'))) {
    $agentsText = Get-Content -Raw -LiteralPath $agentsTemplatePath
    [System.IO.File]::WriteAllText((Join-Path $resolvedRoot 'AGENTS.md'), (ConvertTo-NormalizedText $agentsText) + [Environment]::NewLine, $utf8WithoutBom)
}

$postApplyConflicts = [System.Collections.Generic.List[string]]::new()
foreach ($relativeDirectory in $requiredDirectories) {
    $directoryPath = Join-Path $resolvedRoot $relativeDirectory
    if (-not (Test-Path -LiteralPath $directoryPath -PathType Container)) {
        $postApplyConflicts.Add("Required directory is missing after apply: $directoryPath")
    }
}
foreach ($relativeFile in @('project.yaml', 'README.md', 'AGENTS.md')) {
    $filePath = Join-Path $resolvedRoot $relativeFile
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
        $postApplyConflicts.Add("Required file is missing after apply: $filePath")
    }
}
if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    $writtenManifest = Get-Content -Raw -LiteralPath $manifestPath
    if ((ConvertTo-NormalizedText $writtenManifest) -ne (ConvertTo-NormalizedText $manifest)) {
        $postApplyConflicts.Add("Project manifest differs after apply: $manifestPath")
    }
}

if ($postApplyConflicts.Count -gt 0) {
    Write-Result (New-Result 'conflict' $false $resolvedRoot $changes $preserved $postApplyConflicts) 2
}

$finalAction = if ($changes.Count -eq 0) { 'valid' } else { 'created' }
Write-Result (New-Result $finalAction $true $resolvedRoot $changes $preserved $postApplyConflicts) 0
