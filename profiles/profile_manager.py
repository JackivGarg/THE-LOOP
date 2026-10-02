"""Versioned JSON persistence for editable website-rating profiles."""

from __future__ import annotations

import difflib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any


_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SAVED_DIR = os.path.join(_THIS_DIR, "saved")
_PROMPTS_DIR = os.path.join(_THIS_DIR, "..", "prompts")
_RATER_TEMPLATE_PATH = os.path.join(_PROMPTS_DIR, "rater_prompt_template.txt")
_PROFILE_SCHEMA_VERSION = 1
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,47}$")
_FORBIDDEN_CRITERIA_MARKERS = ("[FIXED", "[EDITABLE", "{{", "}}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_profile_name(name: str) -> str:
    """Validate and normalize a human-readable profile name."""
    if not isinstance(name, str):
        raise ValueError("Profile name must be text.")
    normalized = name.strip()
    if not _NAME_PATTERN.fullmatch(normalized):
        raise ValueError("Profile names must be 1–48 characters and use only letters, numbers, spaces, hyphens, or underscores.")
    return normalized


def validate_criteria(criteria: str) -> str:
    """Accept only the editable, non-empty bulleted criteria block."""
    if not isinstance(criteria, str):
        raise ValueError("Criteria must be text.")
    normalized = criteria.strip()
    if not normalized:
        raise ValueError("Criteria cannot be empty.")
    if len(normalized) > 4_000:
        raise ValueError("Criteria must be at most 4,000 characters.")
    if any(marker.lower() in normalized.lower() for marker in _FORBIDDEN_CRITERIA_MARKERS):
        raise ValueError("Criteria may contain only the editable bullet list, not prompt-template markers.")

    lines = normalized.splitlines()
    if len(lines) > 80 or any(not line.startswith("- ") or len(line[2:].strip()) < 3 for line in lines):
        raise ValueError("Criteria must contain 1–80 non-empty bullet lines, each beginning with '- '.")
    return "\n".join(line.rstrip() for line in lines)


def _json_path(name: str) -> str:
    return os.path.join(_SAVED_DIR, f"{validate_profile_name(name)}.json")


def _legacy_path(name: str) -> str:
    return os.path.join(_SAVED_DIR, f"{validate_profile_name(name)}.txt")


def _validate_document(document: dict[str, Any], expected_name: str | None = None) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema_version") != _PROFILE_SCHEMA_VERSION:
        raise ValueError("Profile file has an unsupported or missing schema version.")
    name = validate_profile_name(document.get("name", ""))
    if expected_name and name != validate_profile_name(expected_name):
        raise ValueError("Profile file name does not match its stored profile name.")
    if not isinstance(document.get("created_at"), str) or not isinstance(document.get("updated_at"), str):
        raise ValueError("Profile timestamps are missing or malformed.")
    versions = document.get("versions")
    current_version = document.get("current_version")
    if not isinstance(versions, list) or not versions or not isinstance(current_version, int):
        raise ValueError("Profile history is missing or malformed.")

    expected_version = 1
    for version in versions:
        if not isinstance(version, dict) or version.get("version") != expected_version:
            raise ValueError("Profile versions must be a contiguous history starting at 1.")
        validate_criteria(version.get("criteria", ""))
        if not isinstance(version.get("created_at"), str) or not isinstance(version.get("changelog"), str):
            raise ValueError("A profile history entry is malformed.")
        expected_version += 1
    if current_version != len(versions):
        raise ValueError("Profile current_version does not match the latest history entry.")
    return document


def _write_document(document: dict[str, Any]) -> None:
    os.makedirs(_SAVED_DIR, exist_ok=True)
    path = _json_path(document["name"])
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(document, file, indent=2, ensure_ascii=False)
        file.write("\n")
    os.replace(temporary_path, path)


def _migrate_legacy_profile(name: str) -> dict[str, Any] | None:
    """Read an old text profile once and persist it as version 1 JSON."""
    legacy_path = _legacy_path(name)
    if not os.path.exists(legacy_path):
        return None
    with open(legacy_path, "r", encoding="utf-8") as file:
        criteria = validate_criteria(file.read())
    timestamp = _now()
    document = {
        "schema_version": _PROFILE_SCHEMA_VERSION,
        "name": validate_profile_name(name),
        "created_at": timestamp,
        "updated_at": timestamp,
        "current_version": 1,
        "versions": [{
            "version": 1,
            "criteria": criteria,
            "changelog": "Migrated from legacy text profile.",
            "created_at": timestamp,
            "source": "migration",
        }],
    }
    _write_document(document)
    return document


def get_profile(name: str) -> dict[str, Any]:
    """Load and validate a JSON profile, migrating a legacy text profile if required."""
    normalized_name = validate_profile_name(name)
    path = _json_path(normalized_name)
    if not os.path.exists(path):
        migrated = _migrate_legacy_profile(normalized_name)
        if migrated is not None:
            return migrated
        raise FileNotFoundError(f"Profile '{normalized_name}' was not found.")
    try:
        with open(path, "r", encoding="utf-8") as file:
            document = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"Profile '{normalized_name}' contains invalid JSON.") from error
    return _validate_document(document, normalized_name)


def list_profiles() -> list[str]:
    """List JSON profiles plus legacy text profiles awaiting migration."""
    os.makedirs(_SAVED_DIR, exist_ok=True)
    names: set[str] = set()
    for filename in os.listdir(_SAVED_DIR):
        if filename.endswith((".json", ".txt")):
            try:
                names.add(validate_profile_name(os.path.splitext(filename)[0]))
            except ValueError:
                continue
    return sorted(names, key=str.lower)


def load_profile(name: str) -> str:
    """Return only the current validated editable criteria block."""
    return get_profile(name)["versions"][-1]["criteria"]


def list_profile_versions(name: str) -> list[dict[str, Any]]:
    return [dict(version) for version in get_profile(name)["versions"]]


def get_profile_version(name: str, version_number: int) -> dict[str, Any]:
    document = get_profile(name)
    if not isinstance(version_number, int) or not 1 <= version_number <= document["current_version"]:
        raise ValueError("Requested profile version does not exist.")
    return dict(document["versions"][version_number - 1])


def save_profile(name: str, criteria: str, *, changelog: str = "Created profile.", source: str = "manual") -> dict[str, Any]:
    """Create a profile or append a validated criteria version to its history."""
    normalized_name = validate_profile_name(name)
    normalized_criteria = validate_criteria(criteria)
    if not isinstance(changelog, str) or not changelog.strip() or len(changelog.strip()) > 500:
        raise ValueError("Profile changelog must be 1–500 characters.")
    try:
        document = get_profile(normalized_name)
    except FileNotFoundError:
        timestamp = _now()
        document = {
            "schema_version": _PROFILE_SCHEMA_VERSION,
            "name": normalized_name,
            "created_at": timestamp,
            "updated_at": timestamp,
            "current_version": 0,
            "versions": [],
        }

    if document["versions"] and document["versions"][-1]["criteria"] == normalized_criteria:
        return document

    timestamp = _now()
    next_version = document["current_version"] + 1
    document["versions"].append({
        "version": next_version,
        "criteria": normalized_criteria,
        "changelog": changelog.strip(),
        "created_at": timestamp,
        "source": source,
    })
    document["current_version"] = next_version
    document["updated_at"] = timestamp
    _write_document(document)
    return document


def clone_profile(source_name: str, destination_name: str) -> dict[str, Any]:
    source = get_profile(source_name)
    destination = validate_profile_name(destination_name)
    if os.path.exists(_json_path(destination)) or os.path.exists(_legacy_path(destination)):
        raise FileExistsError(f"Profile '{destination}' already exists.")
    return save_profile(destination, source["versions"][-1]["criteria"], changelog=f"Cloned from '{source['name']}' version {source['current_version']}.", source="clone")


def rollback_profile(name: str, version_number: int) -> dict[str, Any]:
    """Append a rollback as a new version so no history is discarded."""
    target = get_profile_version(name, version_number)
    return save_profile(name, target["criteria"], changelog=f"Rolled back to version {version_number}.", source="rollback")


def criteria_diff(name: str, from_version: int, to_version: int) -> str:
    before = get_profile_version(name, from_version)["criteria"].splitlines()
    after = get_profile_version(name, to_version)["criteria"].splitlines()
    return "\n".join(difflib.unified_diff(before, after, fromfile=f"v{from_version}", tofile=f"v{to_version}", lineterm=""))


def delete_profile(name: str) -> None:
    normalized_name = validate_profile_name(name)
    if normalized_name.lower() == "default":
        raise ValueError("Cannot delete the default profile.")
    removed = False
    for path in (_json_path(normalized_name), _legacy_path(normalized_name)):
        if os.path.exists(path):
            os.remove(path)
            removed = True
    if not removed:
        raise FileNotFoundError(f"Profile '{normalized_name}' was not found.")


def get_composed_rater_prompt(profile_name: str, *, criteria: str | None = None) -> str:
    """Inject the editable criteria block into the immutable rater template."""
    with open(_RATER_TEMPLATE_PATH, "r", encoding="utf-8") as file:
        template = file.read()
    editable = load_profile(profile_name) if criteria is None else validate_criteria(criteria)
    return template.replace("{{editable_block}}", editable)
