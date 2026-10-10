"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
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
    if (chosen.length > 3) { setError("Choose at most three files per upload."); return; }
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
  async function sample() {
    setBusy(true); setError("");
    try {
      const files = await Promise.all(["sales.csv", "customers.csv", "products.csv"].map(async name => {
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
    if (!window.confirm(`Delete ${item.display_name}? Its stored CSV and snapshot will be removed.`)) return;
    try {
      await api(`/datasets/${item.id}`, { method: "DELETE" });
      const selected = JSON.parse(sessionStorage.getItem("selected-datasets") ?? "[]") as string[];
      sessionStorage.setItem("selected-datasets", JSON.stringify(selected.filter(id => id !== item.id)));
      if (active?.id === item.id) { setActive(null); setPreview(null); }
      await load();
    } catch { setError("Dataset could not be deleted."); }
  }
  return <main id="main" className="content"><div className="page-heading"><div><p className="eyebrow">YOUR DATA</p>
    <h1>Datasets</h1><p>Upload CSV files and inspect their quality before analysis.</p></div>
    <Link href="/analyze">Choose for analysis</Link></div>
    <section className="panel"><h2>Upload CSVs</h2><p>UTF-8 CSV · up to 10 MiB, 100,000 rows, 50 columns per file · three files per batch.</p>
      <div className="drop-zone" onDragOver={event => event.preventDefault()}
        onDrop={event => { event.preventDefault(); if (!busy) void upload(event.dataTransfer.files); }}>
        <label>Choose files<input type="file" accept=".csv,text/csv" multiple disabled={busy}
          onChange={event => { if (event.target.files) void upload(event.target.files); event.target.value = ""; }} /></label>
        <p>Or drop CSV files here</p></div>
      <button disabled={busy} onClick={() => void sample()}>Use sample data</button>
      {error && <p role="alert" className="error">{error}</p>}
      <ul aria-live="polite">{results.map((result, index) => <li key={`${result.filename}-${index}`}>
        {result.filename}: {result.status}{result.error ? ` — ${result.error}` : ""}</li>)}</ul></section>
    <section className="panel"><h2>Stored datasets</h2>{items.length === 0 ? <p>No datasets uploaded yet.</p> :
      <ul className="dataset-list">{items.map(item => <li key={item.id}>
        <div><strong>{item.display_name}</strong><p>v{item.version} · {item.profile.row_count} rows · {item.profile.column_count} columns</p></div>
        <div><button onClick={() => void inspect(item)}>Inspect</button> <button onClick={() => void remove(item)}>Delete</button></div>
      </li>)}</ul>}</section>
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
