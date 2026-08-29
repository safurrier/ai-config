# Read plugin sources through a fail-closed boundary

Status: Accepted
Date: 2026-08-20

## Context

Conversion reads manifests, instructions, assets, includes, and target-native files from a plugin tree. Ordinary path resolution can follow a symlink, leave the plugin root, or read a special file after an earlier check. A broad symlink exception would weaken the source boundary. The repository has one narrow compatibility mirror: sibling `CLAUDE.md -> AGENTS.md` files.

Evidence: [PR #35](https://github.com/safurrier/ai-config/pull/35) has merge SHA `d9cd5b56158ae1e608573a730b84a92ec75a7b40`. It introduced descriptor-relative, no-follow reads. [PR #36](https://github.com/safurrier/ai-config/pull/36) has merge SHA `84fee140c5adba088c99b25da9eb87d47f1cbc23`. It records both the mirror exception and counterevidence. Alternate, absolute, escaping, and other symlink forms remain unsafe.

## Decision

All conversion source reads use the contained-source authority at the plugin directory. It rejects absolute and traversing paths, resolved escape, final and ancestor symlinks, and non-regular files before it reads bytes. Sync hashes the same safely readable file universe and checks that digest again before conversion.

Hashing can record metadata only for the exact sibling `CLAUDE.md -> AGENTS.md` mirror when the target is a no-follow regular file. It records the link and target bytes without reading through the link. Every other symlink makes the source unreadable. Standalone conversion never calculates a sync digest. Hashing and later conversion reads remain separate contained passes.

## Consequences

Source safety is a shared authority, not an emitter convention. Unsafe input fails closed, even when a target could otherwise emit a file. The mirror supports a demonstrated repository convention without creating a general link-following policy. The boundary neither makes output writes atomic nor proves ownership of existing output.
