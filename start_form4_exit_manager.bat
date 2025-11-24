@echo off
echo ============================================================
echo Form 4 Exit Manager - Position Monitoring
echo ============================================================
echo.

cd /d "%~dp0"

REM Check if virtual environment exists
if not exist ".venv-weekly\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    echo Please run this from the trade directory with .venv-weekly
    pause
    exit /b 1
)

REM Activate virtual environment and run exit manager
echo Starting exit manager...
echo.

.\.venv-weekly\Scripts\python.exe weekly_bot\form4_exit_manager.py %*

echo.
echo ============================================================
echo Exit manager finished
echo ============================================================
pause
