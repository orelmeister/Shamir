@echo off
REM Form 4 Insider Strategy - Weekly Runner
REM Run every Sunday at 8:00 PM

echo ================================================================================
echo FORM 4 INSIDER CLUSTER STRATEGY - WEEKLY ANALYSIS
echo ================================================================================
echo.
echo Time: %date% %time%
echo Capital: $1000
echo.

cd /d "C:\Users\orelm\OneDrive\Documents\GitHub\trade"

REM Activate virtual environment and run strategy
call .venv-weekly\Scripts\activate.bat
python weekly_bot\05_form4_strategy.py

echo.
echo ================================================================================
echo Form 4 analysis complete. Check form4_strategy\ folder for results.
echo ================================================================================
echo.

pause
