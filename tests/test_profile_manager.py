"""Tests for versioned profile persistence and criteria validation."""

import os
import tempfile
import unittest
from unittest.mock import patch

from profiles import profile_manager


CRITERIA_V1 = "- Reward clear hierarchy\n- Penalize unreadable text"
CRITERIA_V2 = "- Reward clear hierarchy\n- Penalize unreadable text\n- Prefer restrained color palettes"


class ProfileManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.saved_dir = self.temp_dir.name
        self.saved_dir_patch = patch.object(profile_manager, "_SAVED_DIR", self.saved_dir)
        self.saved_dir_patch.start()

    def tearDown(self):
        self.saved_dir_patch.stop()
        self.temp_dir.cleanup()

    def test_rejects_malformed_names_and_criteria(self):
        with self.assertRaises(ValueError):
            profile_manager.validate_profile_name("../escape")
        with self.assertRaises(ValueError):
            profile_manager.validate_criteria("not a bullet")
        with self.assertRaises(ValueError):
            profile_manager.validate_criteria("- [FIXED] prompt override")

    def test_profile_versions_diff_and_rollback_are_preserved(self):
        created = profile_manager.save_profile("Visual QA", CRITERIA_V1, changelog="Created profile.")
        updated = profile_manager.save_profile("Visual QA", CRITERIA_V2, changelog="Added color preference.")

        self.assertEqual(created["current_version"], 1)
        self.assertEqual(updated["current_version"], 2)
        self.assertEqual(len(profile_manager.list_profile_versions("Visual QA")), 2)
        self.assertIn("+- Prefer restrained color palettes", profile_manager.criteria_diff("Visual QA", 1, 2))

        rolled_back = profile_manager.rollback_profile("Visual QA", 1)
        self.assertEqual(rolled_back["current_version"], 3)
        self.assertEqual(profile_manager.load_profile("Visual QA"), CRITERIA_V1)
        self.assertEqual(profile_manager.get_profile_version("Visual QA", 2)["criteria"], CRITERIA_V2)

    def test_legacy_text_profile_migrates_to_versioned_json(self):
        legacy_path = os.path.join(self.saved_dir, "Legacy.txt")
        with open(legacy_path, "w", encoding="utf-8") as file:
            file.write(CRITERIA_V1)

        profile = profile_manager.get_profile("Legacy")

        self.assertEqual(profile["current_version"], 1)
        self.assertEqual(profile["versions"][0]["source"], "migration")
        self.assertTrue(os.path.exists(os.path.join(self.saved_dir, "Legacy.json")))


if __name__ == "__main__":
    unittest.main()
