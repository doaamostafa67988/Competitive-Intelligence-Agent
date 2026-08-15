import Link from "next/link";
import { api } from "@/lib/api";
import SignalTicker from "@/components/SignalTicker";
import RunPipelineButton from "@/components/RunPipelineButton";

export default async function DashboardPage() {
  const briefs = await api.listBriefs(6).catch(() => []);
  const latestChangeLog = briefs.length ? await api.getBrief(briefs[0].id).catch(() => null) : null;

  const since = new Date();
  since.setDate(since.getDate() - 90);
  const repeatChangers = await api
    .repeatPriceChangers(since.toISOString().slice(0, 10))
    .catch(() => []);

  return (
    <>
      <div className="eyebrow">Weekly digest · sequential agent pipeline</div>
      <h1 style={{ fontSize: 28, marginBottom: 6 }}>Competitive Intelligence Dashboard</h1>
      <p style={{ color: "var(--ink-muted)", marginTop: 6, marginBottom: 24, maxWidth: 640 }}>
        Research → Fact-Check → Graph-Build → Analyze → Change-Log. Five agents, one standing
        knowledge graph, source-verified every week.
      </p>

      <SignalTicker entries={latestChangeLog?.change_log ?? []} />

      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 20 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <RunPipelineButton />

          <div className="card">
            <div className="eyebrow">Repeat price changers (90d)</div>
            {repeatChangers.length === 0 ? (
              <p style={{ color: "var(--ink-muted)", fontSize: 13.5 }}>None yet.</p>
            ) : (
              <table>
                <tbody>
                  {repeatChangers.map((r, i) => (
                    <tr key={i}>
                      <td>{r.competitor}</td>
                      <td className="mono" style={{ color: "var(--signal-amber)" }}>{r.changes}×</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="card">
          <div className="eyebrow">Latest briefs</div>
          {briefs.length === 0 ? (
            <p style={{ color: "var(--ink-muted)", fontSize: 13.5 }}>
              No briefs generated yet. Run the pipeline to produce the first one.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {briefs.map((b) => (
                <Link key={b.id} href={`/briefs/${b.id}`} className="nav-link" style={{ padding: 0 }}>
                  <div style={{ borderBottom: "1px solid var(--line)", paddingBottom: 14 }}>
                    <div className="mono" style={{ fontSize: 11, color: "var(--ink-faint)", marginBottom: 4 }}>
                      {new Date(b.run_date).toLocaleDateString()} · {b.competitors_covered.join(", ")}
                    </div>
                    <div style={{ color: "var(--ink)", fontSize: 14 }}>{b.executive_summary}</div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
