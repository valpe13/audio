@echo off
setlocal
cd /d "%~dp0"
call install_docker_stack.cmd %*
exit /b %ERRORLEVEL%
