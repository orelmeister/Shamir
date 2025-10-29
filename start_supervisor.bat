@echo off
REM Supervisor Launcher - Manages both Day Trader and Exit Manager
REM This script runs both bots with database coordination

echo ============================================================
echo 🤖 Trading Bot Supervisor
echo ============================================================
echo.
echo This supervisor will:
echo  - Start Exit Manager (persistent, monitors all exits)
echo  - Start Day Trader (restartable, handles entries)
echo  - Monitor both bots with auto-restart
echo  - Coordinate via shared database
echo.
echo Press Ctrl+C to stop all bots
echo ============================================================
echo.

REM Activate virtual environment
call .venv-daytrader\Scripts\activate.bat

REM Run supervisor
python supervisor.py

REM Deactivate when done
deactivate

echo.
echo ============================================================
echo ✅ Supervisor stopped
echo ============================================================
pause
