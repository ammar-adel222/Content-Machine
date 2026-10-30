@echo off
setlocal
cd /d "%~dp0"
set "preview_python=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%preview_python%" set "preview_python=python"
"%preview_python%" -m war_content.play %*
if errorlevel 1 pause
