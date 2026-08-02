# ai-config documentation

MkDocs owns this directory's layout and `mkdocs.yml` navigation. Keep reference
pages current-facing; put architectural rationale in ADRs and historical phases
in project evolution.

## Routing

| Path | Purpose |
|---|---|
| `index.md` | Human documentation entrypoint |
| `commands.md` | CLI command reference |
| `config.md` | Version 1 configuration reference |
| `conversion.md` | User-facing conversion behavior and options |
| `explanation/architecture.md` | Current system boundaries, flows, and ownership |
| `explanation/project-evolution.md` | Historical phases and retained tradeoffs |
| `adr/001-use-claude-plugins-as-the-canonical-source.md` | Canonical source-format decision |
| `adr/002-normalize-conversion-through-a-target-independent-ir.md` | IR conversion seam |
| `adr/003-use-native-codex-plugin-packages.md` | Codex package lifecycle |
| `adr/004-require-proven-ownership-before-generated-output-cleanup.md` | Cleanup safety boundary |
| `adr/005-plan-sync-before-applying-it.md` | Observe-plan-apply sync boundary |

## Gotchas

- **DO** update `mkdocs.yml` when adding, removing, or moving a product page.
  **NOT** rely on filesystem discovery. **BECAUSE** nav omissions are warnings
  and strict builds treat them as release failures; this agent-only file is the
  explicit `exclude_docs` exception and is not published.
- **DO** keep SPEC requirements and ADR decisions linked to current code/tests.
  **NOT** copy transient test counts or target versions into durable context.
  **BECAUSE** runtime baselines and release facts have separate owners.
