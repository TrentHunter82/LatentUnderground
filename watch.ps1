param([int]$Interval = 5)

while ($true) {
    Clear-Host
    Write-Host "  ===== SWARM DASHBOARD - $(Get-Date -Format 'HH:mm:ss') =====" -ForegroundColor Cyan
    Write-Host ""

    if (Test-Path ".claude/swarm-phase.json") {
        $pd = Get-Content ".claude/swarm-phase.json" | ConvertFrom-Json
        Write-Host "  Phase: $($pd.Phase) of $($pd.MaxPhases) (auto-chains on completion)" -ForegroundColor White
        Write-Host ""
    }

    if (Test-Path "tasks/TASKS.md") {
        $content = Get-Content "tasks/TASKS.md" -Raw
        $total = ($content | Select-String -Pattern "\- \[[ x]\]" -AllMatches).Matches.Count
        $done  = ($content | Select-String -Pattern "\- \[x\]" -AllMatches).Matches.Count
        $pct   = if ($total -gt 0) { [math]::Round(($done / $total) * 100, 1) } else { 0 }
        $barLen = [math]::Floor($pct / 5)
        $bar = "#" * $barLen + "." * (20 - $barLen)
        Write-Host "  Tasks: [$bar] $pct% ($done/$total)" -ForegroundColor White
    }

    if (Test-Path "tasks/lessons.md") {
        $lc = ((Get-Content "tasks/lessons.md" -Raw) | Select-String -Pattern "^### " -AllMatches).Matches.Count
        Write-Host "  Lessons captured: $lc" -ForegroundColor $(if ($lc -gt 0) { "Green" } else { "Gray" })
    }

    Write-Host ""
    Write-Host "  AGENTS:" -ForegroundColor Yellow
    Get-ChildItem ".claude/heartbeats/*.heartbeat" -ErrorAction SilentlyContinue | ForEach-Object {
        $name = $_.BaseName
        $beat = Get-Content $_.FullName -ErrorAction SilentlyContinue
        $age  = [int]((Get-Date) - (Get-Date $beat -ErrorAction SilentlyContinue)).TotalSeconds
        $status = if ($age -gt 120) { "STALE" } else { "ACTIVE" }
        $color  = if ($age -gt 120) { "Red" } else { "Green" }
        Write-Host "    $name : $status (${age}s ago)" -ForegroundColor $color
    }
    Write-Host ""

    Write-Host "  SIGNALS:" -ForegroundColor Yellow
    @("backend-ready", "frontend-ready", "tests-passing", "phase-complete") | ForEach-Object {
        $present = Test-Path ".claude/signals/$_.signal"
        $icon  = if ($present) { "[x]" } else { "[ ]" }
        $color = if ($present) { "Green" } else { "DarkGray" }
        Write-Host "    $icon $_" -ForegroundColor $color
    }
    Write-Host ""

    Write-Host "  RECENT ACTIVITY:" -ForegroundColor Yellow
    if (Test-Path "logs/activity.log") {
        Get-Content "logs/activity.log" -Tail 8 | ForEach-Object {
            Write-Host "    $_" -ForegroundColor Gray
        }
    } else {
        Write-Host "    (no activity yet)" -ForegroundColor DarkGray
    }

    Write-Host ""
    Write-Host "  Press Ctrl+C to exit dashboard" -ForegroundColor DarkGray
    Start-Sleep -Seconds $Interval
}
