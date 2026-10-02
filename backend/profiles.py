"""Per-account profile history with optimistic concurrency and atomic updates."""
import difflib
import sqlite3
import uuid

from fastapi import HTTPException
from profiles.profile_manager import load_profile, validate_criteria, validate_profile_name
from backend.database import utcnow


def profile_detail(db, user_id, profile_id):
    profile = db.one("SELECT * FROM profiles WHERE id=? AND user_id=?", (profile_id, user_id))
    if not profile:
        raise HTTPException(404, "Profile not found.")
    versions = db.all("SELECT version, criteria, changelog, source, created_at FROM profile_versions WHERE profile_id=? ORDER BY version", (profile_id,))
    return {**profile, "current_version": versions[-1]["version"], "criteria": versions[-1]["criteria"], "versions": versions}


def create_profile(db, user_id, name, criteria):
    name = validate_profile_name(name)
    criteria = validate_criteria(criteria)
    profile_id = str(uuid.uuid4())
    now = utcnow()
    try:
        with db.connection() as connection:
            connection.execute("INSERT INTO profiles VALUES (?, ?, ?, ?, ?)", (profile_id, user_id, name, now, now))
            connection.execute("INSERT INTO profile_versions VALUES (?, 1, ?, ?, ?, ?)", (profile_id, criteria, "Created profile.", "manual", now))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "A profile with this name already exists.")
    return profile_detail(db, user_id, profile_id)


def seed_default_profile(db, user_id):
    return create_profile(db, user_id, "Balanced", load_profile("default"))


def append_version(db, user_id, profile_id, criteria, changelog, source, expected_version):
    criteria = validate_criteria(criteria)
    if not changelog.strip() or len(changelog) > 500:
        raise ValueError("Changelog must contain 1–500 characters.")
    profile_detail(db, user_id, profile_id)
    now = utcnow()
    with db.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute("SELECT * FROM profile_versions WHERE profile_id=? ORDER BY version DESC LIMIT 1", (profile_id,)).fetchone()
        if previous["version"] != expected_version:
            raise HTTPException(409, "The profile changed in another session. Reload before saving.")
        if previous["criteria"] != criteria:
            connection.execute("INSERT INTO profile_versions VALUES (?, ?, ?, ?, ?, ?)", (profile_id, expected_version + 1, criteria, changelog, source, now))
            connection.execute("UPDATE profiles SET updated_at=? WHERE id=?", (now, profile_id))
    detail = profile_detail(db, user_id, profile_id)
    detail["diff"] = "\n".join(difflib.unified_diff(previous["criteria"].splitlines(), criteria.splitlines(),
        fromfile=f"v{expected_version}", tofile=f"v{detail['current_version']}", lineterm=""))
    return detail
