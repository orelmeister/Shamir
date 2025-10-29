#!/usr/bin/env python3
"""
Conversation Logger for Trade Bot Project
Automatically logs AI assistant conversations with timestamps and context.
"""

import os
import json
from datetime import datetime
from pathlib import Path

class ConversationLogger:
    """Logs conversations between user and AI assistant."""
    
    def __init__(self, log_dir="conversations"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.current_session = self._get_session_file()
        
    def _get_session_file(self):
        """Get or create today's session file."""
        today = datetime.now().strftime("%Y%m%d")
        session_file = self.log_dir / f"session_{today}.md"
        
        if not session_file.exists():
            # Create new session with header
            with open(session_file, 'w', encoding='utf-8') as f:
                f.write(f"# Trading Bot Development Session - {datetime.now().strftime('%B %d, %Y')}\n\n")
                f.write(f"**Project**: Day Trading Bot\n")
                f.write(f"**Started**: {datetime.now().strftime('%I:%M %p')}\n\n")
                f.write("---\n\n")
        
        return session_file
    
    def log_exchange(self, user_message, assistant_response, context=None):
        """
        Log a conversation exchange.
        
        Args:
            user_message: What the user asked
            assistant_response: AI assistant's response
            context: Optional dict with additional context (files changed, commands run, etc.)
        """
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        
        with open(self.current_session, 'a', encoding='utf-8') as f:
            # User message
            f.write(f"## 🧑 User ({timestamp})\n\n")
            f.write(f"{user_message}\n\n")
            
            # Context if provided
            if context:
                f.write(f"**Context:**\n")
                if context.get('files_modified'):
                    f.write(f"- Files modified: `{', '.join(context['files_modified'])}`\n")
                if context.get('commands_run'):
                    f.write(f"- Commands executed: {len(context['commands_run'])}\n")
                if context.get('tests_run'):
                    f.write(f"- Tests: {'✅ PASSED' if context['tests_run'] else '❌ FAILED'}\n")
                f.write("\n")
            
            # Assistant response
            f.write(f"## 🤖 Assistant ({timestamp})\n\n")
            f.write(f"{assistant_response}\n\n")
            f.write("---\n\n")
    
    def log_milestone(self, milestone_name, details):
        """Log a significant milestone or achievement."""
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        
        with open(self.current_session, 'a', encoding='utf-8') as f:
            f.write(f"## 🎯 MILESTONE: {milestone_name} ({timestamp})\n\n")
            f.write(f"{details}\n\n")
            f.write("---\n\n")
    
    def log_code_change(self, file_path, change_description, code_snippet=None):
        """Log a code change with optional snippet."""
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        
        with open(self.current_session, 'a', encoding='utf-8') as f:
            f.write(f"### 📝 Code Change: `{file_path}` ({timestamp})\n\n")
            f.write(f"{change_description}\n\n")
            
            if code_snippet:
                f.write(f"```python\n{code_snippet}\n```\n\n")
    
    def add_session_summary(self, summary):
        """Add a summary at the end of the session."""
        with open(self.current_session, 'a', encoding='utf-8') as f:
            f.write(f"\n\n## 📋 Session Summary\n\n")
            f.write(f"{summary}\n\n")
            f.write(f"**Session ended**: {datetime.now().strftime('%I:%M %p')}\n")
    
    def export_to_json(self):
        """Export session to JSON format for programmatic access."""
        json_file = self.current_session.with_suffix('.json')
        
        # This is a placeholder - you'd parse the markdown to extract structured data
        data = {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "project": "Trade Bot",
            "log_file": str(self.current_session),
            "exported_at": datetime.now().isoformat()
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        return json_file


# Quick usage example
if __name__ == "__main__":
    logger = ConversationLogger()
    
    # Example: Log a conversation
    logger.log_exchange(
        user_message="How do I fix the PDT restrictions?",
        assistant_response="Use ExcessLiquidity instead of AvailableFunds...",
        context={
            'files_modified': ['day_trading_agents.py'],
            'commands_run': ['python test_connection.py'],
            'tests_run': True
        }
    )
    
    # Example: Log a milestone
    logger.log_milestone(
        "PDT Fix Completed",
        "Successfully changed capital allocation to use ExcessLiquidity field. All tests passing."
    )
    
    # Example: Log code change
    logger.log_code_change(
        "day_trading_agents.py",
        "Changed allocation from TotalCashValue to ExcessLiquidity",
        code_snippet="excess_liquidity = float(self.account_summary.get('ExcessLiquidity', 0))"
    )
    
    print(f"✅ Session logged to: {logger.current_session}")
