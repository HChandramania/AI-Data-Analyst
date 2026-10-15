"use client";

import { useRef, useState } from "react";
import { downloadReport } from "@/lib/api";

export type ExportChoice = { id: string; title: string; status: string; sources: string };
export function ExportDialog({ choices }: { choices: ExportChoice[] }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [title, setTitle] = useState("Analysis report");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const available = choices.filter(c => c.status === "complete");
  return <><button onClick={() => dialog.current?.showModal()}>Export report</button>
    <dialog className="app-dialog export-dialog" ref={dialog} aria-labelledby="export-title" onCancel={e => { if (busy) e.preventDefault(); }}>
      <div className="dialog-heading">
        <div><p className="eyebrow">EXPORT REPORT</p><h2 id="export-title">Take your insights with you</h2></div>
        <button className="dialog-close" type="button" aria-label="Close export dialog" disabled={busy}
          onClick={() => dialog.current?.close()}>?</button>
      </div>
      <p className="dialog-help">Download a report with your charts, tables and supporting evidence. Opens offline in any browser.</p>
      <div className="export-format"><span>HTML report</span><span>Offline ready ? Up to 8 MiB</span></div>
      <div className="dialog-fields"><label>Report title<input maxLength={200} value={title}
        placeholder="Give your report a name" disabled={busy} onChange={e => setTitle(e.target.value)} /></label></div>
      <div className="export-selection-heading"><h3>Include in your report</h3>
        <button type="button" disabled={busy || !available.length} onClick={() => {
          const all = available.slice(0, 12).map(c => c.id);
          setSelected(all.every(id => selected.includes(id)) ? [] : all);
        }}>{available.length > 0 && available.slice(0, 12).every(c => selected.includes(c.id)) ? "Clear selection" : available.length > 12 ? "Select first 12" : "Select all"}</button>
      </div>
      <div className="export-options" role="group" aria-label="Report contents">
        {!choices.length && <p className="export-empty">No saved analyses yet. Complete an analysis to include it in a report.</p>}
        {choices.map(c => <label className={`export-choice export-option${selected.includes(c.id) ? " is-selected" : ""}${c.status !== "complete" ? " is-unavailable" : ""}`} key={c.id}>
          <input type="checkbox" disabled={busy || c.status !== "complete" || (selected.length >= 12 && !selected.includes(c.id))}
            checked={selected.includes(c.id)} onChange={e => setSelected(old => e.target.checked ? [...old, c.id] : old.filter(id => id !== c.id))} />
          <span className="export-option-copy"><strong>{c.title}</strong><span>{c.sources}</span>
            {c.status !== "complete" && <span className="warning">Unavailable: {c.status}</span>}</span>
        </label>)}
      </div>
      <div className="export-summary"><span>{selected.length} of 12 selected</span><span>Charts, tables &amp; SQL included</span></div>
      <p className="export-feedback" role="status">{message || (!title.trim() ? "Enter a report title to continue." : !selected.length ? "Select at least one analysis to download." : "Your report will use saved evidence.")}</p>
      <div className="dialog-actions">
      <button disabled={busy} onClick={() => dialog.current?.close()}>Cancel</button>
      <button className="primary-action" disabled={busy || !title.trim() || !selected.length} onClick={async () => {
        setBusy(true); setMessage("Generating report…");
        try { await downloadReport(title, selected); setMessage("Download started"); }
        catch (cause) { setMessage(cause instanceof Error ? cause.message : "Export failed. Your selection is preserved."); }
        finally { setBusy(false); }
      }}>{busy ? "Preparing…" : "Download HTML"}</button>
      </div>
    </dialog></>;
}
