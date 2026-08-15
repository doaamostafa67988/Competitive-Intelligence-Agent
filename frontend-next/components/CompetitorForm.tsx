"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function CompetitorForm() {
  const [name, setName] = useState("");
  const [pricingUrl, setPricingUrl] = useState("");
  const [careersUrl, setCareersUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const router = useRouter();

  async function save() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await api.upsertCompetitor({ name, pricing_url: pricingUrl || undefined, careers_url: careersUrl || undefined });
      setName(""); setPricingUrl(""); setCareersUrl("");
      router.refresh();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="eyebrow">Add / update competitor</div>
      <div>
        <label>Competitor name*</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Corp" />
      </div>
      <div>
        <label>Pricing page URL</label>
        <input value={pricingUrl} onChange={(e) => setPricingUrl(e.target.value)} placeholder="https://acme.com/pricing" />
      </div>
      <div>
        <label>Careers page URL</label>
        <input value={careersUrl} onChange={(e) => setCareersUrl(e.target.value)} placeholder="https://acme.com/careers" />
      </div>
      <button className="btn" onClick={save} disabled={saving || !name.trim()}>
        {saving ? "Saving…" : "Save competitor"}
      </button>
    </div>
  );
}
