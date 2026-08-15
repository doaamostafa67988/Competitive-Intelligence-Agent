"use client";
import { ChangeLogEntry } from "@/lib/api";

/**
 * Signature UI element: a scrolling ticker of this week's graph deltas,
 * echoing the Change-Log Agent's output the way a market ticker echoes
 * price moves. Duplicated once so the CSS marquee loops seamlessly.
 */
export default function SignalTicker({ entries }: { entries: ChangeLogEntry[] }) {
  if (!entries.length) {
    return (
      <div className="ticker">
        <div className="ticker-track">
          <span>No graph changes recorded yet — run the pipeline to populate this week's signal feed.</span>
        </div>
      </div>
    );
  }

  const symbolFor = (t: ChangeLogEntry["change_type"]) => (t === "new" ? "▲" : t === "modified" ? "◆" : "▼");
  const classFor = (t: ChangeLogEntry["change_type"]) =>
    t === "new" ? "delta-up" : t === "modified" ? "delta-mod" : "delta-down";

  const items = entries.map((e, i) => (
    <span key={i} className={classFor(e.change_type)}>
      {symbolFor(e.change_type)} {e.competitor} · {e.description}
    </span>
  ));

  return (
    <div className="ticker">
      <div className="ticker-track">
        {items}
        {items}
      </div>
    </div>
  );
}
