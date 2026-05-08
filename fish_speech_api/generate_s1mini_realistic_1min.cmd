@echo off
set PYTHONUTF8=1
"C:\openaudio_s1mini_runtime\venv\Scripts\python.exe" fish_speech_api\audio_workflow.py --config fish_speech_api\config.json --text-file fish_speech_api\sample_russian_sleep_lecture.txt --output fish_speech_api\outputs\s1mini_russian_1min_realistic_zeroshot.wav --max-chars 220 --preset sleep_safe --breath-amount 0.04 --pitch-drift 0.35 --loudness-variation 0.35 --room-tone on --no-mp3
