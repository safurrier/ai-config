# Read plugin sources through a fail-closed boundary

Status: Accepted
Date: 2026-08-20

## Context

Conversion reads manifests, instructions, assets, includes, and target-native files from a plugin tree. Ordinary path resolution can follow a symlink, cross the plugin root, or read a special file after an earlier check. A broad symlink exception would weaken the source boundary. The repository does use one narrow compatibility mirror: sibling `CLAUDE.md -> AGENTS.md` files.

Evidence: [PR #35](https://github.com/safurrier/ai-config/pull/35), merge SHA `d9cd5b56158ae1e608573a730b84a92ec75a7b40`, introduced descriptor-relative, no-follow reads. [PR #36](https://github.com/safurrier/ai-config/pull/36), merge SHA `84fee140c5adba088c99b25da9eb87d47f1cbc23`, records the mirror exception and its counterevidence: alternate, absolute, escaping, and other symlink shapes remain unsafe.

## Decision

All conversion source reads use the contained-source authority rooted at the plugin directory. It rejects absolute and traversing paths, resolved escape, final or ancestor symlinks, and non-regular files before bytes are read. Sync hashes the same safely readable file universe and rechecks that digest before conversion.

Hashing may record metadata for only the exact sibling `CLAUDE.md -> AGENTS.md` mirror when the target is a no-follow regular file. It records the link and target bytes without reading through the link. All other symlinks make the source unreadable. Standalone conversion does not calculate a sync digest, and hashing plus later conversion reads remain separate contained passes.

## Consequences

Source safety is a shared authority rather than an emitter convention. Unsafe input fails closed, even when a target might otherwise emit a file. The mirror supports a demonstrated repository convention without creating a general link-following policy. The boundary does not make output writes atomic and does not establish ownership for existing output.
