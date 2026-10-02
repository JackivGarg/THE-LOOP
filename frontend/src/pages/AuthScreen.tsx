import { useState, type FormEvent } from "react";
import {
  ArrowRight,
  RotateCcw,
  Check,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import { post, type Config, type User } from "../api";
import { LoopMark } from "../components";

export default function AuthScreen({
  onSignedIn,
  error: bootError,
  config,
}: {
  onSignedIn: (user: User) => void;
  error: string;
  config: Config | null;
}) {
  const [register, setRegister] = useState(true);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onSignedIn(
        await post<User>(register ? "/auth/register" : "/auth/login", {
          ...(register ? { name } : {}),
          email,
          password,
        }),
      );
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-shell">
      <section className="auth-story">
        <a className="brand" href="#">
          <LoopMark />
          <span>
            THE LOOP<small>Build. Evaluate. Evolve.</small>
          </span>
        </a>
        <div className="auth-story-content">
          <span className="eyebrow">IDEAS DESERVE MORE THAN A FIRST DRAFT</span>
          <h1>
            From a little
            <br />
            idea to something
            <br />
            <em>worth sharing.</em>
          </h1>
          <p>
            An AI website builder that learns from its own feedback. Plan,
            generate, evaluate, and keep getting better.
          </p>
          <div className="auth-cycle">
            <span>01 / Plan</span>
            <ArrowRight size={14} />
            <span>02 / Build</span>
            <ArrowRight size={14} />
            <span>03 / Refine</span>
            <RotateCcw size={14} />
          </div>
          <div className="auth-art" aria-hidden="true">
            <div className="art-browser">
              <div>
                <i />
                <i />
                <i />
                <span>your-next-idea.preview</span>
              </div>
              <section>
                <small>THOUGHTFULLY CREATED</small>
                <h2>
                  Make room
                  <br />
                  for better.
                </h2>
                <p>Every iteration is a new possibility.</p>
                <span className="art-flower">✳</span>
              </section>
            </div>
            <div className="art-score">
              <CheckCircleIcon />
              <div>
                Evaluated. Improved.
                <small>A little better, every iteration.</small>
              </div>
            </div>
          </div>
        </div>
        <div className="auth-bottom">
          <span>Built around feedback.</span>
          <span>AI at the core. You in control.</span>
        </div>
      </section>
      <section className="auth-form-panel">
        <div>
          <span className="eyebrow">YOUR PERSONAL WORKSPACE</span>
          <h2>{register ? "Let’s make something good." : "Welcome back."}</h2>
          <p>
            {register
              ? "Create an account to save your ideas, drafts, and preferences."
              : "Your projects are right where you left them."}
          </p>
          <form onSubmit={submit}>
            {register && (
              <>
                <label htmlFor="name">Your name</label>
                <input
                  id="name"
                  autoComplete="name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                  minLength={2}
                  maxLength={60}
                  placeholder="Alex Morgan"
                />
              </>
            )}
            <label htmlFor="email">Email address</label>
            <input
              type="email"
              id="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              placeholder="you@example.com"
            />
            <label htmlFor="password">Password</label>
            <input
              type="password"
              id="password"
              autoComplete={register ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={10}
              maxLength={128}
              placeholder="At least 10 characters"
            />
            {(error || bootError) && (
              <p className="form-error" role="alert">
                {error || bootError}
              </p>
            )}
            <button className="button primary" disabled={busy}>
              {busy ? <Loader2 size={16} className="spin" /> : null}
              {register ? "Create your workspace" : "Sign in"}
              <ArrowRight size={16} />
            </button>
          </form>
          <p className="auth-switch">
            {register ? "Already have a workspace?" : "New around here?"}{" "}
            <button
              onClick={() => {
                setRegister(!register);
                setError("");
              }}
            >
              {register ? "Sign in" : "Create an account"}
            </button>
          </p>
          <div className="auth-note">
            <ShieldCheck size={17} />
            <p>
              Your projects are private to your account.
              {config?.demo_available && (
                <span>
                  Try the offline walkthrough without using an API key.
                </span>
              )}
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

function CheckCircleIcon() {
  return (
    <span className="check-art">
      <Check size={19} />
    </span>
  );
}
