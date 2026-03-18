<#
.SYNOPSIS
    Message bus CLI client for Claude agents.

.DESCRIPTION
    Provides commands for inter-agent messaging via the Latent Underground message bus.
    Reads configuration from .swarm/bus.json in the current working directory.

.PARAMETER Command
    The command to execute: send, inbox, ack, lesson, channel

.PARAMETER To
    Target agent for send command (e.g., 'Claude-2', 'all')

.PARAMETER Channel
    Message channel (general, critical, review, handoff, lessons)

.PARAMETER Priority
    Message priority (low, normal, high, critical)

.PARAMETER Body
    Message body text

.PARAMETER Since
    ISO timestamp for filtering inbox messages

.PARAMETER MessageId
    Message ID for ack command

.EXAMPLE
    .\swarm-msg.ps1 send --to Claude-2 --body "API ready"

.EXAMPLE
    .\swarm-msg.ps1 inbox

.EXAMPLE
    .\swarm-msg.ps1 ack <message-id>

.EXAMPLE
    .\swarm-msg.ps1 lesson "Always run typecheck before commit"
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet("send", "inbox", "ack", "lesson", "channel", "sync-lessons", "help")]
    [string]$Command = "help",

    [string]$To,

    [string]$Channel = "general",

    [ValidateSet("low", "normal", "high", "critical")]
    [string]$Priority = "normal",

    [Alias("b")]
    [string]$Body,

    [string]$Since,

    [Alias("id")]
    [string]$MessageId,

    [switch]$Help
)

# --- Configuration ---

function Get-BusConfig {
    <#
    .SYNOPSIS
        Load bus configuration from .swarm/bus.json
    #>
    $configPath = Join-Path (Join-Path (Get-Location) ".swarm") "bus.json"
    if (-not (Test-Path $configPath)) {
        Write-Error "Bus config not found at $configPath. Is the swarm running?"
        exit 1
    }

    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
        return $config
    }
    catch {
        Write-Error "Failed to parse bus config: $_"
        exit 1
    }
}

function Get-AgentName {
    <#
    .SYNOPSIS
        Get the current agent name from environment or prompt file name
    #>
    # Check AGENT_NAME env var first
    if ($env:AGENT_NAME) {
        return $env:AGENT_NAME
    }

    # Fall back to extracting from prompt file path
    $promptDir = Join-Path (Join-Path (Get-Location) ".claude") "prompts"
    if (Test-Path $promptDir) {
        $promptFiles = Get-ChildItem -Path $promptDir -Filter "Claude-*.txt"
        if ($promptFiles.Count -gt 0) {
            # Use the first one as default
            return $promptFiles[0].BaseName
        }
    }

    # Default fallback
    return "unknown-agent"
}

function Invoke-BusApi {
    <#
    .SYNOPSIS
        Make a request to the bus API
    #>
    param(
        [string]$Method,
        [string]$Endpoint,
        [object]$Body = $null
    )

    $config = Get-BusConfig
    $baseUrl = "http://127.0.0.1:$($config.port)/api/bus/$($config.project_id)"
    $url = "$baseUrl$Endpoint"

    $params = @{
        Uri         = $url
        Method      = $Method
        ContentType = "application/json"
    }

    # Add API key if configured
    if ($config.api_key) {
        $params["Headers"] = @{
            "Authorization" = "Bearer $($config.api_key)"
        }
    }

    if ($Body) {
        $params["Body"] = ($Body | ConvertTo-Json -Compress)
    }

    try {
        $response = Invoke-RestMethod @params
        return $response
    }
    catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        $errorBody = $_.ErrorDetails.Message
        Write-Error "API error ($statusCode): $errorBody"
        exit 1
    }
}

# --- Commands ---

function Send-Message {
    param(
        [string]$To,
        [string]$Channel,
        [string]$Priority,
        [string]$Body,
        [string]$MsgType = "info"
    )

    if (-not $To) {
        Write-Error "Missing --to parameter. Usage: swarm-msg send --to <agent|all> --body <text>"
        exit 1
    }

    if (-not $Body) {
        Write-Error "Missing --body parameter. Usage: swarm-msg send --to <agent|all> --body <text>"
        exit 1
    }

    $agentName = Get-AgentName

    $payload = @{
        from_agent = $agentName
        to_agent   = $To
        channel    = $Channel
        priority   = $Priority
        msg_type   = $MsgType
        body       = $Body
    }

    $result = Invoke-BusApi -Method "POST" -Endpoint "/send" -Body $payload

    Write-Host "[OK] Message sent to $To (id: $($result.id))" -ForegroundColor Green
}

function Get-Inbox {
    param(
        [string]$Since
    )

    $agentName = Get-AgentName
    $endpoint = "/inbox/$agentName"

    if ($Since) {
        # Parse relative times like "5m", "1h", "30s"
        if ($Since -match '^(\d+)([smh])$') {
            $amount = [int]$Matches[1]
            $unit = $Matches[2]

            $now = Get-Date
            switch ($unit) {
                "s" { $since_dt = $now.AddSeconds(-$amount) }
                "m" { $since_dt = $now.AddMinutes(-$amount) }
                "h" { $since_dt = $now.AddHours(-$amount) }
            }
            $Since = $since_dt.ToString("yyyy-MM-ddTHH:mm:ss")
        }

        $endpoint += "?since=$Since"
    }

    $result = Invoke-BusApi -Method "GET" -Endpoint $endpoint

    if ($result.messages.Count -eq 0) {
        Write-Host "[INBOX] No new messages" -ForegroundColor Cyan
        return
    }

    Write-Host "[INBOX] $($result.total) message(s)" -ForegroundColor Cyan
    Write-Host ""

    foreach ($msg in $result.messages) {
        $priorityColor = switch ($msg.priority) {
            "critical" { "Red" }
            "high"     { "Yellow" }
            "normal"   { "White" }
            "low"      { "Gray" }
            default    { "White" }
        }

        Write-Host "[$($msg.channel.ToUpper())] " -ForegroundColor Magenta -NoNewline
        Write-Host "$($msg.from_agent) -> $($msg.to_agent) " -ForegroundColor Cyan -NoNewline
        Write-Host "($($msg.priority))" -ForegroundColor $priorityColor
        Write-Host "  $($msg.body)"
        Write-Host "  ID: $($msg.id) | $($msg.created_at)" -ForegroundColor DarkGray
        Write-Host ""
    }
}

function Ack-Message {
    param(
        [string]$MessageId
    )

    if (-not $MessageId) {
        Write-Error "Missing message ID. Usage: swarm-msg ack <message-id>"
        exit 1
    }

    $agentName = Get-AgentName
    $result = Invoke-BusApi -Method "POST" -Endpoint "/ack/$MessageId`?agent=$agentName"

    if ($result.acked) {
        Write-Host "[OK] Message acknowledged" -ForegroundColor Green
    }
    else {
        Write-Host "[INFO] Message was already acknowledged" -ForegroundColor Yellow
    }
}

function Post-Lesson {
    param(
        [string]$Body
    )

    if (-not $Body) {
        Write-Error "Missing lesson text. Usage: swarm-msg lesson <text>"
        exit 1
    }

    $agentName = Get-AgentName

    $payload = @{
        from_agent = $agentName
        to_agent   = "channel:lessons"
        channel    = "lessons"
        priority   = "normal"
        msg_type   = "lesson"
        body       = $Body
    }

    $result = Invoke-BusApi -Method "POST" -Endpoint "/send" -Body $payload

    Write-Host "[OK] Lesson posted to #lessons channel (id: $($result.id))" -ForegroundColor Green
}

function Get-ChannelMessages {
    param(
        [string]$Channel,
        [string]$Since
    )

    $endpoint = "/channels/$Channel/messages"

    if ($Since) {
        $endpoint += "?since=$Since"
    }

    $result = Invoke-BusApi -Method "GET" -Endpoint $endpoint

    if ($result.messages.Count -eq 0) {
        Write-Host "[#$Channel] No messages" -ForegroundColor Cyan
        return
    }

    Write-Host "[#$Channel] $($result.total) message(s)" -ForegroundColor Cyan
    Write-Host ""

    foreach ($msg in $result.messages) {
        Write-Host "$($msg.from_agent): " -ForegroundColor Yellow -NoNewline
        Write-Host "$($msg.body)"
        Write-Host "  $($msg.created_at)" -ForegroundColor DarkGray
        Write-Host ""
    }
}

function Sync-LessonsToFile {
    <#
    .SYNOPSIS
        Sync lessons from message bus to tasks/lessons.md
    #>
    $lessonsFile = "tasks/lessons.md"
    $phaseFile = ".claude/swarm-phase.json"

    # Read last sync timestamp
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

    # Query lessons from bus
    $result = Invoke-BusApi -Method "GET" -Endpoint "/channels/lessons/messages$since"

    if (-not $result.messages -or $result.messages.Count -eq 0) {
        Write-Host "[SYNC] No new lessons to sync" -ForegroundColor Cyan
        return
    }

    # Ensure lessons file exists
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

    # Read existing for dedup
    $existingContent = Get-Content $lessonsFile -Raw
    $syncCount = 0
    $latestTimestamp = ""

    foreach ($msg in $result.messages) {
        $bodyTrimmed = $msg.body.Trim()

        if ($existingContent -and $existingContent.Contains($bodyTrimmed)) {
            if ($msg.created_at -gt $latestTimestamp) { $latestTimestamp = $msg.created_at }
            continue
        }

        $title = $bodyTrimmed
        if ($title.Length -gt 60) { $title = $title.Substring(0, 57) + "..." }

        $agentName = $msg.from_agent
        if (-not $agentName) { $agentName = "Unknown" }

        $entry = @"

### [$agentName] $title
- What happened: $bodyTrimmed
- Source: bus message $($msg.id) at $($msg.created_at)
"@

        Add-Content -Path $lessonsFile -Value $entry -Encoding UTF8
        $syncCount++
        if ($msg.created_at -gt $latestTimestamp) { $latestTimestamp = $msg.created_at }
        $existingContent += $entry
    }

    # Update sync timestamp
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
            Write-Host "[WARN] Failed to update sync timestamp: $_" -ForegroundColor Yellow
        }
    }

    Write-Host "[SYNC] Synced $syncCount new lesson(s) to $lessonsFile" -ForegroundColor Green
}

function Show-Help {
    Write-Host ""
    Write-Host "swarm-msg - Message bus CLI for Claude agents" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Yellow
    Write-Host "  send          Send a message to an agent or channel"
    Write-Host "  inbox         Check your inbox for pending messages"
    Write-Host "  ack           Acknowledge a message"
    Write-Host "  lesson        Post a lesson to the #lessons channel"
    Write-Host "  channel       Read messages from a channel"
    Write-Host "  sync-lessons  Sync lessons from bus to tasks/lessons.md"
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  swarm-msg send --to <agent|all> --body <text> [--channel <ch>] [--priority <p>]"
    Write-Host "  swarm-msg send --to all --channel critical --priority high --body ""STOP: issue"""
    Write-Host "  swarm-msg inbox [--since <time>]"
    Write-Host "  swarm-msg inbox --since 5m"
    Write-Host "  swarm-msg ack <message-id>"
    Write-Host "  swarm-msg lesson ""What I learned..."""
    Write-Host "  swarm-msg channel lessons [--since <time>]"
    Write-Host ""
    Write-Host "Channels:" -ForegroundColor Yellow
    Write-Host "  general   - Default coordination (default)"
    Write-Host "  critical  - Urgent issues, stop signals"
    Write-Host "  review    - Code review requests"
    Write-Host "  handoff   - Task handoffs between agents"
    Write-Host "  lessons   - Shared learnings"
    Write-Host ""
    Write-Host "Priorities:" -ForegroundColor Yellow
    Write-Host "  low       - Background info"
    Write-Host "  normal    - Standard messages (default)"
    Write-Host "  high      - Important, creates attention file"
    Write-Host "  critical  - Urgent, creates attention file"
    Write-Host ""
}

# --- Main ---

switch ($Command) {
    "send" {
        Send-Message -To $To -Channel $Channel -Priority $Priority -Body $Body
    }
    "inbox" {
        Get-Inbox -Since $Since
    }
    "ack" {
        Ack-Message -MessageId $MessageId
    }
    "lesson" {
        Post-Lesson -Body $Body
    }
    "sync-lessons" {
        Sync-LessonsToFile
    }
    "channel" {
        Get-ChannelMessages -Channel $Channel -Since $Since
    }
    "help" {
        Show-Help
    }
    default {
        Show-Help
    }
}
