# Project evolution

This timeline records the phases that established today's architecture. Dates refer to the commits merged into `main`; links point to the original rationale and proof.

## Declarative Claude management

The repository began as a small replacement for manually repeating Claude marketplace and plugin commands across machines. Config version 1 made a Claude target and its marketplaces/plugins the desired-state source. The original scope explicitly deferred other tools rather than pretending they shared one runtime contract.

Evidence: genesis `499cb2b612d26909c6787775401b76e806384310` on 2026-02-03 in `README.md`, `src/ai_config/config.py`, and `src/ai_config/operations.py`.

## Cross-tool conversion through an IR

Research found that skills and MCP concepts traveled reasonably well, while commands, hooks, agents, and LSP support differed. The project added parse → IR → emit conversion, per-target validators, degradation reports, and Docker/Tmux probes instead of coupling the Claude parser directly to every output shape.

Evidence: [PR #3](https://github.com/safurrier/ai-config/pull/3), merge SHA `a11b2c66134b3a6304d23d4dd2daea5910244b2d`, on 2026-02-12.

## Pi and explicit target exceptions

Pi joined as a conversion target, then sync-driven refresh exposed that conversion caches must account for source and output changes. Target-native overrides followed so a plugin could carry deliberate runtime-specific glue, such as a Pi TypeScript extension, without embedding that logic in the shared IR.

Evidence: [PR #8](https://github.com/safurrier/ai-config/pull/8), merge SHA `83d72b74cce072ddee223ad1b04457fde5393fb8`; [PR #11](https://github.com/safurrier/ai-config/pull/11), merge SHA `7256360458cf720616ad559b4cd59d26b48e8428`; and [PR #16](https://github.com/safurrier/ai-config/pull/16), merge SHA `0218de2cd0f393a95a49557d1f2958a52a8145f9`.

## Native Codex packages

Codex conversion first emitted loose files. A feasibility spike preserved that behavior while package APIs were uncertain. Once package and marketplace contracts stabilized, ai-config changed to generated package sources plus Codex-managed installation, with strict identity, version, collision, and lifecycle checks.

Evidence: [PR #17](https://github.com/safurrier/ai-config/pull/17), merge SHA `89dc84ad9f45c6c5c0da56ef86a026abaf4a021c`; superseded by [PR #19](https://github.com/safurrier/ai-config/pull/19), merge SHA `9983cc993795fb24871e3f62f19517066356b830`, on 2026-07-17.

## Ownership becomes a destructive boundary

Pi's loose runtime output could become stale, but deleting by expected path could destroy user files. A durable ledger and pending transaction made create, update, preserve, recover, and remove decisions evidence-based. Codex used the same principle through a different mechanism: reserved generated roots and recorded package ownership, while the runtime retained its own config/cache authority.

Evidence: [PR #24](https://github.com/safurrier/ai-config/pull/24), merge SHA `f3543417abda9296a7ebe2080e019a4f315fc3a7`, on 2026-07-26; Codex boundary evidence in [PR #19](https://github.com/safurrier/ai-config/pull/19).

## Sync becomes observe, plan, apply

The final phase separated current-state observation, pure deterministic planning, precondition validation, execution, and reporting. Dry-run and real sync now consume the same action plan, while target-specific lifecycle and ownership modules keep their authority. This structure makes partial progress and stale evidence visible without erasing the differences between Claude, Codex, Pi, and file emitters.

Evidence: [PR #26](https://github.com/safurrier/ai-config/pull/26), merge SHA `693442307dbd54b1c8e0f9bb4a17937f98539a2f`, on 2026-07-29.
