[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Python
)

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

function Invoke-ProfileHelper {
    param([string[]]$Arguments)

    $output = & $Python $helper @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Dataset-profile helper failed for '$($Arguments -join ' ')': $($output -join [Environment]::NewLine)"
    }
    $outputText = $output -join [Environment]::NewLine
    $result = $outputText | ConvertFrom-Json
    $result | Add-Member -NotePropertyName '_raw_json' -NotePropertyValue $outputText
    return $result
}

function Invoke-ExpectedFailure {
    param(
        [string[]]$Arguments,
        [string[]]$ExpectedText
    )

    $output = & $Python $helper @Arguments 2>&1
    Assert-True ($LASTEXITCODE -eq 2) "Expected a user-correctable failure for '$($Arguments -join ' ')'."
    $outputText = $output -join [Environment]::NewLine
    foreach ($expected in $ExpectedText) {
        Assert-True $outputText.Contains($expected) "Expected '$expected' in failure output: $outputText"
    }
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$helper = Join-Path $repositoryRoot 'skills\dia-dataset-profile\scripts\duckdb_profile.py'
$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase "dia-dataset-profile-$([System.Guid]::NewGuid().ToString('N'))"
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
$safePrefix = $temporaryBase.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $resolvedTestRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Test root '$resolvedTestRoot' is outside '$temporaryBase'."
}

try {
    New-Item -ItemType Directory -Path $resolvedTestRoot | Out-Null

    $source = Join-Path $resolvedTestRoot 'sales.csv'
    $sourceLines = @(
        'ID,Amount,Region',
        '1,10.00,West',
        '2,11.00,East',
        '3,12.00,West',
        '4,13.00,East',
        '5,900.00,West',
        '6,,East'
    )
    Set-Content -LiteralPath $source -Encoding utf8 -Value ($sourceLines -join "`r`n")

    $profile = Invoke-ProfileHelper @('profile', '--source', $source, '--top-values', '5')
    Assert-True ($profile.action -eq 'profile') 'Expected profile action.'
    Assert-True ($profile.row_count -eq 6) "Expected 6 rows, found $($profile.row_count)."
    Assert-True ($profile.column_count -eq 3) "Expected 3 columns, found $($profile.column_count)."
    Assert-True ($profile.candidate_keys -contains 'ID') "Expected 'ID' as a candidate key: $($profile.candidate_keys -join ', ')"

    $amount = $profile.columns | Where-Object { $_.name -eq 'Amount' }
    Assert-True ($null -ne $amount) 'Expected an Amount column in the profile.'
    Assert-True ($amount.null_count -eq 1) "Expected one null Amount, found $($amount.null_count)."
    Assert-True ($amount.outlier_count -ge 1) "Expected at least one Amount outlier, found $($amount.outlier_count)."
    Assert-True ($amount.median -eq 12) "Expected median Amount of 12, found $($amount.median)."

    $region = $profile.columns | Where-Object { $_.name -eq 'Region' }
    Assert-True ($region.top_values.Count -eq 2) 'Expected two Region top values.'
    Assert-True ($region.top_values[0].value -eq 'East') 'Expected East first in top values with a count tie.'

    $legacySource = Join-Path $resolvedTestRoot 'legacy.xls'
    Set-Content -LiteralPath $legacySource -Encoding utf8 -Value 'stub'
    Invoke-ExpectedFailure @('profile', '--source', $legacySource) @('Convert .xls workbooks to .xlsx first')

    $queryFile = Join-Path $resolvedTestRoot 'region-counts.sql'
    Set-Content -LiteralPath $queryFile -Encoding utf8 -Value 'SELECT Region, count(*) AS n FROM dataset GROUP BY 1 ORDER BY 1'
    $query = Invoke-ProfileHelper @('query', '--source', $source, '--sql-file', $queryFile, '--max-rows', '10')
    Assert-True ($query.returned_rows -eq 2) "Expected 2 query rows, found $($query.returned_rows)."
    Assert-True (-not $query.truncated) 'Expected the query result not to be truncated.'

    $blockedFile = Join-Path $resolvedTestRoot 'blocked.sql'
    Set-Content -LiteralPath $blockedFile -Encoding utf8 -Value 'DELETE FROM dataset'
    Invoke-ExpectedFailure @('query', '--source', $source, '--sql-file', $blockedFile) @('exactly one SELECT')

    Write-Host 'Dataset-profile helper tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
