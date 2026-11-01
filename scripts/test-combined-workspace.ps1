[CmdletBinding()]
param([string]$OutputRoot)
$ErrorActionPreference = 'Stop'
$helper = Join-Path $PSScriptRoot '..\skills\dia-new-workspace\scripts\setup_workspace.ps1'
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$testRoot = [IO.Path]::GetFullPath((Join-Path $temporaryBase ('dia-combined-' + [guid]::NewGuid())))
if (-not $testRoot.StartsWith($temporaryBase.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test path.' }
function Assert($condition, $message) { if (-not $condition) { throw $message } }
function Run-Setup($requestPath, $previewPath, $expected=0, [switch]$Apply) {
    $arguments = @('-RequestFile', $requestPath)
    if ($Apply) { $arguments += @('-ApprovedPlanFile', $previewPath, '-Apply') }
    $output = & (Join-Path $PSHOME 'pwsh.exe') -NoProfile -File $helper @arguments
    Assert ($LASTEXITCODE -eq $expected) "Unexpected setup exit: $output"
    ($output -join "`n") | ConvertFrom-Json
}
try {
    New-Item -ItemType Directory -Path $testRoot | Out-Null
    if ($OutputRoot) { New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null }
    $summaries = @()
    foreach ($scenario in @('guide','analysis','unknowns')) {
        $incoming = Join-Path $testRoot ($scenario + '-incoming')
        New-Item -ItemType Directory -Path $incoming | Out-Null
        $target = Join-Path $testRoot ($scenario + ' Project')
        $layout = if ($scenario -eq 'analysis') { 'analysis' } else { 'simple' }
        $files = if ($scenario -eq 'guide') {
            @(
                @{name='interview notes.txt'; destination='Inputs/interview notes.txt'; content='Staff need a checklist for their first day.'},
                @{name='format_guide.py'; destination='Scripts/format_guide.py'; content='print("Synthetic fixture; do not execute during setup")'},
                @{name='existing-summary.json'; destination='Outputs/existing-summary.json'; content='{"status":"draft"}'}
            )
        } elseif ($scenario -eq 'analysis') {
            @(
                @{name='requests.csv'; destination='data/raw/requests.csv'; content="month,requests`n2026-10,42"},
                @{name='data-dictionary.md'; destination='docs/data-dictionary.md'; content="# Existing dictionary`n`nmonth: reporting month.`nrequests: request count."},
                @{name='discovery transcript.txt'; destination='docs/transcripts/discovery transcript.txt'; content='Owner: compare monthly request volumes.'},
                @{name='explore.py'; destination='scratch/explore.py'; content='# Existing exploration, not a pipeline script'}
            )
        } else { @() }
        $moves = @()
        foreach ($file in $files) {
            $source = Join-Path $incoming $file.name
            Set-Content -LiteralPath $source -Value $file.content -Encoding utf8
            $moves += @{ source=$source; destination=$file.destination; hash=(Get-FileHash -LiteralPath $source).Hash }
        }
        if ($scenario -eq 'guide') {
            $source = Join-Path $incoming 'reference.png'
            [IO.File]::WriteAllBytes($source, [Convert]::FromBase64String('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jV1sAAAAASUVORK5CYII='))
            $moves += @{source=$source; destination='Inputs/reference.png'; hash=(Get-FileHash -LiteralPath $source).Hash}
        }
        $purpose = switch ($scenario) { guide {'Prepare a staff onboarding guide.'} analysis {'Review monthly request volumes.'} unknowns {'Organize project discovery notes.'} }
        $goal = switch ($scenario) { guide {'A reviewable guide for new DIA staff.'} analysis {'A repeatable monthly dashboard for team leads.'} unknowns {'A discovery summary for the project sponsor.'} }
        $constraint = switch ($scenario) { guide {'Draft only; no publication. Review due next Friday.'} analysis {'Keep raw exports unchanged. No external publication.'} unknowns {'Deadline and final format are not yet known.'} }
        $unknown = if ($scenario -eq 'unknowns') { 'Source availability, final format, deadline, and success criteria remain open. Find source materials before drafting substantive findings; agree format and criteria before final delivery.' } else { 'Agree acceptance criteria during planning.' }
        $sources = switch ($scenario) { guide {'Staff interview notes, a reference image, an existing script, and a draft summary.'} analysis {'Monthly request export, existing dictionary, discovery transcript, and exploratory script.'} unknowns {'No starting materials supplied yet.'} }
        $startingFiles = if ($moves.Count) { @($moves | ForEach-Object { $_.destination }) -join '; ' } else { 'None supplied' }
        $context = "## Project context`n`n- Purpose: $purpose`n- Intended outcome and audience: $goal`n- Sources: $sources`n- Constraints: $constraint`n- Starting files: $startingFiles.`n- Unresolved questions: $unknown`n"
        $request = [ordered]@{ layout=$layout; root=$target; description=$purpose; dataSources=$sources; projectContext=$context; useSuppliedDictionary=($scenario -eq 'analysis'); moves=@($moves | ForEach-Object { @{source=$_.source; destination=$_.destination} }) }
        $requestPath = Join-Path $testRoot ($scenario + '-request.json')
        $previewPath = Join-Path $testRoot ($scenario + '-preview.json')
        $request | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $requestPath
        $preview = Run-Setup $requestPath $previewPath
        $preview | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $previewPath
        Assert (-not (Test-Path -LiteralPath $target)) 'Preview created the target.'
        if ($scenario -eq 'analysis') { Assert (-not ($preview.changes -contains ('Create file: ' + (Join-Path $target 'docs\data-dictionary.md')))) 'Placeholder was not skipped.' }
        # The fictitious user accepts the displayed layout, context, and exact moves.
        $applied = Run-Setup $requestPath $previewPath -Apply
        Assert $applied.valid 'Setup did not succeed.'
        foreach ($move in $moves) {
            Assert (-not (Test-Path -LiteralPath $move.source)) 'Moved source still exists.'
            Assert ((Get-FileHash -LiteralPath (Join-Path $target $move.destination)).Hash -eq $move.hash) 'Moved file content changed.'
        }
        $readme = Get-Content -Raw -LiteralPath (Join-Path $target 'README.md')
        $agents = Get-Content -Raw -LiteralPath (Join-Path $target 'AGENTS.md')
        foreach ($text in @($readme, $agents)) {
            Assert ($text.Contains($purpose) -and $text.Contains($goal) -and $text.Contains($constraint) -and $text.Contains($target) -and $text.Contains($unknown)) 'Planning context is incomplete.'
            Assert (-not $text.Contains('{{')) 'Unexpanded template marker.'
        }
        if ($OutputRoot) {
            $destination = Join-Path $OutputRoot $scenario
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $target 'README.md'), (Join-Path $target 'AGENTS.md') -Destination $destination
            $interview = "# Simulated interview: $scenario`n`nThis is a self-test with fictitious answers, not a real user interview.`n`nAssistant: What are you working on, and what would you like to produce?`n`nUser: $purpose $goal $constraint`n`nAssistant: I recommend the $layout layout. Where should it live, and are there starting files to move?`n`nUser: $target. Move the listed synthetic materials.`n`nAssistant: Here are the proposed folders, project context, and each move. "
            if ($scenario -eq 'analysis') { $interview += 'Keep the supplied dictionary and skip the generated placeholder. ' }
            $interview += "`n`n$context`nProposed file moves:`n`n"
            $interview += if ($moves.Count) { (@($moves | ForEach-Object { '- ' + $_.source + ' -> ' + $_.destination }) -join "`n") } else { 'None.' }
            $interview += "`n`nConfirm these changes?`n`nUser: Yes.`n`n## Planning handoff rehearsal`n`nThe simulated new chat reads README and AGENTS at the recorded root. Known purpose: $purpose Known audience and outcome: $goal Known constraints: $constraint`n`nAssistant: What would make the first draft useful enough to review?`n`nUser: Include a short summary, evidence or source references, and a list of open questions. Keep unknown deadlines open.`n`nAssistant: I can draft a plan now. First inventory the supplied material, resolve definitions needed by dependent work, then prepare the draft and review it. $unknown`n`nThe rehearsal stops at drafting. No real Harness folder switch was performed. Temporary workspaces are removed after the test; these exported documents are review snapshots.`n"
            Set-Content -LiteralPath (Join-Path $destination 'interview.md') -Value $interview
            $approach = if ($scenario -eq 'analysis') {
                "1. Review the supplied dictionary and transcript to confirm request definitions and intended comparisons. Resolve definition gaps before calculating results.`n2. Inspect the raw CSV without editing it, then agree dashboard acceptance criteria with the team lead.`n3. Plan the numbered transformation scripts and output tables, then build the draft dashboard from those outputs.`n4. Review the draft with the team lead before any publication."
            } elseif ($scenario -eq 'guide') {
                "1. Review the interview notes, reference image, and existing draft summary to list the onboarding topics and gaps.`n2. Agree the guide's acceptance criteria and resolve missing instructions with the staff owner.`n3. Prepare a guide draft in Outputs and request review next Friday. Assess the existing script before deciding whether to use it."
            } else {
                "1. Identify available project evidence and the sponsor who can supply it.`n2. Agree success criteria and the draft format with the sponsor before drafting.`n3. Prepare a discovery summary in Outputs with references and explicit open questions. Agree a deadline before committing to final delivery."
            }
            $draft = "# Plan draft: $scenario`n`nSynthetic rehearsal only; this draft has not received real user approval.`n`n## Goal`n`n$goal`n`n## Success criteria`n`nThe draft includes a summary, source references, and open questions for review. Domain acceptance criteria still need agreement.`n`n## Current state`n`nLayout: $layout. Starting materials: $startingFiles.`n`n## Approach`n`n$approach`n`n## Out of scope`n`nPublication, external-system changes, and final delivery before review.`n`n## Assumptions`n`nNo additional assumptions confirmed.`n`n## Open questions`n`n$unknown`n`n## Constraints`n`n$constraint`n"
            Set-Content -LiteralPath (Join-Path $destination 'plan-draft.md') -Value $draft
        }
        $summaries += "$scenario`: $layout layout, $($moves.Count) files moved intact; README and AGENTS preserve planning context."
    }
    # Reject a supplied dictionary until its placeholder resolution is explicit.
    $request.root = Join-Path $testRoot 'Unresolved dictionary'
    $dict = Join-Path $testRoot 'dictionary.md'
    Set-Content -LiteralPath $dict -Value '# Supplied dictionary'
    $request.layout='analysis'; $request.useSuppliedDictionary=$false
    $request.moves=@(@{source=$dict;destination='docs/data-dictionary.md'})
    $request | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $requestPath
    $null = Run-Setup $requestPath $previewPath 2
    Assert (-not (Test-Path -LiteralPath $request.root)) 'Conflict created a workspace.'
    # Reject stale approvals before creating any folders or moving files.
    $request.useSuppliedDictionary=$true
    $request | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $requestPath
    $preview = Run-Setup $requestPath $previewPath
    $preview | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $previewPath
    Add-Content -LiteralPath $dict -Value 'Changed after preview'
    $null = Run-Setup $requestPath $previewPath 2 -Apply
    Assert (-not (Test-Path -LiteralPath $request.root)) 'Stale approval created a workspace.'
    Assert (Test-Path -LiteralPath $dict) 'Stale approval moved the source.'
    # Other generated-file collisions still require choosing another destination.
    $request.moves=@(@{source=$dict;destination='scripts/README.md'}); $request.useSuppliedDictionary=$false
    $request | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $requestPath
    $null = Run-Setup $requestPath $previewPath 2
    $request.moves=@(@{source=$dict;destination='scripts/README.md/nested.txt'})
    $request | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $requestPath
    $null = Run-Setup $requestPath $previewPath 2
    $summaries += 'Conflict and changed-source cases rejected before workspace writes.'
    if ($OutputRoot) { $summaries | Set-Content -LiteralPath (Join-Path $OutputRoot 'results.txt') }
    $summaries
    Write-Host 'Combined workspace tests passed.'
}
finally {
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
}
