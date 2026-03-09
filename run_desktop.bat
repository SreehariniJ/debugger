@echo off
setlocal
title Offline Debugger Desktop Launcher
echo Launching Offline Debugger Desktop...
python desktop_app.py
if errorlevel 1 (
  echo.
  echo Desktop app exited with an error. Check logs\desktop.log for details.
)
pause
