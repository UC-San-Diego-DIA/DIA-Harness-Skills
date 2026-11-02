[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter()]
    [ValidatePattern('^[a-z0-9]+(?:-[a-z0-9]+)*$')]
    [string[]]$Skill,

    [string]$Destination = (Join-Path $env:USERPROFILE '.tritonai-harness\codex\skills'),

    [string[]]$Status,

    [switch]$All,

    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $repositoryRoot 'skills'
$allowedStatuses = @('production', 'testing', 'development')

if ($All) {
    if ($Skill -or $Status) {
        throw 'Use only one of -Skill, -Status, or -All.'
    }

    $skillsToInstall = @(
        Get-ChildItem -LiteralPath $sourceRoot -Directory |
            Where-Object { (Get-Content -Raw -LiteralPath (Join-Path $_.FullName "SKILL.md")) -notmatch "(?m)^\s+status:\s*archived\s*$" } |
            Sort-Object -Property Name |
            ForEach-Object { $_.Name }
    )

    if ($skillsToInstall.Count -eq 0) {
        throw "No source skills found under '$sourceRoot'."
    }
}
elseif ($Status) {
    if ($Skill) {
        throw 'Use only one of -Skill, -Status, or -All.'
    }

    $requestedStatuses = @(
        $Status |
            ForEach-Object { $_ -split ',' } |
            ForEach-Object { $_.Trim().ToLowerInvariant() } |
            Where-Object { $_ }
    )

    if ($requestedStatuses.Count -eq 0) {
        throw "Specify at least one lifecycle status from: $($allowedStatuses -join ', ')."
    }

    foreach ($requestedStatus in $requestedStatuses) {
        if ($allowedStatuses -notcontains $requestedStatus) {
            throw "Unknown lifecycle status '$requestedStatus'. Allowed values: $($allowedStatuses -join ', ')."
        }
    }

    $skillsToInstall = @()
    foreach ($skillDirectory in (Get-ChildItem -LiteralPath $sourceRoot -Directory | Sort-Object -Property Name)) {
        $entryText = Get-Content -Raw -LiteralPath (Join-Path $skillDirectory.FullName 'SKILL.md')
        $metadataMatch = [regex]::Match($entryText, '(?ms)^metadata:\s*\r?\n(?<block>(?:^[ \t]+[^\r\n]*\r?\n?)+)')
        $skillStatus = ''
        if ($metadataMatch.Success) {
            $statusMatch = [regex]::Match(
                $metadataMatch.Groups['block'].Value,
                "(?m)^[ \t]+status:\s*[""']?(?<value>[^""'\r\n]+)"
            )
            if ($statusMatch.Success) {
                $skillStatus = $statusMatch.Groups['value'].Value.Trim()
            }
        }

        if ($requestedStatuses -contains $skillStatus) {
            $skillsToInstall += $skillDirectory.Name
        }
        elseif ($skillStatus -eq '') {
            Write-Warning "Skipped '$($skillDirectory.Name)': SKILL.md does not declare metadata.status."
        }
    }

    if ($skillsToInstall.Count -eq 0) {
        throw "No source skills match lifecycle status(es): $($requestedStatuses -join ', ')."
    }
}
elseif ($Skill) {
    $skillsToInstall = @($Skill)
}
else {
    throw 'Specify a skill with -Skill <name>, filter with -Status <statuses>, or install every source skill with -All.'
}

$destinationRoot = [System.IO.Path]::GetFullPath($Destination)
$expectedPrefix = $destinationRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

foreach ($currentSkill in $skillsToInstall) {
    $sourceSkill = Join-Path $sourceRoot $currentSkill

    if (-not (Test-Path -LiteralPath (Join-Path $sourceSkill 'SKILL.md') -PathType Leaf)) {
        throw "Source skill '$currentSkill' does not exist at '$sourceSkill'."
    }

    $targetSkill = [System.IO.Path]::GetFullPath((Join-Path $destinationRoot $currentSkill))

    if (-not $targetSkill.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Resolved target '$targetSkill' is outside destination '$destinationRoot'."
    }

    Write-Host "Source:      $sourceSkill"
    Write-Host "Destination: $targetSkill"

    $targetExists = Test-Path -LiteralPath $targetSkill
    if ($targetExists -and -not $Force) {
        $replace = $PSCmdlet.ShouldContinue(
            "Replace '$targetSkill' and keep the current copy as a timestamped backup?",
            "Replace installed skill '$currentSkill'"
        )
        if (-not $replace) {
            Write-Host "Skipped '$currentSkill'. No files changed."
            continue
        }
    }

    if (-not $PSCmdlet.ShouldProcess($targetSkill, "Install source skill '$currentSkill'")) {
        continue
    }

    New-Item -ItemType Directory -Path $destinationRoot -Force | Out-Null

    $stagingSkill = Join-Path $destinationRoot ".$currentSkill.install-$([System.Guid]::NewGuid().ToString('N'))"
    $backupSkill = $null

    try {
        Copy-Item -LiteralPath $sourceSkill -Destination $stagingSkill -Recurse

        # Bundle maintained intake helpers without a second installed skill.
        if ($currentSkill -eq 'dia-tableau-data-dictionary') {
            $intakeScripts = Join-Path $sourceRoot 'dia-tableau-workbook-intake\scripts'
            $bundledScripts = Join-Path $stagingSkill 'scripts\workbook_intake'
            New-Item -ItemType Directory -Path $bundledScripts -Force | Out-Null
            foreach ($helper in @('extract_workbook_facts.py', 'field_metadata.py', 'model_structure.py', 'facts_common.py', 'validate_facts.py', 'schema_check.py', 'yaml_min.py')) {
                Copy-Item -LiteralPath (Join-Path $intakeScripts $helper) -Destination $bundledScripts
            }
            Copy-Item -LiteralPath (Join-Path $repositoryRoot 'docs\shared\workbook-facts.schema.json') -Destination $bundledScripts
        }
        elseif ($currentSkill -eq 'dia-tableau-dataset-intelligence') {
            $dictionaryDependency = Join-Path $stagingSkill 'scripts\dependencies\dia-tableau-data-dictionary'
            New-Item -ItemType Directory -Path (Join-Path $dictionaryDependency 'scripts') -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $dictionaryDependency 'references') -Force | Out-Null
            $dictionarySource = Join-Path $sourceRoot 'dia-tableau-data-dictionary'
            foreach ($helper in @('data_dictionary.py', 'dictionary_enrichment.py', 'prepare_dictionary.py')) {
                Copy-Item -LiteralPath (Join-Path $dictionarySource "scripts\$helper") -Destination (Join-Path $dictionaryDependency 'scripts')
            }
            foreach ($reference in @('data-dictionary.schema.json', 'data-dictionary-v1.schema.json', 'dictionary-guide.md')) {
                Copy-Item -LiteralPath (Join-Path $dictionarySource "references\$reference") -Destination (Join-Path $dictionaryDependency 'references')
            }
            $bundledIntake = Join-Path $dictionaryDependency 'scripts\workbook_intake'
            New-Item -ItemType Directory -Path $bundledIntake -Force | Out-Null
            foreach ($helper in @('extract_workbook_facts.py', 'field_metadata.py', 'model_structure.py', 'facts_common.py', 'validate_facts.py', 'schema_check.py', 'yaml_min.py')) {
                Copy-Item -LiteralPath (Join-Path $sourceRoot "dia-tableau-workbook-intake\scripts\$helper") -Destination $bundledIntake
            }
            Copy-Item -LiteralPath (Join-Path $repositoryRoot 'docs\shared\workbook-facts.schema.json') -Destination $bundledIntake
        }
        elseif ($currentSkill -eq 'dia-tableau-workbook-intake') {
            Copy-Item -LiteralPath (Join-Path $repositoryRoot 'docs\shared\workbook-facts.schema.json') -Destination (Join-Path $stagingSkill 'scripts')
        }

        if (-not (Test-Path -LiteralPath (Join-Path $stagingSkill 'SKILL.md') -PathType Leaf)) {
            throw "Staged skill is missing SKILL.md at '$stagingSkill'."
        }

        if ($targetExists) {
            $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
            $backupSkill = Join-Path $destinationRoot "$currentSkill.backup-$timestamp"
            Move-Item -LiteralPath $targetSkill -Destination $backupSkill
        }

        Move-Item -LiteralPath $stagingSkill -Destination $targetSkill
    }
    catch {
        if ($backupSkill -and (Test-Path -LiteralPath $backupSkill) -and -not (Test-Path -LiteralPath $targetSkill)) {
            Move-Item -LiteralPath $backupSkill -Destination $targetSkill
        }
        throw
    }

    Write-Host "Installed '$currentSkill' at '$targetSkill'."
    if ($backupSkill) {
        Write-Host "Previous copy: $backupSkill"
    }
}

Write-Host 'Restart TritonAI Harness to reload the skill catalog.'
