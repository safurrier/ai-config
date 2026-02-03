# ai-config

Declarative plugin manager for Claude Code.

## Project Commands

```bash
just setup        # Install dependencies
just check        # Run all checks (lint, ty, test)
just lint         # Lint source code
just format       # Format source code
just ty           # Type check
just test         # Run tests
just test-cov     # Run tests with coverage
just docs-serve   # Serve docs locally
just docs-build   # Build docs
```

## Code Style

- **Types**: Strict typing with ty, use proper annotations
- **Imports**: Standard lib first, third-party second, project imports last
- **Formatting**: Enforced by ruff formatter (line-length 100)
- **Docstrings**: Include Args and Returns sections
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Python Version**: 3.9+

## Project Structure

```
src/ai_config/
├── cli.py           # Click CLI commands
├── cli_render.py    # Rich output rendering
├── cli_theme.py     # Theme definitions
├── config.py        # Config file parsing
├── init.py          # Interactive init wizard
├── operations.py    # Sync, update, status operations
├── scaffold.py      # Plugin scaffolding
├── settings.py      # App settings
├── types.py         # Type definitions
├── watch.py         # File watching
├── adapters/        # Tool-specific adapters
│   └── claude.py    # Claude Code CLI wrapper
└── validators/      # Validation components
    ├── base.py      # Base validator
    ├── context.py   # Validation context
    ├── component/   # Component validators (skill, hook, mcp)
    ├── marketplace/ # Marketplace validators
    ├── plugin/      # Plugin validators
    └── target/      # Target validators (claude)
```
