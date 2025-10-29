@echo off
REM Exit Manager - Monitors all positions for profit targets and stop losses
REM Keep this window open all day!

echo ================================================================================
echo Exit Manager - Starting...
echo ================================================================================
echo.
echo This bot will:
echo   - Monitor all open positions
echo   - Maintain profit target orders (+1.8%%)
echo   - Execute stop losses (-0.9%%)
echo   - Keep IBKR connection alive
echo.
echo IMPORTANT: Keep this window open all day!
echo ================================================================================
echo.

cd /d "%~dp0"
call .venv-daytrader\Scripts\activate.bat
python exit_manager.py

pause
