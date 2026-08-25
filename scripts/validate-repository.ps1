[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$skillsRoot = Join-Path $repositoryRoot 'skills'
$errors = [System.Collections.Generic.List[string]]::new()

function Add-ValidationError {
    param([string]$Message)
    $errors.Add($Message)
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

$explicitOnlySkills = @('analyze-csv-with-duckdb', 'connect-clickup')
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
