from fastapi import APIRouter, UploadFile, File

from backend.api.app.models.audio import AudioUploadResponse
from backend.api.app.services.audio_ingestion import save_audio_file


router = APIRouter(
    prefix="/api/v1/audio",
    tags=["Audio"],
)


@router.post(
    "/upload",
    response_model=AudioUploadResponse,
)
def upload_audio(file: UploadFile = File(...)):
    return save_audio_file(file)
