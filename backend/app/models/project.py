from pydantic import BaseModel, Field
from typing import Optional


class ProjectCreate(BaseModel):
    name: str
    goal: str
    project_type: str = "Web Application (frontend + backend)"
    tech_stack: str = "auto-detect based on project type"
    complexity: str = "Medium"
    requirements: str = ""
    folder_path: str


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    goal: Optional[str] = None
    project_type: Optional[str] = None
    tech_stack: Optional[str] = None
    complexity: Optional[str] = None
    requirements: Optional[str] = None
    folder_path: Optional[str] = None
    status: Optional[str] = None


class ProjectConfig(BaseModel):
    agent_count: Optional[int] = Field(None, ge=1, le=16)
    max_phases: Optional[int] = Field(None, ge=1, le=20)
    custom_prompts: Optional[str] = Field(None, max_length=5000)


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
    created_at: str
    updated_at: str
