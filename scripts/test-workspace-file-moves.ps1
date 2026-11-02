$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Clean-TestRoot.ps1')
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$testRoot = [IO.Path]::GetFullPath((Join-Path $temporaryBase ('dia-moves-' + [guid]::NewGuid())))
if (-not $testRoot.StartsWith($temporaryBase.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test root.' }
$helper = Join-Path $PSScriptRoot '..\skills\dia-new-workspace\scripts\move_starting_files.ps1'
function Run-Moves($layout, $expected, [switch]$Apply) {
    $arguments = @('-Root', $workspace, '-Layout', $layout, '-MovesFile', $plan)
    if ($Apply) { $arguments += '-Apply' }
    $output = & (Join-Path $PSHOME 'pwsh.exe') -NoProfile -File $helper @arguments
    if ($LASTEXITCODE -ne $expected) { throw "Unexpected exit: $output" }
    $output | ConvertFrom-Json
}
try {
    New-Item -ItemType Directory -Path $testRoot | Out-Null
    $workspace = Join-Path $testRoot 'Workspace'
    $source = Join-Path $testRoot 'source.csv'
    $plan = Join-Path $testRoot 'moves.json'
    Set-Content -LiteralPath $source -Value 'original data'
    ConvertTo-Json -InputObject @(@{ source = $source; destination = 'Inputs\source.csv' }) | Set-Content -LiteralPath $plan
    $null = Run-Moves simple 0
    if ((Test-Path $workspace) -or -not (Test-Path $source)) { throw 'Preview changed files.' }
    New-Item -ItemType Directory -Path $workspace | Out-Null
    $null = Run-Moves simple 0 -Apply
    if ((Test-Path $source) -or (Get-Content (Join-Path $workspace 'Inputs\source.csv')) -ne 'original data') { throw 'Move did not preserve content and remove source.' }
    Set-Content -LiteralPath $source -Value 'new source'
    $null = Run-Moves simple 2 -Apply
    if ((Get-Content $source) -ne 'new source') { throw 'Conflict changed source.' }
    ConvertTo-Json -InputObject @(
        @{ source = $source; destination = 'Inputs\new.csv' },
        @{ source = (Join-Path $testRoot 'missing.csv'); destination = 'Inputs\missing.csv' }
    ) | Set-Content -LiteralPath $plan
    $null = Run-Moves simple 2 -Apply
    if (-not (Test-Path $source) -or (Test-Path (Join-Path $workspace 'Inputs\new.csv'))) { throw 'Batch preflight moved a file before discovering a conflict.' }
    foreach ($destination in @('..\escaped.csv', 'AGENTS.md', 'data\output\source.csv')) {
        ConvertTo-Json -InputObject @(@{ source = $source; destination = $destination }) | Set-Content -LiteralPath $plan
        $null = Run-Moves analysis 2 -Apply
    }
    ConvertTo-Json -InputObject @(@{ source = $source; destination = 'data\raw\source.csv' }) | Set-Content -LiteralPath $plan
    $null = Run-Moves analysis 0 -Apply
    if (Test-Path $source) { throw 'Analysis move left source in place.' }
    Set-Content -LiteralPath $plan -Value '[]'
    $null = Run-Moves analysis 0
    Write-Host 'Workspace file-move tests passed.'
}
finally {
    Remove-TestRoot $testRoot
}
