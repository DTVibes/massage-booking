import React, { Component, type ReactNode } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { initTelegram } from "./lib/telegram";

initTelegram();

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div style={{ padding: 32, textAlign: "center", fontFamily: "system-ui" }}>
        <p>Что-то пошло не так.</p>
        <button onClick={() => window.location.reload()} style={{ marginTop: 12, padding: "10px 18px" }}>Перезагрузить</button>
      </div>
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
