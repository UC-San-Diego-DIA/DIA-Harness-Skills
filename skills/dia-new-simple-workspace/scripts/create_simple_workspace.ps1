[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

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

$rootName = [System.IO.Path]::GetFileName($resolvedRoot)
$invalidNameCharacters = [System.IO.Path]::GetInvalidFileNameChars()
if ($rootName.IndexOfAny($invalidNameCharacters) -ge 0 -or $rootName -match '[\x00-\x1F]') {
    $conflicts.Add("Root is not a valid Windows directory name: $resolvedRoot")
}
if ($rootName.EndsWith(' ') -or $rootName.EndsWith('.')) {
    $conflicts.Add("Root cannot end with a space or period: $resolvedRoot")
}
$reservedNames = @('CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9')
if ($reservedNames -contains $rootName.Split('.')[0].ToUpperInvariant()) {
    $conflicts.Add("Root uses a name reserved by Windows: $resolvedRoot")
}

if (Test-Path -LiteralPath $resolvedRoot -PathType Leaf) {
    $conflicts.Add("Root is an existing file: $resolvedRoot")
}
elseif (-not (Test-Path -LiteralPath $resolvedRoot -PathType Container)) {
    $parent = [System.IO.Directory]::GetParent($resolvedRoot)
    if ($null -eq $parent) {
        $conflicts.Add("Parent directory does not exist for: $resolvedRoot")
    }
    elseif (-not (Test-Path -LiteralPath $parent.FullName -PathType Container)) {
        $conflicts.Add("Parent directory does not exist: $($parent.FullName)")
    }
    else {
        $changes.Add("Create directory: $resolvedRoot")
    }
}

$skillRoot = Split-Path -Parent $PSScriptRoot
$readmeTemplatePath = Join-Path $skillRoot 'assets\workspace-README.md'
$agentsTemplatePath = Join-Path $skillRoot 'assets\workspace-AGENTS.md'
foreach ($templatePath in @($readmeTemplatePath, $agentsTemplatePath)) {
    if (-not (Test-Path -LiteralPath $templatePath -PathType Leaf)) {
        $conflicts.Add("Installed skill is missing required asset: $templatePath")
    }
}

$requiredDirectories = @('Scripts', 'Inputs', 'Outputs')

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

if (-not (Test-Path -LiteralPath (Join-Path $resolvedRoot 'README.md'))) {
    $readmeText = Get-Content -Raw -LiteralPath $readmeTemplatePath
    $readmeText = $readmeText.Replace('{{FOLDER_NAME}}', $rootName)
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
foreach ($relativeFile in @('README.md', 'AGENTS.md')) {
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
