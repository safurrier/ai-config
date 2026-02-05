#!/bin/bash
# Check for dangerous commands before execution

read -r input
command=$(echo "$input" | jq -r '.tool_input.command // empty')

# Check for dangerous patterns
if echo "$command" | grep -qE 'rm -rf|sudo|chmod 777|> /dev/'; then
    echo '{"hookSpecificOutput": {"permissionDecision": "ask", "permissionDecisionReason": "Command may be dangerous"}}'
    exit 0
fi

echo '{}'
exit 0
