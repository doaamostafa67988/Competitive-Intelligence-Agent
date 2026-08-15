"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, CompetitorSuggestion } from "@/lib/api";

export default function DiscoverCompetitors() {
  const [company, setCompany] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<CompetitorSuggestion[] | null>(null);
  const [addingName, setAddingName] = useState<string | null>(null);
  const router = useRouter();

  async function discover() {
    if (!company.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const results = await api.discoverCompetitors(company.trim());
      setSuggestions(results);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Discovery failed");
    } finally {
      setLoading(false);
    }
  }

  async function addSuggestion(name: string) {
    setAddingName(name);
    try {
      await api.upsertCompetitor({ name });
      setSuggestions((prev) => (prev ? prev.filter((s) => s.name !== name) : prev));
      router.refresh();
    } finally {
      setAddingName(null);
    }
  }

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="eyebrow">Discover competitors</div>
      <p style={{ fontSize: 12.5, color: "var(--ink-muted)", margin: 0 }}>
        Enter your own company — this searches the web and suggests real competitors instead of
        typing each one in by hand.
      </p>
      <div>
        <label>Your company name*</label>
        <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Your Company" />
      </div>
      <button className="btn" onClick={discover} disabled={loading || !company.trim()}>
        {loading ? "Searching the web…" : "🔍 Discover"}
      </button>
      {error && <div style={{ color: "var(--alert-rose)", fontSize: 12.5 }}>{error}</div>}

      {suggestions && suggestions.length === 0 && (
        <p style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>
          No suggestions found. You can still add competitors manually below.
        </p>
      )}

      {suggestions && suggestions.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {suggestions.map((s) => (
            <div
              key={s.name}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 10,
                borderBottom: "1px solid var(--line)",
                paddingBottom: 8,
              }}
            >
              <div>
                <div style={{ fontSize: 13.5 }}>{s.name}</div>
                <div style={{ fontSize: 11.5, color: "var(--ink-muted)" }}>{s.reason}</div>
              </div>
              <button className="btn-ghost" onClick={() => addSuggestion(s.name)} disabled={addingName === s.name}>
                {addingName === s.name ? "Adding…" : "Add"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
