@echo off
setlocal
cd /d "%~dp0"
python audio_workflow.py --output outputs\russian_sleep_lecture_placeholder_test.wav
