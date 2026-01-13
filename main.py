"""
Compatibility entrypoint for the Weekly Bot.

This repository was refactored away from the old monolithic main.py.
Running this file will launch the new Weekly Orchestrator menu.
"""
from weekly_orchestrator import main as orchestrator_main

if __name__ == "__main__":
    orchestrator_main()
