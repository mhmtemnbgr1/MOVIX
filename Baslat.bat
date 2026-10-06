@echo off
cd /d "%~dp0"
python -m movix.app
if errorlevel 1 pause
