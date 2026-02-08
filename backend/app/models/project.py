from pydantic import BaseModel, Field
from typing import Optional


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=2000)
    project_type: str = Field(default="Web Application (frontend + backend)", max_length=200)
    tech_stack: str = Field(default="auto-detect based on project type", max_length=200)
    complexity: str = Field(default="Medium", max_length=50)
    requirements: str = Field(default="", max_length=5000)
    folder_path: str = Field(min_length=1, max_length=500)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    goal: Optional[str] = Field(None, max_length=2000)
    project_type: Optional[str] = Field(None, max_length=200)
    tech_stack: Optional[str] = Field(None, max_length=200)
    complexity: Optional[str] = Field(None, max_length=50)
    requirements: Optional[str] = Field(None, max_length=5000)
    folder_path: Optional[str] = Field(None, min_length=1, max_length=500)
    status: Optional[str] = Field(None, max_length=50)


class ProjectConfig(BaseModel):
    agent_count: Optional[int] = Field(None, ge=1, le=16)
    max_phases: Optional[int] = Field(None, ge=1, le=24)
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
