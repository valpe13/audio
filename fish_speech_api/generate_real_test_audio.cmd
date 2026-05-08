@echo off
setlocal
cd /d "%~dp0\.."
C:\fish_speech_runtime_test\venv\Scripts\python.exe fish_speech_api\audio_workflow.py --config fish_speech_api\config.json --text-file fish_speech_api\sample_russian_sleep_lecture.txt --output fish_speech_api\outputs\russian_sleep_lecture_fish_speech_real_test.wav --max-chars 80 --no-mp3
endlocal
