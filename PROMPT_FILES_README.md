# Prompt Files - Quick Reference

This document explains the purpose and usage of the comprehensive prompt files in this repository.

---

## 📋 Available Prompt Files

### 1. PROMPT_DAY_TRADER.md
**Purpose**: Master documentation for the day trading bot system

**Use this when:**
- Working on `day_trader.py` or `day_trading_agents.py`
- Debugging intraday trading issues
- Understanding the 3-phase workflow (Data → Analysis → Trading)
- Configuring IBKR connections
- Troubleshooting technical indicators (VWAP, RSI, ATR)

**Key Sections:**
- System Architecture (3 phases)
- File structure and isolation principles
- How to run and configure
- Common issues with solutions
- API integration details
- Trading rules and parameters
- Daily workflow timeline

---

### 2. PROMPT_WEEKLY_BOT.md
**Purpose**: Master documentation for the weekly trading bot system

**Use this when:**
- Working on `main.py` or `agents.py`
- Performing fundamental analysis
- Understanding weekly stock selection
- Managing longer-term portfolios
- Configuring weekly runs

**Key Sections:**
- Fundamental analysis framework
- Portfolio management strategy
- Phase breakdown (Data → Analysis → Execution)
- Scoring system (0.40-1.0 scale)
- Weekly workflow and timing
- Integration with day trader

---

## 🎯 How to Use These Files

### For AI Assistants (like GitHub Copilot)
```
"Please review PROMPT_DAY_TRADER.md before working on the day trading bot"
"Follow the rules in PROMPT_WEEKLY_BOT.md when modifying main.py"
```

### For Human Developers
1. Read the relevant prompt file **before** making changes
2. Follow the **CRITICAL RULES** section religiously
3. Consult **Common Issues & Fixes** when debugging
4. Update the prompt file when you discover new patterns

### For New Team Members
1. Start with **System Overview** in each file
2. Understand the **Architecture** section
3. Review **How to Run** for practical usage
4. Bookmark **Common Issues** for troubleshooting

---

## 🔄 Keeping Prompt Files Updated

### When to Update
- ✅ After fixing a bug (add to "Common Issues")
- ✅ When adding new features (update "Architecture")
- ✅ When changing configuration (update "Configuration" section)
- ✅ When discovering edge cases (add to "Critical Rules")

### How to Update
1. Edit the relevant prompt file
2. Add entry to "Version History" section
3. Update "Last Updated" date at bottom
4. Commit with descriptive message: `"Updated PROMPT_DAY_TRADER.md: Added ATR threshold adjustment guide"`

---

## 🚨 Important Notes

### DO NOT:
- ❌ Delete these files (they're the source of truth)
- ❌ Contradict rules in prompt files without documenting why
- ❌ Make changes without consulting the relevant prompt first

### ALWAYS:
- ✅ Read the prompt file before making significant changes
- ✅ Update prompt files when adding features
- ✅ Use prompt files to onboard new developers
- ✅ Reference sections when asking for help

---

## 📚 Document Hierarchy

```
1. Prompt Files (PROMPT_*.md)
   ↓
   Highest level - System architecture, rules, workflows
   
2. README_AGENT.md
   ↓
   Technical details - Bug fixes, deployment plans
   
3. Configuration Files (DAY_TRADER_CONFIGURATION.md)
   ↓
   Detailed settings and parameters
   
4. Code Comments
   ↓
   Line-by-line implementation details
```

**Rule of Thumb**: Start at the top (prompt files) and work down as you need more detail.

---

## 🎓 Examples

### Example 1: Fixing a Bug
```
1. Read PROMPT_DAY_TRADER.md → "Common Issues" section
2. Find similar issue or add new one
3. Implement fix in code
4. Update prompt file with solution
5. Commit: "Fixed ATR calculation bug (documented in PROMPT_DAY_TRADER.md)"
```

### Example 2: Adding a Feature
```
1. Read relevant prompt file → "Architecture" section
2. Understand how feature fits into system
3. Check "Critical Rules" for constraints
4. Implement feature following guidelines
5. Update prompt file → "Architecture" + "Version History"
6. Commit: "Added trailing stop loss feature (see PROMPT_DAY_TRADER.md v2)"
```

### Example 3: Debugging
```
1. Check logs for error message
2. Open relevant prompt file
3. Search for error in "Common Error Messages" table
4. Follow "Fix" column instructions
5. If not found, add to prompt file after solving
```

---

**Created**: October 21, 2025
**Purpose**: Quick reference guide for using prompt files effectively
**Maintenance**: Update when adding new prompt files or changing structure
