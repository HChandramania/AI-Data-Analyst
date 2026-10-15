"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AnalysisEvidence, AnomalySummary, type Result, type Chart, type Anomalies } from "@/components/analysis-evidence";
import { ExportDialog } from "@/components/export-dialog";

type Evidence = { id: string; answer: string; clarification?: string; error?: string; sql: string;
  table?: Result; charts: Chart[]; chart_error?: string; anomalies?: Anomalies; method: Record<string, unknown>;
  dataset_versions: { display_name: string; version: number }[] };
type Dashboard = { title: string; created_at: string; status: string; complete_cards: number; total_cards: number;
  dataset_versions: { display_name: string; version: number }[];
  cards: { title: string; status: string; error?: string; analysis_id?: string; evidence?: Evidence }[] };

function metric(table?: Result) {
  if (!table || table.truncated || table.rows.length !== 1 || table.columns.length !== 1) return null;
  const column = table.columns[0], value = table.rows[0][column];
  if (value === null || !/^(DECIMAL|DOUBLE|FLOAT|.*INT)/.test(table.types?.[column] ?? "") || !Number.isFinite(Number(value))) return null;
  return { label: column, value: String(value) };
}
export default function SavedDashboard({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [item, setItem] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<Dashboard>(`/dashboards/${id}`).then(setItem).catch(() => setError("Dashboard unavailable. Reload to retry.")); }, [id]);
  return <main id="main" className="content"><Link href="/dashboards">All dashboards</Link>
    {error && <p role="alert">{error}</p>}{!item && !error && <p role="status">Loading saved evidence…</p>}
    {item && <><h1>{item.title}</h1><p>Generated {new Date(item.created_at).toLocaleString()}. Saved evidence; no fresh computation.</p>
      <p className="source-list">Sources at generation: {item.dataset_versions.map(v => `${v.display_name} v${v.version}`).join(", ")}</p>
      <p role="status">{item.complete_cards}/{item.total_cards} cards complete · {item.status}</p>
      <ExportDialog choices={item.cards.map((c, i) => ({ id: c.analysis_id ?? `unavailable-${i}`, title: c.title, status: c.status,
        sources: c.evidence?.dataset_versions.map(v => `${v.display_name} v${v.version}`).join(", ") ?? "Source unavailable" }))} />
      {item.status !== "complete" && <p>Successful evidence is preserved. Review clarifications in Analyze or <Link href="/dashboards">generate a new dashboard</Link> after resolving failures.</p>}
      <div className="dashboard-grid">{item.cards.map((card, i) => {
        const e = card.evidence, value = metric(e?.table);
        return <article className="answer-card" key={i}><h2>{card.title}</h2><p>{card.status}</p>
          <p>{card.error ?? e?.answer ?? e?.clarification ?? e?.error}</p>
          {value && <p className="metric"><strong>{value.value}</strong><span>{value.label}</span></p>}
          {e?.chart_error && <p>{e.chart_error}</p>}
          {e?.table && <AnalysisEvidence table={e.table} charts={e.charts} />}
          {e?.anomalies && <AnomalySummary value={e.anomalies} />}
          {e && <><p className="source-list">{e.dataset_versions.map(v => `${v.display_name} v${v.version}`).join(", ")}</p>
            <details><summary>Method, assumptions and join details</summary><pre>{JSON.stringify(e.method, null, 2)}</pre></details>
            <details><summary>SQL</summary><pre>{e.sql ?? "No query executed."}</pre></details></>}
        </article>;
      })}</div></>}
  </main>;
}
