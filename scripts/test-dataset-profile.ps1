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

    Assert-True ($profile.duplicate_row_count -eq 0) 'Unique rows must not be reported as duplicates.'
    $expectedHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-True ($profile.source_sha256 -eq $expectedHash) 'Profile fingerprint must match the source bytes.'
    Assert-True ($profile.parsing_settings.header -eq $true) 'Expected header parsing setting.'
    Assert-True ($profile.parsing_settings.sample_size -eq -1) 'Expected full-file CSV type inference.'
    Assert-True (-not [string]::IsNullOrWhiteSpace($profile.python_version)) 'Python version is missing.'
    Assert-True (-not [string]::IsNullOrWhiteSpace($profile.duckdb_version)) 'DuckDB version is missing.'

    $integerSource = Join-Path $resolvedTestRoot 'integer-hours.csv'
    Set-Content -LiteralPath $integerSource -Encoding utf8 -Value "RequestID,Hours`r`nA,1`r`nB,2`r`nC,3`r`nD,4`r`nE,120`r`nF,"
    $integerProfile = Invoke-ProfileHelper @('profile', '--source', $integerSource)
    $hours = $integerProfile.columns | Where-Object { $_.name -eq 'Hours' }
    Assert-True ($hours.duckdb_type -eq 'BIGINT') 'Expected integer type inference for whole-number hours.'
    Assert-True ($hours.min -eq 1 -and $hours.max -eq 120) 'Whole-number fields need numeric ranges.'
    Assert-True ($hours.median -eq 3) 'Whole-number fields need numeric summaries.'
    Assert-True ($hours.outlier_count -eq 1) 'Whole-number fields need outlier counts.'

    $duplicatesSource = Join-Path $resolvedTestRoot 'duplicates.csv'
    # Two extra rows in one group and one extra in another, including nulls.
    Set-Content -LiteralPath $duplicatesSource -Encoding utf8 -Value "ID,Value`r`n1,A`r`n1,A`r`n1,A`r`n2,`r`n2,`r`n3,C"
    $duplicates = Invoke-ProfileHelper @('profile', '--source', $duplicatesSource)
    Assert-True ($duplicates.duplicate_row_count -eq 3) 'Expected three extra identical rows, not two groups or five participating rows.'
    Assert-True (@($duplicates.candidate_keys).Count -eq 0) 'Repeated values cannot be candidate keys.'

    $emptySource = Join-Path $resolvedTestRoot 'empty.csv'
    Set-Content -LiteralPath $emptySource -Encoding utf8 -Value 'ID,Value'
    $empty = Invoke-ProfileHelper @('profile', '--source', $emptySource)
    Assert-True ($empty.row_count -eq 0) 'Expected no data rows.'
    Assert-True ($empty.duplicate_row_count -eq 0) 'Empty data cannot contain duplicate rows.'
    Assert-True (@($empty.candidate_keys).Count -eq 0) 'Empty data cannot establish candidate keys.'
    Assert-True ($null -eq $empty.columns[0].null_rate) 'An empty file has an undefined null rate.'

    $singleSource = Join-Path $resolvedTestRoot 'single.csv'
    Set-Content -LiteralPath $singleSource -Encoding utf8 -Value "ID,Value`r`n1,A"
    $single = Invoke-ProfileHelper @('profile', '--source', $singleSource)
    Assert-True ($single.duplicate_row_count -eq 0) 'A single row cannot be a duplicate.'

    $overrideSource = Join-Path $resolvedTestRoot 'override.csv'
    Set-Content -LiteralPath $overrideSource -Encoding utf8 -Value "Code;Value`r`n001;10`r`n002;20"
    $override = Invoke-ProfileHelper @('profile', '--source', $overrideSource, '--delimiter', ';', '--all-varchar')
    Assert-True ($override.parsing_settings.delimiter -eq ';') 'Explicit delimiter must be recorded.'
    Assert-True ($override.parsing_settings.all_varchar -eq $true) 'Explicit text parsing must be recorded.'
    Assert-True ($override.columns[0].top_values[0].value -eq '001') 'Text override must preserve leading zeros.'
    Assert-True ($override.source_sha256 -eq (Get-FileHash -LiteralPath $overrideSource -Algorithm SHA256).Hash.ToLowerInvariant()) 'Overrides must not change source bytes.'

    Add-Content -LiteralPath $source -Encoding utf8 -Value '7,20.00,West'
    $changed = Invoke-ProfileHelper @('profile', '--source', $source)
    Assert-True ($changed.source_sha256 -ne $profile.source_sha256) 'Changed source must produce a new fingerprint.'
    Assert-True ($changed.row_count -eq 7) 'Changed source must be profiled afresh.'

    Write-Host 'Dataset-profile helper tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

exit 0
