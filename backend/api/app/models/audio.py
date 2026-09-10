from pydantic import BaseModel


class AudioUploadResponse(BaseModel):
    id: str
    original_filename: str
    stored_filename: str
    extension: str
    content_type: str | None
    size_bytes: int
    sha256: str
    status: str
