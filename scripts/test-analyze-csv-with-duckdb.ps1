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

function Invoke-AnalysisHelper {
    param([string[]]$Arguments)

    $output = & $Python $helper @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "DuckDB helper failed for '$($Arguments -join ' ')': $($output -join [Environment]::NewLine)"
    }
    $outputText = $output -join [Environment]::NewLine
    $result = $outputText | ConvertFrom-Json
    $result | Add-Member -NotePropertyName '_raw_json' -NotePropertyValue $outputText
    return $result
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$helper = Join-Path $repositoryRoot 'skills\analyze-csv-with-duckdb\scripts\duckdb_analysis.py'
$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase "dia-duckdb-analysis-$([System.Guid]::NewGuid().ToString('N'))"
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
$safePrefix = $temporaryBase.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $resolvedTestRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Test root '$resolvedTestRoot' is outside '$temporaryBase'."
}

try {
    $currentFolder = Join-Path $resolvedTestRoot 'work'
    New-Item -ItemType Directory -Path $currentFolder | Out-Null
    $source = Join-Path $currentFolder 'sales.csv'
    $workspace = Join-Path $currentFolder 'analysis\sales'
    $queryFile = Join-Path $resolvedTestRoot 'question.sql'
    $temporalQueryFile = Join-Path $resolvedTestRoot 'temporal.sql'
    $blockedQueryFile = Join-Path $resolvedTestRoot 'blocked.sql'
    $externalQueryFile = Join-Path $resolvedTestRoot 'external.sql'

    @'
Order ID,Revenue,Region
1,10.50,West
2,,East
3,20.00,West
'@ | Set-Content -LiteralPath $source -Encoding utf8 -NoNewline

    $setup = Invoke-AnalysisHelper @(
        'setup',
        '--root', $currentFolder,
        '--source', $source,
        '--workspace', $workspace
    )
    Assert-True ($setup.action -eq 'created') 'Setup did not report a created workspace.'
    Assert-True ($setup.row_count -eq 3) 'Setup row count is incorrect.'
    Assert-True (Test-Path -LiteralPath (Join-Path $workspace 'data\sales.csv') -PathType Leaf) 'Snapshot CSV is missing.'
    Assert-True (Test-Path -LiteralPath (Join-Path $workspace 'analysis.duckdb') -PathType Leaf) 'DuckDB database is missing.'
    Assert-True (Test-Path -LiteralPath (Join-Path $workspace 'ANALYSIS.md') -PathType Leaf) 'ANALYSIS.md is missing.'
    Assert-True (Test-Path -LiteralPath (Join-Path $workspace '.gitignore') -PathType Leaf) '.gitignore is missing.'

    'WITH totals AS (SELECT region, sum(revenue) AS revenue FROM dataset GROUP BY region) SELECT * FROM totals ORDER BY region;' |
        Set-Content -LiteralPath $queryFile -Encoding utf8
    $query = Invoke-AnalysisHelper @(
        'query',
        '--workspace', $workspace,
        '--question', 'What is revenue by region?',
        '--sql-file', $queryFile
    )
    Assert-True ($query.returned_rows -eq 2) 'Query returned an unexpected row count.'
    Assert-True ($query.truncated -eq $false) 'Query was unexpectedly truncated.'
    Assert-True (Test-Path -LiteralPath $query.sql_file -PathType Leaf) 'Successful SQL was not saved.'

    @'
SELECT
    DATE '2026-08-24' AS report_date,
    TIME '12:34:56' AS report_time,
    TIMESTAMP '2026-08-24 12:34:56' AS reported_at,
    TIMESTAMPTZ '2026-08-24 12:34:56-07:00' AS reported_at_tz;
'@ | Set-Content -LiteralPath $temporalQueryFile -Encoding utf8 -NoNewline
    $temporalQuery = Invoke-AnalysisHelper @(
        'query',
        '--workspace', $workspace,
        '--question', 'Can temporal values be returned as JSON?',
        '--sql-file', $temporalQueryFile
    )
    Assert-True ($temporalQuery.rows[0][0] -eq '2026-08-24') 'DATE result was not serialized as ISO 8601.'
    Assert-True ($temporalQuery.rows[0][1] -eq '12:34:56') 'TIME result was not serialized as ISO 8601.'
    Assert-True ($temporalQuery.rows[0][2] -eq '2026-08-24T12:34:56') 'TIMESTAMP result was not serialized as ISO 8601.'
    Assert-True ($temporalQuery._raw_json -match '"2026-08-24T\d{2}:34:56(?:\.\d+)?[+-]\d{2}:\d{2}"') 'TIMESTAMPTZ result was not serialized with a UTC offset.'

    'DELETE FROM dataset;' | Set-Content -LiteralPath $blockedQueryFile -Encoding utf8
    $blockedOutput = & $Python $helper query --workspace $workspace --question 'Delete rows' --sql-file $blockedQueryFile 2>&1
    Assert-True ($LASTEXITCODE -eq 2) 'A DELETE statement was not rejected.'
    Assert-True (($blockedOutput -join [Environment]::NewLine).Contains('exactly one SELECT')) 'DELETE rejection was unclear.'

    "SELECT * FROM read_csv('$($source.Replace("'", "''"))');" |
        Set-Content -LiteralPath $externalQueryFile -Encoding utf8
    $externalOutput = & $Python $helper query --workspace $workspace --question 'Read another file' --sql-file $externalQueryFile 2>&1
    Assert-True ($LASTEXITCODE -eq 2) 'A SELECT with external file access was not rejected.'
    $externalText = $externalOutput -join [Environment]::NewLine
    $externalWasBlocked = $externalText.Contains('external access') -or $externalText.Contains('file system operations are disabled')
    Assert-True $externalWasBlocked 'External-access rejection was unclear.'
    Assert-True ((Get-ChildItem -LiteralPath (Join-Path $workspace 'queries') -File -Filter '*.sql').Count -eq 2) 'A rejected query was saved.'

    @'
Order ID,Revenue,Region
1,10.50,West
2,,East
3,20.00,West
4,5.00,North
'@ | Set-Content -LiteralPath $source -Encoding utf8 -NoNewline
    $refresh = Invoke-AnalysisHelper @(
        'setup',
        '--root', $currentFolder,
        '--source', $source,
        '--workspace', $workspace,
        '--refresh'
    )
    Assert-True ($refresh.action -eq 'refreshed') 'Refresh did not report success.'
    Assert-True ($refresh.row_count -eq 4) 'Refresh row count is incorrect.'
    Assert-True ((Get-ChildItem -LiteralPath (Join-Path $workspace 'queries') -File -Filter '*.sql').Count -eq 2) 'Refresh did not preserve query history.'
    $analysisText = Get-Content -Raw -LiteralPath (Join-Path $workspace 'ANALYSIS.md')
    Assert-True ($analysisText.Contains('order_id')) 'Normalized header mapping is missing.'
    Assert-True ($analysisText.Contains('superseded')) 'Snapshot history did not mark the prior snapshot.'

    $duplicateSource = Join-Path $currentFolder 'duplicate.csv'
    $duplicateWorkspace = Join-Path $currentFolder 'analysis\duplicate'
    @'
Name,name
one,two
'@ | Set-Content -LiteralPath $duplicateSource -Encoding utf8 -NoNewline
    $duplicateOutput = & $Python $helper setup --root $currentFolder --source $duplicateSource --workspace $duplicateWorkspace 2>&1
    Assert-True ($LASTEXITCODE -eq 2) 'Duplicate headers were not rejected.'
    Assert-True (($duplicateOutput -join [Environment]::NewLine).Contains('duplicate headers')) 'Duplicate-header error was unclear.'

    $quotedSource = Join-Path $currentFolder 'quoted.csv'
    $quotedWorkspace = Join-Path $currentFolder 'analysis\quoted'
    @'
"Customer, Name","He said ""Hi"""
"Palacios, Iris","She said ""Hello"""
'@ | Set-Content -LiteralPath $quotedSource -Encoding utf8 -NoNewline
    $quotedSetup = Invoke-AnalysisHelper @(
        'setup',
        '--root', $currentFolder,
        '--source', $quotedSource,
        '--workspace', $quotedWorkspace
    )
    Assert-True ($quotedSetup.columns[0].original_name -eq 'Customer, Name') 'Quoted comma in a header was parsed incorrectly.'
    Assert-True ($quotedSetup.columns[1].original_name -eq 'He said "Hi"') 'Doubled quote in a header was parsed incorrectly.'
    Assert-True ($quotedSetup.columns[0].sql_name -eq 'customer_name') 'Quoted header was not normalized.'

    $utf8BomSource = Join-Path $currentFolder 'utf8-bom.csv'
    $utf8BomWorkspace = Join-Path $currentFolder 'analysis\utf8-bom'
    $utf8BomEncoding = [System.Text.UTF8Encoding]::new($true)
    [System.IO.File]::WriteAllText($utf8BomSource, "Café,Amount`r`nEast,10`r`n", $utf8BomEncoding)
    $utf8BomSetup = Invoke-AnalysisHelper @(
        'setup',
        '--root', $currentFolder,
        '--source', $utf8BomSource,
        '--workspace', $utf8BomWorkspace
    )
    Assert-True ($utf8BomSetup.columns[0].sql_name -eq 'cafe') 'UTF-8 BOM header was not normalized.'

    $utf16Source = Join-Path $currentFolder 'utf16.csv'
    $utf16Workspace = Join-Path $currentFolder 'analysis\utf16'
    $utf16Encoding = [System.Text.UnicodeEncoding]::new($false, $true)
    [System.IO.File]::WriteAllText($utf16Source, "Café,Amount`r`nEast,10`r`n", $utf16Encoding)
    $utf16Setup = Invoke-AnalysisHelper @(
        'setup',
        '--root', $currentFolder,
        '--source', $utf16Source,
        '--workspace', $utf16Workspace,
        '--encoding', 'UTF_16'
    )
    Assert-True ($utf16Setup.columns[0].sql_name -eq 'cafe') 'UTF-16 header was not normalized.'
    Assert-True ($utf16Setup.read_options.encoding -eq 'utf-16') 'UTF-16 alias was not canonicalized.'

    $latin1Source = Join-Path $currentFolder 'latin1.csv'
    $latin1Workspace = Join-Path $currentFolder 'analysis\latin1'
    $latin1Encoding = [System.Text.Encoding]::GetEncoding('iso-8859-1')
    [System.IO.File]::WriteAllText($latin1Source, "Café,Amount`r`nEast,10`r`n", $latin1Encoding)
    $latin1Setup = Invoke-AnalysisHelper @(
        'setup',
        '--root', $currentFolder,
        '--source', $latin1Source,
        '--workspace', $latin1Workspace,
        '--encoding', 'iso-8859-1'
    )
    Assert-True ($latin1Setup.columns[0].sql_name -eq 'cafe') 'Latin-1 header was not normalized.'
    Assert-True ($latin1Setup.read_options.encoding -eq 'latin-1') 'Latin-1 alias was not canonicalized.'

    $unsupportedWorkspace = Join-Path $currentFolder 'analysis\unsupported-encoding'
    $unsupportedOutput = & $Python $helper setup --root $currentFolder --source $source --workspace $unsupportedWorkspace --encoding cp1252 2>&1
    Assert-True ($LASTEXITCODE -eq 2) 'Unsupported encoding was not rejected.'
    $unsupportedText = $unsupportedOutput -join [Environment]::NewLine
    Assert-True ($unsupportedText.Contains('Unsupported encoding')) 'Unsupported-encoding error was unclear.'
    Assert-True ($unsupportedText.Contains('Convert the CSV to UTF-8')) 'Unsupported-encoding remediation was missing.'

    Write-Host 'DuckDB analysis helper tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

exit 0
