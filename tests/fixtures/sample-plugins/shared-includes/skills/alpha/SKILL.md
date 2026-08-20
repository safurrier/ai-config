---
name: alpha
description: First shared-resource consumer
x-ai-config-includes:
  - shared/data.txt
  - shared/dependency.json
  - shared/run.sh
  - shared/blob.bin
---

Read `${CLAUDE_PLUGIN_ROOT}/shared/data.txt` and run `${CLAUDE_PLUGIN_ROOT}/shared/run.sh`.
The dependency is loaded transitively by the script.
