@echo off
rem Start the monitor in the background (no black window). Stop it with stop.bat.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" run.py
