import {
  ArrowUpRight,
  Check,
  CheckCircle2,
  CircleDashed,
  Code2,
  Layers3,
  Loader2,
  Monitor,
  Smartphone,
  Sparkles,
} from "lucide-react";
import type { Iteration, Run } from "./api";
import { friendlyLabel, isActive, scorePercent } from "./api";

export function LoopMark({ small = false }: { small?: boolean }) {
  return (
    <span className={`loop-mark ${small ? "small" : ""}`} aria-hidden="true">
      <svg viewBox="0 0 36 36" fill="none">
        <path
          d="M10 10a11 11 0 1 1-3 14M6 14l4-4 5 1"
          stroke="currentColor"
          strokeWidth="3.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

export function EmptyPreview() {
  return (
    <div className="empty-preview">
      <div className="preview-sketch" aria-hidden="true">
        <div className="sketch-nav">
          <b />
          <span />
          <span />
        </div>
        <div className="sketch-body">
          <div>
            <i />
            <h3>
              Your next
              <br />
              great idea.
            </h3>
            <p />
            <p />
            <button tabIndex={-1}>
              Made into something real <ArrowUpRight size={12} />
            </button>
          </div>
          <div className="sketch-art">
            <span>✳</span>
          </div>
        </div>
        <div className="sketch-cards">
          <span />
          <span />
          <span />
        </div>
      </div>
      <div className="preview-empty-note">
        <Sparkles size={16} />
        <p>
          Your brief is the beginning.
          <br />
          <span>Generate a website to see it take shape here.</span>
        </p>
      </div>
    </div>
  );
}

export function ScoreSummary({ run }: { run: Run | null }) {
  const rewards = run?.result?.reward_history ?? [];
  const score =
    run?.status === "completed" ? run.result?.best_reward : rewards.at(-1);
  return (
    <div className="score-summary">
      <div>
        <span className="eyebrow">Overall quality</span>
        <strong>
          {scorePercent(score)}
          <small>/100</small>
        </strong>
      </div>
      <div>
        <span className="eyebrow">Evaluated rounds</span>
        <strong>
          {run?.iteration ?? 0}
          <small>/ {run?.max_iterations ?? 4}</small>
        </strong>
      </div>
      <div>
        <span className="eyebrow">Deterministic checks</span>
        <strong>
          {run?.result?.deterministic?.score.toFixed(1) ?? "—"}
          <small>/10</small>
        </strong>
      </div>
      <span
        className={`quality-badge ${run?.result?.quality_passed ? "passed" : ""}`}
      >
        {run?.result?.quality_passed ? (
          <CheckCircle2 size={14} />
        ) : (
          <CircleDashed size={14} />
        )}
        {run?.result?.quality_passed
          ? "Quality gate passed"
          : isActive(run)
            ? "Improving"
            : run
              ? "Room to improve"
              : "Ready to build"}
      </span>
    </div>
  );
}

export function Progress({ run }: { run: Run }) {
  const stages = [
    "planning",
    run.iteration === 0 ? "writing" : "improving",
    "evaluating",
  ];
  return (
    <div className="run-progress">
      <div className="progress-caption">
        <span className="live-dot" />
        {isActive(run)
          ? `${run.stage === "waiting" ? "Waiting for provider" : friendlyLabel(run.stage)} · Round ${Math.min(run.iteration + 1, run.max_iterations)}`
          : friendlyLabel(run.status)}
        <span>{run.mode === "demo" ? "Offline walkthrough" : "Live AI"}</span>
      </div>
      <div className="stage-track">
        {stages.map((stage, index) => (
          <span key={stage} className={stage === run.stage ? "current" : ""}>
            <span>
              {stage === run.stage && isActive(run) ? (
                <Loader2 size={11} className="spin" />
              ) : (
                index + 1
              )}
            </span>
            {friendlyLabel(stage)}
          </span>
        ))}
      </div>
      {run.stage === "waiting" && (
        <p className="muted">
          {run.events?.at(-1)?.message}. Your run stays in the queue.
        </p>
      )}
    </div>
  );
}

export function Evaluation({
  run,
  selected,
}: {
  run: Run;
  selected: number | null;
}) {
  const iteration = run.iterations?.find((item) => item.iteration === selected);
  const report =
    iteration?.report ??
    (run.result?.rating && run.result?.deterministic
      ? { rating: run.result.rating, deterministic: run.result.deterministic }
      : null);
  if (!report)
    return (
      <div className="empty-panel">
        <CircleDashed size={25} />
        <h3>The first evaluation is on its way.</h3>
        <p>
          Each complete draft is checked against the brief and the design
          rubric.
        </p>
      </div>
    );
  return (
    <div className="evaluation">
      <div className="evaluation-heading">
        <div>
          <span className="eyebrow">Evaluation breakdown</span>
          <h3>Quality you can inspect.</h3>
        </div>
        <span className="pill">
          {selected
            ? `Round ${selected}`
            : `Selected round ${run.result?.best_iteration ?? run.iteration}`}
        </span>
      </div>
      {run.mode === "demo" && (
        <div className="notice">
          Offline walkthrough: the design rubric below is simulated. Structural
          checks run against the actual sample HTML.
        </div>
      )}
      <div className="weight-grid">
        <div>
          <span>40% · Deterministic</span>
          <strong>
            {report.deterministic.score.toFixed(1)}
            <small>/10</small>
          </strong>
        </div>
        <div>
          <span>40% · Design rubric</span>
          <strong>
            {(
              report.rating.scores.layout * 0.25 +
              report.rating.scores.typography * 0.25 +
              report.rating.scores.responsiveness * 0.2 +
              report.rating.scores.visual_design * 0.3
            ).toFixed(1)}
            <small>/10</small>
          </strong>
        </div>
        <div>
          <span>20% · Brief match</span>
          <strong>
            {report.rating.scores.description_match}
            <small>/10</small>
          </strong>
        </div>
      </div>
      <div className="rubric-list">
        {Object.entries(report.rating.scores).map(([name, score]) => (
          <div key={name}>
            <span>{friendlyLabel(name)}</span>
            <div className="score-track">
              <i style={{ width: `${score * 10}%` }} />
            </div>
            <strong>{score}/10</strong>
          </div>
        ))}
      </div>
      <details open>
        <summary>Reviewer feedback</summary>
        <p className="review-feedback">{report.rating.deductions}</p>
      </details>
      <details>
        <summary>
          {report.deterministic.checks.length} deterministic checks ·{" "}
          {report.deterministic.issues.length} issues
        </summary>
        <div className="checks-list">
          {report.deterministic.checks.map((check) => (
            <div key={check.name}>
              <span className={check.score === 1 ? "check-pass" : "check-fail"}>
                {check.score === 1 ? <Check size={14} /> : "!"}
              </span>
              <div>
                <strong>{friendlyLabel(check.name)}</strong>
                <p>{check.details}</p>
                {check.issues.map((issue) => (
                  <small key={issue}>{issue}</small>
                ))}
              </div>
            </div>
          ))}
        </div>
        <p className="fine-print">
          Static analysis only. External network resources and actual browser
          rendering are not verified by these checks.
        </p>
      </details>
      <RewardChart iterations={run.iterations ?? []} />
      <details>
        <summary>Model requests & timing</summary>
        <div className="trace-list">
          {run.result?.traces?.length ? (
            run.result.traces.map((trace, index) => (
              <div key={index}>
                <strong>{friendlyLabel(trace.task)}</strong>
                <span>{trace.model}</span>
                <small>
                  {trace.total_tokens ?? 0} tokens ·{" "}
                  {(trace.latency_ms / 1000).toFixed(1)}s
                </small>
              </div>
            ))
          ) : (
            <p className="muted">
              No model requests in an offline walkthrough.
            </p>
          )}
        </div>
      </details>
    </div>
  );
}

function RewardChart({ iterations }: { iterations: Iteration[] }) {
  if (!iterations.length) return null;
  const width = 540,
    height = 110;
  const points = iterations.map((item, index) => ({
    x: 24 + (index * (width - 48)) / Math.max(1, iterations.length - 1),
    y: 85 - item.reward * 70,
    value: item.reward,
  }));
  return (
    <div className="reward-chart">
      <span className="eyebrow">Quality across iterations</span>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Iteration scores: ${iterations.map((item) => scorePercent(item.reward)).join(", ")}`}
      >
        <line
          x1="24"
          x2="516"
          y1="22"
          y2="22"
          stroke="#ddd"
          strokeDasharray="4 4"
        />
        <polyline
          points={points.map((point) => `${point.x},${point.y}`).join(" ")}
          fill="none"
          stroke="#5d775e"
          strokeWidth="2.5"
        />
        {points.map((point, index) => (
          <g key={index}>
            <circle cx={point.x} cy={point.y} r="4" fill="#5d775e" />
            <text x={point.x} y={point.y - 9} textAnchor="middle">
              {scorePercent(point.value)}
            </text>
            <text x={point.x} y="104" textAnchor="middle">
              Round {index + 1}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

export const viewIcons = { preview: Monitor, code: Code2, evaluation: Layers3 };
export const viewportIcons = { desktop: Monitor, mobile: Smartphone };
