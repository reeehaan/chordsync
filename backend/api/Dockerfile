# ChordSync API image: the lightweight HTTP API, for AWS Lambda (through AWS
# Lambda Web Adapter) or a plain container. The ML pipeline is packaged
# separately in backend/worker/Dockerfile and is never installed here.

# AWS Lambda Web Adapter 1.1.0, pinned by index digest. Outside Lambda the
# extension is inert, so the same image also runs with `docker run`.
FROM public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0@sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1 AS lambda-adapter

FROM python:3.11-slim-trixie@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHORDSYNC_API_HOSTING_MODE=lambda \
    CHORDSYNC_RUNTIME_MODE=aws \
    CHORDSYNC_DISPATCH_MODE=queue \
    CHORDSYNC_API_STAGING_ROOT=/tmp/chordsync-api \
    AWS_LWA_PORT=8000 \
    AWS_LWA_READINESS_CHECK_PATH=/health

# No ffmpeg or ffprobe here: uploads are validated in Python
# (backend/api/app/services/media_inspection.py), which keeps the media codec
# stack and its native libraries out of the internet-facing image. The ML
# worker image has its own ffmpeg.

WORKDIR /app

COPY backend/api/requirements-runtime.txt /tmp/
# pip, setuptools and wheel are build tooling only; removing them (pip last)
# drops their scanner findings from the runtime image.
RUN python -m pip install --no-cache-dir --requirement /tmp/requirements-runtime.txt \
    && python -m pip uninstall --yes setuptools wheel pip \
    && rm /tmp/requirements-runtime.txt

COPY --from=lambda-adapter /lambda-adapter /opt/extensions/lambda-adapter
COPY analysis ./analysis
COPY backend ./backend

# Lambda runs the image as an unprivileged user and only /tmp is writable, so
# application files are root-owned and world-readable, never writable.
RUN chmod -R a+rX,go-w /app \
    && useradd --system --uid 10001 --no-create-home --home-dir /nonexistent chordsync

USER 10001

# Port 8000: Lambda's local emulator (RIE) occupies 8080 inside the container.
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
