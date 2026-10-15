"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DashboardDialog } from "@/components/dashboard-dialog";

type Summary = { id: string; title: string; created_at: string; status: string; complete_cards: number; total_cards: number };
type Dataset = { id: string; display_name: string };
export default function Dashboards() {
  const [items, setItems] = useState<Summary[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { Promise.all([api<Summary[]>("/dashboards"), api<Dataset[]>("/datasets")])
    .then(([saved, sources]) => { setItems(saved); setDatasets(sources); })
    .catch(() => setError("Could not load dashboards. Reload to try again."))
    .finally(() => setLoading(false)); }, []);
  return <main id="main" className="content"><h1>Dashboards</h1><p>Saved computed evidence with source versions.</p>
    {loading && <p role="status">Loading dashboards…</p>}{error && <p role="alert">{error}</p>}
    <section className="panel"><h2>Generate an overview</h2>
      {!loading && !datasets.length && <p>No datasets yet. <Link href="/datasets">Upload CSVs</Link> to begin.</p>}
      {datasets.map(d => <label className="export-choice" key={d.id}><input type="checkbox" checked={selected.includes(d.id)}
        disabled={!selected.includes(d.id) && selected.length >= 5} onChange={e => setSelected(old => e.target.checked ? [...old, d.id] : old.filter(id => id !== d.id))} />{d.display_name}</label>)}
      <DashboardDialog key={selected.join(",")} sources={datasets.filter(d => selected.includes(d.id)).map(d => d.display_name).join(", ")}
        ensureConversation={async () => (await api<{ id: string }>("/conversations", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ dataset_ids: selected }) })).id} />
      <p>For explicit joins or reusing completed answers, generate from <Link href="/analyze">Analyze</Link>.</p></section>
    {!loading && !error && !items.length && <p>No saved dashboards yet.</p>}
    <div className="dashboard-grid">{items.map(item => <article className="answer-card" key={item.id}>
      <h2><Link href={`/dashboards/${item.id}`}>{item.title}</Link></h2>
      <p>{item.complete_cards}/{item.total_cards} complete · {item.status}</p><p>Generated {new Date(item.created_at).toLocaleString()}</p>
    </article>)}</div></main>;
}
