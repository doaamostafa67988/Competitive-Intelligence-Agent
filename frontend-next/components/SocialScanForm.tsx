"use client";
import { useState } from "react";
import { api, SocialScorecard } from "@/lib/api";

const DIMENSIONS: [keyof SocialScorecard, string][] = [
  ["tone_voice", "Tone & Voice"],
  ["pricing_clarity", "Pricing Clarity"],
  ["hiring_signal", "Hiring Signal"],
  ["social_momentum", "Social Momentum"],
  ["content_velocity", "Content Velocity"],
];

const PLATFORM_OPTIONS: [string, string][] = [
  ["twitter", "Twitter/X"],
  ["linkedin", "LinkedIn"],
  ["reddit", "Reddit"],
];

export default function SocialScanForm() {
  const [names, setNames] = useState<string[]>(["", "", "", "", ""]);
  const [platforms, setPlatforms] = useState<string[]>(["twitter", "linkedin", "reddit"]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<SocialScorecard[] | null>(null);

  function setName(i: number, value: string) {
    setNames((prev) => prev.map((n, idx) => (idx === i ? value : n)));
  }

  function togglePlatform(p: string) {
    setPlatforms((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  }

  async function scan() {
    const competitors = names.map((n) => n.trim()).filter(Boolean).slice(0, 5);
    if (competitors.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.socialScan(competitors, platforms);
      setResults(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="eyebrow">Scan up to 5 competitors</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
          {names.map((n, i) => (
            <input
              key={i}
              value={n}
              onChange={(e) => setName(i, e.target.value)}
              placeholder={`Competitor ${i + 1}`}
            />
          ))}
        </div>
        <div>
          <label>Platforms</label>
          <div style={{ display: "flex", gap: 16 }}>
            {PLATFORM_OPTIONS.map(([value, label]) => (
              <label key={value} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  style={{ width: "auto" }}
                  checked={platforms.includes(value)}
                  onChange={() => togglePlatform(value)}
                />
                {label}
              </label>
            ))}
          </div>
        </div>
        <button className="btn" onClick={scan} disabled={loading || names.every((n) => !n.trim())}>
          {loading ? "Scanning Twitter/X, LinkedIn, Reddit…" : "📡 Scan"}
        </button>
        {error && <div style={{ color: "var(--alert-rose)", fontSize: 12.5 }}>{error}</div>}
      </div>

      {results && results.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {results.map((card) => (
            <div key={card.id} className="card">
              <div className="eyebrow">{new Date(card.scanned_at).toLocaleString()}</div>
              <h2 style={{ fontSize: 20, marginBottom: 6 }}>{card.competitor}</h2>
              <div className="mono" style={{ fontSize: 11.5, color: "var(--ink-faint)", marginBottom: 10 }}>
                platforms with data: {card.platforms_covered.length ? card.platforms_covered.join(", ") : "none found"}
              </div>
              <p style={{ fontSize: 13.5, color: "var(--ink-muted)", marginBottom: 16 }}>{card.overall_summary}</p>

              <div className="score-grid">
                {DIMENSIONS.map(([key, label]) => {
                  const dim = card[key] as { score: number; label: string; rationale: string };
                  return (
                    <div key={key} className="score-tile">
                      <div className="eyebrow" style={{ marginBottom: 6 }}>{label}</div>
                      <div className="score-num">{dim.score}/10</div>
                      <div className="score-label">{dim.label}</div>
                      <div className="score-rationale">{dim.rationale}</div>
                    </div>
                  );
                })}
              </div>

              {card.sample_posts.length > 0 && (
                <details style={{ marginTop: 16 }}>
                  <summary style={{ cursor: "pointer", fontSize: 12.5, color: "var(--ink-muted)" }}>
                    Sample posts ({card.sample_posts.length})
                  </summary>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}>
                    {card.sample_posts.map((p, i) => (
                      <div key={i} style={{ fontSize: 12.5, borderBottom: "1px solid var(--line)", paddingBottom: 8 }}>
                        <span className="badge badge-new" style={{ marginRight: 8 }}>{p.platform}</span>
                        <a href={p.url} target="_blank" rel="noreferrer" style={{ color: "var(--confirmed-teal)" }}>
                          {p.title || p.url}
                        </a>
                        <div style={{ color: "var(--ink-muted)", marginTop: 3 }}>{p.snippet}</div>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
