from fastapi import FastAPI

app = FastAPI(
    title="ChordSync API",
    version="0.1.0",
)


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
