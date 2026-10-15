"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, clearPrivateState, uploadDatasets } from "@/lib/api";

type Column = { id: string; name: string; type: string; missing_count: number; missing_rate: number };
type Dataset = { id: string; display_name: string; version: number; profile: {
  row_count: number; column_count: number; duplicate_row_count: number; columns: Column[]; warnings: string[] } };
type Result = { filename: string; status: string; error?: string };
type Preview = { columns: Column[]; rows: Record<string, string | number | null>[];
  returned_rows: number; total_rows: number; truncated: boolean };

export default function Datasets() {
  const router = useRouter();
  const [items, setItems] = useState<Dataset[]>([]);
  const [results, setResults] = useState<Result[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [active, setActive] = useState<Dataset | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const load = useCallback(async () => {
    try { setItems(await api<Dataset[]>("/datasets")); }
    catch { clearPrivateState(); router.replace("/login"); }
  }, [router]);
  useEffect(() => {
    api<Dataset[]>("/datasets").then(setItems).catch(() => {
      clearPrivateState(); router.replace("/login");
    });
  }, [router]);
  async function upload(files: FileList | File[]) {
    const chosen = Array.from(files);
    if (!chosen.length) return;
    if (chosen.length > 10) { setError("Choose at most 10 files per upload."); return; }
    setError(""); setBusy(true);
    setResults(chosen.map(file => ({ filename: file.name, status: "uploading" })));
    try {
      setResults(await uploadDatasets<Result[]>(chosen, () => {
        setResults(chosen.map(file => ({ filename: file.name, status: "processing" })));
      }));
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Upload failed. Try again."); }
    finally { setBusy(false); }
  }
  async function sample(names: string[]) {
    setBusy(true); setError("");
    try {
      const files = await Promise.all(names.map(async name => {
        const response = await fetch(`/sample_data/${name}`);
        if (!response.ok) throw new Error("Sample data is unavailable.");
        return new File([await response.blob()], name, { type: "text/csv" });
      }));
      await upload(files);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Sample upload failed."); setBusy(false); }
  }
  async function inspect(item: Dataset) {
    setActive(item); setPreview(null);
    try { setPreview(await api<Preview>(`/datasets/${item.id}/preview`)); }
    catch { setError("Preview could not be loaded."); }
  }
  async function remove(item: Dataset) {
    if (!window.confirm(`Delete ${item.display_name}? Its stored file and snapshot will be removed.`)) return;
    try {
      await api(`/datasets/${item.id}`, { method: "DELETE" });
      const selected = JSON.parse(sessionStorage.getItem("selected-datasets") ?? "[]") as string[];
      sessionStorage.setItem("selected-datasets", JSON.stringify(selected.filter(id => id !== item.id)));
      if (active?.id === item.id) { setActive(null); setPreview(null); }
      await load();
    } catch { setError("Dataset could not be deleted."); }
  }
  return <main id="main" className="content"><div className="page-heading"><div><p className="eyebrow">DATA LIBRARY</p>
    <h1>Datasets</h1><p>Manage the source files behind your analysis.</p></div>
    <button className="page-primary-action" onClick={() => fileInput.current?.click()} disabled={busy}>Upload dataset</button></div>
    {items.length === 0 ? <section className="empty-dataset panel">
      <div className="empty-icon" aria-hidden="true">↥</div><h2>Bring your data into focus</h2>
      <p>Upload a CSV or Excel workbook to profile its quality, inspect its columns, and start asking questions.</p>
      <div className={`drop-zone ${dragging ? "drop-zone-active" : ""}`} onDragEnter={event => { event.preventDefault(); setDragging(true); }}
        onDragOver={event => event.preventDefault()} onDragLeave={() => setDragging(false)}
        onDrop={event => { event.preventDefault(); setDragging(false); if (!busy) void upload(event.dataTransfer.files); }}>
        <button className="drop-action" disabled={busy} onClick={() => fileInput.current?.click()}><span aria-hidden="true">＋</span> Choose data files</button>
        <p>CSV, XLS, or XLSX · up to 10 files</p>
      </div>
      <button className="text-button" disabled={busy} onClick={() => void sample(["analysis_flat.csv"])}>Try the analysis sample</button>
    </section> : <section className="dataset-section">
      <div className="section-header"><div><h2>Stored datasets</h2><p>{items.length} source{items.length === 1 ? "" : "s"} available for analysis.</p></div>
        <button className="secondary-action" onClick={() => fileInput.current?.click()} disabled={busy}>＋ Add dataset</button></div>
      <div className="dataset-table"><div className="dataset-table-head"><span>Name</span><span>Rows</span><span>Columns</span><span>Version</span><span aria-hidden="true" /></div>
        {items.map(item => <div className="dataset-row" key={item.id}>
          <div className="dataset-name"><span className="file-icon">{item.display_name.toLowerCase().endsWith(".xlsx") ? "XLSX" : item.display_name.toLowerCase().endsWith(".xls") ? "XLS" : "CSV"}</span><div><strong>{item.display_name}</strong><small>Uploaded source</small></div></div>
          <span>{item.profile.row_count.toLocaleString()}</span><span>{item.profile.column_count}</span><span>v{item.version}</span>
          <div className="row-actions"><button onClick={() => void inspect(item)}>Inspect</button><button className="danger-button" onClick={() => void remove(item)}>Delete</button></div>
        </div>)}
      </div>
      <div className="upload-inline"><span className="upload-inline-icon">↥</span><div><strong>Add another source</strong><small>Up to 10 CSV, XLS, or XLSX files; 64 MiB and 1,100,000 rows per file; 256 MiB total.</small></div><button onClick={() => fileInput.current?.click()} disabled={busy}>Upload</button></div>
    </section>}
    <input ref={fileInput} className="visually-hidden" type="file" multiple disabled={busy}
      aria-label="Choose CSV, XLS, or XLSX files" onChange={event => {
        const chosen = event.currentTarget.files ? Array.from(event.currentTarget.files) : [];
        event.currentTarget.value = "";
        if (chosen.length) void upload(chosen);
      }} />
    {items.length > 0 && <div className="sample-actions"><span>Need a starting point?</span><button className="text-button" disabled={busy} onClick={() => void sample(["sales.csv", "customers.csv", "products.csv"])}>Load sample datasets</button><button className="text-button" disabled={busy} onClick={() => void sample(["analysis_flat.csv"])}>Load analysis sample</button></div>}
    {(error || results.length > 0) && <section className="upload-status" aria-live="polite">{error && <p role="alert" className="error">{error}</p>}
      {results.map((result, index) => <p key={`${result.filename}-${index}`}><strong>{result.filename}</strong> · {result.status}{result.error ? ` — ${result.error}` : ""}</p>)}</section>}
    {active && <section className="panel"><h2>{active.display_name}</h2>
      <p>{active.profile.row_count} rows · {active.profile.duplicate_row_count} duplicate rows</p>
      {active.profile.warnings.map(warning => <p className="warning" key={warning}>{warning}</p>)}
      <div className="table-scroll"><table><thead><tr><th>Column</th><th>Type</th><th>Missing</th><th>Rate</th></tr></thead>
        <tbody>{active.profile.columns.map(column => <tr key={column.id}><td>{column.name}</td><td>{column.type}</td>
          <td>{column.missing_count}</td><td>{(column.missing_rate * 100).toFixed(1)}%</td></tr>)}</tbody></table></div>
      <h3>Preview</h3>{preview ? <><p>{preview.returned_rows} of {preview.total_rows} rows shown{preview.truncated ? " · truncated" : ""}</p>
        <div className="table-scroll"><table><thead><tr>{preview.columns.map(column => <th key={column.id}>{column.name}</th>)}</tr></thead>
          <tbody>{preview.rows.map((row, index) => <tr key={index}>{preview.columns.map(column =>
            <td key={column.id}>{row[column.id] === null ? "—" : String(row[column.id])}</td>)}</tr>)}</tbody></table></div></> : <p>Loading preview…</p>}</section>}
  </main>;
}
