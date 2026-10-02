import { useEffect, useState } from "react";
import {
  Settings2,
  Plus,
  Loader2,
  Sparkles,
  RotateCcw,
  Check,
} from "lucide-react";
import { post, friendlyLabel, type Profile } from "../api";

export default function ProfilesPage({
  profiles,
  onRefresh,
  liveAvailable,
}: {
  profiles: Profile[];
  onRefresh: () => Promise<void>;
  liveAvailable: boolean;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const profile =
    profiles.find((item) => item.id === selectedId) ?? profiles[0];
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [criteria, setCriteria] = useState("");
  const [feedback, setFeedback] = useState("");
  const [diff, setDiff] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState<number | null>(null);
  useEffect(() => {
    setCriteria(profile?.criteria ?? "");
    setVersion(null);
    setEditing(false);
    setCreating(false);
    setError("");
  }, [profile?.id, profile?.current_version]);
  const history = profile?.versions.find((item) => item.version === version);
  async function save(kind: "create" | "edit" | "feedback" | "rollback") {
    setBusy(true);
    setError("");
    try {
      const updated = await post<Profile>(
        kind === "create"
          ? "/profiles"
          : `/profiles/${profile.id}/${kind === "edit" ? "versions" : kind}`,
        kind === "create"
          ? { name: newName, criteria }
          : kind === "edit"
            ? { criteria, expected_version: profile.current_version }
            : kind === "feedback"
              ? { feedback, expected_version: profile.current_version }
              : { version, expected_version: profile.current_version },
      );
      await onRefresh();
      setSelectedId(updated.id);
      setEditing(false);
      setNewName("");
      setFeedback("");
      setDiff(updated.diff ?? "");
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">MAKE THE LOOP YOUR OWN</span>
          <h1>
            Your taste. Your criteria<span>.</span>
          </h1>
          <p>
            Give the evaluator a point of view. Every change keeps its history.
          </p>
        </div>
        <button
          className="button primary"
          onClick={() => {
            setEditing(true);
            setCreating(true);
            setNewName("");
            setCriteria(
              "- Reward clear hierarchy\n- Prefer accessible, responsive layouts",
            );
            setError("");
          }}
        >
          <Plus size={16} />
          New profile
        </button>
      </section>
      <div className="profiles-layout">
        <div className="profile-menu panel">
          {profiles.map((item) => (
            <button
              className={item.id === profile?.id ? "selected" : ""}
              key={item.id}
              onClick={() => {
                setSelectedId(item.id);
                setDiff("");
              }}
            >
              <Settings2 size={16} />
              <div>
                <strong>{item.name}</strong>
                <small>{item.current_version} saved versions</small>
              </div>
              <span>v{item.current_version}</span>
            </button>
          ))}
        </div>
        <div className="profile-editor panel">
          {profile && (
            <>
              <div className="profile-heading">
                <div>
                  <span className="eyebrow">EVALUATION PROFILE</span>
                  <h2>
                    {creating && editing
                      ? "Create a new profile"
                      : profile.name}
                  </h2>
                </div>
                <span className="pill">v{profile.current_version}</span>
              </div>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              {editing ? (
                <>
                  <label htmlFor="profile-name">Profile name</label>
                  <input
                    id="profile-name"
                    value={creating ? newName : profile.name}
                    onChange={(event) => setNewName(event.target.value)}
                    disabled={!creating}
                  />
                  <label htmlFor="criteria-editor">Editable criteria</label>
                  <textarea
                    className="criteria-input"
                    id="criteria-editor"
                    value={criteria}
                    onChange={(event) => setCriteria(event.target.value)}
                  />
                  <p className="fine-print">
                    One preference per line, beginning with “- ”. System rules
                    stay outside this block.
                  </p>
                  <div className="button-row">
                    <button
                      className="button primary"
                      disabled={busy}
                      onClick={() => save(creating ? "create" : "edit")}
                    >
                      Save criteria
                      <Check size={15} />
                    </button>
                    <button
                      className="button secondary"
                      onClick={() => {
                        setEditing(false);
                        setCreating(false);
                        setNewName("");
                        setCriteria(profile.criteria);
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <pre className="criteria-block">
                    {history?.criteria ?? profile.criteria}
                  </pre>
                  <div className="button-row">
                    <button
                      className="button secondary"
                      onClick={() => {
                        setEditing(true);
                        setCreating(false);
                        setNewName("");
                      }}
                    >
                      Edit criteria
                      <Settings2 size={14} />
                    </button>
                    <small className="muted">
                      Updated{" "}
                      {new Date(profile.updated_at).toLocaleDateString()}
                    </small>
                  </div>
                  <details className="profile-feedback">
                    <summary>Improve preferences with AI</summary>
                    <label htmlFor="feedback">
                      What should future evaluations prefer?
                    </label>
                    <textarea
                      id="feedback"
                      value={feedback}
                      onChange={(event) => setFeedback(event.target.value)}
                      placeholder="Prefer quieter colors and more generous spacing…"
                    />
                    <button
                      className="button primary"
                      disabled={
                        busy || feedback.trim().length < 3 || !liveAvailable
                      }
                      onClick={() => save("feedback")}
                    >
                      {busy ? (
                        <Loader2 size={14} className="spin" />
                      ) : (
                        <Sparkles size={14} />
                      )}
                      Apply feedback
                    </button>
                    {!liveAvailable && (
                      <p className="fine-print">
                        Configure Groq on the server to use AI preference
                        updates. Manual editing is available.
                      </p>
                    )}
                  </details>
                  <details className="profile-history">
                    <summary>
                      Version history · {profile.versions.length} versions
                    </summary>
                    {[...profile.versions].reverse().map((item) => (
                      <button
                        key={item.version}
                        className={version === item.version ? "selected" : ""}
                        onClick={() => setVersion(item.version)}
                      >
                        <span>v{item.version}</span>
                        <div>
                          <strong>{item.changelog}</strong>
                          <small>
                            {new Date(item.created_at).toLocaleString()} ·{" "}
                            {friendlyLabel(item.source)}
                          </small>
                        </div>
                        {item.version === profile.current_version && (
                          <span className="pill">Current</span>
                        )}
                      </button>
                    ))}
                    {version && version !== profile.current_version && (
                      <button
                        className="button secondary"
                        disabled={busy}
                        onClick={() => save("rollback")}
                      >
                        <RotateCcw size={14} />
                        Restore v{version} as a new version
                      </button>
                    )}
                  </details>
                </>
              )}
              {diff && (
                <div className="criteria-diff">
                  <span className="eyebrow">SAVED CRITERIA DIFF</span>
                  <pre>{diff}</pre>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
