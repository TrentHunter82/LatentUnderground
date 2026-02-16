# Claude Swarm v3 - Autonomous Multi-Agent Launcher
# Features: Orchestration rules, self-improvement loop, supervisor, signals, auto-recovery, auto-chain
# Usage: .\swarm.ps1 [-Resume] [-NoConfirm] [-AgentCount 4] [-MaxPhases 999]
# Double-click: Use swarm.bat wrapper
# Auto-chain: When a phase completes, supervisor automatically launches the next swarm
#             up to MaxPhases (default 999 = no limit). Override with -MaxPhases N.

param(
    [switch]$Resume,
    [switch]$NoConfirm,
    [int]$AgentCount = 4,
    [int]$MaxPhases = 999,
    [switch]$SetupOnly
)

$ErrorActionPreference = "Stop"

# === DIRECTORY SETUP (must happen first) ===
$dirs = @(".claude", ".claude/signals", ".claude/heartbeats", ".claude/handoffs", ".claude/prompts", ".claude/attention", ".swarm", ".swarm/bus", "tasks", "logs")
foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

# === PRE-LAUNCH CLEANUP ===
# Archive and clear stale artifacts from previous runs so agents start clean.
if (-not $Resume) {
    # Starting fresh — archive everything from previous run
    $prevPhaseFile = ".claude/swarm-phase.json"
    if (Test-Path $prevPhaseFile) {
        $prev = (Get-Content $prevPhaseFile | ConvertFrom-Json)
        $prevPhase = [int]$prev.Phase
        $archiveDir = ".claude/archive/phase-$prevPhase"
        New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
        Copy-Item ".claude/signals/*" "$archiveDir/" -ErrorAction SilentlyContinue
        Copy-Item ".claude/heartbeats/*" "$archiveDir/" -ErrorAction SilentlyContinue
        Copy-Item "tasks/TASKS.md" "$archiveDir/TASKS-phase-$prevPhase.md" -ErrorAction SilentlyContinue
        # Archive logs
        $logArchive = "$archiveDir/logs"
        New-Item -ItemType Directory -Force -Path $logArchive | Out-Null
        Copy-Item "logs/*.log" "$logArchive/" -ErrorAction SilentlyContinue
    }
}

# Always clear transient state (safe for both fresh and resume — agents recreate these)
Remove-Item ".claude/signals/*.signal" -Force -ErrorAction SilentlyContinue
Remove-Item ".claude/heartbeats/*.heartbeat" -Force -ErrorAction SilentlyContinue
Remove-Item ".claude/handoffs/*.md" -Force -ErrorAction SilentlyContinue
# Clear old logs so watcher doesn't re-broadcast stale output
Remove-Item "logs/*.log" -Force -ErrorAction SilentlyContinue

# === PHASE TRACKING ===
$phaseFile = ".claude/swarm-phase.json"
if (Test-Path $phaseFile) {
    $phaseData = Get-Content $phaseFile | ConvertFrom-Json
    $currentPhase = [int]$phaseData.Phase
} else {
    $currentPhase = 1
}

@{ Phase = $currentPhase; MaxPhases = $MaxPhases; StartedAt = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") } |
    ConvertTo-Json | Out-File -FilePath $phaseFile -Encoding UTF8

if ($currentPhase -gt $MaxPhases) {
    Write-Host ""
    Write-Host "  WARNING: Phase $currentPhase exceeds MaxPhases limit ($MaxPhases)." -ForegroundColor Yellow
    Write-Host "  The swarm has auto-chained $MaxPhases times already." -ForegroundColor Yellow
    Write-Host ""
    $override = Read-Host "  Continue anyway? [y/N]"
    if ($override -ne "y" -and $override -ne "Y") {
        Write-Host "  Stopped. Review tasks/lessons.md and tasks/TASKS.md for results so far." -ForegroundColor Cyan
        exit 0
    }
}

# === BANNER ===
function Show-Banner {
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host "         CLAUDE SWARM v3 - Orchestrated Edition" -ForegroundColor Cyan
    Write-Host "       Plan -> Build -> Verify -> Learn -> Repeat" -ForegroundColor Cyan
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host ""
}

Show-Banner

# === PROJECT CONFIGURATION ===
if (-not $Resume) {
    Write-Host "  ---- PROJECT SETUP ----" -ForegroundColor Yellow
    Write-Host ""

    Write-Host "  What do you want to build?" -ForegroundColor White
    $goal = Read-Host "  Goal"

    Write-Host ""
    Write-Host "  Project type:" -ForegroundColor White
    Write-Host "    1. Web App (frontend + backend)"
    Write-Host "    2. API/Backend only"
    Write-Host "    3. Frontend/UI only"
    Write-Host "    4. CLI Tool"
    Write-Host "    5. Python project"
    Write-Host "    6. Other"
    $projectType = Read-Host "  Type [1-6]"

    $projectTypeMap = @{
        "1" = "Web Application (frontend + backend)"
        "2" = "API/Backend Service"
        "3" = "Frontend/UI Application"
        "4" = "CLI Tool"
        "5" = "Python Project"
        "6" = "Custom Project"
    }
    $projectTypeName = $projectTypeMap[$projectType]
    if (-not $projectTypeName) { $projectTypeName = "Custom Project" }

    Write-Host ""
    Write-Host "  Tech stack? (Enter for auto-detect)" -ForegroundColor White
    Write-Host "    Examples: Node.js + React, Python + FastAPI, Rust CLI"
    $techStack = Read-Host "  Stack"
    if ([string]::IsNullOrWhiteSpace($techStack)) { $techStack = "auto-detect based on project type" }

    Write-Host ""
    Write-Host "  Complexity:" -ForegroundColor White
    Write-Host "    1. Simple  (1-2 hours, about 10 tasks)"
    Write-Host "    2. Medium  (half day, about 20 tasks)"
    Write-Host "    3. Complex (full day+, about 30 tasks)"
    $complexity = Read-Host "  Complexity [1-3]"

    $complexityMap = @{ "1" = "Simple"; "2" = "Medium"; "3" = "Complex" }
    $complexityName = $complexityMap[$complexity]
    if (-not $complexityName) { $complexityName = "Medium" }

    Write-Host ""
    Write-Host "  Additional requirements? (Enter to skip)" -ForegroundColor White
    $requirements = Read-Host "  Requirements"

    $config = @{
        Goal         = $goal
        ProjectType  = $projectTypeName
        TechStack    = $techStack
        Complexity   = $complexityName
        Requirements = $requirements
        StartTime    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        AgentCount   = $AgentCount
    }
    $config | ConvertTo-Json | Out-File -FilePath ".claude/swarm-config.json" -Encoding UTF8

} else {
    if (-not (Test-Path ".claude/swarm-config.json")) {
        Write-Host "  ERROR: No existing swarm config found. Run without -Resume first." -ForegroundColor Red
        exit 1
    }
    $config = Get-Content ".claude/swarm-config.json" | ConvertFrom-Json
    $goal = $config.Goal
    $projectTypeName = $config.ProjectType
    $techStack = $config.TechStack
    $complexityName = $config.Complexity
    $requirements = $config.Requirements
    Write-Host "  Resuming: $goal" -ForegroundColor Green
    Write-Host ""
}

# === GENERATE TASK BOARD ===
if (-not (Test-Path "tasks/TASKS.md")) {
    Write-Host "  ---- GENERATING TASK BOARD WITH CLAUDE ----" -ForegroundColor Yellow
    Write-Host ""

    $plannerLines = @(
        "You are a project planner. Generate a tasks/TASKS.md file for this project:",
        "",
        "PROJECT GOAL: $goal",
        "PROJECT TYPE: $projectTypeName",
        "TECH STACK: $techStack",
        "COMPLEXITY: $complexityName",
        "REQUIREMENTS: $requirements",
        "",
        "Create a task board with SPECIFIC checkbox tasks broken into 4 agent sections:",
        "",
        "## Claude-1 [Backend/Core] - Core logic and data",
        "- [ ] specific task 1",
        "- [ ] specific task 2",
        "(3-8 tasks depending on complexity)",
        "",
        "## Claude-2 [Frontend/Interface] - UI and user interaction",
        "- [ ] specific task 1",
        "- [ ] specific task 2",
        "(3-8 tasks depending on complexity)",
        "",
        "## Claude-3 [Integration/Testing] - Connect pieces and verify",
        "- [ ] specific task 1",
        "- [ ] specific task 2",
        "(3-6 tasks depending on complexity)",
        "",
        "## Claude-4 [Polish/Review] - Quality and refinement",
        "- [ ] specific task 1",
        "- [ ] specific task 2",
        "(3-5 tasks for review/polish)",
        "- [ ] FINAL: Generate next-swarm.ps1 script for the next development phase",
        "",
        "RULES:",
        "- Tasks must be SPECIFIC and ACTIONABLE",
        "- Each task completable in one iteration",
        "- Adapt agent roles to project type (CLI might not need Frontend)",
        "- Include setup tasks (init, dependencies) in Claude-1",
        "- Claude-4 LAST task must always be generating next-swarm.ps1",
        "- End with validation section",
        "",
        "Output ONLY the markdown content, no explanations."
    )
    $plannerPrompt = $plannerLines -join "`n"

    $taskOutput = claude --print $plannerPrompt 2>&1
    $taskOutput | Out-File -FilePath "tasks/TASKS.md" -Encoding UTF8
    Write-Host "  OK - Generated tasks/TASKS.md" -ForegroundColor Green

    Write-Host ""
    Write-Host "  Review tasks/TASKS.md before launching." -ForegroundColor Yellow
    Write-Host ""
    Get-Content "tasks/TASKS.md" | Write-Host
    Write-Host ""
    $editChoice = Read-Host "  Edit tasks? [y/N]"
    if ($editChoice -eq "y" -or $editChoice -eq "Y") {
        notepad "tasks/TASKS.md"
        Read-Host "  Press Enter when done editing"
    }
} else {
    Write-Host "  OK - Using existing tasks/TASKS.md" -ForegroundColor Green
}

# === CREATE AGENTS.MD ===
$agentsLines = @(
    "# Agent Guidelines",
    "",
    "## Workflow Orchestration (ALL AGENTS MUST FOLLOW)",
    "",
    "### 1. Skill Discovery (Do Once at Session Start)",
    "- Before starting your first task, search for relevant skills: npx skills find <query>",
    "- Use 2-3 targeted queries based on YOUR role and the project's tech stack",
    "- Install useful skills: npx skills add <owner/repo@skill> -g -y",
    "- Skills provide specialized domain knowledge (frameworks, best practices, patterns)",
    "- Browse https://skills.sh/ for the full catalog",
    "- Only do this once per session, not before every task",
    "",
    "### 2. Web Research (Do Once at Session Start)",
    "- Before starting your first task, use WebSearch or subagents to research best practices for YOUR role and the project's tech stack",
    "- Run 2-3 targeted web searches (e.g. 'FastAPI best practices 2026', 'React testing patterns', 'Python security checklist')",
    "- Focus on: current best practices, common pitfalls, recommended libraries, architecture patterns",
    "- Summarize key findings in tasks/todo.md under a ## [YourName] Research Findings heading",
    "- Use findings to inform your skill installation and implementation approach",
    "- Only do this once per session, not before every task",
    "",
    "### 3. Plan Then Execute (NO Plan Mode)",
    "- NEVER use EnterPlanMode or AskUserQuestion - you are running unattended and these will block forever",
    "- For non-trivial tasks (3+ steps): write your plan to tasks/todo.md, then IMMEDIATELY execute it",
    "- If something goes sideways, STOP, update your plan in tasks/todo.md, then continue executing",
    "- Write detailed specs upfront to reduce ambiguity, but always follow through with implementation",
    "- You are fully autonomous - plan internally, decide, and act without waiting for approval",
    "",
    "### 4. Spawn Teams (Parallel Subagents)",
    "- You are a team lead, not a solo developer. Use the Task tool aggressively to parallelize work",
    "- Break each task into independent subtasks and launch multiple subagents IN PARALLEL (single message, multiple Task tool calls)",
    "- Use subagents for: research, writing tests, implementing independent modules, code exploration, builds",
    "- Run background agents for long-running tasks while you continue other work",
    "- Only do sequential work when there are true dependencies between subtasks",
    "- Goal: maximize throughput by keeping multiple agents working simultaneously",
    "",
    "### 5. Self-Improvement Loop",
    "- After ANY correction or failed attempt: update tasks/lessons.md with the pattern",
    "- Write rules for yourself that prevent the same mistake",
    "- Ruthlessly iterate on these lessons until mistake rate drops",
    "- Read tasks/lessons.md at session start - learn from past mistakes before writing code",
    "",
    "### 6. Verification Before Done",
    "- NEVER mark a task [x] without proving it works",
    "- Diff behavior between main and your changes when relevant",
    "- Ask yourself: Would a staff engineer approve this?",
    "- Run tests, check logs, demonstrate correctness",
    "- If it does not pass verification, it stays [ ]",
    "",
    "### 7. Demand Elegance (Balanced)",
    "- For non-trivial changes: pause and ask - is there a more elegant way?",
    "- If a fix feels hacky: Knowing everything I know now, implement the elegant solution",
    "- Skip this for simple, obvious fixes - do not over-engineer",
    "- Challenge your own work before presenting it",
    "",
    "### 8. Autonomous Bug Fixing",
    "- When given a bug report or encountering a bug: just fix it. Do not ask for hand-holding",
    "- Point at logs, errors, failing tests then resolve them",
    "- Zero context switching required from the user",
    "- Go fix failing CI tests without being told how",
    "",
    "## Core Principles",
    "- Simplicity First: Make every change as simple as possible. Impact minimal code.",
    "- No Laziness: Find root causes. No temporary fixes. Senior developer standards.",
    "- Minimal Impact: Changes should only touch what is necessary. Avoid introducing bugs.",
    "",
    "## Task Management Protocol",
    "1. Plan First: Write plan to tasks/todo.md with checkable items (NEVER use EnterPlanMode - you are unattended)",
    "2. Execute Immediately: After writing the plan, start implementing right away. Do not wait for approval.",
    "3. Spawn Teams: Launch parallel subagents for independent subtasks to maximize throughput",
    "4. Track Progress: Mark items complete as you go in tasks/TASKS.md",
    "5. Explain Changes: High-level summary in logs/activity.log at each step",
    "6. Document Results: Add review notes to tasks/todo.md",
    "7. Capture Lessons: Update tasks/lessons.md after corrections or discoveries",
    "",
    "## Signal Protocol",
    "- backend-ready.signal - Claude-1 creates when core APIs/logic work",
    "- frontend-ready.signal - Claude-2 creates when UI connects to backend",
    "- tests-passing.signal - Claude-3 creates when all tests pass",
    "- phase-complete.signal - Claude-4 creates when all agents report done",
    "",
    "## Heartbeat Protocol",
    "Update .claude/heartbeats/{your-name}.heartbeat regularly so the supervisor knows you are alive.",
    "",
    "## Handoff Protocol",
    "If context is filling up or you are getting slow:",
    "1. Write current state to .claude/handoffs/{your-name}.md",
    "2. Include: what is done, current task, next steps, blockers",
    "3. Exit cleanly - the agent-loop will restart you with the handoff",
    "",
    "## Project Patterns",
    "(Reusable patterns discovered during development - agents add here as they learn)",
    "",
    "## Conventions",
    "(Coding conventions and standards for this project)",
    "",
    "## Gotchas",
    "(Things to watch out for - agents add here when they hit surprises)"
)
$agentsLines -join "`n" | Out-File -FilePath "AGENTS.md" -Encoding UTF8
Write-Host "  OK - Created AGENTS.md (with orchestration rules)" -ForegroundColor Green

# === CREATE SUPPORTING FILES ===

# tasks/lessons.md
if (-not (Test-Path "tasks/lessons.md")) {
    $lessonsLines = @(
        "# Lessons Learned",
        "",
        "ALL AGENTS: Read this file at session start before writing any code.",
        "After ANY correction, failed attempt, or discovery, add a lesson here.",
        "",
        "## Format",
        "### [Agent] Short description",
        "- What happened: What went wrong or was discovered",
        "- Root cause: Why it happened",
        "- Rule: The rule to follow going forward",
        "",
        "## Lessons",
        "",
        "(Agents add lessons here as they work. This file persists across swarm iterations.)"
    )
    $lessonsLines -join "`n" | Out-File -FilePath "tasks/lessons.md" -Encoding UTF8
    Write-Host "  OK - Created tasks/lessons.md (self-improvement loop)" -ForegroundColor Green
} else {
    Write-Host "  OK - Keeping existing tasks/lessons.md (accumulated wisdom)" -ForegroundColor Green
}

# tasks/todo.md
if (-not (Test-Path "tasks/todo.md")) {
    $todoLines = @(
        "# Agent Plans",
        "",
        "Agents write their implementation plans here before coding non-trivial tasks.",
        "Format: ## [Agent] - [Task Name] followed by checkable steps."
    )
    $todoLines -join "`n" | Out-File -FilePath "tasks/todo.md" -Encoding UTF8
    Write-Host "  OK - Created tasks/todo.md (planning scratchpad)" -ForegroundColor Green
}

# progress.txt
if (-not (Test-Path "progress.txt")) {
    $progressLines = @(
        "# Swarm Progress Log",
        "",
        "## Learnings",
        "(Patterns discovered across iterations - READ THIS FIRST)",
        "",
        "---"
    )
    $progressLines -join "`n" | Out-File -FilePath "progress.txt" -Encoding UTF8
    Write-Host "  OK - Created progress.txt" -ForegroundColor Green
}

# === CREATE AGENT-LOOP SCRIPT ===
$agentLoopScript = @'
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
'@
$agentLoopScript | Out-File -FilePath ".claude/agent-loop.ps1" -Encoding UTF8
Write-Host "  OK - Created .claude/agent-loop.ps1" -ForegroundColor Green

# === CREATE SUPERVISOR SCRIPT ===
$supervisorScript = @'
param(
    [int]$CheckInterval = 30,
    [int]$StaleThreshold = 120,
    [int]$MaxPhases = 999
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
'@
$supervisorScript | Out-File -FilePath ".claude/supervisor.ps1" -Encoding UTF8
Write-Host "  OK - Created .claude/supervisor.ps1" -ForegroundColor Green

# === CREATE WATCH DASHBOARD ===
$watchScript = @'
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
'@
$watchScript | Out-File -FilePath "watch.ps1" -Encoding UTF8
Write-Host "  OK - Created watch.ps1 (live dashboard)" -ForegroundColor Green

# === CREATE STOP SCRIPT ===
$stopScript = @'
Write-Host "Stopping swarm..." -ForegroundColor Yellow
Get-Process -Name "claude" -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "All Claude processes stopped." -ForegroundColor Green
Write-Host ""
Write-Host "Files preserved:" -ForegroundColor White
Write-Host "  tasks/TASKS.md    - Task progress" -ForegroundColor Gray
Write-Host "  tasks/lessons.md  - Accumulated lessons" -ForegroundColor Gray
Write-Host "  tasks/todo.md     - Agent plans" -ForegroundColor Gray
Write-Host "  progress.txt      - Learnings" -ForegroundColor Gray
Write-Host "  AGENTS.md         - Agent guidelines" -ForegroundColor Gray
Write-Host ""
Write-Host "Resume with: .\swarm.ps1 -Resume" -ForegroundColor Green
'@
$stopScript | Out-File -FilePath "stop-swarm.ps1" -Encoding UTF8
Write-Host "  OK - Created stop-swarm.ps1" -ForegroundColor Green

# === CREATE SWARM.BAT ===
$batContent = '@echo off' + "`r`n" + 'powershell -ExecutionPolicy Bypass -File "%~dp0swarm.ps1" %*' + "`r`n" + 'pause'
[System.IO.File]::WriteAllText((Join-Path $PWD "swarm.bat"), $batContent)
Write-Host "  OK - Created swarm.bat (double-click launcher)" -ForegroundColor Green

# === CONFIRMATION AND LAUNCH ===
Write-Host ""
Write-Host "  ---- READY TO LAUNCH ----" -ForegroundColor Green
Write-Host ""
Write-Host "  Project: $goal" -ForegroundColor White
Write-Host "  Type:    $projectTypeName" -ForegroundColor Gray
Write-Host "  Stack:   $techStack" -ForegroundColor Gray
Write-Host "  Phase:   $currentPhase of $MaxPhases (auto-chains)" -ForegroundColor Gray
Write-Host ""
Write-Host "  Files:" -ForegroundColor White
Write-Host "    tasks/TASKS.md      - Task board" -ForegroundColor Gray
Write-Host "    tasks/lessons.md    - Self-improvement loop" -ForegroundColor Gray
Write-Host "    tasks/todo.md       - Planning scratchpad" -ForegroundColor Gray
Write-Host "    AGENTS.md           - Orchestration rules" -ForegroundColor Gray
Write-Host "    progress.txt        - Shared learnings" -ForegroundColor Gray
Write-Host "    watch.ps1           - Live dashboard" -ForegroundColor Gray
Write-Host "    stop-swarm.ps1      - Graceful shutdown" -ForegroundColor Gray
Write-Host ""

if (-not $NoConfirm) {
    $confirm = Read-Host "  Launch swarm? [Y/n]"
    if ($confirm -eq "n" -or $confirm -eq "N") {
        Write-Host ""
        Write-Host "  Aborted. Run again when ready." -ForegroundColor Yellow
        exit 0
    }
}

# === READ ROLE-SPECIFIC RULES ===
function Read-RulesFile([string]$Filename) {
    $path = ".claude/rules/$Filename"
    if (Test-Path $path) {
        return (Get-Content $path -Raw -Encoding UTF8)
    }
    return ""
}

$backendRules = Read-RulesFile "BACKEND_RULES.md"
$frontendRules = Read-RulesFile "FRONTEND_RULES.md"
$testingRules = Read-RulesFile "TESTING_RULES.md"
$windowsRules = Read-RulesFile "WINDOWS_RULES.md"
$securityRules = Read-RulesFile "SECURITY_RULES.md"

# === TEMPLATE-BASED PROMPT GENERATION ===
function Read-TemplateFile([string]$Filename) {
    $path = ".claude/templates/$Filename"
    if (Test-Path $path) {
        return (Get-Content $path -Raw -Encoding UTF8)
    }
    return ""
}

function Build-PromptFromTemplate {
    param(
        [string]$AgentName,
        [string]$RoleTitle,
        [string]$Goal,
        [string]$TechStack,
        [string]$RoleKey,      # backend, frontend, integration, polish, distiller
        [string[]]$RuleFiles   # Array of rule file contents
    )

    # Read template files
    $baseTemplate = Read-TemplateFile "base-prompt.txt"
    $sharedRulesTemplate = Read-TemplateFile "shared-rules.txt"
    $roleWorkflow = Read-TemplateFile "role-$RoleKey.txt"
    $handoffProtocol = Read-TemplateFile "handoff-protocol.txt"
    $signaling = Read-TemplateFile "signaling-$RoleKey.txt"

    # Combine role rules
    $combinedRules = ($RuleFiles | Where-Object { $_ -ne "" }) -join "`n`n"

    # Check if templates exist (fallback to legacy mode if not)
    if (-not $baseTemplate -or -not $sharedRulesTemplate) {
        Write-Host "  Templates not found, using legacy prompt generation" -ForegroundColor Yellow
        return $null
    }

    # Build prompt from template with placeholder substitution
    $prompt = $baseTemplate `
        -replace '\{AGENT_NAME\}', $AgentName `
        -replace '\{ROLE_TITLE\}', $RoleTitle `
        -replace '\{GOAL\}', $Goal `
        -replace '\{TECH_STACK\}', $TechStack `
        -replace '\{SHARED_RULES\}', $sharedRulesTemplate `
        -replace '\{ROLE_RULES\}', $combinedRules `
        -replace '\{ROLE_WORKFLOW\}', $roleWorkflow `
        -replace '\{SIGNALING\}', $signaling `
        -replace '\{HANDOFF_PROTOCOL\}', $handoffProtocol

    return $prompt
}

# Role configurations for template-based generation
$roleConfigs = @{
    "Claude-1" = @{
        RoleTitle = "Backend/Core"
        RoleKey = "backend"
        RuleFiles = @($backendRules, $windowsRules, $securityRules)
    }
    "Claude-2" = @{
        RoleTitle = "Frontend/Interface"
        RoleKey = "frontend"
        RuleFiles = @($frontendRules, $securityRules)
    }
    "Claude-3" = @{
        RoleTitle = "Integration/Testing"
        RoleKey = "integration"
        RuleFiles = @($testingRules, $backendRules, $frontendRules)
    }
    "Claude-4" = @{
        RoleTitle = "Polish/Review"
        RoleKey = "polish"
        RuleFiles = @($backendRules, $frontendRules, $testingRules, $windowsRules, $securityRules)
    }
    "Knowledge-Distiller" = @{
        RoleTitle = "Knowledge Extraction"
        RoleKey = "distiller"
        RuleFiles = @()
    }
}

# === DEFINE AGENT PROMPTS ===
$sharedRules = "CRITICAL: You are running FULLY AUTONOMOUSLY. Never wait for user input. Never use EnterPlanMode or AskUserQuestion. Plan internally and execute immediately. You are unattended - act decisively.`n`n" +
    "ORCHESTRATION RULES (non-negotiable):`n" +
    "1. PLAN THEN EXECUTE: For non-trivial tasks (3+ steps), write your plan to tasks/todo.md, then IMMEDIATELY execute it. Do NOT use EnterPlanMode - it blocks waiting for user approval which will never come. Plan internally, execute autonomously.`n" +
    "2. READ LESSONS: Before starting work, read tasks/lessons.md - learn from past mistakes.`n" +
    "3. SKILL UP: Before starting your first task, search for and install relevant skills for your work.`n" +
    "   - Run: npx skills find <query> (use 2-3 targeted queries based on YOUR tasks and tech stack)`n" +
    "   - Install any relevant hits with: npx skills add <owner/repo@skill> -g -y`n" +
    "   - Example queries: 'react performance', 'fastapi testing', 'tailwind design', 'code review'`n" +
    "   - Browse https://skills.sh/ for more. Skills give you specialized domain knowledge.`n" +
    "   - Do this ONCE at the start of your session, not before every task.`n" +
    "4. WEB RESEARCH: Before your first task, use WebSearch to find current best practices for your role.`n" +
    "   - Use subagents to run 2-3 targeted web searches for YOUR role and the project's tech stack`n" +
    "   - Focus on: current best practices, common pitfalls, recommended libraries, architecture patterns`n" +
    "   - Summarize key findings briefly in tasks/todo.md under ## [YourName] Research Findings`n" +
    "   - Use findings to guide your implementation approach`n" +
    "   - Do this ONCE at the start of your session, not before every task.`n" +
    "5. VERIFY BEFORE DONE: Never mark [x] without proving it works. Run tests, check logs, demonstrate correctness.`n" +
    "6. SELF-IMPROVE: After any failed attempt or correction, add a lesson to tasks/lessons.md immediately.`n" +
    "7. SPAWN TEAMS: You are a team lead, not a solo developer. Use the Task tool aggressively to parallelize work:`n" +
    "   - Break each task into independent subtasks and launch multiple subagents IN PARALLEL`n" +
    "   - Use subagents for: research, writing tests, implementing independent modules, code exploration`n" +
    "   - Run background agents for long tasks (builds, test suites) while you continue other work`n" +
    "   - Only do sequential work when there are true dependencies between subtasks`n" +
    "   - Goal: maximize throughput by keeping multiple agents working simultaneously`n" +
    "8. DEMAND ELEGANCE: For non-trivial changes, pause and ask yourself - is there a more elegant way? Skip for trivial fixes.`n" +
    "9. AUTONOMOUS: If you hit a bug, fix it. Do not ask for hand-holding. Read logs, trace errors, resolve.`n" +
    "10. SIMPLICITY: Make every change as simple as possible. No temporary fixes. Find root causes. Minimal impact.`n`n" +
    "DIRECTIVE PROTOCOL:`n" +
    "After completing each task, check for directive files:`n" +
    "1. Check .claude/directives/{your-agent-name}.directive (e.g. .claude/directives/Claude-1.directive)`n" +
    "2. Check .claude/directives/all.directive (broadcast directives for all agents)`n" +
    "If a directive file exists: read it, execute the instructions as HIGHEST PRIORITY (override current task), then delete the file when done.`n" +
    "This allows the orchestrator to redirect you at any point without restarting.`n`n" +
    "MESSAGE BUS PROTOCOL:`n" +
    "Use swarm-msg for reliable inter-agent communication (replaces file polling):`n`n" +
    "CHECK MESSAGES (after each task):`n" +
    "  powershell .swarm/bus/swarm-msg.ps1 inbox`n`n" +
    "SEND MESSAGE to another agent:`n" +
    "  powershell .swarm/bus/swarm-msg.ps1 send --to Claude-2 --body ""API endpoints ready""`n`n" +
    "BROADCAST (urgent, all agents):`n" +
    "  powershell .swarm/bus/swarm-msg.ps1 send --to all --channel critical --priority high --body ""STOP: circular dependency found""`n`n" +
    "POST LESSON (shared with all agents):`n" +
    "  powershell .swarm/bus/swarm-msg.ps1 lesson ""Always run typecheck before committing""`n`n" +
    "ATTENTION FILES:`n" +
    "Before each task, check: if (Test-Path .claude/attention/{your-name}.attention) { check inbox immediately }`n" +
    "This signals a high-priority message requiring immediate attention.`n`n" +
    "CHANNELS: general (default), critical (urgent), review (code review), handoff (context pass), lessons (learnings)`n" +
    "PRIORITIES: low, normal, high, critical (high/critical create attention files)"

$prompt1 = "You are Claude-1 (Backend/Core) working on: $goal`n`n" +
    "FIRST: Read AGENTS.md, tasks/lessons.md, then tasks/TASKS.md.`n`n" +
    "$sharedRules`n`n" +
    "ROLE-SPECIFIC RULES (read these carefully - they are distilled from past mistakes):`n`n" +
    "$backendRules`n`n$windowsRules`n`n$securityRules`n`n" +
    "YOUR WORKFLOW:`n" +
    "1. Read tasks/lessons.md - internalize past mistakes`n" +
    "2. SKILL UP: Search for skills relevant to your backend/core tasks:`n" +
    "   - Run: npx skills find <query> for 2-3 queries based on the tech stack (e.g. 'fastapi', 'python api', 'database')`n" +
    "   - Install useful skills: npx skills add <owner/repo@skill> -g -y`n" +
    "   - Do this once at session start to equip yourself with domain expertise`n" +
    "3. WEB RESEARCH: Use a subagent to search the web for best practices relevant to your tasks:`n" +
    "   - Search for: '$techStack best practices 2026', '$techStack API design patterns', '$techStack performance optimization'`n" +
    "   - Focus on: API design best practices, database patterns, error handling, security`n" +
    "   - Write a brief summary of findings to tasks/todo.md under ## Claude-1 Research Findings`n" +
    "   - Do this once at session start to ground your work in current best practices`n" +
    "4. Find the ## Claude-1 section in tasks/TASKS.md`n" +
    "5. Pick the first unchecked [ ] task`n" +
    "6. PLAN THEN EXECUTE: If task has 3+ steps, write plan to tasks/todo.md then immediately implement (never use EnterPlanMode)`n" +
    "7. Implement it completely - use parallel subagents for independent subtasks. Find root causes, no hacky fixes`n" +
    "8. VERIFY: Run tests/typecheck to prove it works. Would a staff engineer approve this?`n" +
    "9. Mark [x] in tasks/TASKS.md only after verification passes`n" +
    "10. Log to logs/activity.log: [Claude-1] Done: <task> - brief summary`n" +
    "11. Update .claude/heartbeats/Claude-1.heartbeat`n" +
    "12. If anything went wrong or you learned something: update tasks/lessons.md`n" +
    "13. Repeat until all YOUR tasks are done`n`n" +
    "SIGNALING:`n" +
    "When your core APIs/logic work and are verified, create .claude/signals/backend-ready.signal`n`n" +
    "HANDOFF:`n" +
    "If context filling up: write state to .claude/handoffs/Claude-1.md (what is done, current task, next steps, blockers). Exit cleanly."

$prompt2 = "You are Claude-2 (Frontend/Interface) working on: $goal`n`n" +
    "FIRST: Read AGENTS.md, tasks/lessons.md, then tasks/TASKS.md.`n`n" +
    "$sharedRules`n`n" +
    "ROLE-SPECIFIC RULES (read these carefully - they are distilled from past mistakes):`n`n" +
    "$frontendRules`n`n$securityRules`n`n" +
    "YOUR WORKFLOW:`n" +
    "1. Read tasks/lessons.md - internalize past mistakes`n" +
    "2. SKILL UP: Search for skills relevant to your frontend/UI tasks:`n" +
    "   - Run: npx skills find <query> for 2-3 queries based on the tech stack (e.g. 'react', 'tailwind', 'frontend design', 'ui components')`n" +
    "   - Install useful skills: npx skills add <owner/repo@skill> -g -y`n" +
    "   - Do this once at session start to equip yourself with domain expertise`n" +
    "3. WEB RESEARCH: Use a subagent to search the web for best practices relevant to your tasks:`n" +
    "   - Search for: '$techStack UI best practices 2026', '$techStack component patterns', '$techStack accessibility'`n" +
    "   - Focus on: component architecture, responsive design, performance, accessibility, UX patterns`n" +
    "   - Write a brief summary of findings to tasks/todo.md under ## Claude-2 Research Findings`n" +
    "   - Do this once at session start to ground your work in current best practices`n" +
    "4. Check for .claude/signals/backend-ready.signal - if not present, start with tasks that do not depend on backend. Check again before integration tasks`n" +
    "5. Find the ## Claude-2 section in tasks/TASKS.md`n" +
    "6. Pick the first unchecked [ ] task`n" +
    "7. PLAN THEN EXECUTE: If task has 3+ steps, write plan to tasks/todo.md then immediately implement (never use EnterPlanMode)`n" +
    "8. Implement - spawn parallel subagents for independent subtasks, research, or exploring unfamiliar patterns`n" +
    "9. VERIFY: Test in context, check for regressions. Would a staff engineer approve this?`n" +
    "10. Mark [x] only after verification passes`n" +
    "11. Log to logs/activity.log: [Claude-2] Done: <task>`n" +
    "12. Update .claude/heartbeats/Claude-2.heartbeat`n" +
    "13. If anything went wrong: update tasks/lessons.md`n" +
    "14. Repeat`n`n" +
    "SIGNALING:`n" +
    "When frontend connects to backend and works, create .claude/signals/frontend-ready.signal`n`n" +
    "HANDOFF:`n" +
    "If context filling up: write state to .claude/handoffs/Claude-2.md. Exit cleanly.`n`n" +
    "Demand elegance for UI work - pause and ask: is there a better way?"

$prompt3 = "You are Claude-3 (Integration/Testing) working on: $goal`n`n" +
    "FIRST: Read AGENTS.md, tasks/lessons.md, then tasks/TASKS.md.`n`n" +
    "$sharedRules`n`n" +
    "ROLE-SPECIFIC RULES (read these carefully - they are distilled from past mistakes):`n`n" +
    "$testingRules`n`n$backendRules`n`n$frontendRules`n`n" +
    "YOUR WORKFLOW:`n" +
    "1. Read tasks/lessons.md - internalize past mistakes`n" +
    "2. SKILL UP: Search for skills relevant to your testing/integration tasks:`n" +
    "   - Run: npx skills find <query> for 2-3 queries based on the tech stack (e.g. 'testing', 'pytest', 'vitest', 'e2e testing', 'code quality')`n" +
    "   - Install useful skills: npx skills add <owner/repo@skill> -g -y`n" +
    "   - Do this once at session start to equip yourself with domain expertise`n" +
    "3. WEB RESEARCH: Use a subagent to search the web for best practices relevant to your tasks:`n" +
    "   - Search for: '$techStack testing best practices 2026', '$techStack test patterns', 'integration testing strategies'`n" +
    "   - Focus on: test architecture, mocking strategies, coverage vs correctness, CI patterns`n" +
    "   - Write a brief summary of findings to tasks/todo.md under ## Claude-3 Research Findings`n" +
    "   - Do this once at session start to ground your work in current best practices`n" +
    "4. Check signals: start with test scaffolding and test plans immediately. Check for backend-ready/frontend-ready before running integration tests`n" +
    "5. Find the ## Claude-3 section in tasks/TASKS.md`n" +
    "6. Pick the first unchecked [ ] task`n" +
    "7. PLAN THEN EXECUTE: Write test strategy to tasks/todo.md then immediately implement (never use EnterPlanMode)`n" +
    "8. Write tests that prove correctness - spawn parallel subagents for independent test files. Not just coverage theater`n" +
    "9. AUTONOMOUS BUG FIXING: When tests fail, trace the root cause and fix it yourself.`n" +
    "   - Read logs, check error traces, find the actual bug`n" +
    "   - Fix it if it is in scope. If another agent's domain, message them with the full diagnosis`n" +
    "10. VERIFY: All tests must genuinely pass. Check logs. Demonstrate correctness.`n" +
    "11. Mark [x] only after tests pass`n" +
    "12. Log to logs/activity.log: [Claude-3] Done: <task>`n" +
    "13. Update .claude/heartbeats/Claude-3.heartbeat`n" +
    "14. Add discoveries to tasks/lessons.md - especially patterns that cause test failures`n`n" +
    "SIGNALING:`n" +
    "When all tests pass, create .claude/signals/tests-passing.signal`n`n" +
    "HANDOFF:`n" +
    "If context filling up: write state to .claude/handoffs/Claude-3.md. Exit cleanly.`n`n" +
    "You are the quality gate. Nothing ships without your verification."

$prompt4 = "You are Claude-4 (Polish/Review) working on: $goal`n`n" +
    "FIRST: Read AGENTS.md, tasks/lessons.md, then tasks/TASKS.md.`n`n" +
    "$sharedRules`n`n" +
    "ROLE-SPECIFIC RULES (read ALL of these - you review all domains):`n`n" +
    "$backendRules`n`n$frontendRules`n`n$testingRules`n`n$windowsRules`n`n$securityRules`n`n" +
    "YOUR WORKFLOW:`n" +
    "1. Read tasks/lessons.md - internalize ALL past mistakes and patterns`n" +
    "2. SKILL UP: Search for skills relevant to your review/polish tasks:`n" +
    "   - Run: npx skills find <query> for 2-3 queries based on the tech stack (e.g. 'code review', 'security', 'best practices', 'documentation')`n" +
    "   - Install useful skills: npx skills add <owner/repo@skill> -g -y`n" +
    "   - Do this once at session start to equip yourself with domain expertise`n" +
    "3. WEB RESEARCH: Use a subagent to search the web for best practices relevant to your tasks:`n" +
    "   - Search for: '$techStack code review checklist 2026', 'security best practices $techStack', 'production readiness checklist'`n" +
    "   - Focus on: code review standards, security hardening, documentation practices, production readiness`n" +
    "   - Write a brief summary of findings to tasks/todo.md under ## Claude-4 Research Findings`n" +
    "   - Do this once at session start to ground your work in current best practices`n" +
    "4. Start with documentation, code review, and polish tasks immediately`n" +
    "5. Check for tests-passing.signal before doing final integration review. If not present, review what is available so far`n" +
    "6. Find the ## Claude-4 section in tasks/TASKS.md`n" +
    "7. REVIEW: For each completed task across ALL agents:`n" +
    "   - Check code quality: Would a staff engineer approve this?`n" +
    "   - Look for hacky fixes - if found, demand the elegant solution`n" +
    "   - Verify tests actually test the right things`n" +
    "   - Check for consistency across agent work`n" +
    "8. VERIFY: Run full test suite one final time`n" +
    "9. Mark [x] only after review is thorough`n" +
    "10. Log to logs/activity.log: [Claude-4] Done: <task>`n" +
    "11. Update .claude/heartbeats/Claude-4.heartbeat`n" +
    "12. Consolidate lessons: review tasks/lessons.md, deduplicate, sharpen rules`n`n" +
    "FINAL TASKS:`n" +
    "When ALL agents tasks are complete:`n" +
    "1. Create .claude/signals/phase-complete.signal`n" +
    "2. Generate next-swarm.ps1 that:`n" +
    "   - Analyzes what was built in this phase`n" +
    "   - Determines the next logical development phase`n" +
    "   - Generates a new tasks/TASKS.md with the next set of tasks`n" +
    "   - Calls .\swarm.ps1 -Resume -NoConfirm to relaunch the swarm`n" +
    "   - NOTE: Web research and skill discovery are baked into swarm.ps1 prompts - they auto-apply every phase`n" +
    "3. The supervisor will AUTO-LAUNCH next-swarm.ps1 after you signal phase-complete`n" +
    "4. Output COMPLETE-ALL`n`n" +
    "HANDOFF:`n" +
    "If context filling up: write state to .claude/handoffs/Claude-4.md. Exit cleanly.`n`n" +
    "You are the final quality gate and the bridge to the next swarm iteration."

$agents = @(
    @{ Name = "Claude-1"; Role = "Backend/Core";    Color = "Cyan";    WaitFor = "";               Prompt = $prompt1 },
    @{ Name = "Claude-2"; Role = "Frontend/Interface"; Color = "Magenta"; WaitFor = "backend-ready";  Prompt = $prompt2 },
    @{ Name = "Claude-3"; Role = "Integration/Testing"; Color = "Green";   WaitFor = "frontend-ready"; Prompt = $prompt3 },
    @{ Name = "Claude-4"; Role = "Polish/Review";    Color = "Yellow";  WaitFor = "tests-passing";  Prompt = $prompt4 }
)

# === WRITE PROMPT FILES ===
foreach ($agent in $agents) {
    $promptFile = ".claude/prompts/$($agent.Name).txt"

    # Try template-based generation first
    $config = $roleConfigs[$agent.Name]
    $templatePrompt = $null

    if ($config) {
        $templatePrompt = Build-PromptFromTemplate `
            -AgentName $agent.Name `
            -RoleTitle $config.RoleTitle `
            -Goal $goal `
            -TechStack $techStack `
            -RoleKey $config.RoleKey `
            -RuleFiles $config.RuleFiles
    }

    # Use template if available, otherwise fall back to legacy prompt
    if ($templatePrompt) {
        $templatePrompt | Out-File -FilePath $promptFile -Encoding UTF8
        Write-Host "  OK - Wrote $promptFile (template)" -ForegroundColor Gray
    } else {
        $agent.Prompt | Out-File -FilePath $promptFile -Encoding UTF8
        Write-Host "  OK - Wrote $promptFile (legacy)" -ForegroundColor Gray
    }
}

# === SETUP-ONLY MODE ===
if ($SetupOnly) {
    Write-Host ""
    Write-Host "  ===== SETUP COMPLETE (Setup-Only Mode) =====" -ForegroundColor Green
    Write-Host "  Prompt files written to .claude/prompts/" -ForegroundColor Gray
    Write-Host "  Backend will launch agents as subprocesses." -ForegroundColor Gray
    Write-Host ""
    exit 0
}

# === LAUNCH AGENTS ===
Write-Host ""
Write-Host "  Launching agents..." -ForegroundColor Yellow
Write-Host ""

$workDir = Get-Location

foreach ($agent in $agents) {
    $agentArgs = @(
        "-NoExit", "-Command",
        "cd '$workDir'; .\.claude\agent-loop.ps1 -AgentName '$($agent.Name)' -AgentRole '$($agent.Role)' -Prompt (Get-Content '.claude/prompts/$($agent.Name).txt' -Raw) -WaitForSignal '$($agent.WaitFor)' -Color '$($agent.Color)'"
    )

    Start-Process powershell -ArgumentList $agentArgs
    Write-Host "  OK - Launched $($agent.Name) ($($agent.Role))" -ForegroundColor $($agent.Color)
    Start-Sleep -Seconds 2
}

# Launch supervisor
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$workDir'; .\.claude\supervisor.ps1 -MaxPhases $MaxPhases"
Write-Host "  OK - Launched Supervisor (auto-chain up to $MaxPhases phases)" -ForegroundColor Magenta

# === DONE ===
Write-Host ""
Write-Host "  ===== SWARM LAUNCHED SUCCESSFULLY =====" -ForegroundColor Green
Write-Host ""
Write-Host "  Phase $currentPhase of $MaxPhases (auto-chains when complete)" -ForegroundColor White
Write-Host ""
Write-Host "  Monitor:" -ForegroundColor White
Write-Host "    .\watch.ps1          - Live dashboard" -ForegroundColor Gray
Write-Host "    tasks/TASKS.md       - Task progress" -ForegroundColor Gray
Write-Host "    tasks/lessons.md     - Self-improvement loop" -ForegroundColor Gray
Write-Host "    logs/activity.log    - Agent activity" -ForegroundColor Gray
Write-Host ""
Write-Host "  Control:" -ForegroundColor White
Write-Host "    .\stop-swarm.ps1     - Stop all agents" -ForegroundColor Gray
Write-Host "    .\swarm.ps1 -Resume  - Resume after stop" -ForegroundColor Gray
Write-Host "    -MaxPhases N         - Change auto-chain limit (default: 999)" -ForegroundColor Gray
Write-Host ""
