"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, clearPrivateState } from "@/lib/api";
import { AnalysisEvidence, AnomalySummary, type Chart, type Anomalies } from "@/components/analysis-evidence";
import { JoinEditor, JoinReview, type Source, type Join, type JoinProposal } from "@/components/join-editor";
import { DashboardDialog } from "@/components/dashboard-dialog";
import { ExportDialog } from "@/components/export-dialog";

type Dataset = Source;
type Version = { id: string; version: number; display_name: string };
type Conversation = { id: string; title: string; selected_dataset_versions: Version[] };
type Message = { id: string; role: string; content: string; status: string };
type Analysis = { id: string; status: string; question: string; answer?: string; clarification?: string;
  charts?: Chart[]; chart_error?: string; anomalies?: Anomalies; join_proposal?: JoinProposal;
  error?: string; sql?: string; dataset_versions: Version[]; method: {
    calculation?: string; filters?: string; grouping?: string; assumptions?: string[]; joins?: JoinProposal["diagnostics"];
    stages?: { name: string; metrics: string[]; filters: string; grouping: string; ordering: string }[] };
  table?: { columns: string[]; rows: Record<string, unknown>[]; returned_rows: number; truncated: boolean } };
type Detail = { conversation: Conversation; messages: Message[]; analyses: Analysis[] };
type SearchResult = { analysis_id: string; conversation_id: string; title: string;
  question: string; summary: string; score: number; href: string };

export default function Analyze() {
  const router = useRouter();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [multiply, setMultiply] = useState(false);
  const [group, setGroup] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [searchText, setSearchText] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchDone, setSearchDone] = useState(false);
  const [joinReviewTarget, setJoinReviewTarget] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([api<Dataset[]>("/datasets"), api<Conversation[]>("/conversations")]).then(([items, saved]) => {
      setDatasets(items); setConversations(saved);
      const ids = JSON.parse(sessionStorage.getItem("selected-datasets") ?? "[]") as string[];
      setSelected(ids.filter(id => items.some(item => item.id === id)).slice(0, 5));
    }).catch((cause) => {
      if (cause instanceof ApiError && cause.status === 401) { clearPrivateState(); router.replace("/login"); }
      else setError("Could not load datasets and conversations. Reload to try again.");
    });
  }, [router]);
  const open = useCallback(async (id: string) => {
    try {
      const detail = await api<Detail>(`/conversations/${id}`);
      setCurrent(id); setMessages(detail.messages); setAnalyses(detail.analyses);
      setConversations(previous => previous.map(item => item.id === id ? detail.conversation : item));
      const ids = detail.conversation.selected_dataset_versions.map(item => item.id);
      setSelected(ids); sessionStorage.setItem("selected-datasets", JSON.stringify(ids));
      setError("");
    } catch { setError("Conversation is unavailable. It may reference a deleted dataset."); }
  }, []);
  useEffect(() => {
    const target = new URLSearchParams(window.location.search).get("conversation");
    if (target) {
      const timer = window.setTimeout(() => void open(target), 0);
      return () => window.clearTimeout(timer);
    }
  }, [open]);
  useEffect(() => {
    if (!joinReviewTarget) return;
    let attempts = 0;
    let timer: number | undefined;
    const scrollWhenReady = () => {
      const target = document.getElementById(`join-review-${joinReviewTarget}`);
      if (target) {
        target.scrollIntoView({ behavior: "auto", block: "start" });
        target.focus({ preventScroll: true });
        setJoinReviewTarget(null);
        return;
      }
      attempts += 1;
      if (attempts < 20) timer = window.setTimeout(scrollWhenReady, 50);
    };
    timer = window.setTimeout(scrollWhenReady, 0);
    return () => { if (timer) window.clearTimeout(timer); };
  }, [analyses, joinReviewTarget]);
  async function findHistory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!searchText.trim() || searchBusy) return;
    setSearchBusy(true); setSearchError(""); setSearchDone(false);
    try {
      const results = await api<SearchResult[]>("/search", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: searchText.trim() }) });
      setSearchResults(results); setSearchDone(true);
    } catch (cause) { setSearchError(cause instanceof Error ? cause.message : "Search unavailable. Try again."); }
    finally { setSearchBusy(false); }
  }
  async function indexHistory() {
    setSearchBusy(true); setSearchError("");
    try {
      const result = await api<{ indexed: number; remaining: number }>("/search/index", { method: "POST" });
      setSearchError(`${result.indexed} analyses indexed. ${result.remaining} may still need indexing.`);
    } catch (cause) { setSearchError(cause instanceof Error ? cause.message : "Could not index history."); }
    finally { setSearchBusy(false); }
  }
  async function rerunAnalysis(id: string) {
    setBusy(true); setError("");
    try {
      await api<Analysis>(`/analyses/${id}/rerun`, { method: "POST" });
      if (current) await open(current);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not rerun analysis."); }
    finally { setBusy(false); }
  }
  async function openSearchResult(item: SearchResult) {
    await open(item.conversation_id);
    window.setTimeout(() => document.getElementById(`analysis-${item.analysis_id}`)?.scrollIntoView({ behavior: "smooth" }), 0);
  }
  async function deleteAnalysis(item: Analysis) {
    if (!window.confirm(`Delete saved analysis "${item.question}"? This cannot be undone. It will be removed from search and become unavailable in dashboards. Conversation text, datasets and downloaded reports remain.`)) return;
    setBusy(true); setError(""); setCopyStatus("");
    try {
      await api(`/analyses/${item.id}`, { method: "DELETE" });
      setAnalyses(previous => previous.filter(analysis => analysis.id !== item.id));
      setSearchResults(previous => previous.filter(result => result.analysis_id !== item.id));
      if (confirmation === item.id) { setConfirmation(null); setMultiply(false); }
      setCopyStatus("Saved analysis deleted.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not delete the analysis. Try again."); }
    finally { setBusy(false); }
  }
  function toggle(id: string) {
    const next = selected.includes(id) ? selected.filter(value => value !== id) : [...selected, id].slice(0, 5);
    setSelected(next); sessionStorage.setItem("selected-datasets", JSON.stringify(next));
    setCurrent(null); setMessages([]); setAnalyses([]); setError("");
    setConfirmation(null); setMultiply(false); setGroup("");
  }
  async function ensureConversation() {
    if (current) return current;
    const created = await api<Conversation>("/conversations", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dataset_ids: selected }) });
    setCurrent(created.id); setConversations(previous => [created, ...previous]);
    return created.id;
  }
  async function review(joins: Join[]) {
    setBusy(true); setError(""); setConfirmation(null); setMultiply(false);
    try {
      const id = await ensureConversation();
      const reviewed = await api<Analysis>(`/conversations/${id}/joins`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ joins }) });
      await open(id);
      setJoinReviewTarget(reviewed.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not inspect join keys."); }
    finally { setBusy(false); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (!text || !selected.length || busy) return;
    setBusy(true); setError("");
    let id = current;
    try {
      id = await ensureConversation();
      const outcome = await api<Analysis>(`/conversations/${id}/messages`, { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: text,
          join_confirmation: confirmation, accept_multiplication: multiply, anomaly_group_confirmation: group || null }) });
      await open(id); if (outcome.status === "complete") setQuestion("");
    } catch (cause) {
      if (id) await open(id);
      setError(cause instanceof Error ? cause.message : "Analysis failed. Try again.");
    } finally { setBusy(false); }
  }
  return <main id="main" className="content"><div className="page-heading"><div>
    <p className="eyebrow">ANALYZE</p><h1>Ask your data</h1>
    <p>Select a dataset and inspect the calculation behind each answer.</p></div>
    <Link href="/datasets">Manage datasets</Link></div>
    <div className="artifact-actions"><DashboardDialog key={`dashboard-${selected.join(",") || "none"}`} ensureConversation={ensureConversation}
      sources={selected.map(id => datasets.find(d => d.id === id)?.display_name ?? id).join(", ")}
      confirmation={confirmation} multiply={multiply} choices={analyses.map(a => ({ id: a.id, title: a.question,
        status: a.status, sources: a.dataset_versions.map(v => `${v.display_name} v${v.version}`).join(", ") }))} />
      <ExportDialog key={`export-${(current ?? selected.join(",")) || "none"}`} choices={analyses.map(a => ({ id: a.id, title: a.question, status: a.status,
        sources: a.dataset_versions.map(v => `${v.display_name} v${v.version}`).join(", ") }))} /></div>
    <section className="panel"><h2>Selected datasets</h2>
      {datasets.length === 0 ? <p>No datasets yet. <Link href="/datasets">Upload CSVs</Link> to begin.</p> :
        <ul className="dataset-list">{datasets.map(item => <li key={item.id}><label>
          <input type="checkbox" checked={selected.includes(item.id)}
            disabled={busy || (!selected.includes(item.id) && selected.length >= 5)}
            onChange={() => toggle(item.id)} /> {item.display_name} · {item.profile.row_count} rows
        </label></li>)}</ul>}
      <p>{selected.length} of 5 selected. Changing selection starts a new conversation; saved evidence keeps its original sources.</p>
      {selected.length > 1 && <JoinEditor key={selected.join(",")} sources={selected.map(id => datasets.find(d => d.id === id)!).filter(Boolean)}
        busy={busy} changed={() => { setConfirmation(null); setMultiply(false); }} review={joins => void review(joins)} />}
      {selected.length === 1 && <label>Confirmed anomaly grouping (optional)<select value={group} disabled={busy}
        onChange={e => setGroup(e.target.value)}><option value="">No grouped anomaly consent</option>
        {datasets.find(d => d.id === selected[0])?.profile.columns.map(c => <option value={c.id} key={c.id}>{c.name}</option>)}
      </select></label>}</section>
    <section className="panel"><h2>Previous conversations</h2>
      {conversations.length === 0 ? <p>No conversations yet.</p> :
        <ul className="conversation-list">{conversations.map(item => <li key={item.id}>
          <button disabled={busy} aria-current={current === item.id ? "page" : undefined} onClick={() => {
            setConfirmation(null); setMultiply(false); setGroup(""); void open(item.id);
          }}>
            {item.title}</button></li>)}</ul>}</section>
    <section className="panel" aria-label="Search analysis history"><h2>Search past analyses</h2>
      <form onSubmit={findHistory} className="question-form"><label htmlFor="history-query">Search by meaning</label>
        <input id="history-query" value={searchText} onChange={event => setSearchText(event.target.value)}
          maxLength={500} placeholder="Regional performance" />
        <button disabled={searchBusy || !searchText.trim()} type="submit">{searchBusy ? "Searching…" : "Search"}</button></form>
      <button type="button" disabled={searchBusy} onClick={() => void indexHistory()}>Index older analyses</button>
      {searchError && <p role="status">{searchError}</p>}
      {searchDone && searchResults.length === 0 && <p>No sufficiently relevant analyses found. Try another phrase, or index older analyses if saved history is missing.</p>}
      {searchResults.length > 0 && <ul className="conversation-list">{searchResults.map(item => <li key={item.analysis_id}>
        <button type="button" onClick={() => void openSearchResult(item)}>
          <strong>{item.title}</strong> · {item.question} · similarity {item.score.toFixed(2)}</button>
        <p>{item.summary}</p></li>)}</ul>}</section>
    <section className="panel" aria-label="Conversation">
      {messages.length === 0 && analyses.length === 0 ? <p>Ask a question to start. For the single-table analysis fixture, try “Highest revenue region?”</p> :
        <div className="chat-history">
          {analyses.length === 0 && <ol className="messages">{messages.map(message => <li key={message.id} className={`chat-message chat-message-${message.role === "user" ? "user" : "assistant"}`}>
            <span className="chat-role">{message.role === "user" ? "You" : "Analyst"}</span><p>{message.content}</p></li>)}</ol>}
          {analyses.map(item => <article className="chat-turn" id={`analysis-${item.id}`} key={item.id}>
        <div className="chat-message chat-message-user"><span className="chat-role">You</span><p>{item.question}</p></div>
        <div className="chat-message chat-message-assistant">
        <div className="chat-answer-heading"><span className="chat-avatar">AI</span><div>
        <span className="chat-role">Analyst</span><h3>{item.status === "complete" ? "Computed answer" : item.status === "clarification" ? "Clarification" : "Analysis unavailable"}</h3>
        </div></div>
        <p className="chat-answer">{item.answer ?? item.clarification ?? item.error}</p>
        {item.status === "complete" && item.sql && item.dataset_versions.length === 1 && <button type="button" disabled={busy}
          onClick={() => void rerunAnalysis(item.id)}>Rerun saved query</button>}
        {item.anomalies && <AnomalySummary value={item.anomalies} />}
        {item.chart_error && <p role="status">Chart unavailable: {item.chart_error} The computed table is available.</p>}
        {item.table && <AnalysisEvidence table={item.table} charts={item.charts} />}
        {item.join_proposal && <><JoinReview autoScroll={item.id === joinReviewTarget} targetId={`join-review-${item.id}`}
          proposal={item.join_proposal} sources={datasets} />
          <div className="join-confirmation">
          {item.join_proposal.requires_multiplication && <label className="join-consent"><input type="checkbox" checked={multiply}
            disabled={busy} onChange={e => { setMultiply(e.target.checked); setConfirmation(null); }} />
            I accept that these joins can multiply rows and distort aggregates.</label>}
          <button className="join-confirm-button" disabled={busy || (item.join_proposal.requires_multiplication && !multiply)}
            onClick={() => setConfirmation(item.id)}>{confirmation === item.id ? "These exact joins are confirmed" : "Confirm these keys and join types"}</button>
          </div></>}
        {item.sql && <><details><summary>Method</summary><p>Calculation: {item.method.calculation}</p>
          <p>Filters: {item.method.filters}</p><p>Grouping: {item.method.grouping}</p>
          {(item.method.stages?.length ?? 0) > 1 && item.method.stages?.map((s, i) => <div key={i}>
            <h4>Calculation stage: {s.name}</h4><p>{s.metrics.join(", ")}</p>
            <p>{s.filters} · {s.grouping} · {s.ordering}</p></div>)}
          {item.method.joins && <JoinReview proposal={{ joins: item.method.joins.map(d => d.join), diagnostics: item.method.joins,
            requires_multiplication: item.method.joins.some(d => Boolean(d.multiplies_left_rows || d.multiplies_right_rows)) }} sources={datasets} />}
          {item.method.assumptions?.map(text => <p key={text}>{text}</p>)}</details>
          <details><summary>SQL</summary><pre>{item.sql}</pre>
            <button onClick={() => { void navigator.clipboard.writeText(item.sql!).then(() => setCopyStatus("SQL copied."))
              .catch(() => setCopyStatus("Could not copy. Select the SQL text to copy manually.")); }}>Copy SQL</button></details></>}
        <p className="source-list">Sources: {item.dataset_versions.map(source => `${source.display_name} v${source.version}`).join(", ")}</p>
        <button type="button" className="delete-analysis" disabled={busy || searchBusy}
          onClick={() => void deleteAnalysis(item)}>Delete saved analysis</button>
        </div>
          </article>)}
        </div>}
      {error && <p className="error" role="alert">{error}</p>}
      <p role="status">{busy ? "Analyzing the selected data…" : copyStatus}</p>
      {confirmation && <p>Explicit join confirmation attached to your next question.</p>}
      <form className="question-form" onSubmit={submit}><label htmlFor="question">Question</label>
        <textarea id="question" value={question} onChange={event => setQuestion(event.target.value)}
          onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault(); event.currentTarget.form?.requestSubmit();
          } }}
          placeholder="Ask about the selected data" maxLength={1000} rows={3} />
        <button type="submit" disabled={busy || !selected.length || !question.trim()}>
          {busy ? "Calculating…" : "Ask question"}</button>
        {!selected.length && <p>Select at least one dataset to ask a question.</p>}</form>
    </section></main>;
}
