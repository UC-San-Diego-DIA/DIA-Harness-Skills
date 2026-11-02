function Remove-TestRoot {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
        return
    }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        }
        catch {
            if ($attempt -eq 3) {
                Write-Warning "Could not fully remove test directory '$Path': $($_.Exception.Message)"
                return
            }
            Start-Sleep -Milliseconds 250
        }
    }
}
