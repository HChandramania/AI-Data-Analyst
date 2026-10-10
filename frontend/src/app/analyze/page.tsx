"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearPrivateState } from "@/lib/api";

type Dataset = { id: string; display_name: string; profile: { row_count: number } };
export default function Analyze() {
  const router = useRouter();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  useEffect(() => {
    api<Dataset[]>("/datasets").then(items => {
      setDatasets(items);
      const saved = JSON.parse(sessionStorage.getItem("selected-datasets") ?? "[]") as string[];
      setSelected(saved.filter(id => items.some(item => item.id === id)).slice(0, 5));
    }).catch(() => { clearPrivateState(); router.replace("/login"); });
  }, [router]);
  function toggle(id: string) {
    const next = selected.includes(id) ? selected.filter(value => value !== id) : [...selected, id].slice(0, 5);
    setSelected(next); sessionStorage.setItem("selected-datasets", JSON.stringify(next));
  }
  return <main id="main" className="content"><p className="eyebrow">ANALYZE</p><h1>Choose your data</h1>
    <p>Select up to five datasets for the upcoming analysis workflow.</p>
    {datasets.length === 0 ? <p>No datasets yet. <Link href="/datasets">Upload CSVs</Link> to begin.</p> :
      <ul className="dataset-list">{datasets.map(item => <li key={item.id}>
        <label><input type="checkbox" checked={selected.includes(item.id)}
          disabled={!selected.includes(item.id) && selected.length >= 5}
          onChange={() => toggle(item.id)} /> {item.display_name} · {item.profile.row_count} rows</label>
      </li>)}</ul>}
    <p>{selected.length} of 5 selected. Questions become available in Phase 2.</p>
    <Link href="/datasets">Manage datasets</Link></main>;
}
