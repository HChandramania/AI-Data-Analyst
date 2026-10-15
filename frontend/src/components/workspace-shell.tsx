"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { SignOut } from "@/components/signout";

const navigation = [
  { href: "/datasets", label: "Datasets", icon: "▦" },
  { href: "/analyze", label: "Analyze", icon: "✦" },
  { href: "/dashboards", label: "Dashboards", icon: "◫" },
];

export function WorkspaceShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  if (pathname === "/login" || pathname === "/register") {
    return <div className="auth-shell">
      <section className="auth-showcase">
        <Link href="/login" className="brand"><span className="brand-mark" aria-hidden="true">db<span>.</span></span>
          <span className="brand-copy">Digital Back Office<small>AI Data Analyst</small></span></Link>
        <div className="showcase-copy"><p className="eyebrow">TRUSTED ANALYTICS FOR EVERY TEAM</p>
          <h1>Ask better questions<br /><span>of your business data.</span></h1>
          <p>Turn CSV and Excel files into clear, verifiable answers with calculations you can inspect, charts you can trust, and evidence you can share.</p>
        </div>
        <div className="preview-card" aria-label="Example analysis preview">
          <div className="preview-card-header"><span>Revenue overview</span><span className="live-pill"><i />Live evidence</span></div>
          <div className="preview-metric"><strong>$24,680</strong><span>+18.4% vs last month</span></div>
          <div className="preview-bars"><i style={{ height: "38%" }} /><i style={{ height: "57%" }} /><i style={{ height: "49%" }} /><i style={{ height: "78%" }} /><i style={{ height: "67%" }} /><i style={{ height: "92%" }} /></div>
          <div className="preview-card-footer"><span>Calculated from 4,280 rows</span><span>↗ Inspect SQL</span></div>
        </div>
      </section>
      <main className="auth-panel">{children}<p className="auth-footnote">Your data stays private and owner-scoped.</p></main>
    </div>;
  }
  const pageTitle = pathname.startsWith("/analyze") ? "Analyze" : pathname.startsWith("/dashboards") ? "Dashboards" : "Datasets";

  return <div className="app-shell">
    <button className="mobile-backdrop" aria-label="Close navigation" data-open={open} onClick={() => setOpen(false)} />
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <div className="sidebar-top">
        <Link href="/analyze" className="brand" onClick={() => setOpen(false)}>
          <span className="brand-mark" aria-hidden="true">db<span>.</span></span>
          <span className="brand-copy">Digital Back Office<small>AI Data Analyst</small></span>
        </Link>
        <button className="sidebar-close" aria-label="Close navigation" onClick={() => setOpen(false)}>×</button>
      </div>
      <nav aria-label="Main navigation">
        {navigation.map(item => <Link key={item.href} href={item.href}
          className={pathname.startsWith(item.href) ? "nav-link nav-link-active" : "nav-link"} onClick={() => setOpen(false)}>
          <span className="nav-icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span>
        </Link>)}
      </nav>
      <div className="sidebar-account"><div className="account-avatar">A</div><div><strong>Analyst</strong><small>Local account</small></div><SignOut /></div>
    </aside>
    <div className="workspace">
      <header className="topbar">
        <button className="menu-button" aria-label="Open navigation" onClick={() => setOpen(true)}>☰</button>
        <div className="topbar-title"><span className="topbar-dot" aria-hidden="true" />{pageTitle}</div>
        <div className="topbar-actions"><span className="secure-status"><span />Private workspace</span><div className="topbar-user">A</div></div>
      </header>
      {children}
    </div>
  </div>;
}
