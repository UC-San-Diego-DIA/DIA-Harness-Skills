[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$skillsRoot = Join-Path $repositoryRoot 'skills'
$errors = [System.Collections.Generic.List[string]]::new()
$testingSkills = [System.Collections.Generic.List[string]]::new()
$developmentSkills = [System.Collections.Generic.List[string]]::new()
$archivedSkills = [System.Collections.Generic.List[string]]::new()
$catalogSkills = [System.Collections.Generic.List[string]]::new()

function Add-ValidationError {
    param([string]$Message)
    $errors.Add($Message)
}

function Get-FrontmatterStatus {
    param([string]$FrontmatterText)
    $metadataMatch = [regex]::Match($FrontmatterText, '(?ms)^metadata:\s*\r?\n(?<block>(?:^[ \t]+[^\r\n]*\r?\n?)+)')
    if ($metadataMatch.Success) {
        $statusMatch = [regex]::Match(
            $metadataMatch.Groups['block'].Value,
            "(?m)^[ \t]+status:\s*[""']?(?<value>[^""'\r\n]+)"
        )
        if ($statusMatch.Success) {
            return $statusMatch.Groups['value'].Value.Trim()
        }
    }
    return ''
}

function Get-RelativePath {
    param([string]$Path)
    return [System.IO.Path]::GetRelativePath($repositoryRoot, $Path)
}

$requiredFiles = @(
    'README.md',
    'AGENTS.md',
    'CONTEXT.md',
    'CONTRIBUTING.md',
    'scripts\install-skill.ps1',
    'scripts\test-install-skill.ps1',
    'scripts\test-setup-business-insights-folder.ps1',
    'scripts\validate-repository.ps1',
    '.github\workflows\validate.yml'
)

foreach ($relativePath in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot $relativePath) -PathType Leaf)) {
        Add-ValidationError "Missing required file: $relativePath"
    }
}

if (-not (Test-Path -LiteralPath $skillsRoot -PathType Container)) {
    Add-ValidationError 'Missing skills directory.'
}
else {
    $skillDirectories = @(Get-ChildItem -LiteralPath $skillsRoot -Directory)
    if ($skillDirectories.Count -eq 0) {
        Add-ValidationError 'The skills directory has no skill packages.'
    }

    foreach ($skillDirectory in $skillDirectories) {
        $skillName = $skillDirectory.Name
        $relativeSkill = Get-RelativePath $skillDirectory.FullName

        if ($skillName -notmatch '^[a-z0-9]+(?:-[a-z0-9]+)*$') {
            Add-ValidationError "Invalid skill folder name: $relativeSkill"
        }

        $entryPath = Join-Path $skillDirectory.FullName 'SKILL.md'
        if (-not (Test-Path -LiteralPath $entryPath -PathType Leaf)) {
            Add-ValidationError "Missing SKILL.md: $relativeSkill"
            continue
        }

        $entryText = Get-Content -Raw -LiteralPath $entryPath
        $frontmatter = [regex]::Match($entryText, '(?s)\A---\r?\n(?<body>.*?)\r?\n---')
        if (-not $frontmatter.Success) {
            Add-ValidationError "$(Get-RelativePath $entryPath): invalid YAML frontmatter"
            continue
        }

        $frontmatterText = $frontmatter.Groups['body'].Value
        $nameMatch = [regex]::Match($frontmatterText, '(?m)^name:\s*["'']?(?<value>[^"''\r\n]+)')
        $descriptionMatch = [regex]::Match($frontmatterText, '(?m)^description:\s*(?<value>.+)$')
        $allowedFrontmatterKeys = @('name', 'description', 'license', 'allowed-tools', 'metadata')
        $frontmatterKeys = @(
            [regex]::Matches($frontmatterText, '(?m)^(?<key>[A-Za-z0-9_-]+):') |
                ForEach-Object { $_.Groups['key'].Value }
        )

        foreach ($frontmatterKey in $frontmatterKeys) {
            if ($allowedFrontmatterKeys -notcontains $frontmatterKey) {
                Add-ValidationError "$(Get-RelativePath $entryPath): unexpected frontmatter key '$frontmatterKey'"
            }
        }

        if (-not $nameMatch.Success -or $nameMatch.Groups['value'].Value.Trim() -ne $skillName) {
            Add-ValidationError "$(Get-RelativePath $entryPath): frontmatter name must equal folder name"
        }
        $metadataMatch = [regex]::Match($frontmatterText, '(?ms)^metadata:\s*\r?\n(?<block>(?:^[ \t]+[^\r\n]*\r?\n?)+)')
        $statusText = ''
        if ($metadataMatch.Success) {
            $statusMatch = [regex]::Match(
                $metadataMatch.Groups['block'].Value,
                "(?m)^[ \t]+status:\s*[""']?(?<value>[^""'\r\n]+)"
            )
            if ($statusMatch.Success) {
                $statusText = $statusMatch.Groups['value'].Value.Trim()
            }
        }
        if ($statusText -eq '') {
            Add-ValidationError "$(Get-RelativePath $entryPath): frontmatter metadata.status is missing"
        }
        elseif ($statusText -notin @('development', 'testing', 'production', 'archived')) {
            Add-ValidationError "$(Get-RelativePath $entryPath): frontmatter metadata.status must be 'development', 'testing', 'production', or 'archived', found '$statusText'"
        }
        elseif ($statusText -eq 'archived') {
            $archivedSkills.Add($skillName)
        }
        elseif ($statusText -eq 'testing') {
            $testingSkills.Add($skillName)
        }
        elseif ($statusText -eq 'development') {
            $developmentSkills.Add($skillName)
        }
        elseif ($statusText -eq 'production') {
            $catalogSkills.Add($skillName)
        }
        if (-not $descriptionMatch.Success -or [string]::IsNullOrWhiteSpace($descriptionMatch.Groups['value'].Value)) {
            Add-ValidationError "$(Get-RelativePath $entryPath): missing description"
        }
        else {
            $description = $descriptionMatch.Groups['value'].Value.Trim().Trim('"', "'")
            if ($description.Length -gt 1024) {
                Add-ValidationError "$(Get-RelativePath $entryPath): description exceeds 1024 characters"
            }
            if ($description.Contains('<') -or $description.Contains('>')) {
                Add-ValidationError "$(Get-RelativePath $entryPath): description contains an angle bracket"
            }
            if ($description.StartsWith('[TODO:')) {
                Add-ValidationError "$(Get-RelativePath $entryPath): description contains a TODO placeholder"
            }
        }
        if ($skillName.Length -gt 64) {
            Add-ValidationError "$(Get-RelativePath $entryPath): skill name exceeds 64 characters"
        }
        if ($entryText -match '(?m)^[ ]{0,3}\[TODO:[^\r\n]*\][ \t]*$') {
            Add-ValidationError "$(Get-RelativePath $entryPath): instructions contain a TODO placeholder"
        }

        $metadataPath = Join-Path $skillDirectory.FullName 'agents\openai.yaml'
        if (Test-Path -LiteralPath $metadataPath -PathType Leaf) {
            $metadataText = Get-Content -Raw -LiteralPath $metadataPath
            $expectedInvocation = '$' + $skillName
            if (-not $metadataText.Contains($expectedInvocation)) {
                Add-ValidationError "$(Get-RelativePath $metadataPath): default prompt must mention $expectedInvocation"
            }
        }
    }
}

$indexPagePath = Join-Path $repositoryRoot 'docs\index.html'
$indexPageText = if (Test-Path -LiteralPath $indexPagePath -PathType Leaf) { Get-Content -Raw -LiteralPath $indexPagePath } else { '' }
$playbooksRoot = Join-Path $repositoryRoot 'playbooks'
$readmePath = Join-Path $repositoryRoot 'README.md'
$readmeText = if (Test-Path -LiteralPath $readmePath -PathType Leaf) { Get-Content -Raw -LiteralPath $readmePath } else { '' }
if (Test-Path -LiteralPath $playbooksRoot -PathType Container) {
    $playbookFiles = @(Get-ChildItem -LiteralPath $playbooksRoot -File -Filter '*.md')
    foreach ($playbookFile in $playbookFiles) {
        $playbookName = $playbookFile.BaseName
        $playbookLink = "playbooks/$($playbookName).md"
        $playbookText = Get-Content -Raw -LiteralPath $playbookFile.FullName
        $playbookFrontmatter = [regex]::Match($playbookText, '(?s)\A---\r?\n(?<body>.*?)\r?\n---')
        if (-not $playbookFrontmatter.Success) {
            Add-ValidationError "$($playbookFile.Name): invalid YAML frontmatter"
            continue
        }

        $playbookFrontmatterText = $playbookFrontmatter.Groups['body'].Value
        $playbookNameMatch = [regex]::Match($playbookFrontmatterText, '(?m)^name:\s*(?<value>.+)$')
        if (-not $playbookNameMatch.Success -or $playbookNameMatch.Groups['value'].Value.Trim() -ne $playbookName) {
            Add-ValidationError "$($playbookFile.Name): frontmatter name must equal the file base name"
        }
        $playbookPatternMatch = [regex]::Match($playbookFrontmatterText, '(?m)^pattern:\s*(?<value>.+)$')
        if (-not $playbookPatternMatch.Success -or $playbookPatternMatch.Groups['value'].Value.Trim() -notin @('pipeline', 'fan-out')) {
            Add-ValidationError "$($playbookFile.Name): frontmatter pattern must be 'pipeline' or 'fan-out'"
        }

        $playbookStatus = Get-FrontmatterStatus $playbookFrontmatterText
        if ($playbookStatus -notin @('development', 'testing', 'production')) {
            Add-ValidationError "$($playbookFile.Name): frontmatter metadata.status must be 'development', 'testing', or 'production', found '$playbookStatus'"
            continue
        }

        $playbookSkills = @(
            [regex]::Matches($playbookText, '\$dia-[a-z0-9]+(?:-[a-z0-9]+)*') |
                ForEach-Object { $_.Value.TrimStart('$') } |
                Select-Object -Unique
        )
        $playbookSkillStatuses = @{}
        $derivedStatus = 'production'
        foreach ($playbookSkill in $playbookSkills) {
            $playbookSkillEntryPath = Join-Path $skillsRoot "$playbookSkill\SKILL.md"
            if (-not (Test-Path -LiteralPath $playbookSkillEntryPath -PathType Leaf)) {
                Add-ValidationError "$($playbookFile.Name): referenced skill '$playbookSkill' does not exist under skills/"
                $playbookSkillStatuses[$playbookSkill] = 'development'
                $derivedStatus = 'development'
                continue
            }
            $playbookSkillEntryText = Get-Content -Raw -LiteralPath $playbookSkillEntryPath
            $playbookSkillFrontmatter = [regex]::Match($playbookSkillEntryText, '(?s)\A---\r?\n(?<body>.*?)\r?\n---')
            $playbookSkillStatus = if ($playbookSkillFrontmatter.Success) { Get-FrontmatterStatus $playbookSkillFrontmatter.Groups['body'].Value } else { '' }
            if ($playbookSkillStatus -notin @('development', 'testing', 'production', 'archived')) {
                Add-ValidationError "$($playbookFile.Name): referenced skill '$playbookSkill' has no valid metadata.status"
                $playbookSkillStatus = 'development'
            }
            $playbookSkillStatuses[$playbookSkill] = $playbookSkillStatus
            if ($playbookSkillStatus -eq 'archived') {
                Add-ValidationError "$($playbookFile.Name): archived skill '$playbookSkill' cannot be connected to a playbook"
                $derivedStatus = 'development'
            }
            elseif ($playbookSkillStatus -eq 'development') {
                $derivedStatus = 'development'
            }
            elseif ($playbookSkillStatus -eq 'testing' -and $derivedStatus -eq 'production') {
                $derivedStatus = 'testing'
            }
        }
        if ($playbookStatus -ne $derivedStatus) {
            Add-ValidationError "$($playbookFile.Name): frontmatter status '$playbookStatus' does not match the status derived from its connected skills ('$derivedStatus')"
        }

        $playbookBody = $playbookText.Substring($playbookFrontmatter.Index + $playbookFrontmatter.Length)
        $playbookStatusLine = [regex]::Match($playbookBody, '(?m)^Status:\s*(?<value>.+)$')
        if (-not $playbookStatusLine.Success -or -not $playbookStatusLine.Groups['value'].Value.Contains($playbookStatus)) {
            Add-ValidationError "$($playbookFile.Name): body must declare a 'Status:' line matching '$playbookStatus'"
        }

        if ($indexPageText -and -not $indexPageText.Contains($playbookLink)) {
            Add-ValidationError "docs/index.html: playbook '$playbookName' has no card linking to $playbookLink"
        }
        if ($readmeText -and -not $readmeText.Contains($playbookLink)) {
            Add-ValidationError "README.md: playbook '$playbookName' is not listed"
        }
        if ($readmeText) {
            $readmeEntryPattern = '(?m)^\s*-\s*\[[^\]]*\]\(playbooks/' + [regex]::Escape($playbookName) + '\.md\)(?<rest>[^\r\n]*)'
            $readmeEntry = [regex]::Match($readmeText, $readmeEntryPattern)
            if (-not $readmeEntry.Success) {
                Add-ValidationError "README.md: playbook '$playbookName' has no list entry"
            }
            elseif (-not $readmeEntry.Groups['rest'].Value.Contains("*($playbookStatus)*")) {
                Add-ValidationError "README.md: playbook '$playbookName' entry must be marked *($playbookStatus)*"
            }
        }
        if ($indexPageText) {
            $playbookCards = [regex]::Matches($indexPageText, '(?s)<article class="pb[^"]*">(?<body>.*?)</article>')
            $playbookCard = $playbookCards | Where-Object { $_.Groups['body'].Value.Contains($playbookLink) } | Select-Object -First 1
            if (-not $playbookCard) {
                Add-ValidationError "docs/index.html: playbook '$playbookName' has no card article containing $playbookLink"
            }
            else {
                $playbookCardBody = $playbookCard.Groups['body'].Value
                $playbookCardStatusDot = [regex]::Match($playbookCardBody, '<span class="skill-dot (?<status>[a-z-]+)" data-pb-status="[^"]*"></span>')
                if (-not $playbookCardStatusDot.Success -or $playbookCardStatusDot.Groups['status'].Value.Trim() -ne $playbookStatus) {
                    Add-ValidationError "docs/index.html: playbook '$playbookName' card title dot must read '$playbookStatus'"
                }
                $playbookCardDots = [regex]::Matches($playbookCardBody, '<span class="skill-dot (?<status>[a-z-]+)" data-skill="(?<skill>[^"]+)"></span>')
                if ($playbookCardDots.Count -ne $playbookSkills.Count) {
                    Add-ValidationError "docs/index.html: playbook '$playbookName' card must show exactly one skill dot per connected skill"
                }
                foreach ($playbookCardDot in $playbookCardDots) {
                    $dotSkill = $playbookCardDot.Groups['skill'].Value
                    $dotSkillName = $dotSkill.TrimStart('$')
                    $dotStatus = $playbookCardDot.Groups['status'].Value.Trim()
                    if (-not $playbookSkills.Contains($dotSkillName)) {
                        Add-ValidationError "docs/index.html: playbook '$playbookName' card shows a dot for unconnected skill '$dotSkill'"
                        continue
                    }
                    if ($dotStatus -ne $playbookSkillStatuses[$dotSkillName]) {
                        Add-ValidationError "docs/index.html: playbook '$playbookName' card dot for '$dotSkill' reads '$dotStatus' but the skill status is '$($playbookSkillStatuses[$dotSkillName])'"
                    }
                }
            }
        }
    }
}

if (Test-Path -LiteralPath $indexPagePath -PathType Leaf) {
    $indexPageText = Get-Content -Raw -LiteralPath $indexPagePath
    foreach ($archivedSkill in $archivedSkills) {
        if ($indexPageText.Contains('$' + $archivedSkill)) {
            Add-ValidationError "docs/index.html: archived skill '$archivedSkill' must stay outside the active catalog"
        }
        if (-not $readmeText.Contains("skills/$archivedSkill/SKILL.md")) {
            Add-ValidationError "README.md: archived skill '$archivedSkill' must have a recovery link"
        }
    }
    foreach ($catalogSkill in $catalogSkills) {
        if (-not $indexPageText.Contains('$' + $catalogSkill)) {
            Add-ValidationError "docs/index.html: cataloged skill '$catalogSkill' must appear in the landing page catalog"
        }
    }
    foreach ($developmentSkill in $developmentSkills) {
        if (-not $indexPageText.Contains('$' + $developmentSkill)) {
            Add-ValidationError "docs/index.html: development skill '$developmentSkill' must appear in the landing page catalog"
        }
    }

    $landingCardPattern = [regex]'(?s)<a class="skill"[^>]*data-status="(?<status>[^"]*)"[^>]*>\s*<span class="status-chip[^"]*">(?<chip>[^<]*)</span>'
    $landingCards = $landingCardPattern.Matches($indexPageText)
    foreach ($landingCard in $landingCards) {
        $chipText = $landingCard.Groups['chip'].Value.Trim()
        $cardStatus = $landingCard.Groups['status'].Value.Trim()
        if ($chipText -ne $cardStatus) {
            Add-ValidationError "docs/index.html: skill card chip '$chipText' does not match data-status '$cardStatus'"
        }
    }
    $cardCount = [regex]::Matches($indexPageText, 'data-status=').Count
    if ($cardCount -ne $landingCards.Count) {
        Add-ValidationError "docs/index.html: found $cardCount skill cards with data-status but only $($landingCards.Count) with a status chip; every card needs one matching status chip"
    }
}

$explicitOnlySkills = @('dia-analyze-local-data', 'dia-bi-publisher-sql-optimizer', 'dia-clickup-mcp-setup', 'dia-data-model-docs', 'dia-data-model-intake', 'dia-new-workspace', 'dia-otbi-to-bipublisher-sql', 'dia-plan-my-project', 'dia-setup-business-insights-folder', 'dia-start-my-day', 'dia-transcript-to-process-map', 'dia-transcript-to-project-request-draft', 'dia-transcript-to-requirements')
foreach ($explicitOnlySkill in $explicitOnlySkills) {
    $explicitMetadata = Join-Path $skillsRoot "$explicitOnlySkill\agents\openai.yaml"
    if (-not (Test-Path -LiteralPath $explicitMetadata -PathType Leaf)) {
        Add-ValidationError "skills\$explicitOnlySkill\agents\openai.yaml: explicit-only skill metadata is missing"
        continue
    }
    $metadataText = Get-Content -Raw -LiteralPath $explicitMetadata
    if (-not $metadataText.Contains('allow_implicit_invocation: false')) {
        Add-ValidationError "skills\$explicitOnlySkill\agents\openai.yaml: skill must remain explicit-only"
    }
}

$markdownFiles = @(
    Get-ChildItem -LiteralPath $repositoryRoot -Recurse -File -Filter '*.md' |
        Where-Object { $_.FullName -notmatch '[\\/]\.git[\\/]' }
)

$linkPattern = [regex]'!?\[[^\]]*\]\((?<target>[^)]+)\)'
foreach ($markdownFile in $markdownFiles) {
    $text = Get-Content -Raw -LiteralPath $markdownFile.FullName
    foreach ($match in $linkPattern.Matches($text)) {
        $target = $match.Groups['target'].Value.Trim().Trim('<', '>')
        if (
            [string]::IsNullOrWhiteSpace($target) -or
            $target.StartsWith('http://') -or
            $target.StartsWith('https://') -or
            $target.StartsWith('#') -or
            $target.StartsWith('mailto:')
        ) {
            continue
        }

        $targetPath = $target.Split('#', 2)[0]
        $resolvedTarget = [System.IO.Path]::GetFullPath((Join-Path $markdownFile.DirectoryName $targetPath))
        if (-not (Test-Path -LiteralPath $resolvedTarget)) {
            Add-ValidationError "$(Get-RelativePath $markdownFile.FullName): broken local link '$target'"
        }
    }
}

$checkedExtensions = @('.md', '.yaml', '.yml', '.toml', '.json', '.ps1', '.py')
$secretPattern = [regex]'(?i)(?:pk_[a-z0-9]{16,}|clickup_api_token\s*=\s*[''"][^''"]+|sk-[a-z0-9]{20,})'
$checkedFiles = @(
    Get-ChildItem -LiteralPath $repositoryRoot -Recurse -File |
        Where-Object {
            $_.FullName -notmatch '[\\/]\.git[\\/]' -and
            $checkedExtensions -contains $_.Extension.ToLowerInvariant()
        }
)

foreach ($checkedFile in $checkedFiles) {
    $text = Get-Content -Raw -LiteralPath $checkedFile.FullName
    if ($secretPattern.IsMatch($text)) {
        Add-ValidationError "$(Get-RelativePath $checkedFile.FullName): possible committed secret"
    }
}

$powerShellFiles = @(Get-ChildItem -LiteralPath $repositoryRoot -Recurse -File -Filter '*.ps1')
foreach ($powerShellFile in $powerShellFiles) {
    $parseTokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $powerShellFile.FullName,
        [ref]$parseTokens,
        [ref]$parseErrors
    )
    foreach ($parseError in $parseErrors) {
        Add-ValidationError "$(Get-RelativePath $powerShellFile.FullName): $($parseError.Message)"
    }
}

if ($errors.Count -gt 0) {
    Write-Host 'Repository validation failed:'
    foreach ($validationError in $errors) {
        Write-Host "- $validationError"
    }
    exit 1
}

Write-Host 'Repository validation passed.'



