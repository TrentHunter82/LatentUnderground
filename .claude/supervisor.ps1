param(
    [int]$CheckInterval = 30,
    [int]$StaleThreshold = 120,
    [int]$MaxPhases = 999
)

$logFile = "logs/supervisor.log"
$rateLimitSignal = ".claude/signals/rate-limited.signal"

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

function Sync-Lessons {
    <#
    .SYNOPSIS
        Sync lessons from message bus database to tasks/lessons.md
    #>
    $lessonsFile = "tasks/lessons.md"
    $phaseFile = ".claude/swarm-phase.json"
    $busConfig = Join-Path (Join-Path (Get-Location) ".swarm") "bus.json"

    # Need bus config to call the API
    if (-not (Test-Path $busConfig)) { return }

    try {
        $config = Get-Content $busConfig -Raw | ConvertFrom-Json
    }
    catch { return }

    $baseUrl = "http://127.0.0.1:$($config.port)/api/bus/$($config.project_id)"

    # Read last sync timestamp from phase file
    $since = ""
    if (Test-Path $phaseFile) {
        try {
            $phaseData = Get-Content $phaseFile -Raw | ConvertFrom-Json
            if ($phaseData.last_lesson_sync) {
                $since = "?since=$($phaseData.last_lesson_sync)"
            }
        }
        catch { }
    }

    # Query bus API for lesson messages
    $url = "$baseUrl/channels/lessons/messages$since"
    $params = @{
        Uri         = $url
        Method      = "GET"
        ContentType = "application/json"
        TimeoutSec  = 5
    }
    if ($config.api_key) {
        $params["Headers"] = @{ "Authorization" = "Bearer $($config.api_key)" }
    }

    try {
        $result = Invoke-RestMethod @params
    }
    catch {
        # API unreachable (swarm not running) - skip silently
        return
    }

    if (-not $result.messages -or $result.messages.Count -eq 0) { return }

    # Ensure lessons file exists with header
    if (-not (Test-Path $lessonsFile)) {
        @"
# Lessons Learned

ALL AGENTS: Read this file at session start before writing any code.
After ANY correction, failed attempt, or discovery, add a lesson here.

## Format
### [Agent] Short description
- What happened: ...
- Root cause: ...
- Rule: ...

## Lessons
"@ | Out-File -FilePath $lessonsFile -Encoding UTF8
    }

    # Read existing file content for dedup
    $existingContent = Get-Content $lessonsFile -Raw

    $syncCount = 0
    $latestTimestamp = ""

    foreach ($msg in $result.messages) {
        $bodyTrimmed = $msg.body.Trim()

        # Dedup: skip if body text already exists in file
        if ($existingContent -and $existingContent.Contains($bodyTrimmed)) {
            # Still track timestamp for sync state
            if ($msg.created_at -gt $latestTimestamp) {
                $latestTimestamp = $msg.created_at
            }
            continue
        }

        # Build lesson entry - use first 60 chars of body as title
        $title = $bodyTrimmed
        if ($title.Length -gt 60) {
            $title = $title.Substring(0, 57) + "..."
        }

        $agentName = $msg.from_agent
        if (-not $agentName) { $agentName = "Unknown" }

        $entry = @"

### [$agentName] $title
- What happened: $bodyTrimmed
- Source: bus message $($msg.id) at $($msg.created_at)
"@

        Add-Content -Path $lessonsFile -Value $entry -Encoding UTF8
        $syncCount++

        if ($msg.created_at -gt $latestTimestamp) {
            $latestTimestamp = $msg.created_at
        }

        # Update existing content for dedup within same batch
        $existingContent += $entry
    }

    # Update sync timestamp in phase file
    if ($latestTimestamp) {
        try {
            $phaseData = @{}
            if (Test-Path $phaseFile) {
                $phaseData = Get-Content $phaseFile -Raw | ConvertFrom-Json -AsHashtable
            }
            $phaseData["last_lesson_sync"] = $latestTimestamp
            $phaseData | ConvertTo-Json | Out-File -FilePath $phaseFile -Encoding UTF8
        }
        catch {
            Write-Log "Failed to update lesson sync timestamp: $_" "WARN"
        }
    }

    if ($syncCount -gt 0) {
        Write-Log "Synced $syncCount new lesson(s) from message bus" "OK"
    }
}

function Test-RateLimitActive {
    if (-not (Test-Path $rateLimitSignal)) {
        return @{ Active = $false; SecondsRemaining = 0 }
    }
    try {
        $content = Get-Content $rateLimitSignal -Raw | ConvertFrom-Json
        $resetTimestamp = $content.reset_timestamp
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        if ($now -ge $resetTimestamp) {
            Remove-Item $rateLimitSignal -Force -ErrorAction SilentlyContinue
            return @{ Active = $false; SecondsRemaining = 0 }
        }
        $remaining = $resetTimestamp - $now
        return @{
            Active = $true
            SecondsRemaining = [int]$remaining
            DetectedBy = $content.detected_by
            ResetAt = $content.reset_at
        }
    } catch {
        Write-Log "Failed to parse rate limit signal: $_" "WARN"
        return @{ Active = $false; SecondsRemaining = 0 }
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

    # Check rate limit status
    $rateLimit = Test-RateLimitActive
    if ($rateLimit.Active) {
        Write-Log "RATE LIMIT ACTIVE: $($rateLimit.SecondsRemaining)s remaining (detected by $($rateLimit.DetectedBy))" "WARN"
    }

    # Sync lessons from message bus to file, then report count
    Sync-Lessons

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
                        # Check for rate limit before auto-chaining
                        $rateLimitCheck = Test-RateLimitActive
                        if ($rateLimitCheck.Active) {
                            Write-Host ""
                            Write-Log "Rate limit active - waiting $($rateLimitCheck.SecondsRemaining)s before auto-chain..." "WARN"
                            $waitTime = [Math]::Min($rateLimitCheck.SecondsRemaining, 3600)
                            Write-Host "  Auto-chain delayed until $($rateLimitCheck.ResetAt)" -ForegroundColor Yellow
                            Start-Sleep -Seconds $waitTime
                        }

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
