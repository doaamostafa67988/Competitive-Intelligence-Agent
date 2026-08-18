import AskQuestion from "@/components/AskQuestion";
import TopicsManager from "@/components/TopicsManager";

export default function QAPage() {
  return (
    <>
      <div className="eyebrow">Dynamic Q&amp;A</div>
      <h1 style={{ fontSize: 26, marginBottom: 20 }}>Ask About Competitors</h1>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 20, alignItems: "start", maxWidth: 980 }}>
        <AskQuestion />
        <TopicsManager />
      </div>
    </>
  );
}
