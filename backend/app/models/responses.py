"""Pydantic response models for all API endpoints.

These models serve two purposes:
1. Generate accurate OpenAPI schema documentation
2. Validate/filter response data before sending to clients
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Common ---

class ErrorDetail(BaseModel):
    """Standard error response body."""
    detail: str


# --- Project Stats & Analytics ---

class ProjectStatsOut(BaseModel):
    project_id: int
    total_runs: int
    avg_duration_seconds: Optional[int] = None
    total_tasks_completed: int


class RunTrend(BaseModel):
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    status: Optional[str] = None
    tasks_completed: Optional[int] = None


class ProjectAnalyticsOut(BaseModel):
    project_id: int
    total_runs: int
    avg_duration: Optional[int] = None
    total_tasks: int
    success_rate: Optional[float] = None
    run_trends: list[RunTrend]


class ProjectConfigUpdateOut(BaseModel):
    project_id: int
    config: dict[str, Any]


class RecentRunSummary(BaseModel):
    id: int
    status: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = None


class BulkArchiveRequest(BaseModel):
    project_ids: list[int] = Field(min_length=1, max_length=50)


class BulkArchiveOut(BaseModel):
    archived: list[int] = Field(default_factory=list)
    already_archived: list[int] = Field(default_factory=list)
    not_found: list[int] = Field(default_factory=list)


class BulkUnarchiveOut(BaseModel):
    unarchived: list[int] = Field(default_factory=list)
    not_archived: list[int] = Field(default_factory=list)
    not_found: list[int] = Field(default_factory=list)


# --- Swarm ---

class SwarmLaunchOut(BaseModel):
    status: str
    pid: int
    project_id: int
    agents_launched: list[str] = Field(default_factory=list)
    agents_failed: list[str] = Field(default_factory=list)


class SwarmStopOut(BaseModel):
    status: str
    project_id: int


class SwarmInputOut(BaseModel):
    status: str
    project_id: int


class AgentHeartbeat(BaseModel):
    name: str
    last_heartbeat: Optional[str] = None


class TaskProgress(BaseModel):
    total: int = 0
    done: int = 0
    percent: float = 0


class SwarmStatusOut(BaseModel):
    project_id: int
    status: str
    swarm_pid: Optional[int] = None
    process_alive: bool
    agents: list[AgentHeartbeat]
    signals: dict[str, bool]
    tasks: TaskProgress
    phase: Optional[dict[str, Any]] = None


class SwarmOutputOut(BaseModel):
    project_id: int
    offset: int
    limit: int
    total: int
    next_offset: int
    has_more: bool
    lines: list[str]
    agent: Optional[str] = None


class AgentStatusOut(BaseModel):
    name: str
    pid: Optional[int] = None
    alive: bool
    exit_code: Optional[int] = None
    output_lines: int = 0
    started_at: Optional[str] = None
    supports_stdin: bool = False
    circuit_state: Optional[str] = None


class AgentsListOut(BaseModel):
    project_id: int
    agents: list[AgentStatusOut]


class AgentStopOut(BaseModel):
    agent: str
    project_id: int
    status: str


class ProjectDashboardOut(BaseModel):
    """Combined dashboard data in a single response to reduce frontend round-trips."""
    project_id: int
    name: str
    status: str
    folder_path: str
    # Agent info
    agents: list[AgentStatusOut]
    any_alive: bool
    # Task progress
    tasks: TaskProgress
    # Run stats
    total_runs: int
    avg_duration_seconds: Optional[int] = None
    success_rate: Optional[float] = None
    recent_runs: list[RecentRunSummary]
    # Output summary
    output_line_count: int
    last_output_lines: list[str] = Field(default_factory=list)


class AgentMetric(BaseModel):
    name: str
    pid: Optional[int] = None
    alive: bool
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None
    memory_percent: Optional[float] = None
    threads: Optional[int] = None
    uptime_seconds: Optional[int] = None


class AgentMetricsOut(BaseModel):
    project_id: int
    agents: list[AgentMetric]
    psutil_available: bool = True


class SwarmRunOut(BaseModel):
    id: int
    project_id: int
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    status: Optional[str] = None
    phase: Optional[int] = None
    tasks_completed: Optional[int] = None
    task_summary: Optional[str] = None
    duration_seconds: Optional[int] = None
    label: Optional[str] = None
    notes: Optional[str] = None
    summary: Optional[dict[str, Any]] = None
    guardrail_results: Optional[list[dict[str, Any]]] = None


class SwarmHistoryOut(BaseModel):
    project_id: int
    runs: list[SwarmRunOut]


class SwarmRunAnnotationOut(BaseModel):
    id: int
    project_id: int
    label: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


# --- Agent Events ---

class AgentEventOut(BaseModel):
    id: int
    project_id: int
    run_id: Optional[int] = None
    agent_name: str
    event_type: str
    detail: str = ""
    timestamp: Optional[str] = None


class AgentEventsListOut(BaseModel):
    project_id: int
    events: list[AgentEventOut]
    total: int


# --- Run Summary ---

class RunSummaryOut(BaseModel):
    duration_seconds: Optional[int] = None
    agent_count: int = 0
    agents: dict[str, Any] = Field(default_factory=dict)
    total_output_lines: int = 0
    error_count: int = 0
    signals_created: list[str] = Field(default_factory=list)
    tasks_completed_percent: float = 0


# --- Output Search ---

class OutputSearchMatch(BaseModel):
    line_number: int
    text: str
    agent: Optional[str] = None
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)


class OutputSearchOut(BaseModel):
    project_id: int
    query: str
    total_matches: int
    matches: list[OutputSearchMatch]


# --- Run Comparison ---

class RunComparisonSide(BaseModel):
    run_id: int
    status: Optional[str] = None
    duration_seconds: Optional[int] = None
    agent_count: int = 0
    output_lines: int = 0
    error_count: int = 0


class RunComparisonOut(BaseModel):
    run_a: RunComparisonSide
    run_b: RunComparisonSide
    duration_delta_seconds: Optional[int] = None
    agent_count_delta: int = 0
    output_lines_delta: int = 0
    error_count_delta: int = 0


# --- Directives ---

class DirectiveOut(BaseModel):
    agent: str
    project_id: int
    status: str
    priority: str = "normal"


class DirectiveStatusOut(BaseModel):
    pending: bool
    text: Optional[str] = None
    queued_at: Optional[str] = None


class PromptUpdateOut(BaseModel):
    agent: str
    project_id: int
    old_prompt: str
    status: str


# --- Files ---

class FileReadOut(BaseModel):
    path: str
    content: str


class FileWriteOut(BaseModel):
    path: str
    status: str


# --- Logs ---

class AgentLogOut(BaseModel):
    agent: str
    lines: list[str]


class LogsOut(BaseModel):
    logs: list[AgentLogOut]


class LogSearchResult(BaseModel):
    text: str
    agent: str


class LogSearchOut(BaseModel):
    results: list[LogSearchResult]
    total: int


# --- Templates ---

class TemplateOut(BaseModel):
    id: int
    name: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# --- Browse ---

class BrowseDirEntry(BaseModel):
    name: str
    path: str


class BrowseOut(BaseModel):
    path: str
    parent: Optional[str] = None
    dirs: list[BrowseDirEntry]
    truncated: bool = False


# --- Plugins ---

class PluginOut(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0.0"
    config: dict[str, Any] = Field(default_factory=dict)
    hooks: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    source_path: str = ""


class PluginToggleOut(BaseModel):
    name: str
    enabled: bool


# --- Webhooks ---

class WebhookOut(BaseModel):
    id: int
    url: str
    events: list[str]
    has_secret: bool = False
    project_id: Optional[int] = None
    enabled: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# --- Watcher ---

class WatchStatusOut(BaseModel):
    status: str
    folder: str


# --- Health ---

class HealthOut(BaseModel):
    app: str
    version: str
    uptime_seconds: int
    status: str
    db: str
    active_processes: int


# --- System Metrics ---

class SystemInfoOut(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_mb: int
    memory_total_mb: int
    disk_percent: float
    disk_free_gb: float
    disk_total_gb: float
    python_version: str
    platform: str
    app_version: str
    uptime_seconds: int
    db_size_bytes: int
    cpu_count: int


# --- Resource Quotas ---

class QuotaConfig(BaseModel):
    max_agents_concurrent: Optional[int] = None
    max_duration_hours: Optional[float] = None
    max_restarts_per_agent: Optional[int] = None


class QuotaUsage(BaseModel):
    agent_count: int = 0
    restart_counts: dict[str, int] = Field(default_factory=dict)
    started_at: Optional[str] = None
    elapsed_hours: Optional[float] = None


class QuotaOut(BaseModel):
    project_id: int
    quota: QuotaConfig
    usage: QuotaUsage


# --- Health Trends ---

class ProjectHealthScore(BaseModel):
    project_id: int
    project_name: str
    crash_rate: float = 0.0
    error_density: float = 0.0
    avg_duration_seconds: Optional[int] = None
    status: str = "healthy"  # healthy | warning | critical
    trend: str = "stable"  # improving | degrading | stable
    total_runs_analyzed: int = 0


class HealthTrendsOut(BaseModel):
    projects: list[ProjectHealthScore]
    computed_at: str


class ProjectHealthOut(BaseModel):
    project_id: int
    crash_rate: float = 0.0
    error_density: float = 0.0
    avg_duration_seconds: Optional[int] = None
    status: str = "healthy"
    trend: str = "stable"
    run_count: int = 0


# --- Agent Checkpoints ---

class CheckpointOut(BaseModel):
    id: int
    project_id: int
    run_id: Optional[int] = None
    agent_name: str
    checkpoint_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None


class CheckpointsListOut(BaseModel):
    run_id: int
    checkpoints: list[CheckpointOut]
    total: int


# --- Guardrails ---

class GuardrailResultOut(BaseModel):
    rule_type: str
    pattern: Optional[str] = None
    threshold: Optional[int] = None
    action: str
    passed: bool
    detail: str = ""


class GuardrailValidationOut(BaseModel):
    project_id: int
    guardrails: list[dict[str, Any]] = Field(default_factory=list)
    last_results: Optional[list[GuardrailResultOut]] = None
    last_run_id: Optional[int] = None


# --- Agent Logs ---

class AgentLogLinesOut(BaseModel):
    """Response for per-agent log file retrieval."""
    project_id: int
    agent: str
    lines: list[str]
    total_lines: int
    log_file: Optional[str] = None


class OutputTailOut(BaseModel):
    """Response for tail of combined output buffer."""
    project_id: int
    lines: list[str]
    total: int
    agent: Optional[str] = None
