export type User = { id: string; name: string; email: string };
export type Config = {
  live_available: boolean;
  demo_available: boolean;
  models: Record<string, string>;
  quality_threshold: number;
};
export type Scores = Record<
  | "layout"
  | "typography"
  | "responsiveness"
  | "visual_design"
  | "description_match",
  number
>;
export type Check = {
  name: string;
  score: number;
  details: string;
  issues: string[];
};
export type Report = {
  rating: { scores: Scores; deductions: string };
  deterministic: { score: number; checks: Check[]; issues: string[] };
};
export type Iteration = {
  iteration: number;
  reward: number;
  report: Report;
  created_at: string;
};
export type Run = {
  id: string;
  project_id: string;
  mode: "live" | "demo";
  status: string;
  stage: string;
  iteration: number;
  max_iterations: number;
  cancel_requested: number;
  error: string | null;
  created_at: string;
  input: {
    title: string;
    description: string;
    profile_name: string;
    profile_version: number;
  };
  result: {
    reward_history: number[];
    best_reward: number | null;
    best_iteration: number | null;
    quality_passed: boolean;
    stop_reason: string | null;
    rating: Report["rating"];
    deterministic: Report["deterministic"];
    token_usage: number;
    latency_ms: number;
    traces: {
      task: string;
      model: string;
      request_id: string;
      latency_ms: number;
      total_tokens: number;
    }[];
  } | null;
  events?: { id: number; stage: string; message: string; created_at: string }[];
  iterations?: Iteration[];
};
export type Project = {
  id: string;
  title: string;
  description: string;
  updated_at: string;
  run_count?: number;
  latest_run?: Run | null;
  runs?: Run[];
};
export type Profile = {
  id: string;
  name: string;
  criteria: string;
  current_version: number;
  updated_at: string;
  diff?: string;
  versions: {
    version: number;
    criteria: string;
    changelog: string;
    source: string;
    created_at: string;
  }[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : Array.isArray(body.detail)
          ? body.detail.map((item: { msg: string }) => item.msg).join(" · ")
          : "Something went wrong. Please try again.";
    throw new ApiError(detail, response.status);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
export const isActive = (run?: Run | null) =>
  !!run && ["queued", "running"].includes(run.status);
export const scorePercent = (score?: number | null) =>
  score == null ? "—" : `${Math.round(score * 100)}`;
export const friendlyLabel = (value: string) =>
  value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
