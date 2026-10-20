#!/usr/bin/env python3
"""PreToolUse hook: block `pkill -f` / `pgrep -f` patterns that match the agent's own shell.

The Bash tool runs each command as `bash -c '<command>'`, so `pkill -f "http.server 8085"`
matches that shell's command line too and kills it (exit 144), taking any chained
commands with it. A bracketed first character (`[h]ttp.server 8085`) still matches the
target but not the literal text in the shell's own command line.
"""

import json
import re
import sys

command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
# Heredoc bodies are data (PR bodies, scripts written to files), not commands.
command = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n.*?^\s*\1\s*$", "", command, flags=re.S | re.M)

for segment in re.findall(r"\b(?:pkill|pgrep)\b[^;&|\n]*", command):
    if re.search(r"\s(-[a-zA-Z0-9]*f|--full)\b", segment) and "[" not in segment:
        print(
            "Blocked: `pkill -f`/`pgrep -f` without a bracketed pattern matches this Bash "
            "call's own shell and kills it. Bracket the first character "
            '(`pkill -f "[h]ttp.server 8085"`), or stop a `run_in_background` server with TaskStop.',
            file=sys.stderr,
        )
        sys.exit(2)
