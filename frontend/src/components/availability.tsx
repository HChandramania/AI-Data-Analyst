"use client";

import { useEffect, useState } from "react";
import { ApiError, getReadiness } from "@/lib/api";

type State = { status: "loading" | "ready" | "error"; message?: string; requestId?: string };

export function Availability() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State>({ status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    let active = true;
    getReadiness(controller.signal).then(() => {
      if (active) setState({ status: "ready" });
    }).catch((error: unknown) => {
      if (active) setState({ status: "error",
        message: error instanceof ApiError ? error.message : "Connection interrupted. Try again.",
        requestId: error instanceof ApiError ? error.requestId : undefined });
    }).finally(() => clearTimeout(timeout));
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [attempt]);

  return <section className="availability" aria-label="Service availability">
    <div role="status" aria-live="polite">
      <span className={`status-dot ${state.status}`} aria-hidden="true" />
      {state.status === "loading" ? "Checking service availability…" :
        state.status === "ready" ? "Backend connected · storage ready" : "Service unavailable"}
    </div>
    {state.status === "error" && <p>{state.message}</p>}
    {state.requestId && <details><summary>Support details</summary><code>{state.requestId}</code></details>}
    <button disabled={state.status === "loading"} onClick={() => {
      setState({ status: "loading" }); setAttempt((value) => value + 1);
    }}>{state.status === "error" ? "Try again" : "Check connection"}</button>
  </section>;
}
