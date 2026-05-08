@echo off
setlocal
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" "%~dp0generate_xtts_v2_ru_sleep_slow.py" ^
  --reference "%~dp0reference_audio\natalia_shtin\natalia_shtin_clean_reference.wav" ^
  --output "%~dp0outputs\xtts_v2_ru_natalia_shtin_sleep_slow_test.wav" ^
  --temperature 0.58 ^
  --top-p 0.74 ^
  --top-k 30 ^
  --repetition-penalty 6.5 ^
  --speed 0.88 ^
  --pause 0.95 ^
  --crossfade 0.055
endlocal
