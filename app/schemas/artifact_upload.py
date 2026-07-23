from pydantic import BaseModel, Field


class ArtifactUploadForm(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., min_length=1, max_length=127)
    kind: str = "artifact"
    creator: str = "mcp_tool"
    cleanup_after_send: bool = False


class ArtifactUploadResponse(BaseModel):
    artifact_id: str
    filename: str
    mime_type: str
    size_bytes: int
    created_at: str
    expires_at: str
    cleanup_after_send: bool = False
