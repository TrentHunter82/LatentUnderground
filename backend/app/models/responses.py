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


# --- Swarm ---

class SwarmLaunchOut(BaseModel):
    status: str
    pid: int
    project_id: int


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


class SwarmHistoryOut(BaseModel):
    project_id: int
    runs: list[SwarmRunOut]


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
