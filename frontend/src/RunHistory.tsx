import { useEffect, useState } from "react";
import { History, ArrowUpRight } from "lucide-react";
import {
  api,
  friendlyLabel,
  scorePercent,
  type Run,
  type Project,
} from "./api";

export default function RunHistory({
  projectId,
  currentRun,
  onSelect,
}: {
  projectId: string;
  currentRun: string | null;
  onSelect: (id: string) => void;
}) {
  const [runs, setRuns] = useState<Run[]>([]);
  useEffect(() => {
    let closed = false;
    api<Project>(`/projects/${projectId}`)
      .then((project) => {
        if (!closed) setRuns(project.runs ?? []);
      })
      .catch(() => {
        if (!closed) setRuns([]);
      });
    return () => {
      closed = true;
    };
  }, [projectId, currentRun]);
  if (!runs.length) return null;
  return (
    <details className="run-history panel">
      <summary>
        <History size={14} />
        Previous runs<span>{runs.length} saved</span>
      </summary>
      {runs.map((run) => (
        <button
          key={run.id}
          className={run.id === currentRun ? "selected" : ""}
          onClick={() => onSelect(run.id)}
        >
          <div>
            <strong>
              {run.mode === "demo" ? "Offline walkthrough" : "Live generation"}
            </strong>
            <small>
              {new Date(run.created_at).toLocaleString()} ·{" "}
              {run.input.profile_name} v{run.input.profile_version}
            </small>
          </div>
          <span>{friendlyLabel(run.status)}</span>
          <b>{scorePercent(run.result?.best_reward)}</b>
          <ArrowUpRight size={14} />
        </button>
      ))}
    </details>
  );
}
