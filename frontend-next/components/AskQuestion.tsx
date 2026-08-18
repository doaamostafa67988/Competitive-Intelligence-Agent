"use client";
import { useState } from "react";
import { api, QAAnswer } from "@/lib/api";

const EXAMPLES = [
  "Which competitors have changed their pricing more than once recently?",
  "Is anyone talking about AI features in their announcements?",
  "What has Acme Corp announced lately?",
];

export default function AskQuestion() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QAAnswer | null>(null);

  async function ask(q?: string) {
    const finalQuestion = (q ?? question).trim();
    if (!finalQuestion) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const answer = await api.askQuestion(finalQuestion);
      setResult(answer);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to get an answer");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="eyebrow">Ask a question</div>
      <p style={{ fontSize: 12.5, color: "var(--ink-muted)", margin: 0 }}>
        Ask anything about tracked competitors — the agent decides on the fly whether to run a
        semantic search over announcements or a graph lookup for pricing patterns, rather than a
        fixed set of questions.
      </p>

      <div>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Which competitors raised prices twice this quarter?"
          rows={3}
          style={{ width: "100%", resize: "vertical" }}
        />
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {EXAMPLES.map((ex) => (
          <button key={ex} className="btn-ghost" style={{ fontSize: 11.5 }} onClick={() => { setQuestion(ex); ask(ex); }}>
            {ex}
          </button>
        ))}
      </div>

      <button className="btn" onClick={() => ask()} disabled={loading || !question.trim()}>
        {loading ? "Thinking…" : "Ask"}
      </button>

      {error && <div style={{ color: "var(--alert-rose)", fontSize: 12.5 }}>{error}</div>}

      {result && (
        <div style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
          <div style={{ fontSize: 14, lineHeight: 1.5 }}>{result.answer}</div>
          {result.tools_used.length > 0 ? (
            <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
              {result.tools_used.map((t, i) => (
                <span
                  key={i}
                  className="mono"
                  style={{ fontSize: 10.5, color: "var(--ink-faint)", border: "1px solid var(--line)", borderRadius: 4, padding: "2px 6px" }}
                >
                  {t}
                </span>
              ))}
            </div>
          ) : (
            <div style={{ marginTop: 10, fontSize: 11.5, color: "var(--ink-faint)" }}>
              No data lookup was needed to answer this.
            </div>
          )}
          {result.sources.length > 0 && (
            <div style={{ marginTop: 10, fontSize: 11.5, color: "var(--ink-muted)" }}>
              <div style={{ marginBottom: 4 }}>Sources used:</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {result.sources.map((s, i) => (
                  <li key={i}>
                    {s.competitor ? `${s.competitor} — ` : ""}
                    {s.source_url ? (
                      <a href={s.source_url} target="_blank" rel="noreferrer">{s.source_url}</a>
                    ) : (
                      "no link"
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
