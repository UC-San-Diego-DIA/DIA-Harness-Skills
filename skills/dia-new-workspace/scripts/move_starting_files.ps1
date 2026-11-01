[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$Root,
    [Parameter(Mandatory)] [ValidateSet('simple', 'analysis')] [string]$Layout,
    [Parameter(Mandatory)] [string]$MovesFile,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$completed = [System.Collections.Generic.List[object]]::new()
$planned = [System.Collections.Generic.List[object]]::new()
try {
    if (-not [IO.Path]::IsPathFullyQualified($Root)) { throw 'Root must be absolute.' }
    $targetRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    if ($targetRoot -eq [IO.Path]::GetPathRoot($targetRoot).TrimEnd('\', '/')) { throw 'Root cannot be a filesystem root.' }
    $prefix = $targetRoot + [IO.Path]::DirectorySeparatorChar
    $entries = Get-Content -Raw -LiteralPath $MovesFile | ConvertFrom-Json -NoEnumerate
    if ($entries -isnot [array]) { throw 'MovesFile must contain a JSON array.' }
    $destinations = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $sources = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $allowed = if ($Layout -eq 'simple') { @('Inputs','Scripts','Outputs') } else { @('data\raw','docs','scratch','scripts','reports') }
    foreach ($entry in $entries) {
        if (-not $entry.source -or -not $entry.destination) { throw 'Each move needs source and destination.' }
        if (-not [IO.Path]::IsPathFullyQualified($entry.source) -or [IO.Path]::IsPathRooted($entry.destination)) { throw 'Source must be absolute and destination relative.' }
        $source = [IO.Path]::GetFullPath($entry.source)
        $destination = [IO.Path]::GetFullPath((Join-Path $targetRoot $entry.destination))
        if (-not $destination.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Destination escapes workspace: $destination" }
        $relative = [IO.Path]::GetRelativePath($targetRoot, $destination)
        $permitted = @($allowed | Where-Object { $relative.StartsWith($_ + '\', [StringComparison]::OrdinalIgnoreCase) }).Count -gt 0
        if (-not $permitted -or $relative -match '(^|[\\/])[^\\/]*:') { throw "Destination is outside layout file locations: $destination" }
        if (-not $destinations.Add($destination) -or -not $sources.Add($source)) { throw 'Duplicate source or destination.' }
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Source is not a regular file: $source" }
        if (Test-Path -LiteralPath $destination) { throw "Destination already exists: $destination" }
        # Check all existing ancestors, not just the final path, for redirected locations.
        foreach ($candidate in @($source, $destination)) {
            $cursor = $candidate
            while ($cursor) {
                if (Test-Path -LiteralPath $cursor) {
                    $item = Get-Item -LiteralPath $cursor -Force
                    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked path is not supported: $cursor" }
                    if ($cursor -ne $source -and $cursor -ne $destination -and -not $item.PSIsContainer) { throw "Parent is not a directory: $cursor" }
                }
                $cursor = Split-Path -Parent $cursor
            }
        }
        if ($source.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Starting files must come from outside the new workspace.' }
        $planned.Add([ordered]@{ source = $source; destination = $destination })
    }
    if ($Apply) {
        if (-not (Test-Path -LiteralPath $targetRoot -PathType Container)) { throw 'Create the workspace before applying moves.' }
        foreach ($move in $planned) {
            [IO.Directory]::CreateDirectory((Split-Path -Parent $move.destination)) | Out-Null
            # The two-argument File.Move refuses an existing destination, including a late collision.
            [IO.File]::Move($move.source, $move.destination)
            $completed.Add($move)
        }
    }
    [ordered]@{ action = $(if ($Apply) { 'moved' } else { 'planned' }); valid = $true; moves = @($planned); completed = @($completed) } | ConvertTo-Json -Depth 5
}
catch {
    [ordered]@{ action = 'conflict'; valid = $false; error = $_.Exception.Message; completed = @($completed) } | ConvertTo-Json -Depth 5
    exit 2
}
