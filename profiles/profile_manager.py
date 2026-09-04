"""
Profile Manager — CRUD operations for reward profiles.
Each profile is a .txt file in profiles/saved/ containing only the [EDITABLE] criteria block.
The fixed blocks live in prompts/rater_prompt_template.txt and are injected at call time.
"""

import os
import shutil

# Resolve paths relative to this file's location
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SAVED_DIR = os.path.join(_THIS_DIR, "saved")
_PROMPTS_DIR = os.path.join(_THIS_DIR, "..", "prompts")
_RATER_TEMPLATE_PATH = os.path.join(_PROMPTS_DIR, "rater_prompt_template.txt")


def _profile_path(name: str) -> str:
    """Get the full filesystem path for a profile by name."""
    # Sanitize: strip .txt if user passes it, prevent path traversal
    clean_name = os.path.basename(name.replace(".txt", ""))
    return os.path.join(_SAVED_DIR, f"{clean_name}.txt")


def list_profiles() -> list[str]:
    """Return a sorted list of all profile names (without .txt extension)."""
    os.makedirs(_SAVED_DIR, exist_ok=True)
    profiles = []
    for f in os.listdir(_SAVED_DIR):
        if f.endswith(".txt"):
            profiles.append(f.replace(".txt", ""))
    return sorted(profiles)


def load_profile(name: str) -> str:
    """
    Load the editable criteria block text for a profile.
    Raises FileNotFoundError if the profile doesn't exist.
    """
    path = _profile_path(name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Profile '{name}' not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def save_profile(name: str, text: str) -> None:
    """Create or overwrite a profile with the given criteria text."""
    os.makedirs(_SAVED_DIR, exist_ok=True)
    path = _profile_path(name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")


def clone_profile(src: str, dst: str) -> None:
    """Clone an existing profile to a new name."""
    src_path = _profile_path(src)
    dst_path = _profile_path(dst)
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Source profile '{src}' not found")
    if os.path.exists(dst_path):
        raise FileExistsError(f"Destination profile '{dst}' already exists")
    shutil.copy2(src_path, dst_path)


def delete_profile(name: str) -> None:
    """
    Delete a profile. Raises ValueError if trying to delete 'default'.
    Raises FileNotFoundError if profile doesn't exist.
    """
    if name.lower() == "default":
        raise ValueError("Cannot delete the default profile")
    path = _profile_path(name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Profile '{name}' not found")
    os.remove(path)


def get_composed_rater_prompt(profile_name: str) -> str:
    """
    Build the full rater prompt by injecting the profile's editable block
    into the rater prompt template's {{editable_block}} placeholder.
    """
    # Load template
    with open(_RATER_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    # Load profile's editable block
    editable_block = load_profile(profile_name)

    # Inject
    composed = template.replace("{{editable_block}}", editable_block)
    return composed
