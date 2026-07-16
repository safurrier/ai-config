#!/usr/bin/env bash
# Resolve npm latest, verify registry tarballs, and run isolated package plus public-sync probes.
# Direct tarball extraction avoids npm's intentional install-date cutoff while preserving
# registry integrity verification and the exact package layout used by the npm launcher.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/ai-config-codex-latest.XXXXXX")
trap 'rm -rf "$work"' EXIT

version=$(npm view @openai/codex@latest version)
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) platform=darwin-arm64 ;;
  Darwin-x86_64) platform=darwin-x64 ;;
  Linux-aarch64|Linux-arm64) platform=linux-arm64 ;;
  Linux-x86_64) platform=linux-x64 ;;
  *) echo "unsupported Codex probe platform: $(uname -s)-$(uname -m)" >&2; exit 2 ;;
esac

install_package() {
  local spec=$1 destination=$2 archive=$3
  local url integrity expected actual
  url=$(npm view "$spec" dist.tarball)
  integrity=$(npm view "$spec" dist.integrity)
  expected=${integrity#sha512-}
  curl -fsSL "$url" -o "$archive"
  actual=$(openssl dgst -sha512 -binary "$archive" | openssl base64 -A)
  if [[ "$actual" != "$expected" ]]; then
    echo "integrity mismatch for $spec" >&2
    exit 1
  fi
  mkdir -p "$destination"
  tar -xzf "$archive" -C "$destination" --strip-components=1
  printf '%s|%s|%s\n' "$spec" "$url" "$integrity"
}

mkdir -p "$work/install/node_modules/@openai"
main_evidence=$(install_package \
  "@openai/codex@$version" \
  "$work/install/node_modules/@openai/codex" \
  "$work/codex.tgz")
platform_evidence=$(install_package \
  "@openai/codex@$version-$platform" \
  "$work/install/node_modules/@openai/codex-$platform" \
  "$work/codex-platform.tgz")
codex="$work/install/node_modules/@openai/codex/bin/codex.js"
chmod +x "$codex"

printf 'resolved_package=@openai/codex@%s\n' "$version"
printf 'main_registry_tarball=%s\n' "$main_evidence"
printf 'platform_registry_tarball=%s\n' "$platform_evidence"
printf 'install_method=integrity-verified direct registry tarball extraction (npm cutoff-safe)\n'
printf 'binary=%s\n' "$codex"
cd "$repo_root"
uv run python tests/probes/probe_codex_plugin_package.py \
  --codex "$codex" \
  --expected-version "$version"
uv run python tests/probes/probe_ai_config_sync_codex.py --codex "$codex"
