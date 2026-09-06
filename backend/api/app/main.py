from fastapi import FastAPI

from backend.api.app.routers.audio import router as audio_router


app = FastAPI(
    title="ChordSync API",
    version="0.1.0",
)


app.include_router(audio_router)


@app.get("/")
def root():
    return {
        "name": "ChordSync API",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }
