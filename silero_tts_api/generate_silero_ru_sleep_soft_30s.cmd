@echo off
setlocal
cd /d "%~dp0\.."
set PYTHONUTF8=1
if exist ".venv-silero\Scripts\python.exe" (
  ".venv-silero\Scripts\python.exe" silero_tts_api\generate_silero_ru.py --text-file silero_tts_api\sample_ru_soft_female_30s.txt --output silero_tts_api\outputs\silero_ru_30s_sleep_soft_baya.wav --speaker baya --sample-rate 48000 --device cpu --realism-enabled --preset sleep_soft --pause-scale 0.90 --breath-amount 0.0 --room-tone on --loudness-variation 0.11 --seed 42 --speed 0.90 --soften on --target-peak 0.76 --tone-softening 0.34 --sleep-softness 0.55
) else (
  python silero_tts_api\generate_silero_ru.py --text-file silero_tts_api\sample_ru_soft_female_30s.txt --output silero_tts_api\outputs\silero_ru_30s_sleep_soft_baya.wav --speaker baya --sample-rate 48000 --device cpu --realism-enabled --preset sleep_soft --pause-scale 0.90 --breath-amount 0.0 --room-tone on --loudness-variation 0.11 --seed 42 --speed 0.90 --soften on --target-peak 0.76 --tone-softening 0.34 --sleep-softness 0.55
)
