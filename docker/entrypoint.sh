#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-/app:/app/xtts_api:/app/fish_speech_api:/app/silero_tts_api}"
export PYTHONUTF8="${PYTHONUTF8:-1}"
export COQUI_TOS_AGREED="${COQUI_TOS_AGREED:-1}"
export XTTS_PORT="${XTTS_PORT:-7870}"
export SILERO_PORT="${SILERO_PORT:-7866}"
export FISH_PORT="${FISH_PORT:-7865}"
export XTTS_DEVICE="${XTTS_DEVICE:-auto}"
export SILERO_DEVICE="${SILERO_DEVICE:-cpu}"
export SILERO_API_URL="${SILERO_API_URL:-http://127.0.0.1:${SILERO_PORT}}"
export COMFYUI_AUTOSTART="${COMFYUI_AUTOSTART:-0}"
export FISH_BACKEND="${FISH_BACKEND:-placeholder}"
export FISH_OUTPUT_DIR="${FISH_OUTPUT_DIR:-/app/fish_speech_api/outputs}"

mkdir -p \
  /app/xtts_api/studio_projects \
  /app/xtts_api/reference_audio \
  /app/fish_speech_api/outputs \
  /app/silero_tts_api/outputs \
  "${TTS_HOME:-/models/coqui}" \
  "${TORCH_HOME:-/models/torch}" \
  "${HF_HOME:-/models/huggingface}" \
  "${XDG_CACHE_HOME:-/models/cache}"

if [ ! -f /app/fish_speech_api/config.json ]; then
  cp /app/fish_speech_api/config.example.json /app/fish_speech_api/config.json
fi

python - <<'PY'
import json
import os
from pathlib import Path

path = Path("/app/fish_speech_api/config.json")
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    data = {}
data["host"] = "0.0.0.0"
data["port"] = int(os.environ.get("FISH_PORT", "7865"))
data["backend"] = os.environ.get("FISH_BACKEND", "placeholder")
data["output_dir"] = os.environ.get("FISH_OUTPUT_DIR", "/app/fish_speech_api/outputs")
path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
PY

pids=()

start_service() {
  local name="$1"
  shift
  echo "Starting ${name}: $*"
  "$@" &
  pids+=("$!")
}

stop_services() {
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap stop_services EXIT INT TERM

if [ "${START_SILERO:-1}" != "0" ]; then
  start_service "Silero API" bash -lc "cd /app/silero_tts_api && exec python -m uvicorn server:app --host 0.0.0.0 --port ${SILERO_PORT}"
fi

if [ "${START_FISH:-1}" != "0" ]; then
  start_service "Fish Speech API" bash -lc "cd /app/fish_speech_api && exec python -m uvicorn server:app --host 0.0.0.0 --port ${FISH_PORT}"
fi

if [ "${START_XTTS:-1}" != "0" ]; then
  start_service "XTTS Studio" bash -lc "cd /app && exec python -m uvicorn xtts_api.studio_server:app --host 0.0.0.0 --port ${XTTS_PORT}"
fi

if [ "${#pids[@]}" -eq 0 ]; then
  echo "No services enabled. Set START_XTTS, START_SILERO, or START_FISH to 1."
  exit 1
fi

set +e
wait -n "${pids[@]}"
exit_code="$?"
set -e
stop_services
exit "$exit_code"
