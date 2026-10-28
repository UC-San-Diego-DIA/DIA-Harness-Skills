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
$helper = Join-Path $repositoryRoot 'skills\dia-analyze-local-data\scripts\duckdb_analysis.py'
$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase "dia-duckdb-analysis-$([System.Guid]::NewGuid().ToString('N'))"
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
$safePrefix = $temporaryBase.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $resolvedTestRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Test root '$resolvedTestRoot' is outside '$temporaryBase'."
}

try {
    $root = Join-Path $resolvedTestRoot 'project'
    New-Item -ItemType Directory -Path (Join-Path $root 'data\raw') | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $root 'data\output') | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $root 'scripts') | Out-Null
    Set-Content -LiteralPath (Join-Path $root 'AGENTS.md') -Value '# Project agents' -Encoding utf8
    Set-Content -LiteralPath (Join-Path $root 'scripts\README.md') -Value '# Pipeline manifest' -Encoding utf8

    $source = Join-Path $root 'data\raw\sales.csv'
    $workspace = Join-Path $root 'scratch\analysis\sales'
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
        '--workspace', $workspace,
        '--source', $source
    )
    Assert-True ($setup.action -eq 'created') 'Setup did not report a created workspace.'
    Assert-True ($setup.row_count -eq 3) 'Setup row count is incorrect.'
    Assert-True ($setup.source_format -eq 'csv') 'Setup did not report the CSV format.'
    Assert-True (Test-Path -LiteralPath (Join-Path $workspace 'analysis.duckdb') -PathType Leaf) 'DuckDB database is missing.'
    Assert-True (Test-Path -LiteralPath (Join-Path $workspace 'ANALYSIS.md') -PathType Leaf) 'ANALYSIS.md is missing.'
    Assert-True (Test-Path -LiteralPath (Join-Path $workspace 'queries') -PathType Container) 'Queries folder is missing.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $workspace 'data'))) 'Analysis workspace must not copy the source data.'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $workspace '.gitignore'))) 'Analysis workspace must not contain a .gitignore.'

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
    Invoke-ExpectedFailure @(
        'query',
        '--workspace', $workspace,
        '--question', 'Delete rows',
        '--sql-file', $blockedQueryFile
    ) @('exactly one SELECT')

    $otherSource = Join-Path $root 'data\raw\other.csv'
    'A,B' + [Environment]::NewLine + '1,2' | Set-Content -LiteralPath $otherSource -Encoding utf8 -NoNewline
    "SELECT * FROM read_csv('$($otherSource.Replace("'", "''"))');" |
        Set-Content -LiteralPath $externalQueryFile -Encoding utf8
    $externalOutput = & $Python $helper query --workspace $workspace --question 'Read another file' --sql-file $externalQueryFile 2>&1
    Assert-True ($LASTEXITCODE -eq 2) 'A SELECT reading a different file was not rejected.'
    $externalText = $externalOutput -join [Environment]::NewLine
    Assert-True ($externalText.Contains('DuckDB query failed') -or $externalText.Contains('allowed_paths') -or $externalText.Contains('extension')) "External-file rejection was unclear: $externalText"
    Assert-True ((Get-ChildItem -LiteralPath (Join-Path $workspace 'queries') -File -Filter '*.sql').Count -eq 2) 'A rejected query was saved.'

    @'
Order ID,Revenue,Region
1,10.50,West
2,,East
3,20.00,West
4,5.00,North
'@ | Set-Content -LiteralPath $source -Encoding utf8 -NoNewline
    Invoke-ExpectedFailure @(
        'query',
        '--workspace', $workspace,
        '--question', 'Stale source',
        '--sql-file', $queryFile
    ) @('changed since this workspace was linked')

    $relink = Invoke-AnalysisHelper @(
        'setup',
        '--workspace', $workspace,
        '--source', $source,
        '--refresh'
    )
    Assert-True ($relink.action -eq 'relinked') 'Re-link did not report success.'
    Assert-True ($relink.row_count -eq 4) 'Re-link row count is incorrect.'
    Assert-True ((Get-ChildItem -LiteralPath (Join-Path $workspace 'queries') -File -Filter '*.sql').Count -eq 2) 'Re-link did not preserve query history.'
    $analysisText = Get-Content -Raw -LiteralPath (Join-Path $workspace 'ANALYSIS.md')
    Assert-True ($analysisText.Contains('order_id')) 'Normalized header mapping is missing.'
    Assert-True ($analysisText.Contains('superseded')) 'Source history did not mark the prior link.'

    $duplicateSource = Join-Path $root 'data\raw\duplicate.csv'
    $duplicateWorkspace = Join-Path $root 'scratch\analysis\duplicate'
    @'
Name,name
one,two
'@ | Set-Content -LiteralPath $duplicateSource -Encoding utf8 -NoNewline
    Invoke-ExpectedFailure @(
        'setup',
        '--workspace', $duplicateWorkspace,
        '--source', $duplicateSource
    ) @('duplicate headers')

    $quotedSource = Join-Path $root 'data\raw\quoted.csv'
    $quotedWorkspace = Join-Path $root 'scratch\analysis\quoted'
    @'
"Customer, Name","He said ""Hi"""
"Palacios, Iris","She said ""Hello"""
'@ | Set-Content -LiteralPath $quotedSource -Encoding utf8 -NoNewline
    $quotedSetup = Invoke-AnalysisHelper @(
        'setup',
        '--workspace', $quotedWorkspace,
        '--source', $quotedSource
    )
    Assert-True ($quotedSetup.columns[0].original_name -eq 'Customer, Name') 'Quoted comma in a header was parsed incorrectly.'
    Assert-True ($quotedSetup.columns[1].original_name -eq 'He said "Hi"') 'Doubled quote in a header was parsed incorrectly.'
    Assert-True ($quotedSetup.columns[0].sql_name -eq 'customer_name') 'Quoted header was not normalized.'

    $utf8BomSource = Join-Path $root 'data\raw\utf8-bom.csv'
    $utf8BomWorkspace = Join-Path $root 'scratch\analysis\utf8-bom'
    $utf8BomEncoding = [System.Text.UTF8Encoding]::new($true)
    [System.IO.File]::WriteAllText($utf8BomSource, "Café,Amount`r`nEast,10`r`n", $utf8BomEncoding)
    $utf8BomSetup = Invoke-AnalysisHelper @(
        'setup',
        '--workspace', $utf8BomWorkspace,
        '--source', $utf8BomSource
    )
    Assert-True ($utf8BomSetup.columns[0].sql_name -eq 'cafe') 'UTF-8 BOM header was not normalized.'

    $utf16Source = Join-Path $root 'data\raw\utf16.csv'
    $utf16Workspace = Join-Path $root 'scratch\analysis\utf16'
    $utf16Encoding = [System.Text.UnicodeEncoding]::new($false, $true)
    [System.IO.File]::WriteAllText($utf16Source, "Café,Amount`r`nEast,10`r`n", $utf16Encoding)
    $utf16Setup = Invoke-AnalysisHelper @(
        'setup',
        '--workspace', $utf16Workspace,
        '--source', $utf16Source,
        '--encoding', 'UTF_16'
    )
    Assert-True ($utf16Setup.columns[0].sql_name -eq 'cafe') 'UTF-16 header was not normalized.'
    Assert-True ($utf16Setup.read_options.encoding -eq 'utf-16') 'UTF-16 alias was not canonicalized.'

    $latin1Source = Join-Path $root 'data\raw\latin1.csv'
    $latin1Workspace = Join-Path $root 'scratch\analysis\latin1'
    $latin1Encoding = [System.Text.Encoding]::GetEncoding('iso-8859-1')
    [System.IO.File]::WriteAllText($latin1Source, "Café,Amount`r`nEast,10`r`n", $latin1Encoding)
    $latin1Setup = Invoke-AnalysisHelper @(
        'setup',
        '--workspace', $latin1Workspace,
        '--source', $latin1Source,
        '--encoding', 'iso-8859-1'
    )
    Assert-True ($latin1Setup.columns[0].sql_name -eq 'cafe') 'Latin-1 header was not normalized.'
    Assert-True ($latin1Setup.read_options.encoding -eq 'latin-1') 'Latin-1 alias was not canonicalized.'

    $unsupportedWorkspace = Join-Path $root 'scratch\analysis\unsupported-encoding'
    Invoke-ExpectedFailure @(
        'setup',
        '--workspace', $unsupportedWorkspace,
        '--source', $source,
        '--encoding', 'cp1252'
    ) @('Unsupported encoding', 'Convert the CSV to UTF-8')

    $outsideSource = Join-Path $root 'scratch\outside.csv'
    'A' + [Environment]::NewLine + '1' | Set-Content -LiteralPath $outsideSource -Encoding utf8 -NoNewline
    $outsideWorkspace = Join-Path $root 'scratch\analysis\outside'
    Invoke-ExpectedFailure @(
        'setup',
        '--workspace', $outsideWorkspace,
        '--source', $outsideSource
    ) @('data\raw or data\output')

    $missingRoot = Join-Path $resolvedTestRoot 'not-a-workspace'
    New-Item -ItemType Directory -Path $missingRoot | Out-Null
    $missingRootWorkspace = Join-Path $missingRoot 'scratch\analysis\sales'
    Invoke-ExpectedFailure @(
        'setup',
        '--workspace', $missingRootWorkspace,
        '--source', $source
    ) @('not a data-analysis workspace')

    $genXlsx = Join-Path $resolvedTestRoot 'gen_xlsx.py'
    @'
import sys
import zipfile


def cell(column, row, value, is_number):
    reference = f"{column}{row}"
    if is_number:
        return f'<c r="{reference}"><v>{value}</v></c>'
    return f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>'


rows = [("Region", "Revenue"), ("West", 10.5), ("East", 20.0), ("North", 5.0)]
sheet_rows = []
for index, (first, second) in enumerate(rows, start=1):
    numeric = index > 1
    sheet_rows.append(
        f'<row r="{index}">{cell("A", index, first, False)}{cell("B", index, second, numeric)}</row>'
    )
sheet_xml = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<sheetData>' + "".join(sheet_rows) + '</sheetData></worksheet>'
)
workbook_xml = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="Regions" sheetId="1" r:id="rId1"/></sheets></workbook>'
)
workbook_rels = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
    'Target="worksheets/sheet1.xml"/></Relationships>'
)
content_types = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '</Types>'
)
root_rels = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="xl/workbook.xml"/></Relationships>'
)
target = sys.argv[1]
with zipfile.ZipFile(target, "w") as archive:
    archive.writestr("[Content_Types].xml", content_types)
    archive.writestr("_rels/.rels", root_rels)
    archive.writestr("xl/workbook.xml", workbook_xml)
    archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
    archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
print("generated")
'@ | Set-Content -LiteralPath $genXlsx -Encoding utf8

    $xlsxSource = Join-Path $root 'data\output\regions.xlsx'
    $xlsxPathArgument = $xlsxSource.Replace('\', '/')
    & $Python $genXlsx $xlsxPathArgument
    Assert-True ($LASTEXITCODE -eq 0) 'Could not generate the xlsx test workbook.'

    $inspect = Invoke-AnalysisHelper @(
        'inspect',
        '--source', $xlsxSource
    )
    Assert-True ($inspect.format -eq 'xlsx') 'Inspect did not report the xlsx format.'
    Assert-True ($inspect.sheets.Count -ge 1) 'Inspect did not list workbook sheets.'
    $sheetName = $inspect.sheets[0]

    $xlsxWorkspace = Join-Path $root 'scratch\analysis\regions'
    $xlsxSetupOutput = & $Python $helper setup --workspace $xlsxWorkspace --source $xlsxSource --sheet $sheetName 2>&1
    if ($LASTEXITCODE -ne 0) {
        $setupText = $xlsxSetupOutput -join [Environment]::NewLine
        Assert-True $setupText.Contains('--install-excel-extension') "xlsx setup failed without the extension hint: $setupText"
        $xlsxSetup = Invoke-AnalysisHelper @(
            'setup',
            '--workspace', $xlsxWorkspace,
            '--source', $xlsxSource,
            '--sheet', $sheetName,
            '--install-excel-extension'
        )
    }
    else {
        $xlsxSetup = $xlsxSetupOutput | ConvertFrom-Json
    }
    Assert-True ($xlsxSetup.action -eq 'created') 'xlsx setup did not report a created workspace.'
    Assert-True ($xlsxSetup.row_count -eq 3) 'xlsx setup row count is incorrect.'
    Assert-True ($xlsxSetup.source_format -eq 'xlsx') 'xlsx setup did not report the format.'
    Assert-True ($xlsxSetup.sheet -eq $sheetName) 'xlsx setup did not record the sheet.'

    'SELECT region, sum(revenue) AS revenue FROM dataset GROUP BY region ORDER BY region;' |
        Set-Content -LiteralPath $queryFile -Encoding utf8
    $xlsxQuery = Invoke-AnalysisHelper @(
        'query',
        '--workspace', $xlsxWorkspace,
        '--question', 'What is revenue by region from the workbook?',
        '--sql-file', $queryFile
    )
    Assert-True ($xlsxQuery.returned_rows -eq 3) 'xlsx query returned an unexpected row count.'

    $wrongSheetWorkspace = Join-Path $root 'scratch\analysis\wrong-sheet'
    Invoke-ExpectedFailure @(
        'setup',
        '--workspace', $wrongSheetWorkspace,
        '--source', $xlsxSource,
        '--sheet', 'Nope'
    ) @('not found in the workbook')

    Write-Host 'DuckDB analysis helper tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

exit 0
