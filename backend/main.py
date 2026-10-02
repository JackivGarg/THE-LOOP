"""FastAPI application factory for THE LOOP.

API routes enforce ownership at every resource boundary. The frontend is served
from the same origin in production, with an explicit development proxy.
"""
import json
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.auth import SESSION_COOKIE, create_session, current_user, hash_password, session_hash, throttle, verify_password
from backend.config import Settings
from backend.database import Database, json_dump, utcnow
from backend.profiles import append_version, create_profile, profile_detail, seed_default_profile
from backend.schemas import Credentials, FeedbackInput, ProfileEdit, ProfileInput, ProjectInput, Registration, RollbackInput, RunInput
from backend.worker import RunWorker
from nodes.criteria_updater import _call_criteria_updater
from state import init_state
from utils.groq_provider import get_provider_config, load_model_config
from utils.retry import call_with_retry

ROOT = Path(__file__).resolve().parent.parent


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.database_path)
    worker = RunWorker(db)

    @asynccontextmanager
    async def lifespan(app):
        db.initialize()
        if settings.start_worker:
            worker.start()
        yield
        worker.stop()

    app = FastAPI(title="THE LOOP API", version="1.0.0", lifespan=lifespan,
                  description="An evaluator-driven website generation workspace.")
    app.state.db = db
    app.state.worker = worker
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.origins),
                       allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Content-Type"])

    @app.middleware("http")
    async def request_guards(request: Request, call_next):
        if request.method in {"POST", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"detail": "Origin is not allowed."}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site request rejected."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid_value(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    def owned_project(project_id, user):
        project = db.one("SELECT * FROM projects WHERE id=? AND user_id=?", (project_id, user["id"]))
        if not project:
            raise HTTPException(404, "Project not found.")
        return project

    def owned_run(run_id, user):
        run = db.one("SELECT r.* FROM runs r JOIN projects p ON p.id=r.project_id WHERE r.id=? AND p.user_id=?", (run_id, user["id"]))
        if not run:
            raise HTTPException(404, "Run not found.")
        return run

    def serialize_run(run):
        return {key: value for key, value in run.items() if key not in {"state_json", "result_json", "input_json"}} | {
            "input": json.loads(run["input_json"]),
            "result": json.loads(run["result_json"]) if run["result_json"] else None,
        }

    @app.get("/api/health", tags=["System"])
    def health():
        db.one("SELECT 1")
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/api/config", tags=["System"])
    def config():
        try:
            get_provider_config()
            available = True
        except (RuntimeError, ValueError):
            available = False
        return {"live_available": available, "demo_available": settings.enable_demo,
                "models": vars(load_model_config()), "min_iterations": 3,
                "quality_threshold": 0.90, "evaluation_weights": {"deterministic": 0.4, "rubric": 0.4, "description": 0.2}}

    @app.post("/api/auth/register", status_code=201, tags=["Accounts"])
    def register(payload: Registration, request: Request, response: Response):
        throttle(db, f"register:{request.client.host}", limit=5)
        user_id = str(uuid.uuid4())
        try:
            db.execute("INSERT INTO users VALUES (?,?,?,?,?)", (user_id, payload.email, payload.name, hash_password(payload.password), utcnow()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "An account with this email already exists.")
        seed_default_profile(db, user_id)
        create_session(db, user_id, response, settings.secure_cookies)
        return db.one("SELECT id, email, name, created_at FROM users WHERE id=?", (user_id,))

    @app.post("/api/auth/login", tags=["Accounts"])
    def login(payload: Credentials, request: Request, response: Response):
        throttle(db, f"login:{request.client.host}")
        user = db.one("SELECT * FROM users WHERE email=?", (payload.email,))
        # Use a real password computation even for a missing user.
        stored = user["password_hash"] if user else "scrypt$" + "00" * 16 + "$" + "00" * 64
        if not verify_password(payload.password, stored) or not user:
            raise HTTPException(401, "Email or password is incorrect.")
        create_session(db, user["id"], response, settings.secure_cookies)
        return {key: user[key] for key in ("id", "email", "name", "created_at")}

    @app.get("/api/auth/me", tags=["Accounts"])
    def me(user=Depends(current_user)):
        return user

    @app.post("/api/auth/logout", status_code=204, tags=["Accounts"])
    def logout(request: Request, response: Response):
        db.execute("DELETE FROM sessions WHERE token_hash=?", (session_hash(request.cookies.get(SESSION_COOKIE, "")),))
        response.delete_cookie(SESSION_COOKIE, path="/api")

    @app.get("/api/projects", tags=["Projects"])
    def projects(user=Depends(current_user)):
        records = db.all("SELECT * FROM projects WHERE user_id=? ORDER BY updated_at DESC", (user["id"],))
        for project in records:
            latest = db.one("SELECT * FROM runs WHERE project_id=? ORDER BY created_at DESC LIMIT 1", (project["id"],))
            project["latest_run"] = serialize_run(latest) if latest else None
            project["run_count"] = db.one("SELECT COUNT(*) AS count FROM runs WHERE project_id=?", (project["id"],))["count"]
        return records

    @app.post("/api/projects", status_code=201, tags=["Projects"])
    def create_project(payload: ProjectInput, user=Depends(current_user)):
        project_id = str(uuid.uuid4())
        now = utcnow()
        db.execute("INSERT INTO projects VALUES (?,?,?,?,?,?)", (project_id, user["id"], payload.title, payload.description, now, now))
        return owned_project(project_id, user)

    @app.get("/api/projects/{project_id}", tags=["Projects"])
    def project_detail(project_id: str, user=Depends(current_user)):
        project = owned_project(project_id, user)
        project["runs"] = [serialize_run(row) for row in db.all("SELECT * FROM runs WHERE project_id=? ORDER BY created_at DESC", (project_id,))]
        return project

    @app.patch("/api/projects/{project_id}", tags=["Projects"])
    def edit_project(project_id: str, payload: ProjectInput, user=Depends(current_user)):
        owned_project(project_id, user)
        if db.one("SELECT id FROM runs WHERE project_id=? AND status IN ('queued','running')", (project_id,)):
            raise HTTPException(409, "Wait for the active run before editing its brief.")
        db.execute("UPDATE projects SET title=?,description=?,updated_at=? WHERE id=?", (payload.title, payload.description, utcnow(), project_id))
        return owned_project(project_id, user)

    @app.post("/api/projects/{project_id}/runs", status_code=202, tags=["Runs"])
    def start_run(project_id: str, payload: RunInput, user=Depends(current_user)):
        project = owned_project(project_id, user)
        profile = profile_detail(db, user["id"], payload.profile_id)
        if payload.mode == "demo" and not settings.enable_demo:
            raise HTTPException(400, "Offline walkthrough is disabled.")
        if payload.mode == "live":
            try:
                get_provider_config()
            except (RuntimeError, ValueError):
                raise HTTPException(503, "Live generation requires a configured server-side GROQ_API_KEY.")
        state = init_state()
        state.update(user_input={"title": project["title"], "description": project["description"]},
            active_profile=profile["name"], profile_criteria=profile["criteria"],
            criteria_version=profile["current_version"], max_iterations=payload.max_iterations,
            check_external_resources=False)
        run_id, now = str(uuid.uuid4()), utcnow()
        inputs = {**payload.model_dump(), "title": project["title"], "description": project["description"],
                  "profile_name": profile["name"], "profile_version": profile["current_version"], "criteria": profile["criteria"]}
        with db.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute("SELECT r.id FROM runs r JOIN projects p ON p.id=r.project_id WHERE p.user_id=? AND r.status IN ('queued','running')", (user["id"],)).fetchone()
            if active:
                raise HTTPException(409, "You already have an active run. Finish or stop it first.")
            count = connection.execute("SELECT COUNT(*) FROM runs WHERE status IN ('queued','running')").fetchone()[0]
            if count >= 20:
                raise HTTPException(429, "The run queue is full. Try again shortly.")
            connection.execute("INSERT INTO runs(id,project_id,mode,status,stage,max_iterations,input_json,state_json,created_at,updated_at) VALUES (?,?,?,'queued','queued',?,?,?,?,?)",
                               (run_id, project_id, payload.mode, payload.max_iterations, json_dump(inputs), json_dump(state), now, now))
        worker.notify()
        return serialize_run(owned_run(run_id, user))

    @app.get("/api/runs/{run_id}", tags=["Runs"])
    def run_detail(run_id: str, user=Depends(current_user)):
        run = owned_run(run_id, user)
        result = serialize_run(run)
        result["events"] = db.all("SELECT id,stage,message,iteration,created_at FROM run_events WHERE run_id=? ORDER BY id", (run_id,))
        records = db.all("SELECT iteration,reward,report_json,created_at FROM iterations WHERE run_id=? ORDER BY iteration", (run_id,))
        result["iterations"] = [{**{k: v for k, v in row.items() if k != "report_json"}, "report": json.loads(row["report_json"])} for row in records]
        return result

    @app.post("/api/runs/{run_id}/cancel", tags=["Runs"])
    def cancel_run(run_id: str, user=Depends(current_user)):
        run = owned_run(run_id, user)
        if run["status"] in {"queued", "running"}:
            db.execute("UPDATE runs SET cancel_requested=1, status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END, updated_at=? WHERE id=?", (utcnow(), run_id))
        return serialize_run(owned_run(run_id, user))

    @app.get("/api/runs/{run_id}/artifact", tags=["Runs"])
    def artifact(run_id: str, iteration: int | None = None, download: bool = False, user=Depends(current_user)):
        run = owned_run(run_id, user)
        if iteration is not None:
            row = db.one("SELECT html FROM iterations WHERE run_id=? AND iteration=?", (run_id, iteration))
            source = row["html"] if row else None
        else:
            source = json.loads(run["state_json"]).get("current_code")
        if not source:
            raise HTTPException(404, "This run has no HTML artifact yet.")
        headers = {"Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; style-src 'unsafe-inline' https:; script-src 'unsafe-inline' https:; font-src https:; img-src https: data:; connect-src 'none'; form-action 'none'; base-uri 'none'"}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="loop-{run_id[:8]}.html"'
            return Response(source, media_type="application/octet-stream", headers=headers)
        # Source is read by the frontend and inserted into an iframe with an opaque
        # sandbox origin. Never render generated source as same-origin application HTML.
        return JSONResponse({"html": source}, headers=headers)

    @app.get("/api/profiles", tags=["Profiles"])
    def profiles(user=Depends(current_user)):
        return [profile_detail(db, user["id"], row["id"]) for row in db.all("SELECT id FROM profiles WHERE user_id=? ORDER BY name", (user["id"],))]

    @app.post("/api/profiles", status_code=201, tags=["Profiles"])
    def new_profile(payload: ProfileInput, user=Depends(current_user)):
        return create_profile(db, user["id"], payload.name, payload.criteria)

    @app.get("/api/profiles/{profile_id}", tags=["Profiles"])
    def get_profile(profile_id: str, user=Depends(current_user)):
        return profile_detail(db, user["id"], profile_id)

    @app.post("/api/profiles/{profile_id}/versions", tags=["Profiles"])
    def update_profile(profile_id: str, payload: ProfileEdit, user=Depends(current_user)):
        return append_version(db, user["id"], profile_id, payload.criteria, payload.changelog, "manual", payload.expected_version)

    @app.post("/api/profiles/{profile_id}/rollback", tags=["Profiles"])
    def rollback(profile_id: str, payload: RollbackInput, user=Depends(current_user)):
        profile = profile_detail(db, user["id"], profile_id)
        version = next((v for v in profile["versions"] if v["version"] == payload.version), None)
        if not version:
            raise HTTPException(404, "Profile version not found.")
        return append_version(db, user["id"], profile_id, version["criteria"], f"Restored version {payload.version}.", "rollback", payload.expected_version)

    @app.post("/api/profiles/{profile_id}/feedback", tags=["Profiles"])
    def profile_feedback(profile_id: str, payload: FeedbackInput, user=Depends(current_user)):
        profile = profile_detail(db, user["id"], profile_id)
        if profile["current_version"] != payload.expected_version:
            raise HTTPException(409, "Reload the latest profile before applying feedback.")
        throttle(db, f"feedback:{user['id']}", limit=3)
        try:
            result, _ = call_with_retry(_call_criteria_updater, profile["criteria"], payload.feedback)
        except Exception:
            raise HTTPException(503, "The model could not update these preferences. You can still edit the criteria manually.")
        return append_version(db, user["id"], profile_id, result.updated_criteria, result.changelog, "ai_feedback", payload.expected_version)

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "API route not found.")
            return FileResponse(dist / "index.html")
    return app


app = create_app()
