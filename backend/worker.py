"""A bounded, single-worker job queue backed by SQLite checkpoints.

Queued jobs survive restarts. In-flight jobs are marked interrupted on startup;
we do not quietly reissue paid provider calls after a process crash.
"""
import json
import logging
import threading

from backend.database import json_dump, utcnow
from backend.demo import DEMO_NODES
from core.pipeline import RunCancelled, run_pipeline
from utils.retry import retry_context

logger = logging.getLogger(__name__)


def summary(state):
    traces = [{k: v for k, v in trace.items() if k != "raw_content"} for trace in state.get("llm_request_trace", [])]
    return {
        "reward_history": state.get("reward_history", []), "best_reward": state.get("best_reward"),
        "best_iteration": state.get("best_iteration"), "quality_passed": state.get("quality_passed", False),
        "stop_reason": state.get("stop_reason"), "rating": state.get("last_rating_json"),
        "deterministic": state.get("last_deterministic_evaluation"), "traces": traces,
        "token_usage": sum(trace.get("total_tokens") or 0 for trace in traces),
        "latency_ms": sum(trace.get("latency_ms") or 0 for trace in traces),
    }


class RunWorker:
    def __init__(self, db):
        self.db = db
        self.stop_event = threading.Event()
        self.wakeup = threading.Event()
        self.thread = None

    def start(self):
        self.db.execute("UPDATE runs SET status='interrupted', error='The server restarted during this run. Saved iterations remain available.', updated_at=? WHERE status='running'", (utcnow(),))
        self.thread = threading.Thread(target=self._loop, name="loop-runner", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.wakeup.set()
        if self.thread:
            self.thread.join(timeout=3)

    def notify(self):
        self.wakeup.set()

    def _loop(self):
        while not self.stop_event.is_set():
            with self.db.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute("SELECT * FROM runs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
                if row:
                    connection.execute("UPDATE runs SET status='running', updated_at=? WHERE id=?", (utcnow(), row["id"]))
            if row:
                self._run(dict(row))
            else:
                self.wakeup.wait(timeout=1)
                self.wakeup.clear()

    def _run(self, run):
        run_id = run["id"]
        state = json.loads(run["state_json"])

        def cancelled():
            return self.stop_event.is_set() or bool(self.db.one("SELECT cancel_requested FROM runs WHERE id=?", (run_id,))["cancel_requested"])

        def emit(stage, candidate, message):
            now = utcnow()
            data = summary(candidate)
            with self.db.connection() as connection:
                current_stage = stage if stage not in {"checkpoint", "iteration"} else None
                connection.execute("UPDATE runs SET stage=COALESCE(?,stage), iteration=?, state_json=?, result_json=?, updated_at=? WHERE id=?", (current_stage, candidate["iteration"], json_dump(candidate), json_dump(data), now, run_id))
                if stage != "checkpoint":
                    connection.execute("INSERT INTO run_events(run_id,stage,message,iteration,created_at) VALUES (?,?,?,?,?)", (run_id, stage, message, candidate["iteration"], now))
                if stage == "iteration":
                    report = {"rating": candidate["last_rating_json"], "deterministic": candidate["last_deterministic_evaluation"]}
                    connection.execute("INSERT INTO iterations VALUES (?,?,?,?,?,?)", (run_id, candidate["iteration"], candidate["current_code"], json_dump(report), candidate["reward_history"][-1], now))
                if stage == "completed":
                    connection.execute("UPDATE runs SET status='completed' WHERE id=?", (run_id,))
                connection.execute("UPDATE projects SET updated_at=? WHERE id=?", (now, run["project_id"]))

        try:
            def retry_observer(attempt, delay):
                emit("waiting", state, f"Provider cooldown: retry {attempt + 1} in {delay:.1f}s")
            with retry_context(retry_observer, cancelled):
                run_pipeline(state, on_event=emit, cancelled=cancelled,
                             nodes=DEMO_NODES if run["mode"] == "demo" else None)
        except RunCancelled:
            self.db.execute("UPDATE runs SET status=?, stage='stopped', error=?, updated_at=? WHERE id=?",
                ("interrupted" if self.stop_event.is_set() else "cancelled", "Run stopped. Completed iterations are saved.", utcnow(), run_id))
        except Exception as error:
            logger.warning("Run %s failed (%s)", run_id, type(error).__name__)
            # No raw provider messages, org identifiers, credentials, or source HTML
            # are returned to the public error surface.
            message = "The provider could not complete this run. Try again after its limits reset or use the offline walkthrough."
            if isinstance(error, ValueError):
                message = "A generation response was incomplete or unchanged. Try a shorter brief or increase the server output budget."
            self.db.execute("UPDATE runs SET status='failed', error=?, updated_at=? WHERE id=?", (message, utcnow(), run_id))
