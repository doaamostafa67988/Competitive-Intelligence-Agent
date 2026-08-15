"use client";
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { GraphEdge, api } from "@/lib/api";

// react-force-graph relies on window/canvas — must load client-side only.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const LABEL_COLORS: Record<string, string> = {
  Competitor: "#D8A24A",
  Product: "#4FD1C5",
  PricePoint: "#8A97AD",
  Announcement: "#E2725B",
  JobPosting: "#6E8AC4",
};

function inferLabel(key: string): string {
  // Node label isn't in the flat edge list, so infer from key shape:
  // "Acme" -> Competitor, "Acme::Pro Plan" -> Product, deeper nesting -> PricePoint/etc.
  const depth = key.split("::").length;
  if (depth === 1) return "Competitor";
  if (depth === 2) return "Product";
  return "PricePoint";
}

export default function GraphExplorer() {
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.graphSnapshot().then(setEdges).catch(() => setEdges([])).finally(() => setLoading(false));
  }, []);

  const graphData = useMemo(() => {
    const nodeKeys = new Set<string>();
    edges.forEach((e) => { nodeKeys.add(e.from_key); nodeKeys.add(e.to_key); });
    const nodes = Array.from(nodeKeys).map((key) => ({ id: key, label: inferLabel(key) }));
    const links = edges.map((e) => ({ source: e.from_key, target: e.to_key, rel: e.rel_type }));
    return { nodes, links };
  }, [edges]);

  if (loading) return <p style={{ color: "var(--ink-muted)" }}>Loading graph…</p>;
  if (!edges.length)
    return <p style={{ color: "var(--ink-muted)" }}>Graph is empty — run the pipeline from the Dashboard first.</p>;

  return (
    <div className="card" style={{ height: 620, padding: 0, overflow: "hidden" }}>
      <ForceGraph2D
        graphData={graphData}
        backgroundColor="#121B2E"
        nodeLabel={(n: any) => `${n.id} (${n.label})`}
        nodeColor={(n: any) => LABEL_COLORS[n.label] || "#8A97AD"}
        linkColor={() => "#223049"}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        linkLabel={(l: any) => l.rel}
        nodeRelSize={5}
      />
    </div>
  );
}
