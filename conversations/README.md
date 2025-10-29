# Conversation History

This folder stores logs of development conversations to preserve context across sessions.

## Files

- `session_YYYYMMDD.md` - Daily conversation logs in markdown format
- `session_YYYYMMDD.json` - Structured data exports
- `project_knowledge.md` - Key decisions and architectural notes

## Why This Exists

VS Code conversations are lost between sessions. These logs preserve:
- User questions and AI responses
- Code changes made
- Commands executed
- Problems solved
- Milestones reached

## Usage

### Manual Logging (After Each Major Change)

```python
from conversation_logger import ConversationLogger

logger = ConversationLogger()

# Log an exchange
logger.log_exchange(
    user_message="Your question here",
    assistant_response="AI's response here",
    context={'files_modified': ['file.py'], 'tests_run': True}
)

# Log a milestone
logger.log_milestone("Feature Complete", "Description of what was achieved")

# Log code changes
logger.log_code_change("file.py", "What changed", code_snippet="...")
```

### Quick Add to Any Script

Add at the end of `day_trader.py`, `test_connection.py`, etc.:

```python
from conversation_logger import ConversationLogger
logger = ConversationLogger()
logger.log_milestone("Script Executed", f"Ran successfully at {datetime.now()}")
```

## Better Solution: Use VS Code Built-in Export

1. In Copilot Chat → Click `...` menu → "Export Session"
2. Save to this folder
3. Rename to match date pattern

## Even Better: GitHub Copilot Memory

Enable in VS Code settings:
```json
"github.copilot.chat.memory.enabled": true
```

This preserves context across sessions automatically.
