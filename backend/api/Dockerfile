FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg=7:5.1.8-0+deb12u1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system chordsync \
    && useradd --system --gid chordsync --create-home chordsync

WORKDIR /app

COPY backend/api/requirements-runtime.txt /tmp/requirements-runtime.txt
RUN python -m pip install --no-cache-dir --requirement /tmp/requirements-runtime.txt

COPY analysis ./analysis
COPY backend ./backend

RUN mkdir -p /app/storage/uploads/analysis_jobs \
    && chown -R chordsync:chordsync /app/storage

USER chordsync

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["python", "-m", "uvicorn", "backend.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
