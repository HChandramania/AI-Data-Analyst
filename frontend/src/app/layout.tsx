import type { Metadata } from "next";
import Link from "next/link";
import { SignOut } from "@/components/signout";
import "./globals.css";

export const metadata: Metadata = {
  title: "Digital Back Office", description: "Upload and inspect CSV datasets.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>
    <a className="skip-link" href="#main">Skip to content</a>
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/analyze" className="brand"><span className="brand-mark" aria-hidden="true">dbo<span>.</span></span>
          <span>Digital Back Office<small>AI Data Analyst</small></span></Link>
        <nav aria-label="Main navigation"><Link className="nav-active" href="/datasets">Datasets</Link>
          <Link className="nav-active" href="/analyze">Analyze</Link></nav>
        <div className="sidebar-note"><span className="phase-tag">Phase 1</span>
          <p>CSV intake</p><SignOut /></div>
      </aside>
      <div className="workspace"><header className="topbar"><span>Workspace <span aria-hidden="true">/</span> <strong>Datasets</strong></span>
        <span className="preview-label">Phase 1</span></header>{children}</div>
    </div>
  </body></html>;
}
