"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { ExportChoice } from "./export-dialog";

export function DashboardDialog({ ensureConversation, sources, confirmation = null, multiply = false, choices = [] }: {
  ensureConversation: () => Promise<string>; sources: string; confirmation?: string | null;
  multiply?: boolean; choices?: ExportChoice[];
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const router = useRouter();
  const [title, setTitle] = useState("Data overview");
  const [prompt, setPrompt] = useState("Suggest a useful overview using supported metrics and charts.");
  const [reuse, setReuse] = useState<string[]>([]);
  const [generate, setGenerate] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <><button disabled={!sources} onClick={() => dialog.current?.showModal()}>Generate dashboard</button>
    <dialog className="app-dialog dashboard-dialog" ref={dialog} aria-labelledby="dashboard-dialog-title" onCancel={e => { if (busy) e.preventDefault(); }}>
      <div className="dialog-heading"><div><p className="eyebrow">DASHBOARD BUILDER</p><h2 id="dashboard-dialog-title">Generate and save dashboard</h2></div>
        <button className="dialog-close" type="button" aria-label="Close dashboard dialog" disabled={busy} onClick={() => dialog.current?.close()}>×</button>
      </div>
      <p className="dialog-sources"><strong>Sources</strong> {sources}</p>
      <p className="dialog-help">Up to six cards. Successful cards are saved even if others fail. Generation can take up to 90 seconds.</p>
      <p className="dialog-notice">{confirmation ? "Your explicit join confirmation will be used." : "Relationships will not be guessed. Confirm joins in Analyze for cross-file cards."}</p>
      <div className="dialog-fields">
        <label>Title<input value={title} maxLength={200} onChange={e => setTitle(e.target.value)} /></label>
        <label>Overview request<textarea maxLength={800} value={prompt} onChange={e => setPrompt(e.target.value)} /></label>
      </div>
      {choices.filter(c => c.status === "complete").map(c => <label className="export-choice" key={c.id}>
        <input type="checkbox" checked={reuse.includes(c.id)} disabled={busy || (reuse.length >= 6 && !reuse.includes(c.id))}
          onChange={e => setReuse(old => e.target.checked ? [...old, c.id] : old.filter(id => id !== c.id))} />Reuse: {c.title}</label>)}
      <label className="dialog-check"><input type="checkbox" checked={generate} onChange={e => setGenerate(e.target.checked)} /> <span>Generate additional cards</span></label>
      <p className="dialog-status" role="status">{busy ? "Planning and computing cards…" : error}</p>
      <div className="dialog-actions"><button className="primary-action" disabled={busy || !title.trim() || !prompt.trim() || (!generate && !reuse.length)} onClick={async () => {
        setBusy(true); setError("");
        try {
          const id = await ensureConversation();
          const saved = await api<{ id: string }>("/dashboards", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, prompt, conversation_id: id, analysis_ids: reuse, generate,
              join_confirmation: confirmation, accept_multiplication: multiply }) });
          router.push(`/dashboards/${saved.id}`);
        } catch (cause) { setError(cause instanceof Error ? cause.message : "Generation failed. Try again."); }
        finally { setBusy(false); }
      }}>{busy ? "Generating…" : "Generate and save"}</button><button disabled={busy} onClick={() => dialog.current?.close()}>Cancel</button></div>
    </dialog></>;
}
