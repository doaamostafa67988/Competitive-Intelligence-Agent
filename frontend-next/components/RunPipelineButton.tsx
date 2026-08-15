"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function RunPipelineButton() {
  const [loading, setLoading] = useState(false);
  const [publish, setPublish] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function run() {
    setLoading(true);
    setError(null);
    try {
      // Use whatever is configured on the Competitors page, if any. api.ts
      // omits `targets` entirely when this is empty, so the backend falls
      // back to TRACKED_COMPETITORS from .env when nothing's been added yet.
      const configured = await api.listCompetitors().catch(() => []);
      await api.runPipeline(publish, configured);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Pipeline run failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="eyebrow">Run pipeline</div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
        <input
          type="checkbox"
          style={{ width: "auto" }}
          checked={publish}
          onChange={(e) => setPublish(e.target.checked)}
        />
        Publish result to Telegram
      </label>
      <button className="btn" onClick={run} disabled={loading}>
        {loading ? "Research → Fact-Check → Graph → Analyze…" : "▶ Run weekly pipeline now"}
      </button>
      {error && <div style={{ color: "var(--alert-rose)", fontSize: 12.5 }}>{error}</div>}
    </div>
  );
}
