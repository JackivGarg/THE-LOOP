import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <main className="fatal">
        <h1>The workspace needs a refresh.</h1>
        <p>Your projects and completed iterations are saved on the server.</p>
        <button onClick={() => location.reload()}>Reload workspace</button>
      </main>
    ) : (
      this.props.children
    );
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
