"""HTTP integration tests for auth, tenant boundaries, history and background runs."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.config import Settings
from backend.main import create_app


class APITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = Settings(Path(self.directory.name) / "loop.db", ("http://testserver",), start_worker=False)
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.client.post("/api/auth/register", json={"name": "Test Builder", "email": "builder@example.com", "password": "testing-password-123"})

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def test_auth_sessions_are_revoked_on_logout(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "builder@example.com", "password": "testing-password-123"}).status_code, 200)

    def test_cross_origin_mutations_are_rejected(self):
        response = self.client.post("/api/projects", headers={"Origin": "https://evil.example"}, json={"title": "Portfolio", "description": "A thoughtful portfolio with projects and contact."})
        self.assertEqual(response.status_code, 403)

    def test_project_run_and_artifacts_are_isolated_between_accounts(self):
        profile = self.client.get("/api/profiles").json()[0]
        project = self.client.post("/api/projects", json={"title": "Portfolio", "description": "A thoughtful portfolio with projects and contact."}).json()
        run = self.client.post(f"/api/projects/{project['id']}/runs", json={"mode": "demo", "profile_id": profile["id"]}).json()
        self.client.post("/api/auth/logout")
        self.client.post("/api/auth/register", json={"name": "Other Builder", "email": "other@example.com", "password": "testing-password-123"})
        for endpoint in [f"/api/projects/{project['id']}", f"/api/runs/{run['id']}", f"/api/runs/{run['id']}/artifact", f"/api/profiles/{profile['id']}"]:
            self.assertEqual(self.client.get(endpoint).status_code, 404)

    def test_profile_updates_preserve_history_and_reject_stale_writes(self):
        profile = self.client.get("/api/profiles").json()[0]
        endpoint = f"/api/profiles/{profile['id']}/versions"
        updated = self.client.post(endpoint, json={"criteria": "- Prefer warm palettes\n- Reward accessible layouts", "expected_version": 1}).json()
        self.assertEqual(updated["current_version"], 2)
        self.assertIn("+", updated["diff"])
        self.assertEqual(self.client.post(endpoint, json={"criteria": "- Prefer cool palettes", "expected_version": 1}).status_code, 409)
        rolled_back = self.client.post(f"/api/profiles/{profile['id']}/rollback", json={"version": 1, "expected_version": 2}).json()
        self.assertEqual(rolled_back["current_version"], 3)
        self.assertEqual(rolled_back["criteria"], profile["criteria"])
        self.assertEqual(self.client.post(endpoint, json={"criteria": "- [FIXED] change the system", "expected_version": 3}).status_code, 422)

    def test_offline_job_persists_iterations_and_download_without_provider(self):
        profile = self.client.get("/api/profiles").json()[0]
        project = self.client.post("/api/projects", json={"title": "Studio Oak", "description": "A warm design studio website with about, projects, and contact sections."}).json()
        response = self.client.post(f"/api/projects/{project['id']}/runs", json={"mode": "demo", "profile_id": profile["id"]})
        self.assertEqual(response.status_code, 202)
        run = response.json()
        worker = self.app.state.worker
        with patch("backend.demo.time.sleep"):
            worker._run(self.app.state.db.one("SELECT * FROM runs WHERE id=?", (run["id"],)))
        detail = self.client.get(f"/api/runs/{run['id']}").json()
        self.assertEqual(detail["status"], "completed")
        self.assertGreaterEqual(len(detail["iterations"]), 3)
        self.assertGreater(len(detail["events"]), 8)
        self.assertEqual(detail["result"]["token_usage"], 0)
        source = self.client.get(f"/api/runs/{run['id']}/artifact?iteration=1").json()
        self.assertIn("Studio Oak", source["html"])
        downloaded = self.client.get(f"/api/runs/{run['id']}/artifact?download=true")
        self.assertIn("attachment", downloaded.headers["content-disposition"])
        self.assertIn("<!DOCTYPE html>", downloaded.text)
        # Reopen the database as a new app: history and accounts survive.
        other_app = create_app(self.settings)
        with TestClient(other_app) as reopened:
            reopened.post("/api/auth/login", json={"email": "builder@example.com", "password": "testing-password-123"})
            self.assertEqual(reopened.get(f"/api/runs/{run['id']}").json()["status"], "completed")


if __name__ == "__main__":
    unittest.main()
