FROM python:3.10-slim-trixie@sha256:6ff506466f8b1e981719b468cc0023b8ef000b983cdec0eafe119d01f379e31d AS beats-builder

ENV PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

WORKDIR /opt/chordsync/app

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /opt/chordsync/app/requirements.txt
COPY analysis/beats/requirements.txt /opt/chordsync/app/analysis/beats/requirements.txt

# madmom 0.16.1 requires its legacy Cython toolchain and Python 3.10 headers.
RUN python -m venv /opt/chordsync/venvs/beats \
    && /opt/chordsync/venvs/beats/bin/pip install --no-cache-dir \
        Cython==0.29.37 numpy==1.26.4 setuptools==80.10.2 \
    && /opt/chordsync/venvs/beats/bin/pip install --no-build-isolation --no-cache-dir \
        --requirement analysis/beats/requirements.txt

FROM python:3.11-slim-trixie@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/chordsync/venvs/backend/bin:/usr/local/bin:/usr/bin:/bin \
    CHORDSYNC_API_PYTHON=/opt/chordsync/venvs/backend/bin/python \
    CHORDSYNC_BTC_PYTHON=/opt/chordsync/venvs/btc/bin/python \
    CHORDSYNC_BTC_SOURCE=/opt/chordsync/models/btc/source \
    CHORDSYNC_BTC_CHECKPOINT=/opt/chordsync/models/btc/btc_model.pt \
    CHORDSYNC_BEAT_PYTHON=/opt/chordsync/venvs/beats/bin/python \
    CHORDSYNC_WHISPERX_EXECUTABLE=/opt/chordsync/venvs/whisperx/bin/whisperx \
    CHORDSYNC_DEMUCS_EXECUTABLE=/opt/chordsync/venvs/demucs/bin/demucs \
    CHORDSYNC_WORKSPACE_ROOT=/tmp/chordsync \
    TORCH_HOME=/opt/chordsync/cache/torch \
    HF_HOME=/opt/chordsync/cache/huggingface \
    XDG_CACHE_HOME=/opt/chordsync/cache

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential \
        ffmpeg \
        libffi-dev \
        libsndfile1 \
        libsndfile1-dev \
        pkg-config \
        rubberband-cli \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

WORKDIR /opt/chordsync/app

COPY requirements.txt /opt/chordsync/app/requirements.txt
COPY backend/api/requirements-runtime.txt /opt/chordsync/app/backend/api/requirements-runtime.txt
COPY analysis/chords/btc/requirements.txt /opt/chordsync/app/analysis/chords/btc/requirements.txt
COPY analysis/beats/requirements.txt /opt/chordsync/app/analysis/beats/requirements.txt
COPY analysis/lyrics/requirements-whisperx.txt /opt/chordsync/app/analysis/lyrics/requirements-whisperx.txt
COPY analysis/separation/requirements.txt /opt/chordsync/app/analysis/separation/requirements.txt

RUN python -m venv /opt/chordsync/venvs/backend \
    && /opt/chordsync/venvs/backend/bin/pip install --no-cache-dir --requirement backend/api/requirements-runtime.txt

RUN python -m venv /opt/chordsync/venvs/btc \
    && /opt/chordsync/venvs/btc/bin/pip install --no-cache-dir --requirement analysis/chords/btc/requirements.txt

RUN --mount=type=cache,target=/opt/chordsync/cache/pip \
    python -m venv /opt/chordsync/venvs/whisperx \
    && /opt/chordsync/venvs/whisperx/bin/pip install --requirement analysis/lyrics/requirements-whisperx.txt

RUN --mount=type=cache,target=/opt/chordsync/cache/pip \
    python -m venv /opt/chordsync/venvs/demucs \
    && /opt/chordsync/venvs/demucs/bin/pip install --requirement analysis/separation/requirements.txt

COPY --from=beats-builder /usr/local/bin/python3.10 /usr/local/bin/python3.10
COPY --from=beats-builder /usr/local/lib/libpython3.10.so.1.0 /usr/local/lib/libpython3.10.so.1.0
COPY --from=beats-builder /usr/local/lib/python3.10 /usr/local/lib/python3.10
COPY --from=beats-builder /opt/chordsync/venvs/beats /opt/chordsync/venvs/beats

COPY analysis /opt/chordsync/app/analysis
COPY backend /opt/chordsync/app/backend

RUN ln -sfn /usr/local/bin/python3.10 /opt/chordsync/venvs/beats/bin/python \
    && /usr/sbin/groupadd --system chordsync \
    && /usr/sbin/useradd --system --gid chordsync --home-dir /opt/chordsync --no-create-home chordsync \
    && mkdir -p \
        /opt/chordsync/cache/huggingface \
        /opt/chordsync/cache/torch \
        /opt/chordsync/models/btc/source \
        /tmp/chordsync \
    && chown -R chordsync:chordsync /opt/chordsync/cache /opt/chordsync/models /tmp/chordsync

USER chordsync

CMD ["python", "-m", "backend.api.app.analysis_worker_consumer", "--once"]
