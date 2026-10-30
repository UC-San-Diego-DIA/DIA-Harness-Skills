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

$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testRoot = Join-Path $temporaryBase "dia-workbook-intake-$([System.Guid]::NewGuid().ToString('N'))"
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
$safePrefix = $temporaryBase.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $resolvedTestRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Test root '$resolvedTestRoot' is outside '$temporaryBase'."
}

try {
    New-Item -ItemType Directory -Path $resolvedTestRoot | Out-Null

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    $extractor = Join-Path $repositoryRoot 'skills\dia-tableau-workbook-intake\scripts\extract_workbook_facts.py'
    Assert-True (Test-Path -LiteralPath $extractor -PathType Leaf) 'Workbook facts extractor script is missing.'

    $workbookXml = @'
<?xml version='1.0' encoding='utf-8' ?>
<workbook original-version='18.1' source-build='2025.1.7 (20251.25.0825.1650)' source-platform='win' version='18.1'>
  <repository-location derived-from='https://tableau.example.com/workbooks/Example?rev=1.0' id='Example' path='/workbooks' revision='1.0' />
  <datasources>
    <datasource hasconnection='false' inline='true' name='Parameters' version='18.1'>
      <column caption='Segment Performance' datatype='string' name='[Parameter 1]' param-domain-type='list' role='measure' type='nominal' value='&quot;Location Name&quot;'>
        <calculation class='tableau' formula='&quot;Location Name&quot;' />
        <members>
          <member value='&quot;Location Name&quot;' />
          <member value='&quot;POS&quot;' />
        </members>
      </column>
    </datasource>
    <datasource caption='Example-Transactions' hasconnection='false' name='sqlproxy.example' version='18.1'>
      <column caption='Location Name' datatype='string' name='[LocationName]' role='dimension' type='nominal' />
      <column caption='Current FYTD Sales' datatype='real' name='[Calculation_1]' role='measure' type='quantitative'>
        <calculation class='tableau' formula='IF [Fiscal Year] = [Current FY] THEN [PaymentAmount] END' />
      </column>
    </datasource>
  </datasources>
  <worksheets>
    <worksheet name='KPI Card'>
      <layout-options>
        <title>
          <formatted-text>
            <run bold='true'>Total Sales</run>
            <run>&#198;&#10;</run>
            <run fontsize='10'>How much revenue?</run>
          </formatted-text>
        </title>
      </layout-options>
      <table>
        <view>
          <datasources>
            <datasource caption='Example-Transactions' name='sqlproxy.example' />
          </datasources>
          <datasource-dependencies datasource='sqlproxy.example'>
            <column caption='Current FYTD Sales' datatype='real' name='[Calculation_1]' role='measure' type='quantitative'>
              <calculation class='tableau' formula='IF [Fiscal Year] = [Current FY] THEN [PaymentAmount] END' />
            </column>
          </datasource-dependencies>
          <filters>
            <filter class='categorical' column='[sqlproxy.example].[LocationName]' />
          </filters>
          <panes>
            <pane>
              <mark class='Automatic' />
            </pane>
          </panes>
          <rows />
          <cols />
        </view>
      </table>
      <simple-id uuid='{11111111-1111-1111-1111-111111111111}' />
    </worksheet>
    <worksheet name='Sales by Location'>
      <layout-options>
        <title>
          <formatted-text>
            <run>Sales by Location</run>
          </formatted-text>
        </title>
      </layout-options>
      <table>
        <view>
          <datasources>
            <datasource caption='Example-Transactions' name='sqlproxy.example' />
          </datasources>
          <datasource-dependencies datasource='sqlproxy.example' />
          <panes>
            <pane>
              <mark class='bar' />
              <encodings>
                <encoding attr='color' field='[sqlproxy.example].[LocationName]' />
              </encodings>
            </pane>
          </panes>
          <rows>[sqlproxy.example].[LocationName]</rows>
          <cols>[sqlproxy.example].[PaymentAmount]</cols>
        </view>
      </table>
      <simple-id uuid='{22222222-2222-2222-2222-222222222222}' />
    </worksheet>
    <worksheet name='Sheet 15'>
      <table>
        <view>
          <datasources>
            <datasource caption='Example-Transactions' name='sqlproxy.example' />
          </datasources>
        </view>
      </table>
      <simple-id uuid='{33333333-3333-3333-3333-333333333333}' />
    </worksheet>
  </worksheets>
  <dashboards>
    <dashboard name='Example Overview'>
      <layout-options>
        <title>
          <formatted-text>
            <run bold='true'>Example Overview</run>
            <run>&#198;&#10;</run>
            <run>Sample caveat.</run>
          </formatted-text>
        </title>
      </layout-options>
      <size maxheight='1200' maxwidth='1200' minheight='1200' minwidth='1200' sizing-mode='fixed' />
      <datasources>
        <datasource caption='Example-Transactions' name='sqlproxy.example' />
      </datasources>
      <zones>
        <zone h='100000' id='12' w='100000' x='0' y='0'>
          <zone h='50000' id='13' type-v2='layout-flow' param='horz' w='50000' x='0' y='0'>
            <zone h='5000' id='14' name='KPI Card' show-title='false' w='20000' x='0' y='0' />
            <zone h='5000' id='15' name='Sales by Location' show-title='false' w='20000' x='20000' y='0' />
          </zone>
          <zone h='2000' id='16' mode='checkdropdown' name='KPI Card' param='[sqlproxy.example].[LocationName]' show-apply='true' type-v2='filter' values='relevant' w='20000' x='0' y='50000' />
          <zone h='2000' id='18' mode='checkdropdown' name='Sales by Location' param='[sqlproxy.example].[Uncaptioned Thing ]' show-apply='true' type-v2='filter' values='relevant' w='20000' x='0' y='70000' />
          <zone h='2000' id='17' caption='Segment' param='[Parameters].[Parameter 1]' type-v2='paramctrl' w='20000' x='20000' y='50000' />
        </zone>
      </zones>
      <simple-id uuid='{44444444-4444-4444-4444-444444444444}' />
    </dashboard>
  </dashboards>
</workbook>
'@

    $twbPath = Join-Path $resolvedTestRoot 'Example.twb'
    Set-Content -LiteralPath $twbPath -Value $workbookXml -Encoding UTF8

    $twbxPath = Join-Path $resolvedTestRoot 'Example.twbx'
    Compress-Archive -LiteralPath $twbPath -DestinationPath $twbxPath

    $twbOutput = Join-Path $resolvedTestRoot 'workbook-facts-twb.yaml'
    $summaryJson = & $Python $extractor --input $twbPath --output $twbOutput
    Assert-True ($LASTEXITCODE -eq 0) "Bare .twb extraction failed with exit code $LASTEXITCODE."
    $summary = $summaryJson | ConvertFrom-Json
    Assert-True ($summary.container -eq 'twb') "Unexpected container kind: $($summary.container)."
    Assert-True ($summary.dashboards -eq 1) 'Summary did not count one dashboard.'
    Assert-True ($summary.worksheets -eq 3) 'Summary did not count three worksheets.'
    Assert-True ($summary.orphan_sheets -eq 1) 'Summary did not count one orphan sheet.'
    Assert-True ($summary.parameters -eq 1) 'Summary did not count one parameter.'

    $twbFacts = Get-Content -Raw -LiteralPath $twbOutput
    foreach ($needle in @(
        'schema_version: 2',
        'provenance:',
        'run_id:',
        'input_sha256',
        'extracted_at:',
        'completeness:',
        'anomalies:',
        'ORPHAN_SHEET',
        'status: complete',
        'name: Example Overview',
        'title_text: Example Overview | Sample caveat.',
        'title_text: "Total Sales | How much revenue?"',
        'caption: Segment Performance',
        'IF [Fiscal Year] = [Current FY] THEN [PaymentAmount] END',
        '- KPI Card',
        '- Sales by Location',
        'orphan_sheets:',
        '- Sheet 15',
        'field: "[sqlproxy.example].[LocationName]"',
        'field_caption: Location Name',
        'column_caption: Location Name',
        'field_caption: Uncaptioned Thing'
    )) {
        Assert-True ($twbFacts.Contains($needle)) "Expected '$needle' in the bare .twb facts output."
    }

    $twbxOutput = Join-Path $resolvedTestRoot 'workbook-facts-twbx.yaml'
    & $Python $extractor --input $twbxPath --output $twbxOutput | Out-Null
    Assert-True ($LASTEXITCODE -eq 0) "Package extraction failed with exit code $LASTEXITCODE."
    $twbxFacts = Get-Content -Raw -LiteralPath $twbxOutput
    Assert-True ($twbxFacts.Contains('container: twbx')) 'Facts did not record the twbx container.'
    Assert-True ($twbxFacts.Contains('entry: Example.twb')) 'Facts did not record the workbook XML entry.'

    & $Python $extractor --input $twbxPath --output $twbxOutput 2>$null | Out-Null
    Assert-True ($LASTEXITCODE -eq 1) 'Extractor did not refuse to overwrite an existing output.'
    & $Python $extractor --input $twbxPath --output $twbxOutput --replace | Out-Null
    Assert-True ($LASTEXITCODE -eq 0) 'Extractor --replace run failed.'

    $relativeExit = 0
    Push-Location $resolvedTestRoot
    try {
        & $Python $extractor --input 'Example.twb' --output (Join-Path $resolvedTestRoot 'relative.yaml') 2>$null | Out-Null
        $relativeExit = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    Assert-True ($relativeExit -eq 2) "Extractor did not reject relative paths (exit code $relativeExit)."

    $validator = Join-Path $repositoryRoot 'skills\dia-tableau-workbook-intake\scripts\validate_facts.py'
    $migrator = Join-Path $repositoryRoot 'skills\dia-tableau-workbook-intake\scripts\migrate_facts_v1_to_v2.py'

    & $Python $validator --facts $twbOutput | Out-Null
    Assert-True ($LASTEXITCODE -eq 0) "Validator did not accept the extracted v2 facts (exit code $LASTEXITCODE)."

    $v1Facts = Join-Path $resolvedTestRoot 'workbook-facts-v1.yaml'
    Set-Content -LiteralPath $v1Facts -Value @'
schema_version: 1
workbook:
  name: Migration Test
  tableau_version: "18.1"
  source_build: 2025.1.7 (20251.25.0825.1650)
  source_platform: win
  repository_location: ""
extraction:
  container: twb
  entry: ""
  timestamp: 2026-01-01T00:00:00+00:00
  warnings:
    - "dashboard 'Overview' has 2 empty zones"
datasources:
  - name: Parameters
    caption: null
parameters: []
dashboards:
  - name: Overview
    datasources: []
    size: {}
    title_text: Overview
    sheets: []
    layout: []
    filters: []
    legends: []
    parameter_controls: []
    actions: []
worksheets:
  - name: Overview
    title_text: ""
    datasources: []
    rows: []
    cols: []
    calculations: []
    filters: []
    mark_types: []
    encodings: []
derived:
  sheets_on_dashboards: []
  orphan_sheets:
    - Overview
  duplicate_name_groups: []
'@ -Encoding UTF8

    & $Python $validator --facts $v1Facts 2>$null | Out-Null
    Assert-True ($LASTEXITCODE -eq 2) "Validator did not reject the v1 facts file (exit code $LASTEXITCODE)."

    $v2Facts = Join-Path $resolvedTestRoot 'workbook-facts-v2.yaml'
    & $Python $migrator --input $v1Facts --output $v2Facts | Out-Null
    Assert-True ($LASTEXITCODE -eq 0) "Migration failed with exit code $LASTEXITCODE."
    & $Python $migrator --input $v1Facts --output $v2Facts 2>$null | Out-Null
    Assert-True ($LASTEXITCODE -eq 1) 'Migrator did not refuse to overwrite an existing output.'
    $v2Content = Get-Content -Raw -LiteralPath $v2Facts
    foreach ($needle in @(
        'schema_version: 2',
        'input_sha256: null',
        'input_sha256_reason: migrated_from_v1',
        'id: migration-test__dash__overview',
        'id: migration-test__sheet__overview',
        'code: EMPTY_ZONE',
        'status: observed'
    )) {
        Assert-True ($v2Content.Contains($needle)) "Expected '$needle' in the migrated v2 facts output."
    }
    & $Python $validator --facts $v2Facts | Out-Null
    Assert-True ($LASTEXITCODE -eq 0) "Validator did not accept the migrated v2 facts (exit code $LASTEXITCODE)."

    Write-Host 'Workbook intake tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

exit 0
