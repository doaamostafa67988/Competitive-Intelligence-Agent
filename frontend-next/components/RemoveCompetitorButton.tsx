"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function RemoveCompetitorButton({ name }: { name: string }) {
  const [removing, setRemoving] = useState(false);
  const router = useRouter();

  async function remove() {
    if (!confirm(`Stop tracking "${name}"?`)) return;
    setRemoving(true);
    try {
      await api.removeCompetitor(name);
      router.refresh();
    } finally {
      setRemoving(false);
    }
  }

  return (
    <button
      onClick={remove}
      disabled={removing}
      style={{
        background: "none",
        border: "none",
        color: "var(--alert-rose, #e11d48)",
        cursor: "pointer",
        fontSize: 12.5,
        padding: 0,
      }}
    >
      {removing ? "Removing…" : "Remove"}
    </button>
  );
}
