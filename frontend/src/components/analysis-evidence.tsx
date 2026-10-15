"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { Data, Layout } from "plotly.js";

export type Chart = { type: "bar" | "line" | "pie" | "scatter"; title: string;
  x_label: string; y_label: string; points: { x: string | number; y: string | number | null }[]; caveats: string[] };
export type Result = { columns: string[]; types?: Record<string, string>; rows: Record<string, unknown>[]; returned_rows: number; truncated: boolean };
export type Anomalies = { rule: string; measure: string; group: string | null; flagged_count: number;
  caveats: string[]; groups: Record<string, unknown>[] };

// Plotly supports HTML-like labels; escape every untrusted string at that boundary.
const plain = (value: unknown) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

function Plot({ chart }: { chart: Chart }) {
  const element = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const target = element.current;
    if (!target) return;
    let disposed = false;
    let cleanup: (() => void) | undefined;
    import("plotly.js-basic-dist-min").then(async ({ default: Plotly }) => {
      if (disposed) return;
      const x = chart.points.map(p => typeof p.x === "number" ? p.x : plain(p.x));
      const y = chart.points.map(p => p.y === null ? null : Number(p.y));
      const colors = ["#A854F7", "#60A5FA", "#2DD4BF", "#FBBF24", "#FB7185", "#C4B5FD"];
      const trace: Data = chart.type === "pie" ? {
        type: "pie", labels: x, values: y as number[], textinfo: "label+percent", marker: { colors },
        hovertemplate: "%{label}: %{value} (%{percent})<extra></extra>",
      } : { type: chart.type === "bar" ? "bar" : "scatter", x, y,
        mode: chart.type === "line" ? "lines+markers" : "markers", connectgaps: false,
        name: plain(chart.y_label), marker: { color: colors[0], size: 8 },
        hovertemplate: "%{x}: %{y}<extra></extra>" };
      const layout: Partial<Layout> = { autosize: true, height: 340,
        paper_bgcolor: "#111116", plot_bgcolor: "#111116", font: { color: "#F5F5F8", family: "Inter, sans-serif" },
        title: { text: plain(chart.title) }, margin: { l: 65, r: 24, t: 70, b: 80 },
        xaxis: { title: { text: plain(chart.x_label) }, automargin: true, gridcolor: "#34343F" },
        yaxis: { title: { text: plain(chart.y_label) }, automargin: true, gridcolor: "#34343F" },
        showlegend: true, legend: { orientation: "h", y: -0.35 } };
      // The observer below owns resizing, including visibility and unmount checks.
      await Plotly.newPlot(target, [trace], layout, { responsive: false, displayModeBar: false, staticPlot: false });
      if (disposed) { Plotly.purge(target); return; }
      setReady(true);
      const displayed = () => !disposed && target.isConnected && target.getClientRects().length > 0
        && target.clientWidth > 0 && target.clientHeight > 0;
      let resizing = false;
      const observer = new ResizeObserver(() => {
        if (!displayed() || resizing) return;
        resizing = true;
        void (async () => {
          try {
            await Plotly.Plots.resize(target);
          } catch {
            // Plotly defers resizing; the user can switch tabs or navigate during that delay.
            if (displayed()) setError("Chart could not resize. The supporting table remains available.");
          } finally {
            resizing = false;
          }
        })();
      });
      observer.observe(target);
      cleanup = () => { observer.disconnect(); Plotly.purge(target); };
    }).catch(() => { if (!disposed) setError("Chart could not render. The supporting table remains available."); });
    return () => { disposed = true; cleanup?.(); };
  }, [chart]);
  return <>{!ready && !error && <p role="status">Loading chart…</p>}{error && <p role="alert">{error}</p>}<div ref={element} className="analysis-plot" role="img"
    aria-label={`${chart.title}. ${chart.x_label} against ${chart.y_label}. Values available in the Table tab.`} /></>;
}

export function ResultTable({ table, caption = "Executed result values" }: { table: Result; caption?: string }) {
  return <div className="table-scroll" role="region" aria-label={caption} tabIndex={0}><table>
    <caption>{caption}</caption><thead><tr>{table.columns.map(c => <th scope="col" key={c}>{c}</th>)}</tr></thead>
    <tbody>{table.rows.map((row, i) => <tr key={i}>{table.columns.map(c => <td key={c}
      className={typeof row[c] === "number" || /^(DECIMAL|DOUBLE|FLOAT|.*INT)/.test(table.types?.[c] ?? "") ? "numeric" : undefined}>
      {row[c] === null ? "null" : String(row[c])}</td>)}</tr>)}</tbody></table>
    {!table.rows.length && <p>No result rows.</p>}</div>;
}

export function AnalysisEvidence({ table, charts = [] }: { table: Result; charts?: Chart[] }) {
  const [tab, setTab] = useState<"chart" | "table">(charts.length ? "chart" : "table");
  const id = useId();
  return <><p>{table.returned_rows} result rows shown{table.truncated ? " · Truncated at 500 rows; omitted values are not shown." : ""}</p>
    {charts.length > 0 && <div role="tablist" aria-label="Result representation">{(["chart", "table"] as const).map(t =>
      <button key={t} role="tab" id={`${id}-${t}`} aria-controls={`${id}-panel`} aria-selected={tab === t}
        tabIndex={tab === t ? 0 : -1} onClick={() => setTab(t)} onKeyDown={e => {
          if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
            e.preventDefault(); const next = e.key === "Home" ? "chart" : e.key === "End" ? "table" : tab === "chart" ? "table" : "chart";
            setTab(next); document.getElementById(`${id}-${next}`)?.focus();
          }
        }}>{t === "chart" ? "Chart" : "Table"}</button>)}</div>}
    <div id={`${id}-panel`} role={charts.length ? "tabpanel" : undefined} aria-labelledby={charts.length ? `${id}-${tab}` : undefined}>
      {tab === "chart" && charts.length ? <Plot chart={charts[0]} /> : <ResultTable table={table} />}
    </div>{charts[0]?.caveats.map(c => <p className="chart-caveat" key={c}>{c}</p>)}</>;
}

export function AnomalySummary({ value }: { value: Anomalies }) {
  return <section aria-label="Anomaly evidence"><h4>Anomaly evidence: {value.measure}</h4>
    <p>{value.rule}</p><p>Grouping: {value.group ?? "Entire dataset"} · {value.flagged_count} flagged records</p>
    <ResultTable table={{ columns: ["group_value", "status", "sample_size", "null_count", "q1", "q3", "lower_bound", "upper_bound", "flagged_count"],
      rows: value.groups, returned_rows: value.groups.length, truncated: false }} caption="IQR baseline, thresholds, and verdict per group" />
    {value.caveats.map(c => <p key={c}>{c}</p>)}</section>;
}
