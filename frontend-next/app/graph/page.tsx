import GraphExplorer from "@/components/GraphExplorer";

export default function GraphPage() {
  return (
    <>
      <div className="eyebrow">Bonus feature</div>
      <h1 style={{ fontSize: 26, marginBottom: 6 }}>Knowledge Graph Explorer</h1>
      <p style={{ color: "var(--ink-muted)", marginBottom: 20, maxWidth: 640 }}>
        Competitor → Product → PricePoint → Announcement, drawn live from Neo4j.
        Drag nodes to explore relationships; hover an edge to see the relationship type.
      </p>
      <GraphExplorer />
    </>
  );
}
