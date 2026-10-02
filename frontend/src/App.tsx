import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  Clock3,
  FolderOpen,
  History,
  LayoutDashboard,
  Loader2,
  LogOut,
  Plus,
  RotateCcw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import {
  api,
  ApiError,
  friendlyLabel,
  isActive,
  post,
  scorePercent,
  type Config,
  type Profile,
  type Project,
  type Run,
  type User,
} from "./api";
import {
  EmptyPreview,
  Evaluation,
  LoopMark,
  Progress,
  ScoreSummary,
  viewIcons,
  viewportIcons,
} from "./components";
import AuthScreen from "./pages/AuthScreen";
import ProfilesPage from "./pages/ProfilesPage";
import RunHistory from "./RunHistory";

type Page = "workspace" | "projects" | "profiles";
type View = "preview" | "code" | "evaluation";
const DEFAULT_BRIEF =
  "A warm, editorial website for an independent design studio. Include a confident hero, an about section, a curated projects grid, and a clear contact call to action. Use natural tones, generous whitespace, and thoughtful typography.";
const exampleBriefs = [
  { title: "Forma Studio", description: DEFAULT_BRIEF, label: "Design studio" },
  {
    title: "Alex · Developer",
    description:
      "A minimalist personal portfolio for a full-stack developer. Include about, technical skills, three project case studies, experience, and contact. Use a dark neutral palette with one accent and accessible responsive layouts.",
    label: "Developer portfolio",
  },
  {
    title: "Gather Coffee",
    description:
      "A welcoming website for a neighbourhood coffee shop. Include an inviting hero, our story, a seasonal menu, and a contact section with opening hours. Use warm cream, deep brown, and a friendly editorial style.",
    label: "Coffee shop",
  },
];

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [config, setConfig] = useState<Config | null>(null);
  const [booting, setBooting] = useState(true);
  const [page, setPage] = useState<Page>("workspace");
  const [projects, setProjects] = useState<Project[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [profileId, setProfileId] = useState("");
  const [mode, setMode] = useState<"live" | "demo">("live");
  const [rounds, setRounds] = useState(4);
  const [view, setView] = useState<View>("preview");
  const [viewport, setViewport] = useState<"desktop" | "mobile">("desktop");
  const [selectedIteration, setSelectedIteration] = useState<number | null>(
    null,
  );
  const [html, setHtml] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const runIdRef = useRef<string | null>(null);
  runIdRef.current = run?.id ?? null;

  useEffect(() => {
    Promise.all([
      api<Config>("/config"),
      api<User>("/auth/me").catch((error) => {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }),
    ])
      .then(([cfg, person]) => {
        setConfig(cfg);
        setUser(person);
        setMode(cfg.live_available ? "live" : "demo");
      })
      .catch((error) => setError(error.message))
      .finally(() => setBooting(false));
  }, []);

  const refresh = useCallback(async () => {
    const [savedProjects, savedProfiles] = await Promise.all([
      api<Project[]>("/projects"),
      api<Profile[]>("/profiles"),
    ]);
    setProjects(savedProjects);
    setProfiles(savedProfiles);
    setProfileId((current) =>
      savedProfiles.some((profile) => profile.id === current)
        ? current
        : (savedProfiles[0]?.id ?? ""),
    );
  }, []);

  useEffect(() => {
    if (user) refresh().catch((error) => setError(error.message));
  }, [user, refresh]);

  useEffect(() => {
    if (!run || !isActive(run)) return;
    let closed = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const updated = await api<Run>(`/runs/${run.id}`, {
          signal: controller.signal,
        });
        if (closed || runIdRef.current !== run.id) return;
        setRun(updated);
        if (isActive(updated)) timer = setTimeout(poll, 1500);
        else refresh().catch(() => {});
      } catch (error) {
        if (closed) return;
        setError(
          error instanceof Error ? error.message : "Connection interrupted.",
        );
        timer = setTimeout(poll, 4000);
      }
    };
    timer = setTimeout(poll, 500);
    return () => {
      closed = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [run?.id, run?.status, refresh]);

  useEffect(() => {
    if (!run) {
      setHtml("");
      return;
    }
    const controller = new AbortController();
    const query = selectedIteration ? `?iteration=${selectedIteration}` : "";
    api<{ html: string }>(`/runs/${run.id}/artifact${query}`, {
      signal: controller.signal,
    })
      .then((data) => setHtml(data.html))
      .catch((error) => {
        if (error instanceof ApiError && error.status === 404) setHtml("");
      });
    return () => controller.abort();
  }, [run?.id, run?.iteration, run?.stage, run?.status, selectedIteration]);

  async function openProject(id: string) {
    setError("");
    setBusy(true);
    try {
      const saved = await api<Project>(`/projects/${id}`);
      const latest = saved.runs?.[0];
      const detail = latest ? await api<Run>(`/runs/${latest.id}`) : null;
      setProject(saved);
      setTitle(saved.title);
      setDescription(saved.description);
      setRun(detail);
      setSelectedIteration(null);
      setPage("workspace");
      setView("preview");
      if (detail) {
        setMode(detail.mode);
        setProfileId(
          detail.input
            ? (profiles.find((item) => item.name === detail.input.profile_name)
                ?.id ?? profiles[0]?.id)
            : profiles[0]?.id,
        );
      }
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function newProject() {
    setProject(null);
    setRun(null);
    setHtml("");
    setTitle("");
    setDescription("");
    setSelectedIteration(null);
    setPage("workspace");
    setView("preview");
    setError("");
    setNotice("");
  }

  async function generate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = project
        ? await api<Project>(`/projects/${project.id}`, {
            method: "PATCH",
            body: JSON.stringify({ title, description }),
          })
        : await post<Project>("/projects", { title, description });
      setProject(saved);
      const started = await post<Run>(`/projects/${saved.id}/runs`, {
        profile_id: profileId,
        mode,
        max_iterations: rounds,
      });
      setRun(started);
      setSelectedIteration(null);
      setView("preview");
      setHtml("");
      await refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function stopRun() {
    if (!run) return;
    try {
      const stopped = await post<Run>(`/runs/${run.id}/cancel`);
      setRun({ ...run, ...stopped });
      setNotice(
        "Stop requested. The current provider request may finish first.",
      );
    } catch (error) {
      setError((error as Error).message);
    }
  }

  async function download() {
    if (!run) return;
    try {
      const query = selectedIteration ? `&iteration=${selectedIteration}` : "";
      const response = await fetch(
        `/api/runs/${run.id}/artifact?download=true${query}`,
        { credentials: "same-origin" },
      );
      if (!response.ok)
        throw new Error("Download is unavailable for this draft.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `${run.input.title.replace(/[^a-z0-9-]/gi, "-").toLowerCase()}.html`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setError((error as Error).message);
    }
  }

  if (booting)
    return (
      <div className="boot">
        <LoopMark />
        <p>Opening your workspace…</p>
      </div>
    );
  if (!user)
    return <AuthScreen error={error} onSignedIn={setUser} config={config} />;

  const totalRuns = projects.reduce(
    (sum, item) => sum + (item.run_count ?? 0),
    0,
  );
  const active = isActive(run);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#workspace"
          onClick={(event) => {
            event.preventDefault();
            setPage("workspace");
          }}
        >
          <LoopMark />
          <span>
            THE LOOP<small>Build. Evaluate. Evolve.</small>
          </span>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav aria-label="Workspace navigation">
          {(
            [
              { id: "workspace", icon: LayoutDashboard, label: "Builder" },
              { id: "projects", icon: FolderOpen, label: "My projects" },
              { id: "profiles", icon: Settings2, label: "Evaluation profiles" },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              className={page === item.id ? "active" : ""}
              onClick={() => {
                setPage(item.id);
                setError("");
              }}
            >
              <item.icon size={17} />
              {item.label}
              {item.id === "projects" && (
                <span className="nav-count">{projects.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-loop">
          <span className="eyebrow">A little better, each time.</span>
          <div>
            <span>01</span> Plan <ArrowRight size={12} />
          </div>
          <div>
            <span>02</span> Generate <ArrowRight size={12} />
          </div>
          <div>
            <span>03</span> Evaluate <RotateCcw size={12} />
          </div>
          <p>
            Your AI workflow,
            <br />
            with a feedback loop built in.
          </p>
        </div>
        <div className="sidebar-bottom">
          <div className="provider-status">
            <span
              className={`live-dot ${config?.live_available ? "" : "offline"}`}
            />
            <span>
              {config?.live_available
                ? "Groq connected"
                : "Offline walkthrough available"}
            </span>
          </div>
          <div className="account">
            <span className="avatar">{user.name[0].toUpperCase()}</span>
            <div>
              <strong>{user.name}</strong>
              <small>Personal workspace</small>
            </div>
            <button
              title="Sign out"
              aria-label="Sign out"
              onClick={async () => {
                try {
                  await post("/auth/logout");
                  setUser(null);
                  newProject();
                } catch (error) {
                  setError((error as Error).message);
                }
              }}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <div>
            <span>Workspace</span>
            <span>/</span>
            <strong>
              {page === "workspace"
                ? "Website builder"
                : page === "projects"
                  ? "My projects"
                  : "Evaluation profiles"}
            </strong>
          </div>
          <span className="topbar-note">
            <ShieldCheck size={14} />
            Your work is saved privately
          </span>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {notice && (
          <div className="notice" role="status">
            {notice}
          </div>
        )}
        {page === "workspace" && (
          <>
            <section className="page-heading">
              <div>
                <span className="eyebrow">THE WEBSITE WORKSHOP</span>
                <h1>
                  A better website,
                  <br className="mobile-break" /> every iteration<span>.</span>
                </h1>
                <p>
                  Start with an idea. Let AI build, critique, and refine it.
                </p>
              </div>
              <button className="button secondary" onClick={newProject}>
                <Plus size={15} /> New project
              </button>
            </section>
            <div className="workspace-grid">
              <section className="brief-panel panel">
                <div className="panel-heading">
                  <span className="step-number">01</span>
                  <div>
                    <h2>The starting point</h2>
                    <p>Give your idea a little direction.</p>
                  </div>
                  <Sparkles size={18} className="accent-icon" />
                </div>
                <form onSubmit={generate}>
                  <label htmlFor="project-title">Project name</label>
                  <input
                    id="project-title"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="e.g. Forma Studio"
                    required
                    minLength={2}
                    maxLength={100}
                    disabled={active}
                  />
                  <label htmlFor="project-brief">What are we building?</label>
                  <textarea
                    id="project-brief"
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="Describe the audience, content, sections, and visual direction you have in mind…"
                    required
                    minLength={20}
                    maxLength={3000}
                    disabled={active}
                  />
                  <div className="input-footnote">
                    <span>The more specific, the better.</span>
                    <span>{description.length}/3000</span>
                  </div>
                  {!project && (
                    <div className="examples">
                      <span>Need a starting point?</span>
                      <div>
                        {exampleBriefs.map((example) => (
                          <button
                            key={example.label}
                            type="button"
                            onClick={() => {
                              setTitle(example.title);
                              setDescription(example.description);
                            }}
                            disabled={active}
                          >
                            {example.label}
                            <ArrowUpRight size={11} />
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="form-divider" />
                  <label htmlFor="profile-select">
                    Evaluation profile{" "}
                    <span className="label-note">
                      Your taste, made measurable
                    </span>
                  </label>
                  <div className="select-wrap">
                    <select
                      id="profile-select"
                      value={profileId}
                      onChange={(event) => setProfileId(event.target.value)}
                      disabled={active}
                      required
                    >
                      {profiles.map((profile) => (
                        <option key={profile.id} value={profile.id}>
                          {profile.name} · v{profile.current_version}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={14} />
                  </div>
                  <div
                    className="generation-mode"
                    role="group"
                    aria-label="Generation mode"
                  >
                    <button
                      type="button"
                      disabled={!config?.live_available || active}
                      className={mode === "live" ? "selected" : ""}
                      onClick={() => setMode("live")}
                    >
                      <Sparkles size={14} />
                      Live AI
                    </button>
                    <button
                      type="button"
                      disabled={!config?.demo_available || active}
                      className={mode === "demo" ? "selected" : ""}
                      onClick={() => setMode("demo")}
                    >
                      <LayersIcon />
                      Walkthrough
                    </button>
                  </div>
                  <p className="mode-note">
                    {mode === "live"
                      ? "Uses Groq to generate and evaluate your website."
                      : "Offline sample workflow. Rubric scores are simulated; no API credits used."}
                  </p>
                  <details className="advanced">
                    <summary>Run settings</summary>
                    <label htmlFor="rounds">Maximum improvement rounds</label>
                    <select
                      id="rounds"
                      value={rounds}
                      onChange={(event) =>
                        setRounds(Number(event.target.value))
                      }
                      disabled={active}
                    >
                      {[3, 4, 5, 6].map((value) => (
                        <option key={value} value={value}>
                          {value} rounds
                        </option>
                      ))}
                    </select>
                    <p>
                      At least 3 rounds. Stops at the quality gate, a plateau,
                      or this limit.
                    </p>
                  </details>
                  <button
                    type="submit"
                    className="button primary generate-button"
                    disabled={
                      busy ||
                      active ||
                      !profileId ||
                      !config ||
                      (mode === "live" && !config.live_available) ||
                      (mode === "demo" && !config.demo_available)
                    }
                  >
                    {busy ? (
                      <Loader2 size={17} className="spin" />
                    ) : active ? (
                      <Loader2 size={17} className="spin" />
                    ) : (
                      <Sparkles size={17} />
                    )}
                    {active
                      ? "The loop is running…"
                      : project
                        ? "Run another iteration cycle"
                        : mode === "demo"
                          ? "Try the walkthrough"
                          : "Bring it to life"}
                    {!active && <ArrowRight size={16} />}
                  </button>
                  <p className="build-note">
                    <ShieldCheck size={12} />
                    Your brief and every draft are saved automatically.
                  </p>
                </form>
                {run && <Progress run={run} />}
                {active && (
                  <button
                    className="text-button stop-button"
                    onClick={stopRun}
                    disabled={!!run?.cancel_requested}
                  >
                    <Square size={11} />
                    {run?.cancel_requested
                      ? "Stopping after current request…"
                      : "Stop run"}
                  </button>
                )}
                {run?.error && <p className="run-error">{run.error}</p>}
              </section>
              <section className="canvas-panel panel">
                <div className="canvas-header">
                  <div
                    className="view-tabs"
                    role="tablist"
                    aria-label="Draft view"
                  >
                    {(Object.keys(viewIcons) as View[]).map((key) => {
                      const Icon = viewIcons[key];
                      return (
                        <button
                          key={key}
                          role="tab"
                          aria-selected={view === key}
                          className={view === key ? "selected" : ""}
                          onClick={() => setView(key)}
                        >
                          <Icon size={14} />
                          {friendlyLabel(key)}
                        </button>
                      );
                    })}
                  </div>
                  <div className="canvas-actions">
                    {(
                      Object.keys(viewportIcons) as ("desktop" | "mobile")[]
                    ).map((key) => {
                      const Icon = viewportIcons[key];
                      return (
                        <button
                          key={key}
                          title={`${key} preview`}
                          aria-label={`${key} preview`}
                          aria-pressed={viewport === key}
                          className={viewport === key ? "selected" : ""}
                          onClick={() => {
                            setViewport(key);
                            setView("preview");
                          }}
                        >
                          <Icon size={15} />
                        </button>
                      );
                    })}
                    <span className="toolbar-divider" />
                    <button
                      title="Download HTML"
                      aria-label="Download HTML"
                      disabled={!html}
                      onClick={download}
                    >
                      <ArrowDownToLine size={16} />
                    </button>
                  </div>
                </div>
                <div className="preview-address">
                  <span className="browser-dots">
                    <i />
                    <i />
                    <i />
                  </span>
                  <span>
                    <ShieldCheck size={11} />{" "}
                    {project
                      ? `${project.title.toLowerCase().replaceAll(" ", "-")}.preview`
                      : "your-next-idea.preview"}
                  </span>
                  {run && (
                    <span className="preview-mode">
                      {run.mode === "demo" ? "OFFLINE SAMPLE" : "LIVE AI"}
                    </span>
                  )}
                </div>
                <div className={`canvas-body ${view}`}>
                  {view === "preview" ? (
                    html ? (
                      <div className={`iframe-container ${viewport}`}>
                        <iframe
                          title="Generated website preview"
                          srcDoc={sandboxSource(html)}
                          sandbox="allow-scripts"
                          referrerPolicy="no-referrer"
                        />
                      </div>
                    ) : (
                      <EmptyPreview />
                    )
                  ) : view === "code" ? (
                    <pre className="code-view">
                      {html || "Your generated HTML will appear here."}
                    </pre>
                  ) : run ? (
                    <Evaluation run={run} selected={selectedIteration} />
                  ) : (
                    <div className="empty-panel">
                      <ShieldCheck size={28} />
                      <h3>Every draft earns its score.</h3>
                      <p>
                        Generate a website to inspect its quality, feedback, and
                        improvement history.
                      </p>
                    </div>
                  )}
                </div>
                {run?.iterations?.length ? (
                  <div className="iteration-strip">
                    <History size={14} />
                    <span>Drafts</span>
                    {run.iterations.map((item) => (
                      <button
                        key={item.iteration}
                        className={
                          selectedIteration === item.iteration ? "selected" : ""
                        }
                        onClick={() => setSelectedIteration(item.iteration)}
                      >
                        v{item.iteration}
                        <small>{scorePercent(item.reward)}</small>
                      </button>
                    ))}
                    <button
                      className={selectedIteration === null ? "selected" : ""}
                      onClick={() => setSelectedIteration(null)}
                    >
                      Selected <Check size={11} />
                    </button>
                  </div>
                ) : (
                  <div className="canvas-footnote">
                    <span className="live-dot offline" />
                    Preview will update as each draft is generated.
                  </div>
                )}
              </section>
            </div>
            <ScoreSummary run={run} />
            {run && (
              <details className="activity-panel panel">
                <summary>
                  <Clock3 size={14} />
                  Run activity <span>{run.events?.length ?? 0} events</span>
                </summary>
                <div className="activity-list">
                  {run.events?.map((event) => (
                    <div key={event.id}>
                      <time>
                        {new Date(event.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </time>
                      <span>{event.message}</span>
                    </div>
                  ))}
                </div>
                {run.status === "completed" && (
                  <p className="fine-print">
                    Stopped because:{" "}
                    {friendlyLabel(
                      run.result?.stop_reason ?? "iteration_limit",
                    )}
                    . The highest-scoring evaluated draft is selected.
                  </p>
                )}
              </details>
            )}
          </>
        )}
        {page === "projects" && (
          <>
            <section className="page-heading">
              <div>
                <span className="eyebrow">YOUR IDEAS, IN PROGRESS</span>
                <h1>
                  A place for your projects<span>.</span>
                </h1>
                <p>
                  {projects.length} projects · {totalRuns} generation runs · All
                  your drafts, preserved.
                </p>
              </div>
              <button className="button primary" onClick={newProject}>
                <Plus size={16} />
                New project
              </button>
            </section>
            {projects.length ? (
              <div className="projects-grid">
                {projects.map((item) => (
                  <button
                    className="project-card panel"
                    key={item.id}
                    onClick={() => openProject(item.id)}
                    disabled={busy}
                  >
                    <div className="project-thumbnail">
                      <LoopMark />
                      <span>{item.title[0]}</span>
                      <span className="project-badge">
                        {item.latest_run?.mode === "demo"
                          ? "Walkthrough"
                          : item.latest_run
                            ? friendlyLabel(item.latest_run.status)
                            : "Brief saved"}
                      </span>
                    </div>
                    <div className="project-card-body">
                      <h2>
                        {item.title}
                        <ArrowUpRight size={18} />
                      </h2>
                      <p>{item.description}</p>
                      <div>
                        <span>{item.run_count ?? 0} runs</span>
                        <span>
                          {item.latest_run?.result?.best_reward != null
                            ? `${scorePercent(item.latest_run.result.best_reward)}/100`
                            : "Not yet evaluated"}
                        </span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="empty-panel panel large">
                <FolderOpen size={35} />
                <h2>Your first project starts with an idea.</h2>
                <p>
                  Write a brief in the builder and your project will be saved
                  here.
                </p>
                <button className="button primary" onClick={newProject}>
                  Open the builder
                  <ArrowRight size={16} />
                </button>
              </div>
            )}
          </>
        )}
        {page === "profiles" && (
          <ProfilesPage
            profiles={profiles}
            onRefresh={refresh}
            liveAvailable={!!config?.live_available}
          />
        )}
        {page === "workspace" && project && (
          <RunHistory
            projectId={project.id}
            currentRun={run?.id ?? null}
            onSelect={async (id) => {
              try {
                setRun(await api<Run>(`/runs/${id}`));
                setSelectedIteration(null);
              } catch (error) {
                setError((error as Error).message);
              }
            }}
          />
        )}
        <footer className="app-footer">
          <span>THE LOOP</span>
          <p>Better websites begin with better feedback.</p>
          <span>Plan → Build → Evaluate → Improve</span>
        </footer>
      </main>
    </div>
  );
}

function LayersIcon() {
  return <History size={14} />;
}

function sandboxSource(source: string) {
  const policy = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' https:; script-src 'unsafe-inline' https:; img-src https: data:; font-src https:; connect-src 'none'; form-action 'none'; base-uri 'none';">`;
  return source.replace(/<head([^>]*)>/i, `<head$1>${policy}`);
}
