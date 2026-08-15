import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Competitive Intel — Market Watch Agent",
  description: "Multi-agent competitive intelligence dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">
              <span className="brand-dot" />
              MARKET WATCH
            </div>
            <nav>
              <Link className="nav-link" href="/">Dashboard</Link>
              <Link className="nav-link" href="/competitors">Competitors</Link>
              <Link className="nav-link" href="/social">Social Listening</Link>
              <Link className="nav-link" href="/graph">Knowledge Graph</Link>
            </nav>
          </aside>
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
