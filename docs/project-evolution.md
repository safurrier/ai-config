# Project evolution

This timeline records how the design developed. Dates are merge dates on `main`. Each entry links the decision to its evidence. Read the evidence with the claim. It fixes the date. It fixes the scope. It names the change. It also records supersession.

## Declarative Claude management

The project started by reducing repeated Claude marketplace and plugin commands. Configuration version 1 defined Claude marketplaces and plugins as the desired state. It kept the contract small. Other tools were outside that first contract. The project had no shared runtime model.

Evidence: genesis `499cb2b612d26909c6787775401b76e806384310` on 2026-02-03. See `README.md`, `src/ai_config/config.py`, and `src/ai_config/operations.py`.

## Cross-tool conversion through an IR

Skills and MCP settings can move between tools. Commands, hooks, agents, and LSP settings often cannot. The project added a parse, IR, and emit pipeline. It also added target validators, degradation reports, and Docker and Tmux probes. The parser does not write target formats directly.

Evidence: [PR #3](https://github.com/safurrier/ai-config/pull/3), merge SHA `a11b2c66134b3a6304d23d4dd2daea5910244b2d`, on 2026-02-12.

## Pi and target exceptions

Pi became a target. Sync refresh showed that caches must track source and output changes. Target-native overrides let a plugin carry a required runtime file, such as a Pi TypeScript extension. The file does not change the shared IR.

Evidence: [PR #8](https://github.com/safurrier/ai-config/pull/8), merge SHA `83d72b74cce072ddee223ad1b04457fde5393fb8`; [PR #11](https://github.com/safurrier/ai-config/pull/11), merge SHA `7256360458cf720616ad559b4cd59d26b48e8428`; and [PR #16](https://github.com/safurrier/ai-config/pull/16), merge SHA `0218de2cd0f393a95a49557d1f2958a52a8145f9`.

## Native Codex packages

Codex conversion first wrote loose files. A feasibility spike retained that approach while package APIs were unclear. When the APIs settled, ai-config adopted generated packages and Codex-managed installation. It checks identity, version, collisions, and lifecycle state before mutation.

Evidence: [PR #17](https://github.com/safurrier/ai-config/pull/17), merge SHA `89dc84ad9f45c6c5c0da56ef86a026abaf4a021c`. [PR #19](https://github.com/safurrier/ai-config/pull/19), merge SHA `9983cc993795fb24871e3f62f19517066356b830`, superseded that approach on 2026-07-17.

## Ownership as a destructive boundary

Pi output can become stale. Deleting an expected path can also delete a user file. A durable ledger and pending transaction guide create, update, preserve, recover, and remove actions. Codex follows the same ownership rule differently. ai-config only manages reserved generated roots and recorded package ownership. Codex controls its own configuration and cache.

Evidence: [PR #24](https://github.com/safurrier/ai-config/pull/24), merge SHA `f3543417abda9296a7ebe2080e019a4f315fc3a7`, on 2026-07-26. Codex boundary evidence: [PR #19](https://github.com/safurrier/ai-config/pull/19).

## Observe, plan, apply

The next phase split observation, planning, checks, execution, and reporting. Dry-run and real sync use the same action plan. Lifecycle and ownership modules keep narrow authority. The plan stays visible. This design exposes partial progress and stale evidence. It also preserves the differences among Claude, Codex, Pi, and file emitters.

Evidence: [PR #26](https://github.com/safurrier/ai-config/pull/26), merge SHA `693442307dbd54b1c8e0f9bb4a17937f98539a2f`, on 2026-07-29.

## Self-contained skills and contained source reads

A converted skill could reference a shared plugin file that conversion did not emit. Conversion now captures declared regular files and copies them into each consuming skill. It rewrites only declared root references. The same release made source reads descriptor-relative and no-follow. Codex and Pi remove only proven-owned output. Cursor and OpenCode have no deletion authority. [ADR 0007](adr/0007-materialize-shared-skill-resources.md) records the resource decision. [ADR 0009](adr/0009-contained-plugin-source-reads.md) records the source-read boundary.

Evidence: [PR #35](https://github.com/safurrier/ai-config/pull/35), merge SHA `d9cd5b56158ae1e608573a730b84a92ec75a7b40`, on 2026-08-20.

## Narrow context-mirror exception

Plugin source hashing rejects symlinks by default. One repository mirror needs an exception: `CLAUDE.md -> AGENTS.md` must link to a sibling no-follow regular file. The hash records link and target metadata. It does not read through the link. All other symlink shapes remain unreadable.

Evidence: [PR #36](https://github.com/safurrier/ai-config/pull/36), merge SHA `84fee140c5adba088c99b25da9eb87d47f1cbc23`, on 2026-08-21.

## Bounded staged convergence

A remote plugin source might not exist until Claude installs it. Sync can apply one Claude-only prerequisite plan, observe once more, and apply one conversion-only plan. A configured local marketplace remains the source authority. Cache identity uses the configured selector and conversion signature, not an installed path. Sync reports incomplete conversion. It never loops until quiet.

Evidence: [PR #37](https://github.com/safurrier/ai-config/pull/37), merge SHA `22360adcd87716e88edd9469b9751f30a71c800d`, on 2026-08-21.
