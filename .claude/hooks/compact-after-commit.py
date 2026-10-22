#!/usr/bin/env python3
"""PostToolUse hook: after a commit made with a large context, have the agent stop for /compact.

Every API call re-reads the whole conversation. The review runs in fresh subagents, but acting
on it (the fixes, tests, screenshots and the PR) runs here, and needs the diff and the review, not
the exploration that led to them: 33 calls at ~285k in #111, ~9M tokens, ~3M after a compact.
The agent can't compact itself; it can end its turn and ask the user to. Its context is the size
of its last API call, read from the session transcript.
"""

import json
import re
import subprocess
import sys
import time

THRESHOLD = 150_000

hook = json.load(sys.stdin)
command = hook.get("tool_input", {}).get("command", "")
# Heredoc bodies and quoted strings are data (PR bodies, commit messages), not commands.
command = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n.*?^\s*\1\s*$", "", command, flags=re.S | re.M)
command = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "", command)
if not re.search(r"\bgit\b(\s+-C\s+\S+)?\s+commit\b", command):
    sys.exit(0)

# Only a commit that happened: HEAD was committed in the last two minutes.
committed = subprocess.run(
    ["git", "log", "-1", "--format=%ct"], cwd=hook.get("cwd"), capture_output=True, text=True
).stdout.strip()
if not committed or time.time() - int(committed) > 120:
    sys.exit(0)

context = 0
try:
    with open(hook["transcript_path"]) as transcript:
        for line in transcript:
            entry = json.loads(line)
            usage = entry.get("message", {}).get("usage")
            if entry.get("type") == "assistant" and not entry.get("isSidechain") and usage:
                context = sum(
                    usage.get(k) or 0
                    for k in (
                        "input_tokens",
                        "cache_read_input_tokens",
                        "cache_creation_input_tokens",
                    )
                )
except (KeyError, OSError, ValueError):
    sys.exit(0)
if context < THRESHOLD:
    sys.exit(0)

print(
    json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    f"Context is {context // 1000}k tokens at this commit. Finish this step "
                    "(push it if that was next), then end your turn: say the commit is in and "
                    "what comes next, and ask the user to run /compact and then say continue. "
                    "Every later call re-reads this context; after /compact the review fixes "
                    "and the PR work from the diff and a summary. If the user has already "
                    "declined in this session, carry on."
                ),
            }
        }
    )
)
