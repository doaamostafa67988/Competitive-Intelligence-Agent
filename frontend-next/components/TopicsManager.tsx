"use client";
import { useEffect, useState } from "react";
import { api, TrackedTopic } from "@/lib/api";

export default function TopicsManager() {
  const [topics, setTopics] = useState<TrackedTopic[]>([]);
  const [newTopic, setNewTopic] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setTopics(await api.listTopics());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load topics");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function add() {
    const topic = newTopic.trim();
    if (!topic) return;
    setError(null);
    try {
      await api.addTopic(topic);
      setNewTopic("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add topic");
    }
  }

  async function remove(id: string) {
    try {
      await api.removeTopic(id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove topic");
    }
  }

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="eyebrow">Tracked topics</div>
      <p style={{ fontSize: 12.5, color: "var(--ink-muted)", margin: 0 }}>
        These drive the weekly brief&apos;s &quot;Thematic Trends&quot; section and the &quot;What&apos;s New&quot;
        summary — add whatever you actually want watched instead of the default set.
      </p>

      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={newTopic}
          onChange={(e) => setNewTopic(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="e.g. layoffs, enterprise pricing, EU expansion"
          style={{ flex: 1 }}
        />
        <button className="btn" onClick={add} disabled={!newTopic.trim()}>Add</button>
      </div>

      {error && <div style={{ color: "var(--alert-rose)", fontSize: 12.5 }}>{error}</div>}

      {loading ? (
        <p style={{ color: "var(--ink-muted)", fontSize: 13.5 }}>Loading…</p>
      ) : topics.length === 0 ? (
        <p style={{ color: "var(--ink-muted)", fontSize: 13.5 }}>
          No topics yet — the brief falls back to a default set (AI features, enterprise expansion, new integrations).
        </p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
          {topics.map((t) => (
            <li key={t.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13.5 }}>
              <span>{t.topic}</span>
              <button className="btn-ghost" style={{ fontSize: 11 }} onClick={() => remove(t.id)}>Remove</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
