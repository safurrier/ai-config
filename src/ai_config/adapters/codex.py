"""Fail-closed subprocess adapter for the Codex plugin lifecycle CLI."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ai_config.semver import SemanticVersion

_SUPPORTED_CODEX_MAJOR_MINOR = (0, 144)
_DEFAULT_TIMEOUT_SECONDS = 30.0
_MAX_ERROR_OUTPUT = 4_000
_KNOWN_SOURCE_TYPES = {"local", "git", "github", "remote"}
_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class _DuplicateJSONKey(ValueError):
    """Raised when Codex emits an ambiguous JSON object."""


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(f"duplicate JSON key '{key}'")
        result[key] = value
    return result


def _as_object_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        return None
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _timeout_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _sanitize_output(value: str) -> str:
    """Bound and strip terminal control characters from child output."""
    without_ansi = _ANSI_ESCAPE.sub("", value)
    cleaned = "".join(
        character for character in without_ansi if character in "\n\r\t" or ord(character) >= 32
    )
    if len(cleaned) > _MAX_ERROR_OUTPUT:
        return cleaned[:_MAX_ERROR_OUTPUT] + "\n...[truncated]"
    return cleaned


@dataclass(frozen=True)
class CodexMarketplace:
    """One validated marketplace reported by Codex."""

    name: str
    root: Path


@dataclass(frozen=True)
class CodexInstalledPlugin:
    """One validated installed plugin reported by Codex."""

    plugin_id: str
    name: str
    marketplace_name: str
    version: str
    enabled: bool
    source_path: Path | None
    marketplace_root: Path | None


@dataclass(frozen=True)
class CodexPluginInstall:
    """Validated result of installing one Codex plugin."""

    plugin_id: str
    name: str
    marketplace_name: str
    version: str
    installed_path: Path


@dataclass(frozen=True)
class CodexCommandError(RuntimeError):
    """Actionable failure from one Codex lifecycle stage."""

    stage: str
    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    remediation: str

    def __str__(self) -> str:
        rendered = shlex.join(self.command)
        detail = self.stderr.strip() or self.stdout.strip() or "no command output"
        return (
            f"Codex plugin lifecycle failed at stage '{self.stage}': {rendered} "
            f"(exit {self.returncode}). {detail}. Remediation: {self.remediation}"
        )


@dataclass(frozen=True)
class _CommandOutput:
    returncode: int
    stdout: str
    stderr: str


class CodexCLI:
    """Typed wrapper around the supported Codex plugin JSON contract."""

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Codex subprocess timeout must be greater than zero seconds")
        self.executable = executable or shutil.which("codex") or "codex"
        self.timeout_seconds = timeout_seconds
        self._version: str | None = None

    def _error(
        self,
        stage: str,
        args: list[str],
        *,
        returncode: int | None,
        stdout: str,
        stderr: str,
        remediation: str,
    ) -> CodexCommandError:
        return CodexCommandError(
            stage=stage,
            command=(self.executable, *args),
            returncode=returncode,
            stdout=_sanitize_output(stdout),
            stderr=_sanitize_output(stderr),
            remediation=remediation,
        )

    def _stop_process_tree(self, process: subprocess.Popen[str]) -> None:
        """Terminate a timed-out command and every descendant in its process group."""
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        else:
            process.terminate()
        try:
            process.communicate(timeout=0.5)
            return
        except subprocess.TimeoutExpired:
            pass
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
        else:
            process.kill()
        process.communicate()

    def _run(
        self,
        stage: str,
        args: list[str],
        *,
        remediation: str,
    ) -> _CommandOutput:
        command = (self.executable, *args)
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=os.name == "posix",
            )
        except OSError as error:
            raise self._error(
                stage,
                args,
                returncode=None,
                stdout="",
                stderr=str(error),
                remediation=remediation,
            ) from error
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as error:
            self._stop_process_tree(process)
            raise self._error(
                stage,
                args,
                returncode=None,
                stdout=_timeout_text(error.stdout),
                stderr=f"command timed out after {self.timeout_seconds:g} seconds",
                remediation=remediation,
            ) from error
        if process.returncode != 0:
            raise self._error(
                stage,
                args,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                remediation=remediation,
            )
        return _CommandOutput(process.returncode, stdout, stderr)

    def _ensure_supported_version(self) -> str:
        if self._version is not None:
            return self._version
        remediation = (
            "Install the Codex 0.144.x compatibility baseline or update ai-config's "
            "Codex adapter and probes for the new CLI contract."
        )
        output = self._run("inspect-version", ["--version"], remediation=remediation)
        match = re.fullmatch(r"codex-cli (\S+)\s*", output.stdout)
        if match is None:
            raise self._error(
                "inspect-version",
                ["--version"],
                returncode=output.returncode,
                stdout=output.stdout,
                stderr="unrecognized Codex version output",
                remediation=remediation,
            )
        version_text = match.group(1)
        try:
            version = SemanticVersion.parse(version_text, context="Codex CLI version")
        except ValueError as error:
            raise self._error(
                "inspect-version",
                ["--version"],
                returncode=output.returncode,
                stdout=output.stdout,
                stderr=str(error),
                remediation=remediation,
            ) from error
        if (version.major, version.minor) != _SUPPORTED_CODEX_MAJOR_MINOR:
            raise self._error(
                "inspect-version",
                ["--version"],
                returncode=output.returncode,
                stdout=output.stdout,
                stderr=(
                    f"unsupported Codex CLI response contract {version_text}; expected 0.144.x"
                ),
                remediation=remediation,
            )
        self._version = version_text
        return version_text

    def run_json(
        self,
        stage: str,
        args: list[str],
        *,
        remediation: str,
    ) -> dict[str, object]:
        """Run one JSON command and reject malformed or duplicate-key payloads."""
        output = self._run(stage, args, remediation=remediation)
        try:
            payload: object = json.loads(output.stdout, object_pairs_hook=_json_object)
        except (json.JSONDecodeError, _DuplicateJSONKey) as error:
            raise self._error(
                stage,
                args,
                returncode=output.returncode,
                stdout=output.stdout,
                stderr=f"expected unambiguous JSON output: {error}",
                remediation=remediation,
            ) from error
        if not isinstance(payload, dict):
            raise self._error(
                stage,
                args,
                returncode=output.returncode,
                stdout=output.stdout,
                stderr="expected a JSON object",
                remediation=remediation,
            )
        return payload

    def _schema_error(
        self,
        stage: str,
        args: list[str],
        payload: dict[str, object],
        detail: str,
        remediation: str,
    ) -> CodexCommandError:
        return self._error(
            stage,
            args,
            returncode=0,
            stdout=json.dumps(payload, sort_keys=True),
            stderr=f"invalid Codex 0.144.x JSON response: {detail}",
            remediation=remediation,
        )

    def list_marketplaces(self) -> list[CodexMarketplace]:
        self._ensure_supported_version()
        args = ["plugin", "marketplace", "list", "--json"]
        remediation = "Run `codex plugin marketplace list --json` and repair Codex config errors."
        payload = self.run_json("list-marketplaces", args, remediation=remediation)
        value = payload.get("marketplaces")
        if not isinstance(value, list):
            raise self._schema_error(
                "list-marketplaces", args, payload, "marketplaces must be an array", remediation
            )
        results: list[CodexMarketplace] = []
        seen: set[str] = set()
        for index, entry in enumerate(value):
            object_entry = _as_object_dict(entry)
            if object_entry is None:
                raise self._schema_error(
                    "list-marketplaces",
                    args,
                    payload,
                    f"marketplaces[{index}] must be an object with string keys",
                    remediation,
                )
            entry = object_entry
            name = entry.get("name")
            root = entry.get("root")
            source = entry.get("marketplaceSource")
            if not isinstance(name, str) or not name:
                detail = f"marketplaces[{index}].name must be a non-empty string"
                raise self._schema_error("list-marketplaces", args, payload, detail, remediation)
            if name in seen:
                raise self._schema_error(
                    "list-marketplaces",
                    args,
                    payload,
                    f"duplicate marketplace '{name}'",
                    remediation,
                )
            if not isinstance(root, str) or not root:
                detail = f"marketplaces[{index}].root must be a non-empty string"
                raise self._schema_error("list-marketplaces", args, payload, detail, remediation)
            source_object = _as_object_dict(source)
            if source_object is None:
                detail = f"marketplaces[{index}].marketplaceSource must be an object"
                raise self._schema_error("list-marketplaces", args, payload, detail, remediation)
            source_type = source_object.get("sourceType")
            source_value = source_object.get("source")
            if source_type not in _KNOWN_SOURCE_TYPES or not isinstance(source_value, str):
                detail = f"marketplaces[{index}] has an unknown marketplace source"
                raise self._schema_error("list-marketplaces", args, payload, detail, remediation)
            if source_type == "local" and Path(source_value).resolve() != Path(root).resolve():
                detail = f"marketplaces[{index}] local root and source disagree"
                raise self._schema_error("list-marketplaces", args, payload, detail, remediation)
            seen.add(name)
            results.append(CodexMarketplace(name=name, root=Path(root).resolve()))
        return results

    def add_marketplace(self, path: str, expected_name: str) -> CodexMarketplace:
        self._ensure_supported_version()
        args = ["plugin", "marketplace", "add", path, "--json"]
        remediation = "Validate the generated .agents/plugins/marketplace.json, then retry sync."
        payload = self.run_json("add-marketplace", args, remediation=remediation)
        name = payload.get("marketplaceName")
        root = payload.get("installedRoot")
        already_added = payload.get("alreadyAdded")
        if (
            not isinstance(name, str)
            or name != expected_name
            or not isinstance(root, str)
            or not isinstance(already_added, bool)
        ):
            raise self._schema_error(
                "add-marketplace",
                args,
                payload,
                "marketplaceName, installedRoot, or alreadyAdded did not match the request",
                remediation,
            )
        expected_root = Path(path).resolve()
        if Path(root).resolve() != expected_root:
            raise self._schema_error(
                "add-marketplace",
                args,
                payload,
                f"installedRoot does not match requested path {expected_root}",
                remediation,
            )
        return CodexMarketplace(name=name, root=expected_root)

    def remove_marketplace(self, name: str) -> None:
        self._ensure_supported_version()
        args = ["plugin", "marketplace", "remove", name, "--json"]
        remediation = "Inspect the named ai-config marketplace with Codex, then retry sync."
        payload = self.run_json("remove-marketplace", args, remediation=remediation)
        if payload.get("marketplaceName") != name or payload.get("installedRoot") is not None:
            raise self._schema_error(
                "remove-marketplace",
                args,
                payload,
                "response did not confirm removal of the requested marketplace",
                remediation,
            )

    def list_plugins(self) -> list[CodexInstalledPlugin]:
        self._ensure_supported_version()
        args = ["plugin", "list", "--json"]
        remediation = "Run `codex plugin list --json` and repair Codex config errors."
        payload = self.run_json("list-plugins", args, remediation=remediation)
        installed = payload.get("installed")
        available = payload.get("available")
        if not isinstance(installed, list) or not isinstance(available, list):
            raise self._schema_error(
                "list-plugins",
                args,
                payload,
                "installed and available must both be arrays",
                remediation,
            )
        if any(_as_object_dict(entry) is None for entry in available):
            raise self._schema_error(
                "list-plugins",
                args,
                payload,
                "available entries must be objects with string keys",
                remediation,
            )
        results: list[CodexInstalledPlugin] = []
        seen: set[str] = set()
        for index, entry in enumerate(installed):
            object_entry = _as_object_dict(entry)
            if object_entry is None:
                raise self._schema_error(
                    "list-plugins",
                    args,
                    payload,
                    f"installed[{index}] must be an object with string keys",
                    remediation,
                )
            entry = object_entry
            plugin_id = entry.get("pluginId")
            name = entry.get("name")
            marketplace_name = entry.get("marketplaceName")
            version = entry.get("version")
            enabled = entry.get("enabled")
            source = entry.get("source")
            marketplace_source = entry.get("marketplaceSource")
            if (
                not isinstance(plugin_id, str)
                or not plugin_id
                or not isinstance(name, str)
                or not name
                or not isinstance(marketplace_name, str)
                or not marketplace_name
                or not isinstance(version, str)
                or not isinstance(enabled, bool)
                or entry.get("installed") is not True
                or not isinstance(entry.get("installPolicy"), str)
                or not isinstance(entry.get("authPolicy"), str)
            ):
                raise self._schema_error(
                    "list-plugins",
                    args,
                    payload,
                    f"installed[{index}] is missing required typed fields",
                    remediation,
                )
            if plugin_id != f"{name}@{marketplace_name}":
                raise self._schema_error(
                    "list-plugins",
                    args,
                    payload,
                    f"installed[{index}] plugin identity fields disagree",
                    remediation,
                )
            if plugin_id in seen:
                raise self._schema_error(
                    "list-plugins",
                    args,
                    payload,
                    f"duplicate installed plugin '{plugin_id}'",
                    remediation,
                )
            try:
                SemanticVersion.parse(
                    version, context=f"installed Codex plugin {plugin_id} version"
                )
            except ValueError as error:
                raise self._schema_error(
                    "list-plugins", args, payload, str(error), remediation
                ) from error
            source_object = _as_object_dict(source)
            source_type = source_object.get("source") if source_object is not None else None
            if source_object is None or source_type not in _KNOWN_SOURCE_TYPES:
                detail = f"installed[{index}].source has an unknown source type"
                raise self._schema_error("list-plugins", args, payload, detail, remediation)
            source_path_value = source_object.get("path")
            if source_type == "local" and (
                not isinstance(source_path_value, str) or not source_path_value
            ):
                detail = f"installed[{index}].source.path must be a non-empty string"
                raise self._schema_error("list-plugins", args, payload, detail, remediation)
            resolved_source = (
                Path(source_path_value).resolve() if isinstance(source_path_value, str) else None
            )
            marketplace_source_object = _as_object_dict(marketplace_source)
            marketplace_source_value = (
                marketplace_source_object.get("source")
                if marketplace_source_object is not None
                else None
            )
            if (
                marketplace_source_object is None
                or marketplace_source_object.get("sourceType") not in _KNOWN_SOURCE_TYPES
                or not isinstance(marketplace_source_value, str)
            ):
                detail = f"installed[{index}].marketplaceSource has an unknown source type"
                raise self._schema_error("list-plugins", args, payload, detail, remediation)
            marketplace_source_type = marketplace_source_object.get("sourceType")
            marketplace_root = (
                Path(marketplace_source_value).resolve()
                if marketplace_source_type == "local"
                else None
            )
            if (
                marketplace_root is not None
                and resolved_source is not None
                and marketplace_root not in resolved_source.parents
            ):
                detail = f"installed[{index}] plugin source is outside its marketplace root"
                raise self._schema_error("list-plugins", args, payload, detail, remediation)
            seen.add(plugin_id)
            results.append(
                CodexInstalledPlugin(
                    plugin_id=plugin_id,
                    name=name,
                    marketplace_name=marketplace_name,
                    version=version,
                    enabled=enabled,
                    source_path=resolved_source,
                    marketplace_root=marketplace_root,
                )
            )
        return results

    def add_plugin(self, plugin_id: str) -> CodexPluginInstall:
        self._ensure_supported_version()
        args = ["plugin", "add", plugin_id, "--json"]
        remediation = (
            "Confirm the generated marketplace is registered and the plugin is available, "
            "then retry sync."
        )
        payload = self.run_json("install-plugin", args, remediation=remediation)
        name, marketplace_name = self._plugin_parts(plugin_id, "install-plugin", args, remediation)
        version = payload.get("version")
        installed_path = payload.get("installedPath")
        if (
            payload.get("pluginId") != plugin_id
            or payload.get("name") != name
            or payload.get("marketplaceName") != marketplace_name
            or not isinstance(version, str)
            or not isinstance(installed_path, str)
            or not installed_path
            or not isinstance(payload.get("authPolicy"), str)
        ):
            raise self._schema_error(
                "install-plugin",
                args,
                payload,
                "response identity or required fields did not match the install request",
                remediation,
            )
        try:
            SemanticVersion.parse(version, context=f"installed Codex plugin {plugin_id} version")
        except ValueError as error:
            raise self._schema_error(
                "install-plugin", args, payload, str(error), remediation
            ) from error
        return CodexPluginInstall(
            plugin_id=plugin_id,
            name=name,
            marketplace_name=marketplace_name,
            version=version,
            installed_path=Path(installed_path).resolve(),
        )

    def remove_plugin(self, plugin_id: str) -> None:
        self._ensure_supported_version()
        args = ["plugin", "remove", plugin_id, "--json"]
        remediation = (
            "Inspect the ai-config-owned plugin entry and cache with Codex, then retry sync."
        )
        payload = self.run_json("remove-plugin", args, remediation=remediation)
        name, marketplace_name = self._plugin_parts(plugin_id, "remove-plugin", args, remediation)
        if (
            payload.get("pluginId") != plugin_id
            or payload.get("name") != name
            or payload.get("marketplaceName") != marketplace_name
        ):
            raise self._schema_error(
                "remove-plugin",
                args,
                payload,
                "response did not confirm removal of the requested plugin",
                remediation,
            )

    def _plugin_parts(
        self,
        plugin_id: str,
        stage: str,
        args: list[str],
        remediation: str,
    ) -> tuple[str, str]:
        parts = plugin_id.rsplit("@", 1)
        if len(parts) != 2 or not all(parts):
            raise self._error(
                stage,
                args,
                returncode=None,
                stdout="",
                stderr=f"invalid plugin selector '{plugin_id}'",
                remediation=remediation,
            )
        return parts[0], parts[1]
