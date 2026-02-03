# Contributing to ai-config

Thank you for your interest in contributing!

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone git@github.com:your-username/ai-config.git`
3. Create a new branch: `git checkout -b feature-name`
4. Make your changes
5. Run quality checks: `just check`
6. Commit your changes: `git commit -m "Description of changes"`
7. Push to your fork: `git push origin feature-name`
8. Open a Pull Request

## Development Setup

```bash
# Install dependencies
just setup

# Run all quality checks (lint, type check, test)
just check
```

## Code Quality Standards

- All code must be typed with proper type hints
- Tests must be included for new features
- All quality checks must pass (`just check`)

## Pull Request Process

1. Update the README.md with details of significant changes
2. Update the CHANGELOG.md following the existing format
3. The PR will be merged once you have the sign-off of a maintainer

## Questions?

Feel free to open an issue for any questions or concerns.
