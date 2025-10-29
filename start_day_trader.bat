@echo off
REM ============================================================
REM Day Trader Bot - Automated Startup Script
REM ============================================================
REM This script activates the virtual environment and runs the day trader
REM Use with Windows Task Scheduler to start at 7:00 AM daily
REM ============================================================

echo [%date% %time%] Starting Day Trader Bot...

REM Change to the project directory
cd /d "C:\Users\orelm\OneDrive\Documents\GitHub\trade"

REM Activate virtual environment
call .venv-daytrader\Scripts\activate.bat

REM Run the day trader with 25% capital allocation using venv Python explicitly
echo [%date% %time%] Launching day_trader.py with 25%% allocation...
.venv-daytrader\Scripts\python.exe day_trader.py --allocation 0.25

REM Log the exit code
echo [%date% %time%] Day trader exited with code: %ERRORLEVEL%

REM Keep window open if run manually (will auto-close if scheduled)
if "%1"=="manual" pause

exit /b %ERRORLEVEL%
