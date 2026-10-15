"use client";

import { useState } from "react";

export type Source = { id: string; display_name: string; profile: { row_count: number;
  columns: { id: string; name: string; type: string }[] } };
export type Join = { left: string; right: string; left_key: string; right_key: string; type: "inner" | "left" };
export type JoinProposal = { joins: Join[]; diagnostics: (Record<string, unknown> & { join: Join })[];
  requires_multiplication: boolean; fanout_warning?: string | null };

export function JoinEditor({ sources, busy, review, changed }: {
  sources: Source[]; busy: boolean; review: (joins: Join[]) => void; changed?: () => void;
}) {
  const empty = (): Join => ({ left: sources[0].id, right: sources[1].id, left_key: "", right_key: "", type: "inner" });
  const [joins, setJoins] = useState<Join[]>(() => [empty()]);
  function change(index: number, patch: Partial<Join>) {
    changed?.();
    setJoins(current => current.map((j, i) => i === index ? { ...j, ...patch } : j));
  }
  function problem() {
    if (sources.length > 5) return "New join configurations support at most five datasets.";
    if (joins.length !== sources.length - 1) return `Connect all ${sources.length} datasets with ${sources.length - 1} relationships.`;
    const parents = new Set<string>(), pairs = new Set<string>();
    for (const j of joins) {
      if (j.left === j.right) return "A dataset cannot join to itself.";
      if (!j.left_key || !j.right_key) return "Choose both columns for every relationship.";
      const pair = [j.left, j.right].sort().join(":");
      if (pairs.has(pair)) return "Remove duplicate relationships.";
      pairs.add(pair);
      if (parents.has(j.right)) return "Each right dataset must have one parent; check relationship directions.";
      parents.add(j.right);
      const lt = sources.find(s => s.id === j.left)?.profile.columns.find(c => c.id === j.left_key)?.type;
      const rt = sources.find(s => s.id === j.right)?.profile.columns.find(c => c.id === j.right_key)?.type;
      if (!lt || !rt || (lt !== rt && ![lt, rt].every(t => ["integer", "decimal"].includes(t)))) return "Join columns must have compatible types.";
    }
    const roots = sources.filter(s => !parents.has(s.id));
    if (roots.length !== 1) return "Relationships must form a connected tree without cycles.";
    const seen = new Set([roots[0].id]);
    for (let pass = 0; pass < joins.length; pass++) for (const j of joins) if (seen.has(j.left)) seen.add(j.right);
    if (seen.size !== sources.length) return "Relationships are disconnected or cyclic. Check left/right directions.";
    return "";
  }
  const error = problem();
  return <details className="join-editor"><summary><span className="join-summary-title">Configure cross-file joins</span><span className="join-summary-count">{joins.length} links</span></summary>
    <p className="join-editor-intro">Connect up to five datasets in a tree. Relationships may be entered in any order. The backend orders them from the root without reversing LEFT joins.</p>
    <div className="join-cards">{joins.map((j, index) => {
      const left = sources.find(s => s.id === j.left), right = sources.find(s => s.id === j.right);
      return <fieldset disabled={busy} className="join-card" key={index}>
        <legend>Relationship {index + 1}</legend>
        <div className="join-controls">
          <label>Left dataset<select aria-label={`Relationship ${index + 1} left source`} value={j.left}
            onChange={e => change(index, { left: e.target.value, left_key: "" })}>
            {sources.map(s => <option key={s.id} value={s.id}>{s.display_name}</option>)}</select></label>
          <label>Left column<select aria-label={`Relationship ${index + 1} left key`} value={j.left_key}
            onChange={e => change(index, { left_key: e.target.value })}><option value="">Choose a column</option>
            {left?.profile.columns.map(c => <option key={c.id} value={c.id}>{c.name} · {c.type}</option>)}</select></label>
          <label>Right dataset<select aria-label={`Relationship ${index + 1} right source`} value={j.right}
            onChange={e => change(index, { right: e.target.value, right_key: "" })}>
            {sources.map(s => <option key={s.id} value={s.id}>{s.display_name}</option>)}</select></label>
          <label>Right column<select aria-label={`Relationship ${index + 1} right key`} value={j.right_key}
            onChange={e => change(index, { right_key: e.target.value })}><option value="">Choose a column</option>
            {right?.profile.columns.map(c => <option key={c.id} value={c.id}>{c.name} · {c.type}</option>)}</select></label>
          <label>Join type<select aria-label={`Relationship ${index + 1} join type`} value={j.type}
            onChange={e => change(index, { type: e.target.value as Join["type"] })}><option value="inner">Inner</option><option value="left">Left</option></select></label>
        </div>
        <p className="join-card-hint">{left?.display_name}.{left?.profile.columns.find(c => c.id === j.left_key)?.name ?? "?"} → {right?.display_name}.{right?.profile.columns.find(c => c.id === j.right_key)?.name ?? "?"} ({j.type.toUpperCase()})</p>
        <button type="button" onClick={() => { changed?.(); setJoins(old => old.filter((_, i) => i !== index)); }}>Remove relationship {index + 1}</button>
      </fieldset>;
    })}</div>
    <button type="button" disabled={busy || joins.length >= Math.min(4, sources.length - 1)}
      onClick={() => { changed?.(); setJoins(old => [...old, empty()]); }}>Add relationship</button>
    {error && <p className="warning" role="status">{error}</p>}
    <div className="join-editor-footer"><p>Inner joins omit unmatched rows. Left joins retain the left source. Multiple expanding branches can inflate aggregates; review diagnostics before confirming.</p>
      <button type="button" disabled={busy || Boolean(error)} onClick={() => review(joins)}>Review join diagnostics</button>
    </div>
  </details>;
}

export function JoinReview({ proposal, sources, autoScroll = false, targetId }: { proposal: JoinProposal; sources: Source[]; autoScroll?: boolean; targetId?: string }) {
  const label = (id: string, key: string) => {
    const s = sources.find(s => s.id === id);
    return `${s?.display_name ?? "Unavailable source"} / ${s?.profile.columns.find(c => c.id === key)?.name ?? key}`;
  };
  const metricLabel = (key: string) => key.replaceAll("_", " ").replace(/\b\w/g, character => character.toUpperCase());
  const metricValue = (value: unknown) => typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);
  return <section id={targetId} className="join-review" aria-label="Join diagnostics" tabIndex={autoScroll ? -1 : undefined}>
    <div className="join-review-heading"><div><p className="eyebrow">JOIN REVIEW</p><h3>Check your relationships</h3></div>
      <span>{proposal.diagnostics.length} {proposal.diagnostics.length === 1 ? "join" : "joins"} checked</span></div>
    <div className="join-review-cards">{proposal.diagnostics.map((d, i) => <article className="join-diagnostic" key={i}>
      <div className="join-diagnostic-title"><strong>{label(d.join.left, d.join.left_key)}</strong><span aria-hidden="true">→</span>
        <strong>{label(d.join.right, d.join.right_key)}</strong><em>{d.join.type}</em></div>
      <dl>{Object.entries(d).filter(([k]) => k !== "join").map(([k, v]) => <div key={k} className={k.includes("unmatched") && Number(v) > 0 ? "join-metric-warning" : undefined}>
        <dt>{metricLabel(k)}</dt><dd>{metricValue(v)}</dd></div>)}</dl>
      <p className="join-review-note">Duplicate counts exclude null keys. Null keys do not match. Counts describe this pair before earlier joins.</p>
    </article>)}</div>
    {proposal.fanout_warning && <p className="join-review-warning" role="alert"><strong>Fanout risk.</strong> {proposal.fanout_warning}</p>}
    {proposal.requires_multiplication && <p className="join-review-warning"><strong>Review row multiplication.</strong> This join can repeat source records and distort sums or averages.</p>}
  </section>;
}
