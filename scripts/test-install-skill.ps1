[CmdletBinding()]
param()

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
$testRoot = Join-Path $temporaryBase "dia-harness-skills-$([System.Guid]::NewGuid().ToString('N'))"
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
$safePrefix = $temporaryBase.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

if (-not $resolvedTestRoot.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Test root '$resolvedTestRoot' is outside '$temporaryBase'."
}

$installer = Join-Path $PSScriptRoot 'install-skill.ps1'
$destination = Join-Path $resolvedTestRoot 'installed-skills'
$whatIfDestination = Join-Path $resolvedTestRoot 'what-if-skills'

try {
    $skillsToInstall = @('dia-analyze-local-data', 'dia-clickup-mcp-setup', 'dia-data-model-docs', 'dia-data-model-intake', 'dia-new-data-analysis-workspace', 'dia-process-meeting-transcript', 'dia-setup-business-insights-folder', 'dia-start-my-day', 'dia-transcript-to-process-map', 'dia-transcript-to-project-request-draft')
    foreach ($skillName in $skillsToInstall) {
        & $installer -Skill $skillName -Destination $destination -Force

        $installedSkillPath = Join-Path $destination $skillName
        $installedSkillEntry = Join-Path $installedSkillPath 'SKILL.md'
        Assert-True (Test-Path -LiteralPath $installedSkillEntry -PathType Leaf) "$skillName fresh install did not copy SKILL.md."
    }

    $installedSkill = Join-Path $destination 'dia-clickup-mcp-setup'
    $installedEntry = Join-Path $installedSkill 'SKILL.md'
    $duckdbHelper = Join-Path $destination 'dia-analyze-local-data\scripts\duckdb_analysis.py'
    $projectFolderHelper = Join-Path $destination 'dia-setup-business-insights-folder\scripts\setup_business_insights_folder.ps1'
    $projectAgentsTemplate = Join-Path $destination 'dia-setup-business-insights-folder\assets\project-AGENTS.md'
    $workspaceHelper = Join-Path $destination 'dia-new-data-analysis-workspace\scripts\create_workspace.ps1'
    $workspaceAgentsTemplate = Join-Path $destination 'dia-new-data-analysis-workspace\assets\workspace-AGENTS.md'
    $meetingNoteFormat = Join-Path $destination 'dia-process-meeting-transcript\references\meeting-note-format.md'
    $dailyBriefTemplate = Join-Path $destination 'dia-start-my-day\assets\brief-template.html'
    $dataModelFactsHelper = Join-Path $destination 'dia-data-model-intake\scripts\extract_model_facts.py'
    $dataModelFactsSchema = Join-Path $destination 'dia-data-model-intake\references\model-facts.schema.json'
    $dataModelFactsIntakeContract = Join-Path $destination 'dia-data-model-intake\references\model-facts-contract.md'
    $dataModelFactsContract = Join-Path $destination 'dia-data-model-docs\references\model-facts-contract.md'
    $dataModelDocumentationTemplates = Join-Path $destination 'dia-data-model-docs\references\documentation-templates.md'
    Assert-True (Test-Path -LiteralPath $duckdbHelper -PathType Leaf) 'DuckDB helper script was not installed.'
    Assert-True (Test-Path -LiteralPath $projectFolderHelper -PathType Leaf) 'Project-folder helper script was not installed.'
    Assert-True (Test-Path -LiteralPath $projectAgentsTemplate -PathType Leaf) 'Project AGENTS template was not installed.'
    Assert-True (Test-Path -LiteralPath $workspaceHelper -PathType Leaf) 'Workspace helper script was not installed.'
    Assert-True (Test-Path -LiteralPath $workspaceAgentsTemplate -PathType Leaf) 'Workspace AGENTS template was not installed.'
    Assert-True (Test-Path -LiteralPath $meetingNoteFormat -PathType Leaf) 'Meeting-note format reference was not installed.'
    Assert-True (Test-Path -LiteralPath $dailyBriefTemplate -PathType Leaf) 'Start My Day HTML template was not installed.'
    Assert-True (Test-Path -LiteralPath $dataModelFactsHelper -PathType Leaf) 'Data-model facts helper was not installed.'
    Assert-True (Test-Path -LiteralPath $dataModelFactsSchema -PathType Leaf) 'Model-facts JSON Schema was not installed.'
    Assert-True (Test-Path -LiteralPath $dataModelFactsIntakeContract -PathType Leaf) 'Model-facts intake contract was not installed.'
    Assert-True (Test-Path -LiteralPath $dataModelFactsContract -PathType Leaf) 'Model-facts contract was not installed.'
    Assert-True (Test-Path -LiteralPath $dataModelDocumentationTemplates -PathType Leaf) 'Data-model documentation templates were not installed.'

    $marker = 'installer-backup-test-marker'
    Set-Content -LiteralPath $installedEntry -Value $marker

    & $installer -Skill dia-clickup-mcp-setup -Destination $destination -Force

    $currentText = Get-Content -Raw -LiteralPath $installedEntry
    Assert-True (-not $currentText.Contains($marker)) 'Replacement did not install the source copy.'

    $backups = @(Get-ChildItem -LiteralPath $destination -Directory -Filter 'dia-clickup-mcp-setup.backup-*')
    Assert-True ($backups.Count -eq 1) 'Replacement did not create exactly one backup.'

    $backupText = Get-Content -Raw -LiteralPath (Join-Path $backups[0].FullName 'SKILL.md')
    Assert-True ($backupText.Contains($marker)) 'Backup does not contain the replaced copy.'

    & $installer -Skill dia-analyze-local-data -Destination $whatIfDestination -Force -WhatIf
    Assert-True (-not (Test-Path -LiteralPath $whatIfDestination)) 'WhatIf created a destination directory.'

    $allDestination = Join-Path $resolvedTestRoot 'all-skills'
    & $installer -All -Destination $allDestination -Force

    $sourceSkillDirectories = @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '..\skills') -Directory)
    Assert-True ($sourceSkillDirectories.Count -gt 0) 'No source skill directories found for the -All test.'
    foreach ($sourceSkillDirectory in $sourceSkillDirectories) {
        $installedAllEntry = Join-Path $allDestination "$($sourceSkillDirectory.Name)\SKILL.md"
        Assert-True (Test-Path -LiteralPath $installedAllEntry -PathType Leaf) "$($sourceSkillDirectory.Name) was not installed by -All."
    }

    $conflictRejected = $false
    try {
        & $installer -All -Skill dia-start-my-day -Destination $allDestination -Force | Out-Null
    }
    catch {
        $conflictRejected = $true
    }
    Assert-True $conflictRejected 'Installer did not reject -Skill combined with -All.'

    $statusDestination = Join-Path $resolvedTestRoot 'status-skills'
    & $installer -Status production,testing -Destination $statusDestination -Force

    $expectedStatusSkills = @(
        'dia-analyze-local-data',
        'dia-clickup-mcp-setup',
        'dia-data-model-docs',
        'dia-data-model-intake',
        'dia-data-model-profiler',
        'dia-new-data-analysis-workspace',
        'dia-start-my-day',
        'dia-transcript-to-meeting-notes',
        'dia-transcript-to-process-map',
        'dia-transcript-to-project-request-draft',
        'dia-transcript-to-requirements'
    )
    foreach ($expectedSkill in $expectedStatusSkills) {
        $installedStatusEntry = Join-Path $statusDestination "$expectedSkill\SKILL.md"
        Assert-True (Test-Path -LiteralPath $installedStatusEntry -PathType Leaf) "$expectedSkill was not installed by -Status production,testing."
    }

    foreach ($unexpectedSkill in @(
        'dia-process-meeting-transcript',
        'dia-setup-business-insights-folder'
    )) {
        $unexpectedPath = Join-Path $statusDestination $unexpectedSkill
        Assert-True (-not (Test-Path -LiteralPath $unexpectedPath)) "$unexpectedSkill must not be installed by -Status production,testing."
    }

    foreach ($conflictingArguments in @(
        @{ Status = 'production'; Skill = 'dia-start-my-day' },
        @{ Status = 'production'; All = $true }
    )) {
        $conflictRejected = $false
        try {
            & $installer @conflictingArguments -Destination $statusDestination -Force | Out-Null
        }
        catch {
            $conflictRejected = $true
        }
        Assert-True $conflictRejected 'Installer did not reject conflicting selection parameters.'
    }

    $invalidStatusRejected = $false
    try {
        & $installer -Status beta -Destination $statusDestination -Force | Out-Null
    }
    catch {
        $invalidStatusRejected = $true
    }
    Assert-True $invalidStatusRejected 'Installer did not reject an unknown lifecycle status.'

    Write-Host 'Installer tests passed.'
}
finally {
    if (Test-Path -LiteralPath $resolvedTestRoot) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}

