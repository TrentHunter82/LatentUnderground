param(
    [int]$CheckInterval = 30,
    [int]$StaleThreshold = 120,
    [int]$MaxPhases = 3
)

$logFile = "logs/supervisor.log"

function Write-Log {
    param([string]$msg, [string]$level = "INFO")
    $timestamp = Get-Date -Format "HH:mm:ss"
    $color = switch ($level) {
        "OK"   { "Green" }
        "WARN" { "Yellow" }
        "ERR"  { "Red" }
        default { "Gray" }
    }
    Write-Host "  [$timestamp] $msg" -ForegroundColor $color
    "[$timestamp][$level] $msg" | Out-File -FilePath $logFile -Append -Encoding UTF8
}

function Get-AgentStatus {
    $agents = @()
    $heartbeatDir = ".claude/heartbeats"
    if (-not (Test-Path $heartbeatDir)) { return $agents }

    Get-ChildItem "$heartbeatDir/*.heartbeat" -ErrorAction SilentlyContinue | ForEach-Object {
        $name = $_.BaseName
        $lastBeatTime = Get-Content $_.FullName -ErrorAction SilentlyContinue
        $age = (Get-Date) - (Get-Date $lastBeatTime -ErrorAction SilentlyContinue)
        $agents += [PSCustomObject]@{
            Name          = $name
            LastHeartbeat = $lastBeatTime
            AgeSeconds    = [int]$age.TotalSeconds
            Status        = if ($age.TotalSeconds -gt $StaleThreshold) { "STALE" } else { "ACTIVE" }
        }
    }
    return $agents
}

function Get-TaskProgress {
    if (-not (Test-Path "tasks/TASKS.md")) { return $null }
    $content = Get-Content "tasks/TASKS.md" -Raw
    $total = ($content | Select-String -Pattern "\- \[[ x]\]" -AllMatches).Matches.Count
    $done  = ($content | Select-String -Pattern "\- \[x\]" -AllMatches).Matches.Count
    return [PSCustomObject]@{
        Total     = $total
        Done      = $done
        Remaining = $total - $done
        Percent   = if ($total -gt 0) { [math]::Round(($done / $total) * 100, 1) } else { 0 }
    }
}

Write-Host ""
Write-Host "  ===== SWARM SUPERVISOR - Monitoring Active =====" -ForegroundColor Magenta
Write-Host ""

"# Supervisor Log`nStarted: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -FilePath $logFile -Encoding UTF8
Write-Log "Supervisor started - checking every ${CheckInterval}s, stale threshold: ${StaleThreshold}s"

$lastProgress = $null

while ($true) {
    Write-Host "`n  -----------------------------------------" -ForegroundColor DarkGray
    Write-Host "  Check: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor DarkGray

    $agents = Get-AgentStatus
    if ($agents.Count -eq 0) {
        Write-Log "No agent heartbeats detected" "WARN"
    } else {
        foreach ($agent in $agents) {
            if ($agent.Status -eq "STALE") {
                Write-Log "$($agent.Name): STALE (last heartbeat $($agent.AgeSeconds)s ago)" "WARN"
            } else {
                Write-Log "$($agent.Name): Active ($($agent.AgeSeconds)s ago)" "OK"
            }
        }
    }

    $signalNames = @("backend-ready", "frontend-ready", "tests-passing", "phase-complete")
    $activeSignals = $signalNames | Where-Object { Test-Path ".claude/signals/$_.signal" }
    if ($activeSignals) {
        Write-Log "Signals: $($activeSignals -join ', ')" "OK"
    }

    if (Test-Path "tasks/lessons.md") {
        $lessonCount = ((Get-Content "tasks/lessons.md" -Raw) | Select-String -Pattern "^### " -AllMatches).Matches.Count
        if ($lessonCount -gt 0) {
            Write-Log "Lessons captured: $lessonCount"
        }
    }

    $progress = Get-TaskProgress
    if ($progress) {
        $barLen = [math]::Floor($progress.Percent / 5)
        $progressBar = "[" + ("#" * $barLen) + ("." * (20 - $barLen)) + "]"
        Write-Log "Progress: $progressBar $($progress.Percent)% ($($progress.Done)/$($progress.Total) tasks)"

        if ($lastProgress -and $progress.Done -eq $lastProgress.Done) {
            Write-Log "No progress since last check" "WARN"
        }
        $lastProgress = $progress

        if ($progress.Remaining -eq 0) {
            Write-Log "ALL TASKS COMPLETE!" "OK"
            if (Test-Path ".claude/signals/phase-complete.signal") {
                Write-Log "Phase complete signal received - swarm finished!" "OK"
                Write-Host ""
                Write-Host "  ===== SWARM COMPLETE! =====" -ForegroundColor Green

                if (Test-Path "next-swarm.ps1") {
                    $currentPhase = 1
                    if (Test-Path ".claude/swarm-phase.json") {
                        $pd = Get-Content ".claude/swarm-phase.json" | ConvertFrom-Json
                        $currentPhase = [int]$pd.Phase
                    }
                    $nextPhase = $currentPhase + 1

                    if ($nextPhase -gt $MaxPhases) {
                        Write-Host ""
                        Write-Log "Auto-chain limit reached ($MaxPhases phases). Stopping." "WARN"
                        Write-Host "  Run .\next-swarm.ps1 manually to continue, or re-run with -MaxPhases $($MaxPhases + 3)" -ForegroundColor Yellow
                    } else {
                        Write-Host ""
                        Write-Log "Auto-chaining to Phase $nextPhase of $MaxPhases..." "OK"
                        Write-Host "  Preparing next swarm in 10 seconds... (Ctrl+C to cancel)" -ForegroundColor Yellow
                        Start-Sleep -Seconds 10

                        $archiveDir = ".claude/archive/phase-$currentPhase"
                        New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
                        Copy-Item ".claude/signals/*" "$archiveDir/" -ErrorAction SilentlyContinue
                        Copy-Item ".claude/heartbeats/*" "$archiveDir/" -ErrorAction SilentlyContinue
                        Copy-Item "tasks/TASKS.md" "$archiveDir/TASKS-phase-$currentPhase.md" -ErrorAction SilentlyContinue
                        Remove-Item ".claude/signals/*" -ErrorAction SilentlyContinue
                        Remove-Item ".claude/heartbeats/*" -ErrorAction SilentlyContinue

                        @{ Phase = $nextPhase; MaxPhases = $MaxPhases; StartedAt = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") } |
                            ConvertTo-Json | Out-File -FilePath ".claude/swarm-phase.json" -Encoding UTF8

                        Write-Log "Archived phase $currentPhase, launching phase $nextPhase"
                        & .\next-swarm.ps1
                    }
                } else {
                    Write-Log "No next-swarm.ps1 found - swarm sequence complete" "OK"
                }
                break
            }
        }
    }

    Start-Sleep -Seconds $CheckInterval
}

Write-Host "`nSupervisor shutting down. Press any key to close."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
