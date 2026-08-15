import SocialScanForm from "@/components/SocialScanForm";

export default function SocialListeningPage() {
  return (
    <>
      <div className="eyebrow">On-demand · Twitter/X · LinkedIn · Reddit</div>
      <h1 style={{ fontSize: 26, marginBottom: 6 }}>Social Listening</h1>
      <p style={{ color: "var(--ink-muted)", marginTop: 6, marginBottom: 24, maxWidth: 640 }}>
        Enter up to 5 competitors to scan tone &amp; voice, pricing clarity, hiring signal, social
        momentum, and content velocity from recent social activity.
      </p>
      <SocialScanForm />
    </>
  );
}
