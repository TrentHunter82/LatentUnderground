from pydantic import BaseModel, Field
from typing import Literal, Optional, Union

# Valid project status values
VALID_STATUSES = ("created", "running", "stopped", "completed", "error")


class ProjectCreate(BaseModel):
    """Create a new project to manage with Claude Swarm."""
    name: str = Field(min_length=1, max_length=200, examples=["My Web App"])
    goal: str = Field(min_length=1, max_length=2000, examples=["Build a task management dashboard with React + FastAPI"])
    project_type: str = Field(default="Web Application (frontend + backend)", max_length=200, examples=["Web Application (frontend + backend)"])
    tech_stack: str = Field(default="auto-detect based on project type", max_length=200, examples=["Python + FastAPI + React"])
    complexity: str = Field(default="Medium", max_length=50, examples=["Medium"])
    requirements: str = Field(default="", max_length=5000, examples=["Must include authentication and real-time updates"])
    folder_path: str = Field(min_length=1, max_length=500, examples=["F:/Projects/MyWebApp"])


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    goal: Optional[str] = Field(None, max_length=2000)
    project_type: Optional[str] = Field(None, max_length=200)
    tech_stack: Optional[str] = Field(None, max_length=200)
    complexity: Optional[str] = Field(None, max_length=50)
    requirements: Optional[str] = Field(None, max_length=5000)
    folder_path: Optional[str] = Field(None, min_length=1, max_length=500)
    status: Optional[Literal["created", "running", "stopped", "completed", "error"]] = Field(
        None, description="Project status (created, running, stopped, completed, error)",
    )


class GuardrailRule(BaseModel):
    """A single guardrail validation rule applied to swarm output."""
    type: Literal["regex_match", "regex_reject", "min_lines", "max_errors"] = Field(
        ..., description="Rule type: regex_match (require pattern), regex_reject (reject pattern), "
                        "min_lines (minimum output lines), max_errors (max error count)",
    )
    pattern: Optional[str] = Field(
        None, max_length=200,
        description="Regex pattern (required for regex_match and regex_reject types)",
    )
    threshold: Optional[int] = Field(
        None, ge=0,
        description="Numeric threshold (required for min_lines and max_errors types)",
    )
    action: Literal["warn", "halt"] = Field(
        "warn", description="Action on violation: warn (emit event, continue) or halt (fail run, stop chaining)",
    )


class ProjectConfig(BaseModel):
    """Project agent configuration: control swarm behavior."""
    agent_count: Optional[int] = Field(None, ge=1, le=16, examples=[4])
    max_phases: Optional[int] = Field(None, ge=1, le=24, examples=[12])
    custom_prompts: Optional[str] = Field(None, max_length=5000)
    auto_stop_minutes: Optional[int] = Field(
        None, ge=0, le=1440,
        description="Auto-stop swarm if no output for N minutes (0 = disabled)",
        examples=[0],
    )
    # Resource quotas (None = unlimited)
    max_agents_concurrent: Optional[int] = Field(
        None, ge=1, le=20,
        description="Max concurrent agents (1-20, None = unlimited)",
    )
    max_duration_hours: Optional[float] = Field(
        None, ge=0.5, le=48,
        description="Max swarm duration in hours (0.5-48, None = unlimited)",
    )
    max_restarts_per_agent: Optional[int] = Field(
        None, ge=0, le=10,
        description="Max restarts per agent (0-10, None = unlimited)",
    )
    # Circuit breaker for agent restart protection
    circuit_breaker_max_failures: Optional[int] = Field(
        None, ge=1, le=10,
        description="Max failures within window before circuit opens (1-10, None = disabled)",
    )
    circuit_breaker_window_seconds: Optional[int] = Field(
        None, ge=60, le=3600,
        description="Failure counting window in seconds (60-3600, None = 300)",
    )
    circuit_breaker_recovery_seconds: Optional[int] = Field(
        None, ge=30, le=600,
        description="Wait time before half-open probe attempt (30-600, None = 60)",
    )
    # Output guardrails (None = disabled)
    guardrails: Optional[list[GuardrailRule]] = Field(
        None,
        description="Output guardrail rules validated when all agents exit (None = disabled)",
        max_length=20,
    )


class ProjectOut(BaseModel):
    id: int
    name: str
    goal: str
    project_type: str
    tech_stack: str
    complexity: str
    requirements: str
    folder_path: str
    status: str
    swarm_pid: Optional[int] = None
    config: Optional[str] = None
    archived_at: Optional[str] = None
    created_at: str
    updated_at: str
