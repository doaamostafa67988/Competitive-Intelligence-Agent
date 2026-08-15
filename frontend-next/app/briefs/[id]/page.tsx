import { api } from "@/lib/api";

export default async function BriefDetailPage({ params }: { params: { id: string } }) {
  const brief = await api.getBrief(params.id);

  const badgeClass = (t: string) => (t === "new" ? "badge-new" : t === "modified" ? "badge-modified" : "badge-removed");

  return (
    <>
      <div className="eyebrow mono">{new Date(brief.run_date).toLocaleString()}</div>
      <h1 style={{ fontSize: 26, marginBottom: 14 }}>{brief.competitors_covered.join(", ")}</h1>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="eyebrow">Executive summary</div>
        <p style={{ lineHeight: 1.6 }}>{brief.executive_summary}</p>
      </div>

      {brief.sections.map((s, i) => (
        <div key={i} className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 16, marginBottom: 10 }}>{s.heading}</h3>
          <p style={{ lineHeight: 1.6, whiteSpace: "pre-wrap", color: "var(--ink)" }}>{s.body_markdown}</p>
          {s.cited_source_urls.length > 0 && (
            <div className="mono" style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 10 }}>
              Sources: {s.cited_source_urls.join(", ")}
            </div>
          )}
        </div>
      ))}

      {brief.change_log.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="eyebrow">What&apos;s new this week</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {brief.change_log.map((c, i) => (
              <div key={i} style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                <span className={`badge ${badgeClass(c.change_type)}`}>{c.change_type}</span>
                <span style={{ fontSize: 13.5 }}>
                  <strong>{c.competitor}</strong> — {c.description}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {brief.unconfirmed_claims.length > 0 && (
        <div className="card" style={{ borderColor: "var(--alert-rose)" }}>
          <div className="eyebrow" style={{ color: "var(--alert-rose)" }}>
            Unconfirmed — flagged, not asserted as fact
          </div>
          <ul style={{ margin: 0, paddingLeft: 18, color: "var(--ink-muted)", fontSize: 13.5 }}>
            {brief.unconfirmed_claims.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
