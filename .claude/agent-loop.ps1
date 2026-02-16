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
    Write-Log "Starting iteration $iteration"
    Write-Heartbeat

    $currentPrompt = $Prompt
    if ((Test-Path $handoffFile) -and $iteration -gt 1) {
        Write-Log "Resuming from handoff file"
        $handoffContent = Get-Content $handoffFile -Raw
        $currentPrompt = "RESUMING FROM HANDOFF:`n$handoffContent`n`nOriginal prompt context:`n$Prompt`n`nContinue from where you left off. Check tasks/TASKS.md for current state. Read tasks/lessons.md for accumulated learnings."
        Remove-Item $handoffFile -Force
    }

    try {
        claude --dangerously-skip-permissions $currentPrompt
        $exitCode = $LASTEXITCODE
    } catch {
        Write-Log "ERROR: Claude crashed - $_"
        $exitCode = 1
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
