"""Opt-in verification against a running local API. This consumes Groq tokens.

Creates a dedicated verification account and project, runs three actual AI rounds,
and prints only status/timing information. It is never executed by CI.
"""
import secrets
import time
import uuid

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=15) as client:
        config = client.get("/api/config").json()
        if not config["live_available"]:
            raise SystemExit("Configure GROQ_API_KEY on the running API before live verification.")
        account = client.post("/api/auth/register", json={
            "name": "Live verification", "email": f"verify-{uuid.uuid4().hex}@example.com",
            "password": secrets.token_urlsafe(24),
        })
        account.raise_for_status()
        profile = client.get("/api/profiles").json()[0]
        project = client.post("/api/projects", json={
            "title": "Solace Studio",
            "description": "A concise responsive design studio website. Three sections: hero, about, and contact. Warm cream background, dark green text, expressive typography. Clear contact email CTA and accessible navigation. Use compact inline CSS, no external images, and keep the entire site under 1200 words.",
        })
        project.raise_for_status()
        response = client.post(f"/api/projects/{project.json()['id']}/runs", json={"mode": "live", "profile_id": profile["id"], "max_iterations": 3})
        response.raise_for_status()
        run_id = response.json()["id"]
        deadline = time.monotonic() + 600
        previous = None
        while time.monotonic() < deadline:
            run = client.get(f"/api/runs/{run_id}").json()
            milestone = (run["status"], run["stage"], run["iteration"])
            if milestone != previous:
                print(f"{run['status']}: {run['stage']}, {run['iteration']} evaluated rounds", flush=True)
                previous = milestone
            if run["status"] not in {"queued", "running"}:
                if run["status"] != "completed":
                    raise SystemExit(run.get("error") or "Live run did not complete.")
                assert len(run["iterations"]) == 3
                assert run["result"]["traces"]
                artifact = client.get(f"/api/runs/{run_id}/artifact").json()["html"]
                assert "</html>" in artifact.lower()
                print(f"Verified: 3 actual AI rounds, {len(run['result']['traces'])} requests, {run['result']['token_usage']} tokens, best reward {run['result']['best_reward']}", flush=True)
                return
            time.sleep(3)
        client.post(f"/api/runs/{run_id}/cancel")
        raise SystemExit("Verification timed out; requested cancellation.")


if __name__ == "__main__":
    main()
