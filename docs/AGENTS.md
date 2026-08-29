# Documentation routing

MkDocs builds the public documentation. Keep `docs/index.md` as the reader
entry point. Update `mkdocs.yml` when you add or rename a public page.

## Gotchas

- **DO** put current behavior in architecture, commands, config, or conversion
  pages. **NOT** duplicate it in ADRs or project evolution. **BECAUSE** those
  documents preserve decisions and history, not live reference.
- **DO** cite a commit or merged PR URL and merge SHA for historical claims.
  **NOT** turn a retrospective into an unsupported narrative. **BECAUSE** project
  evolution and ADRs need immutable provenance.
- **DO** preserve exact command names, paths, safety boundaries, and ownership
  limits. **NOT** simplify them into weaker claims. **BECAUSE** this documentation
  describes destructive and compatibility-sensitive behavior.

## Related context

| Path | Purpose |
|---|---|
| `index.md` | Public navigation and shortest path. |
| `architecture.md` | Current structure and boundaries. |
| `commands.md` | CLI reference. |
| `config.md` | Configuration schema and paths. |
| `conversion.md` | Target mappings and conversion limits. |
| `adr/README.md` | Decision index. |
| `adr/0001-claude-plugin-source-model.md` | Claude plugin source model. |
| `adr/0002-target-neutral-plugin-ir.md` | Shared conversion IR. |
| `adr/0003-target-native-overrides.md` | Explicit target exceptions. |
| `adr/0004-codex-plugin-packages.md` | Codex package output. |
| `adr/0005-proven-output-ownership.md` | Destructive ownership proof. |
| `adr/0006-observe-plan-apply-sync.md` | Immutable sync stages. |
| `adr/0007-materialize-shared-skill-resources.md` | Self-contained skills. |
| `adr/0008-bounded-sync-convergence-stages.md` | One prerequisite and conversion stage. |
| `adr/0009-contained-plugin-source-reads.md` | Fail-closed source reads. |
| `project-evolution.md` | Evidence-backed history. |

<!-- generated-by: context-engineering@2.6.5 | last-updated: 2026-08-22 -->
