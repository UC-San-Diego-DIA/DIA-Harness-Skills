[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$RequestFile,
    [string]$ApprovedPlanFile,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$completed = @()
$layoutCreated = $false
$temporaryMoves = Join-Path ([IO.Path]::GetTempPath()) ('dia-workspace-moves-' + [guid]::NewGuid() + '.json')
function Invoke-Helper([string]$Name, [hashtable]$Arguments) {
    $output = & (Join-Path $PSScriptRoot $Name) @Arguments
    # Helpers exit their script scope; their JSON is the source of truth.
    $result = ($output -join "`n") | ConvertFrom-Json
    if ($result.action -eq 'conflict' -or $result.valid -eq $false -and $result.action -ne 'planned') {
        throw ($result | ConvertTo-Json -Depth 8 -Compress)
    }
    return $result
}
function Hash-Text([string]$Value) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($Value)))
}
try {
    $requestText = Get-Content -Raw -LiteralPath $RequestFile
    $request = $requestText | ConvertFrom-Json
    if ($request.layout -notin @('simple','analysis')) { throw 'Choose simple or analysis.' }
    if (-not [IO.Path]::IsPathFullyQualified($request.root)) { throw 'Root must be absolute.' }
    $target = [IO.Path]::GetFullPath($request.root).TrimEnd('\','/')
    if (-not $request.projectContext) { throw 'Record project context before setup.' }
    $moves = @($request.moves | Where-Object { $null -ne $_ })
    ConvertTo-Json -InputObject $moves -Depth 6 | Set-Content -LiteralPath $temporaryMoves -Encoding utf8
    $moveArguments = @{ Root=$target; Layout=$request.layout; MovesFile=$temporaryMoves }
    $movePlan = Invoke-Helper 'move_starting_files.ps1' $moveArguments
    $dictionaryDestination = Join-Path $target 'docs\data-dictionary.md'
    $hasDictionary = @($movePlan.moves | Where-Object { $_.destination -eq $dictionaryDestination }).Count -gt 0
    if ($request.useSuppliedDictionary -and ($request.layout -ne 'analysis' -or -not $hasDictionary)) {
        throw 'UseSuppliedDictionary requires an incoming file at docs/data-dictionary.md in the analysis layout.'
    }
    if ($hasDictionary -and -not $request.useSuppliedDictionary) {
        throw 'Incoming data dictionary conflicts with the generated placeholder. Confirm useSuppliedDictionary to keep the supplied dictionary, or select another destination.'
    }
    $context = "`n`n## Workspace location`n`n- Root: $target`n- Layout: $($request.layout)`n`n" + $request.projectContext
    if ($request.layout -eq 'simple') {
        $helper = 'create_simple_workspace.ps1'
        $layoutArguments = @{ Root=$target; ProjectContext=$context }
    } else {
        $helper = 'create_workspace.ps1'
        $layoutArguments = @{ Root=(Split-Path -Parent $target); WorkspaceName=(Split-Path -Leaf $target); Description=$request.description; DataSources=$request.dataSources; ProjectContext=$context; UseSuppliedDictionary=[bool]$request.useSuppliedDictionary }
    }
    $layoutPlan = Invoke-Helper $helper $layoutArguments
    foreach ($move in $movePlan.moves) {
        foreach ($change in $layoutPlan.changes) {
            $isFile = $change.StartsWith('Create file: ')
            $generatedPath = if ($isFile) { $change.Substring(13) } elseif ($change.StartsWith('Create directory: ')) { $change.Substring(18) } else { continue }
            if ($move.destination -eq $generatedPath -or
                $generatedPath.StartsWith($move.destination + '\', [StringComparison]::OrdinalIgnoreCase) -or
                ($isFile -and $move.destination.StartsWith($generatedPath + '\', [StringComparison]::OrdinalIgnoreCase))) {
                throw "Incoming file conflicts with generated layout: $($move.destination). Select another destination."
            }
        }
        foreach ($other in $movePlan.moves) {
            if ($other.destination.StartsWith($move.destination + '\', [StringComparison]::OrdinalIgnoreCase)) {
                throw "Incoming file would become another move's parent directory: $($move.destination). Select another destination."
            }
        }
    }
    $sourceHashes = @($movePlan.moves | ForEach-Object { [ordered]@{ path=$_.source; hash=(Get-FileHash -LiteralPath $_.source -Algorithm SHA256).Hash } })
    $preservedHashes = @($layoutPlan.preserved | Where-Object { $_.StartsWith('Existing file: ') } | ForEach-Object { $path=$_.Substring(15); [ordered]@{ path=$path; hash=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash } })
    $resourceHashes = @(Get-ChildItem -LiteralPath (Split-Path -Parent $PSScriptRoot) -Recurse -File | Sort-Object FullName | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash })
    $snapshot = [ordered]@{ request=(Hash-Text $requestText); layout=$layoutPlan; moves=$movePlan.moves; sources=$sourceHashes; preserved=$preservedHashes; resources=$resourceHashes }
    $fingerprint = Hash-Text ($snapshot | ConvertTo-Json -Depth 12 -Compress)
    $plan = [ordered]@{ action='planned'; valid=$true; root=$target; layout=$request.layout; changes=$layoutPlan.changes; preserved=$layoutPlan.preserved; moves=$movePlan.moves; useSuppliedDictionary=[bool]$request.useSuppliedDictionary; projectContext=$context; fingerprint=$fingerprint }
    if (-not $Apply) { $plan | ConvertTo-Json -Depth 10; exit 0 }
    if (-not $ApprovedPlanFile) { throw 'Apply requires the exact saved preview in ApprovedPlanFile.' }
    $approved = Get-Content -Raw -LiteralPath $ApprovedPlanFile | ConvertFrom-Json
    if ($approved.fingerprint -ne $fingerprint) { throw 'The request, source files, workspace, or skill changed since preview. Generate a new preview and obtain confirmation.' }
    $created = Invoke-Helper $helper ($layoutArguments + @{Apply=$true})
    $layoutCreated = $created.valid
    $moved = & (Join-Path $PSScriptRoot 'move_starting_files.ps1') @moveArguments -Apply | ConvertFrom-Json
    $completed = @($moved.completed)
    if (-not $moved.valid) { throw $moved.error }
    if ($request.useSuppliedDictionary -and -not (Test-Path -LiteralPath $dictionaryDestination -PathType Leaf)) { throw 'Supplied dictionary missing after setup.' }
    [ordered]@{ action='created'; valid=$true; root=$target; created=$created.changes; preserved=$created.preserved; completed=$completed } | ConvertTo-Json -Depth 10
}
catch {
    [ordered]@{ action='conflict'; valid=$false; error=$_.Exception.Message; layoutCreated=$layoutCreated; completed=$completed } | ConvertTo-Json -Depth 10
    exit 2
}
finally {
    if (Test-Path -LiteralPath $temporaryMoves) { Remove-Item -LiteralPath $temporaryMoves }
}
