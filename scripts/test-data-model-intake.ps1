[CmdletBinding()]
param(
    [string]$Python = 'python'
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

function Invoke-Extractor {
    param(
        [string[]]$Arguments,
        [int]$ExpectedExitCode = 0
    )

    $output = & $Python $helper @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $outputText = $output -join [Environment]::NewLine
    if ($exitCode -ne $ExpectedExitCode) {
        throw "Extractor exited $exitCode instead of $ExpectedExitCode. Output: $outputText"
    }

    return $outputText
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$helper = Join-Path $repositoryRoot 'skills\dia-data-model-intake\scripts\extract_model_facts.py'
$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase "dia-data-model-intake-$([System.Guid]::NewGuid().ToString('N'))"
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
$safePrefix = $temporaryBase.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $resolvedTestRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Test root '$resolvedTestRoot' is outside '$temporaryBase'."
}

try {
    New-Item -ItemType Directory -Path $resolvedTestRoot | Out-Null

    $modelPath = Join-Path $resolvedTestRoot 'Example Data Model.xdm'
    $factsPath = Join-Path $resolvedTestRoot 'model-facts.yaml'
    $containerPath = Join-Path $resolvedTestRoot 'Example Data Model.xdm.catalog'
    $containerFactsPath = Join-Path $resolvedTestRoot 'model-facts-container.yaml'

    $modelXml = @'
<?xml version="1.0" encoding="UTF-8"?>
<dataModel version="2.1" defaultDataSourceRef="ExampleDB">
  <description>A synthetic model used only by repository tests.</description>
  <dataProperties>
    <property name="generate_output_format" value="xml" />
  </dataProperties>
  <parameters>
    <parameter name="PAYMENT_YEAR" dataType="xsd:integer" defaultValue="2025">
      <label>Payment year</label>
    </parameter>
  </parameters>
  <dataSets>
    <dataSet name="example_spend" type="SQL">
      <sql dataSourceRef="ExampleDB"><![CDATA[-- Header comment for the synthetic model
WITH payments AS (
    SELECT
        payment_id,
        supplier_id,
        supplier_name,
        payment_date,
        payment_amount,
        invoice_status
    FROM example_payments
    WHERE invoice_status <> 'CANCELLED'
),
year_rollup AS (
    SELECT
        supplier_id,
        supplier_name,
        EXTRACT(YEAR FROM payment_date) AS payment_year,
        SUM(payment_amount) AS payment_total
    FROM payments
    GROUP BY supplier_id, supplier_name, EXTRACT(YEAR FROM payment_date)
),
classification AS (
    SELECT
        supplier_id,
        supplier_name,
        payment_year,
        payment_total,
        CASE supplier_name
            WHEN 'Small Supplier' THEN 'Y'
            ELSE 'N'
        END AS small_business_flag
    FROM year_rollup
)
SELECT
    supplier_id,
    supplier_name,
    payment_year,
    payment_total,
    small_business_flag,
    CASE WHEN payment_total > 100 THEN 'high' ELSE 'low' END flag_bound
FROM classification
WHERE payment_year = :PAYMENT_YEAR
ORDER BY payment_total DESC]]></sql>
    </dataSet>
  </dataSets>
  <dataStructure>
    <group name="G_1" source="example_spend">
      <element name="SUPPLIER_ID" value="SUPPLIER_ID" label="Supplier ID" dataType="xsd:string" breakOrder="1" fieldOrder="1" />
      <element name="SUPPLIER_NAME" value="SUPPLIER_NAME" label="Supplier Name" dataType="xsd:string" fieldOrder="2" />
      <element name="PAYMENT_YEAR" value="PAYMENT_YEAR" label="Payment Year" dataType="xsd:integer" fieldOrder="3" />
      <element name="FLAG_BOUND" value="FLAG_BOUND" label="Flag Bound" dataType="xsd:string" fieldOrder="4" />
    </group>
  </dataStructure>
</dataModel>
'@
    Set-Content -LiteralPath $modelPath -Value $modelXml -NoNewline -Encoding utf8NoBOM

    $relativeFailure = Invoke-Extractor -Arguments @(
        '--input', 'Example Data Model.xdm',
        '--output', $factsPath
    ) -ExpectedExitCode 2
    Assert-True ($relativeFailure.Contains('must be absolute paths')) 'A relative input path was accepted.'

    $summaryText = Invoke-Extractor -Arguments @(
        '--input', $modelPath,
        '--output', $factsPath
    )
    $summary = $summaryText | ConvertFrom-Json
    Assert-True ($summary.model -eq 'Example Data Model') 'The XML model name was not taken from the file stem.'
    Assert-True ($summary.container -eq 'xml-document') 'The XML model was not detected as an XML document.'
    Assert-True ($summary.ctes -eq 3) 'The synthetic model did not produce three CTEs.'
    Assert-True ($summary.source_tables -eq 1) 'The synthetic model did not produce one source table.'
    Assert-True ($summary.output_columns -eq 4) 'The synthetic model did not produce four output columns.'
    Assert-True ($summary.parameters -eq 1) 'The synthetic model did not produce one parameter.'
    Assert-True ($summary.warnings.Count -eq 1) 'The synthetic XML extraction did not produce the AMBIGUOUS_ALIAS_NO_AS note.'
    Assert-True ($summary.warnings[0].code -eq 'AMBIGUOUS_ALIAS_NO_AS') 'The warning code was not AMBIGUOUS_ALIAS_NO_AS.'
    Assert-True ($summary.warnings[0].severity -eq 'info') 'The AMBIGUOUS_ALIAS_NO_AS severity was not info.'

    $facts = Get-Content -Raw -LiteralPath $factsPath
    Assert-True ($facts.Contains('schema_version: 2')) 'The facts schema version is not 2.'
    Assert-True ($facts.Contains('provenance:')) 'The provenance block is missing.'
    Assert-True ($facts.Contains('source_sha256:')) 'The provenance source SHA-256 is missing.'
    Assert-True ($facts.Contains('extracted_at:')) 'The provenance extraction timestamp is missing.'
    Assert-True ($facts.Contains('extractor_version:')) 'The provenance extractor version is missing.'
    Assert-True ($facts.Contains('container: xml-document')) 'The provenance container kind is missing.'
    Assert-True ($facts.Contains('model:')) 'The model facet is missing.'
    Assert-True ($facts.Contains('facet_version: 1')) 'A facet version is missing.'
    Assert-True ($facts.Contains('model_id: mdl_')) 'The model stable ID is missing.'
    Assert-True ($facts.Contains('content_hash:')) 'A dataset content hash is missing.'
    Assert-True ($facts.Contains('run:')) 'The run facet is missing.'
    Assert-True ($facts.Contains('lineage:')) 'The lineage array is missing.'
    Assert-True ($facts.Contains('nullability: not_null')) 'The CASE-nullability descriptor is missing.'
    Assert-True ($facts.Contains('parameter_bindings:')) 'The parameter-binding descriptor is missing.'
    Assert-True ($facts.Contains('name: classification')) 'The classification CTE is missing.'
    Assert-True ($facts.Contains("operand: supplier_name")) 'The CASE operand was not extracted.'
    Assert-True ($facts.Contains('when: "''Small Supplier''"')) 'The CASE WHEN value was not extracted.'
    Assert-True ($facts.Contains('EXTRACT(YEAR FROM payment_date) AS payment_year')) 'The EXTRACT expression was not preserved.'
    Assert-True ($facts.Contains('where: "invoice_status <> ''CANCELLED''"')) 'The WHERE exclusion was not preserved.'
    Assert-True ($facts.Contains('PAYMENT_YEAR')) 'The parameter is missing from the facts.'

    $existingFailure = Invoke-Extractor -Arguments @(
        '--input', $modelPath,
        '--output', $factsPath
    ) -ExpectedExitCode 1
    Assert-True ($existingFailure.Contains('output already exists')) 'An existing output file was accepted without --replace.'
    Assert-True ((Get-Content -Raw -LiteralPath $factsPath).Contains('schema_version: 2')) 'The refusal overwrote the existing facts file.'

    $replacedSummaryText = Invoke-Extractor -Arguments @(
        '--input', $modelPath,
        '--output', $factsPath,
        '--replace'
    )
    $replacedSummary = $replacedSummaryText | ConvertFrom-Json
    Assert-True ($replacedSummary.ctes -eq 3) 'Replacement extraction produced a different CTE count.'

    $metadataJson = '{"ItemName":"Example Data Model.xdm","ItemType":"1","WCProperties":{"Build":"Test Build 2026.1","bip:AUTHOR":"example@example.invalid","bip:MODIFIED":"1735689600000"}}'
    $buildContainer = @(
        "import pathlib, zlib",
        "source = pathlib.Path(r'$modelPath').read_bytes()",
        "metadata = '$metadataJson'.encode('utf-8') + b'\n'",
        "container = metadata + source",
        "pathlib.Path(r'$containerPath').write_bytes(zlib.compress(container))"
    ) -join '; '
    & $Python -c $buildContainer
    if ($LASTEXITCODE -ne 0) {
        throw "Could not build the synthetic .xdm.catalog container."
    }

    $containerSummaryText = Invoke-Extractor -Arguments @(
        '--input', $containerPath,
        '--output', $containerFactsPath
    )
    $containerSummary = $containerSummaryText | ConvertFrom-Json
    Assert-True ($containerSummary.model -eq 'Example Data Model') 'Catalog metadata did not supply the model name.'
    Assert-True ($containerSummary.container -eq 'zlib-archive') 'The zlib container was not detected.'
    Assert-True ($containerSummary.ctes -eq 3) 'The zlib extraction produced a different CTE count.'
    Assert-True ($containerSummary.warnings.Count -eq 1) 'The zlib extraction did not produce the AMBIGUOUS_ALIAS_NO_AS note.'
    Assert-True ($containerSummary.warnings[0].code -eq 'AMBIGUOUS_ALIAS_NO_AS') 'The zlib warning code was not AMBIGUOUS_ALIAS_NO_AS.'

    $containerFacts = Get-Content -Raw -LiteralPath $containerFactsPath
    Assert-True ($containerFacts.Contains('bi_publisher_build: Test Build 2026.1')) 'The catalog build was not extracted.'
    Assert-True ($containerFacts.Contains('author: example@example.invalid')) 'The catalog author was not extracted.'
    Assert-True ($containerFacts.Contains('modified_at: "2025-01-01T00:00:00+00:00"')) 'The catalog modification time was not converted.'

    $migrationHelper = Join-Path $repositoryRoot 'skills\dia-data-model-intake\scripts\migrate_model_facts_v1_to_v2.py'
    $v1FactsPath = Join-Path $resolvedTestRoot 'model-facts-v1.yaml'
    $v2FactsPath = Join-Path $resolvedTestRoot 'model-facts-migrated.yaml'
    $v1Yaml = @'
schema_version: 1
extraction:
  source_file: "NONEXISTENT_SOURCE_PATH"
  container: xml-document
  extracted_at: "2025-01-01T00:00:00+00:00"
model:
  name: Migration Test Model
  description: A synthetic v1 model for migration testing.
  xdm_version: "2.1"
  default_data_source: MigrationDB
  bi_publisher_build: null
  author: null
  modified_at: null
catalog_items: []
data_properties: {}
data_sources:
  - MigrationDB
parameters:
  - name: TEST_YEAR
    dataType: xsd:integer
    defaultValue: "2025"
    label: Test year
value_sets: []
datasets:
  - name: migration_test
    type: SQL
    data_source: MigrationDB
    sql: |-
      SELECT
          region_code,
          CASE region_code
              WHEN 'WEST' THEN 'Y'
              ELSE 'N'
          END is_west
      FROM sales_regions
      WHERE region_code = :TEST_YEAR
bursting: []
output_columns:
  - name: REGION_CODE
    value: REGION_CODE
    label: Region Code
    data_type: xsd:string
    group: G_1
    group_source: migration_test
    break_order: null
    format_mask: null
    field_order: 1
  - name: IS_WEST
    value: IS_WEST
    label: Is West
    data_type: xsd:string
    group: G_1
    group_source: migration_test
    break_order: null
    format_mask: null
    field_order: 2
warnings:
  - select item has no derivable column name
'@
    Set-Content -LiteralPath $v1FactsPath -Value $v1Yaml -NoNewline -Encoding utf8NoBOM

    $migrationOutput = & $Python $migrationHelper --input $v1FactsPath --output $v2FactsPath 2>&1
    $migrationExit = $LASTEXITCODE
    $migrationText = $migrationOutput -join [Environment]::NewLine
    if ($migrationExit -ne 0) {
        throw "Migration helper exited $migrationExit. Output: $migrationText"
    }
    $v2Facts = Get-Content -Raw -LiteralPath $v2FactsPath
    Assert-True ($v2Facts.Contains('schema_version: 2')) 'The migrated facts schema version is not 2.'
    Assert-True ($v2Facts.Contains('migration:')) 'The migration block is missing from the migrated output.'
    Assert-True ($v2Facts.Contains('SOURCE_FILE_UNAVAILABLE')) 'The SOURCE_FILE_UNAVAILABLE warning is missing from the migrated output.'
    Assert-True ($v2Facts.Contains('source_sha256: null')) 'The migrated provenance SHA-256 was not null for an unavailable source file.'
    Assert-True ($v2Facts.Contains('model_id: mdl_')) 'The migrated model stable ID is missing.'
    Assert-True ($v2Facts.Contains('name: Migration Test Model')) 'The migrated model name is missing.'
    Assert-True ($v2Facts.Contains('lineage:')) 'The migrated lineage array is missing.'

    Write-Host 'Data-model intake tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

exit 0
