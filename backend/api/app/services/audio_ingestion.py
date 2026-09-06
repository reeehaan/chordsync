from pathlib import Path
from uuid import uuid4
import hashlib
import shutil

from fastapi import UploadFile, HTTPException


ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a"}

UPLOAD_DIR = Path("storage/uploads")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def calculate_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def save_audio_file(upload_file: UploadFile) -> dict:
    original_filename = upload_file.filename

    if not original_filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format. Allowed: MP3, WAV, M4A.",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid4())
    stored_filename = f"{file_id}{extension}"
    destination = UPLOAD_DIR / stored_filename

    with destination.open("wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    size_bytes = destination.stat().st_size

    if size_bytes == 0:
        destination.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty.",
        )

    if size_bytes > MAX_FILE_SIZE:
        destination.unlink(missing_ok=True)

        raise HTTPException(
            status_code=413,
            detail="Audio file exceeds the 50 MB limit.",
        )

    sha256 = calculate_sha256(destination)

    return {
        "id": file_id,
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "extension": extension,
        "content_type": upload_file.content_type,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "status": "uploaded",
    }
