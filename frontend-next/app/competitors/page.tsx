import { api } from "@/lib/api";
import CompetitorForm from "@/components/CompetitorForm";
import DiscoverCompetitors from "@/components/DiscoverCompetitors";
import RemoveCompetitorButton from "@/components/RemoveCompetitorButton";

export default async function CompetitorsPage() {
  const competitors = await api.listCompetitors().catch(() => []);

  return (
    <>
      <div className="eyebrow">Configuration</div>
      <h1 style={{ fontSize: 26, marginBottom: 20 }}>Tracked Competitors</h1>

      <div style={{ marginBottom: 20 }}>
        <DiscoverCompetitors />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 20 }}>
        <CompetitorForm />

        <div className="card">
          <div className="eyebrow">Currently tracked</div>
          {competitors.length === 0 ? (
            <p style={{ color: "var(--ink-muted)", fontSize: 13.5 }}>No competitors added yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Pricing page</th>
                  <th>Careers page</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {competitors.map((c, i) => (
                  <tr key={i}>
                    <td>{c.name}</td>
                    <td className="mono" style={{ fontSize: 12 }}>{c.pricing_url || "—"}</td>
                    <td className="mono" style={{ fontSize: 12 }}>{c.careers_url || "—"}</td>
                    <td><RemoveCompetitorButton name={c.name} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}
