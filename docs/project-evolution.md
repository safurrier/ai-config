# Project evolution

This timeline explains how the current design took shape. Dates are merge dates on `main`. Each link points to the decision and its proof.

## Declarative Claude management

The project began as a way to avoid repeating Claude marketplace and plugin commands. Config version 1 made Claude marketplaces and plugins the desired state. Other tools stayed out of that first contract. They did not yet share a runtime model.

Evidence: genesis `499cb2b612d26909c6787775401b76e806384310` on 2026-02-03 in `README.md`, `src/ai_config/config.py`, and `src/ai_config/operations.py`.

## Cross-tool conversion through an IR

Skills and MCP settings can often move between tools. Commands, hooks, agents, and LSP support often cannot. The project therefore added a parse, IR, and emit pipeline. It also added target validators, degradation reports, and Docker/Tmux probes. The parser does not write each target format itself.

Evidence: [PR #3](https://github.com/safurrier/ai-config/pull/3), merge SHA `a11b2c66134b3a6304d23d4dd2daea5910244b2d`, on 2026-02-12.

## Pi and explicit target exceptions

Pi became a target. Sync refresh then showed that caches must track both source and output changes. Target-native overrides let a plugin carry a needed runtime file, such as a Pi TypeScript extension. That file does not alter the shared IR.

Evidence: [PR #8](https://github.com/safurrier/ai-config/pull/8), merge SHA `83d72b74cce072ddee223ad1b04457fde5393fb8`; [PR #11](https://github.com/safurrier/ai-config/pull/11), merge SHA `7256360458cf720616ad559b4cd59d26b48e8428`; and [PR #16](https://github.com/safurrier/ai-config/pull/16), merge SHA `0218de2cd0f393a95a49557d1f2958a52a8145f9`.

## Native Codex packages

Codex conversion first wrote loose files. A feasibility spike kept that approach while package APIs were unclear. Once those APIs settled, ai-config switched to generated packages and Codex-managed installation. It now checks identity, version, collision, and lifecycle state before mutation.

Evidence: [PR #17](https://github.com/safurrier/ai-config/pull/17), merge SHA `89dc84ad9f45c6c5c0da56ef86a026abaf4a021c`; superseded by [PR #19](https://github.com/safurrier/ai-config/pull/19), merge SHA `9983cc993795fb24871e3f62f19517066356b830`, on 2026-07-17.

## Ownership as a destructive boundary

Pi output can become stale. Deleting an expected path can also delete a user file. A durable ledger and pending transaction now guide create, update, preserve, recover, and remove actions. Codex uses the same rule in a different way. It limits ai-config to reserved generated roots and recorded package ownership. Codex keeps control of its own config and cache.

Evidence: [PR #24](https://github.com/safurrier/ai-config/pull/24), merge SHA `f3543417abda9296a7ebe2080e019a4f315fc3a7`, on 2026-07-26; Codex boundary evidence in [PR #19](https://github.com/safurrier/ai-config/pull/19).

## Sync becomes observe, plan, apply

The next phase split observation, planning, checks, execution, and reporting. Dry-run and real sync use the same action plan. Lifecycle and ownership modules keep their own narrow authority. This makes partial progress and stale evidence visible. It also preserves the differences among Claude, Codex, Pi, and file emitters.

Evidence: [PR #26](https://github.com/safurrier/ai-config/pull/26), merge SHA `693442307dbd54b1c8e0f9bb4a17937f98539a2f`, on 2026-07-29.

## Self-contained skills and contained source reads

A converted skill could point to a shared plugin file that was not emitted. Conversion now captures declared regular files and copies them into each consuming skill. It rewrites only declared root references. The same release made source reads descriptor-relative and no-follow. Codex and Pi still remove only proven-owned output. Cursor and OpenCode do not gain deletion authority. [ADR 0007](adr/0007-materialize-shared-skill-resources.md) records the resource decision. [ADR 0009](adr/0009-contained-plugin-source-reads.md) records the source-read boundary.

Evidence: [PR #35](https://github.com/safurrier/ai-config/pull/35), merge SHA `d9cd5b56158ae1e608573a730b84a92ec75a7b40`, on 2026-08-20.

## Narrow context-mirror exception

Plugin source hashing rejects symlinks by default. One repository mirror needs a narrow exception: `CLAUDE.md -> AGENTS.md` must be a sibling link to a no-follow regular file. The hash records link and target metadata without reading through the link. All other symlink shapes remain unreadable.

Evidence: [PR #36](https://github.com/safurrier/ai-config/pull/36), merge SHA `84fee140c5adba088c99b25da9eb87d47f1cbc23`, on 2026-08-21.

## Bounded staged convergence

A remote plugin source may not exist until Claude installs it. Sync can apply one Claude-only prerequisite plan, observe once more, then apply one conversion-only plan. A configured local marketplace remains the source authority. Cache identity uses the configured selector and conversion signature, not an installed path. Sync reports incomplete conversion. It never loops until quiet.

Evidence: [PR #37](https://github.com/safurrier/ai-config/pull/37), merge SHA `22360adcd87716e88edd9469b9751f30a71c800d`, on 2026-08-21.
