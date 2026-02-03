# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-02-03

### Added

- Initial release as standalone package
- Declarative YAML config for plugins and marketplaces
- Interactive init wizard with questionary prompts
- Commands: init, sync, status, watch, update, doctor
- Plugin scaffolding with `plugin create`
- Cache management with `cache clear`
- Rich CLI output with tables, panels, and spinners
- File watching with debounced auto-sync
- Comprehensive validation for:
  - Plugins and plugin manifests
  - Skills and skill frontmatter
  - Hooks and hook executability
  - MCP servers and configurations
  - Marketplaces and manifest files
- Claude Code adapter for CLI operations
- Support for user and project plugin scopes
