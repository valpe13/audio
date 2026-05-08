@echo off
setlocal
cd /d "%~dp0\.."
set PYTHONUTF8=1
if exist ".venv-silero\Scripts\python.exe" (
  ".venv-silero\Scripts\python.exe" silero_tts_api\generate_silero_ru.py --text-file silero_tts_api\sample_ru_soft_female_30s.txt --output silero_tts_api\outputs\silero_ru_30s_soft_female_test.wav --speaker baya --sample-rate 48000 --device cpu
) else (
  python silero_tts_api\generate_silero_ru.py --text-file silero_tts_api\sample_ru_soft_female_30s.txt --output silero_tts_api\outputs\silero_ru_30s_soft_female_test.wav --speaker baya --sample-rate 48000 --device cpu
)

