import { useState } from "react";

import "./app.css";
import { ProviderBadge } from "./components/ProviderBadge";
import { EvalAnalytics } from "./evals/EvalAnalytics";
import { Playground } from "./playground/Playground";

type Tab = "playground" | "evals";

export function App() {
  const [tab, setTab] = useState<Tab>("playground");
  return (
    <div className="app">
      <header className="app-header">
        <h1>Code Review Assistant</h1>
        <nav className="tabs">
          <button
            aria-current={tab === "playground"}
            onClick={() => setTab("playground")}
          >
            Playground
          </button>
          <button aria-current={tab === "evals"} onClick={() => setTab("evals")}>
            Eval Analytics
          </button>
        </nav>
        <ProviderBadge />
      </header>
      <main className="app-main">
        {tab === "playground" ? <Playground /> : <EvalAnalytics />}
      </main>
    </div>
  );
}
