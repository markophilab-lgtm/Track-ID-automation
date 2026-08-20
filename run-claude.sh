#!/bin/bash
# run-claude.sh - Run Claude Code with your custom prompt + dangerous mode

# === CONFIGURE THESE ===
CUSTOM_PROMPT="Run humble-moseying-grove.md plan and implement"
# Example: "Refactor the entire project for performance, run tests, and commit changes."

# Optional: add extra flags
# EXTRA_FLAGS="--dangerously-skip"   # or just use the dangerous flag

echo "=== Starting Claude at $(date) ==="

# Run Claude with your prompt
claude "$CUSTOM_PROMPT" \
	--permission-mode bypassPermissions \
	--dangerously-skip-permissions 

crontab -l | grep -v 'open -a Terminal /Users/waterhousestudios/git/track_id_project/run-claude.sh' | crontab - 
