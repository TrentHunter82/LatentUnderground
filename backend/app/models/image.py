from pydantic import BaseModel, Field


class ImageReferenceOut(BaseModel):
    """An image reference attached to a project, returned to the frontend.

    Field names match what the React client consumes (``targetRoles`` camelCase,
    ``url`` for the thumbnail src). See frontend ProjectSettings.jsx.
    """
    id: str
    project_id: int
    filename: str  # original (human-readable) filename
    caption: str = ""
    targetRoles: list[str] = Field(default_factory=lambda: ["designer", "frontend"])
    url: str  # servable URL for the raw image bytes
    path: str  # relative path from project root (references/images/<id>.<ext>)
    created_at: str


class ImageUploadResponse(BaseModel):
    """Response after uploading a batch of image references."""
    uploaded: list[ImageReferenceOut] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
