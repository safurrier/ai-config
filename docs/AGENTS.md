# Documentation routing

MkDocs owns this directory's public structure. Keep `docs/index.md` as the human landing page and update `mkdocs.yml` when adding a public page.

## Explanation

| Doc | Description |
|---|---|
| `architecture.md` | Current component, lifecycle, conversion, and ownership boundaries. |
| `project-evolution.md` | Evidence-backed phases and superseded architectural directions. |
| `conversion.md` | User-facing conversion behavior and target mappings. |

## Reference

| Doc | Description |
|---|---|
| `commands.md` | CLI command and option reference. |
| `config.md` | YAML schema, paths, scopes, and examples. |
| `adr/README.md` | Architecture decision index and retrospective records. |
| `adr/0001-claude-plugin-source-model.md` | Why Claude plugins are the source model. |
| `adr/0002-target-neutral-plugin-ir.md` | Why conversion passes through an IR. |
| `adr/0003-target-native-overrides.md` | Why explicit target-native files may override generated output. |
| `adr/0004-codex-plugin-packages.md` | Why Codex output uses packages and local marketplaces. |
| `adr/0005-proven-output-ownership.md` | Why destructive cleanup requires target-specific ownership proof. |
| `adr/0006-observe-plan-apply-sync.md` | Why sync separates observation, planning, and application. |
| `adr/0007-materialize-shared-skill-resources.md` | Why shared plugin files are materialized into self-contained generated skills. |
| `adr/0008-bounded-sync-convergence-stages.md` | Why fresh remote sync uses at most one prerequisite plan and one conversion plan. |

## Entry point

| Doc | Description |
|---|---|
| `index.md` | MkDocs home and user navigation. |
