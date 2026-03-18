param(
    [string]$AgentName,
    [string]$AgentRole,
    [string]$Prompt,
    [string]$WaitForSignal = "",
    [string]$Color = "White",
    [int]$MaxIterations = 20,
    [int]$TimeoutMinutes = 30
)

$iteration = 1
$handoffFile = ".claude/handoffs/$AgentName.md"
$heartbeatFile = ".claude/heartbeats/$AgentName.heartbeat"
$logFile = "logs/$AgentName.log"
$rateLimitSignal = ".claude/signals/rate-limited.signal"
$RATE_LIMIT_EXIT_CODE = 75

function Write-Log {
    param([string]$msg)
    $timestamp = Get-Date -Format "HH:mm:ss"
    $entry = "[$timestamp] $msg"
    Write-Host "  $entry" -ForegroundColor $Color
    $entry | Out-File -FilePath $logFile -Append -Encoding UTF8
}

function Write-Heartbeat {
    Get-Date -Format "yyyy-MM-dd HH:mm:ss" | Out-File -FilePath $heartbeatFile -Encoding UTF8
}

function Test-RateLimitActive {
    if (-not (Test-Path $rateLimitSignal)) { return $false }
    try {
        $content = Get-Content $rateLimitSignal -Raw | ConvertFrom-Json
        $resetTimestamp = $content.reset_timestamp
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        if ($now -ge $resetTimestamp) {
            Remove-Item $rateLimitSignal -Force -ErrorAction SilentlyContinue
            return $false
        }
        $remaining = $resetTimestamp - $now
        Write-Log "Rate limit active, $([int]$remaining) seconds remaining"
        return $true
    } catch { return $false }
}

function Get-RateLimitResetTime {
    if (-not (Test-Path $rateLimitSignal)) { return $null }
    try {
        $content = Get-Content $rateLimitSignal -Raw | ConvertFrom-Json
        return $content.reset_timestamp
    } catch { return $null }
}

function Write-RateLimitSignal {
    param([string]$Message)
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $resetAt = $now + 3600
    $signalData = @{
        detected_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
        detected_by = $AgentName
        reset_at = (Get-Date).AddHours(1).ToString("yyyy-MM-ddTHH:mm:ss")
        reset_timestamp = $resetAt
        message = $Message.Substring(0, [Math]::Min(500, $Message.Length))
    }
    $signalDir = Split-Path $rateLimitSignal -Parent
    if (-not (Test-Path $signalDir)) { New-Item -ItemType Directory -Force -Path $signalDir | Out-Null }
    $signalData | ConvertTo-Json | Out-File -FilePath $rateLimitSignal -Encoding UTF8
    Write-Log "RATE LIMIT: Signal file written"
}

function Wait-ForSignal {
    param([string]$Signal)
    if ([string]::IsNullOrWhiteSpace($Signal)) { return $true }
    $signalFile = ".claude/signals/$Signal.signal"
    if (Test-Path $signalFile) {
        Write-Log "Signal already present: $Signal"
        return $true
    }
    Write-Log "Signal $Signal not yet present - starting work on non-dependent tasks"
    return $false
}

Write-Host ""
Write-Host "  ===== $AgentName - $AgentRole =====" -ForegroundColor $Color
Write-Host ""

# Set AGENT_NAME env var for swarm-msg client
$env:AGENT_NAME = $AgentName

# Non-blocking: just check signal status, always proceed
$signalReady = Wait-ForSignal -Signal $WaitForSignal
if (-not [string]::IsNullOrWhiteSpace($WaitForSignal) -and -not $signalReady) {
    Write-Log "Will work on independent tasks first, then check for $WaitForSignal signal"
}

while ($iteration -le $MaxIterations) {
    # Rate limit check before each iteration
    if (Test-RateLimitActive) {
        $resetTime = Get-RateLimitResetTime
        if ($resetTime) {
            $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
            $waitSeconds = $resetTime - $now
            if ($waitSeconds -gt 300) {
                Write-Log "Rate limit active for $([int]$waitSeconds)s - exiting"
                exit $RATE_LIMIT_EXIT_CODE
            } elseif ($waitSeconds -gt 0) {
                Write-Log "Rate limit active, waiting $([int]$waitSeconds) seconds..."
                Start-Sleep -Seconds $waitSeconds
            }
        }
    }

    Write-Log "Starting iteration $iteration"
    Write-Heartbeat

    $currentPrompt = $Prompt
    if ((Test-Path $handoffFile) -and $iteration -gt 1) {
        Write-Log "Resuming from handoff file"
        $handoffContent = Get-Content $handoffFile -Raw
        $currentPrompt = "RESUMING FROM HANDOFF:`n$handoffContent`n`nOriginal prompt context:`n$Prompt`n`nContinue from where you left off. Check tasks/TASKS.md for current state. Read tasks/lessons.md for accumulated learnings."
        Remove-Item $handoffFile -Force
    }

    $claudeOutput = $null
    try {
        $claudeOutput = claude --dangerously-skip-permissions $currentPrompt 2>&1 | Tee-Object -Variable claudeOutput
        $exitCode = $LASTEXITCODE
    } catch {
        Write-Log "ERROR: Claude crashed - $_"
        $exitCode = 1
    }

    # Check for rate limit in output
    $outputText = $claudeOutput -join "`n"
    $rateLimitPatterns = @("hit your.*limit", "out of extra usage", "rate.?limit", "too many requests", "quota exceeded", "usage limit", "429")
    $isRateLimited = $false
    foreach ($pattern in $rateLimitPatterns) {
        if ($outputText -match $pattern) {
            $isRateLimited = $true
            Write-Log "RATE LIMIT DETECTED in output"
            break
        }
    }
    if ($isRateLimited) {
        Write-RateLimitSignal -Message $outputText.Substring(0, [Math]::Min(500, $outputText.Length))
        Write-Log "Exiting due to rate limit (code $RATE_LIMIT_EXIT_CODE)"
        exit $RATE_LIMIT_EXIT_CODE
    }

    Write-Heartbeat

    if (Test-Path $handoffFile) {
        Write-Log "Handoff requested, restarting..."
        $iteration++
        Start-Sleep -Seconds 3
        continue
    }

    if (Test-Path "tasks/TASKS.md") {
        $tasks = Get-Content "tasks/TASKS.md" -Raw
        if ($tasks -match "(?s)## $AgentName.*?(?=## Claude-|## Completion|$)") {
            $section = $Matches[0]
            $incomplete = ($section | Select-String -Pattern "\- \[ \]" -AllMatches).Matches.Count
            if ($incomplete -eq 0) {
                Write-Log "All tasks complete!"
                break
            } else {
                Write-Log "$incomplete tasks remaining"
            }
        }
    }

    if ($exitCode -eq 0) {
        Write-Log "Session ended normally"
        break
    }

    if ($exitCode -eq $RATE_LIMIT_EXIT_CODE) {
        Write-Log "Agent exited due to rate limit - not restarting"
        break
    }

    if (Test-RateLimitActive) {
        Write-Log "Rate limit signal detected - pausing before restart"
        $resetTime = Get-RateLimitResetTime
        if ($resetTime) {
            $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
            $waitSeconds = $resetTime - $now
            if ($waitSeconds -gt 0) {
                Write-Log "Waiting $([int]$waitSeconds) seconds for rate limit..."
                Start-Sleep -Seconds ([Math]::Min($waitSeconds, 300))
            }
        }
    }

    Write-Log "Unexpected exit (code: $exitCode), restarting..."
    $iteration++
    Start-Sleep -Seconds 5
}

if ($iteration -gt $MaxIterations) {
    Write-Log "Max iterations reached"
}

Write-Log "Agent finished"
Write-Host ""
Write-Host "[$AgentName] Complete. Press any key to close." -ForegroundColor $Color
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
