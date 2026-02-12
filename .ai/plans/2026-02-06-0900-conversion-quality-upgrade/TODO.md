# TODO: Conversion Quality Upgrade (B- → A)

## Phase 0: Research & Decisions
- [x] Verify Codex prompt/command formats via CLI/docs
- [x] Verify OpenCode commands directory + frontmatter requirements
- [x] Confirm sync-driven conversion model and document rationale

## Phase 0.5: TDD Tests
- [x] Add unit tests for sync-driven conversion + scope output mapping
- [x] Add unit tests for Codex prompt warning and report output files
- [x] Add unit tests for multi-LSP aggregation, env var transform, binary files
- [x] Add Docker E2E tests for Codex user-scope prompts, multi-LSP, env vars, binaries

## Phase 1: Parser/IR Robustness
- [x] Add slugify helper for plugin_id + skill names
- [x] Normalize plugin_id safely; emit WARN on changes
- [x] Catch `ValidationError` for PluginIdentity/Skill; continue best-effort
- [x] Add tests for non-kebab plugin/skill names
- [x] Add tests for name length trimming and empty-name fallback

## Phase 2: Emitters Fixes
- [x] Fix Codex user-scope prompt path to `.codex/prompts/`
- [x] Warn when Codex project-scope prompts are emitted (include instructions for `--commands-as-skills` or `scope=user`)
- [x] Aggregate OpenCode LSP servers into single `opencode.lsp.json`
- [x] Add tests for multi-LSP output
- [x] Implement MCP env var syntax transformation per target
- [x] Update tests to expect transformed env var syntax
- [x] Parse and emit binary files in skill directories
- [x] Add binary file fixture + unit tests
- [x] Update command emitters if research requires format changes (no changes needed)

## Phase 3: Reporting & CLI
- [x] Replace lost-feature heuristic with explicit emitter-provided list
- [x] Add `--report` output file option to `ai-config convert`
- [x] Add report format selection for file output
- [x] Resolve scope-based output directory in CLI `convert` and `sync`
- [x] Update docs/tests for scope-based output resolution

## Phase 4: Init Wizard + Sync Integration
- [x] Extend config schema for optional `conversion` section
- [x] Update config loader/validator to accept conversion section
- [x] Offer “run sync now?” prompt after init when conversion enabled
- [x] Add tests for init config generation + sync-triggered conversion

## Phase 5: Sync Conversion Pipeline
- [x] `ai-config sync` performs conversion when configured
- [x] Overwrite converted outputs (derived artifacts) on sync
- [x] Hash-based change detection + `--force-convert`

## Phase 6: Validators & Doctor
- [x] Update target validators for new outputs (existing validators sufficient)
- [ ] Add warnings for env var syntax mismatch (optional)
- [x] Update doctor target-mode tests as needed

## Phase 7: E2E, CI, Docs, Changelog
- [x] Add E2E tests for multi-LSP, env vars, user-scope prompts, binaries
- [x] Keep tmux tests fail-loudly when tmux missing (document in CI)
- [x] Update `CLAUDE.md` with tmux E2E instructions
- [x] Update CI workflow to run tmux E2E tests + timeouts
- [x] Update `CHANGELOG.md` under `[Unreleased]`
- [x] Manual tmux-driven validation of conversion outputs (local)
- [x] Re-run full validation suite (ruff/ty/unit + docker E2E)
