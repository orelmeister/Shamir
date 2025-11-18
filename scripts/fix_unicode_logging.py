"""
Fix Unicode emoji characters in logger.info() calls that cause Windows console crashes.
Replaces emojis with safe ASCII equivalents.
"""
import re
from pathlib import Path

# Emoji to ASCII mapping
EMOJI_MAP = {
    '✅': '[OK]',
    '❌': '[ERROR]',
    '⚠️': '[WARNING]',
    '📊': '[INFO]',
    '🔄': '[PROCESS]',
    '⭐': '*',
}

def fix_file(file_path):
    """Remove emojis from logger statements in a file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Replace emojis in logger calls only
    for emoji, replacement in EMOJI_MAP.items():
        # Match logger.info/warning/error with emoji
        pattern = r'(logger\.(info|warning|error|debug)\([^)]*?)' + re.escape(emoji)
        content = re.sub(pattern, r'\1' + replacement, content)
    
    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed: {file_path.name}")
        return True
    return False

if __name__ == "__main__":
    weekly_bot_dir = Path("weekly_bot")
    fixed_count = 0
    
    for py_file in weekly_bot_dir.glob("*.py"):
        if fix_file(py_file):
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")
