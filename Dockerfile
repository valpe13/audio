FROM python:3.10-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    COQUI_TOS_AGREED=1 \
    PIP_NO_CACHE_DIR=1 \
    TTS_HOME=/models/coqui \
    TORCH_HOME=/models/torch \
    HF_HOME=/models/huggingface \
    XDG_CACHE_HOME=/models/cache \
    PYTHONPATH=/app:/app/xtts_api:/app/fish_speech_api:/app/silero_tts_api

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        espeak-ng \
        ffmpeg \
        git \
        libgomp1 \
        libsndfile1 \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-docker.txt ./
RUN python -m pip install --upgrade "pip<26" "setuptools<81" wheel \
    && python -m pip install -r requirements-docker.txt \
    && python -c "import fastapi, soundfile, torch, torchaudio, TTS; print('docker deps ok', torch.__version__)"

COPY . .

RUN chmod +x docker/entrypoint.sh \
    && mkdir -p \
        /app/xtts_api/studio_projects \
        /app/xtts_api/reference_audio \
        /app/fish_speech_api/outputs \
        /app/silero_tts_api/outputs \
        /models/coqui \
        /models/torch \
        /models/huggingface \
        /models/cache

EXPOSE 7870 7866 7865

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -fsS http://127.0.0.1:7870/api/health >/dev/null || exit 1

ENTRYPOINT ["docker/entrypoint.sh"]
