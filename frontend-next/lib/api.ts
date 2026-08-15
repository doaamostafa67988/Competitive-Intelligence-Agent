/**
 * Typed fetch wrapper around the FastAPI backend. All frontend pages go
 * through this module rather than calling fetch() directly.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

export interface BriefSummary {
  id: string;
  run_date: string;
  competitors_covered: string[];
  executive_summary: string;
}

export interface BriefSection {
  heading: string;
  body_markdown: string;
  cited_source_urls: string[];
}

export interface ChangeLogEntry {
  competitor: string;
  change_type: "new" | "modified" | "removed";
  description: string;
  previous_value?: string;
  new_value?: string;
}

export interface BriefDetail extends BriefSummary {
  sections: BriefSection[];
  change_log: ChangeLogEntry[];
  unconfirmed_claims: string[];
}

export interface Competitor {
  name: string;
  pricing_url?: string;
  careers_url?: string;
}

export interface CompetitorSuggestion {
  name: string;
  reason: string;
}

export interface GraphEdge {
  from_key: string;
  rel_type: string;
  to_key: string;
  props: Record<string, unknown>;
}

export interface DimensionScore {
  score: number;
  label: string;
  rationale: string;
}

export interface SocialPost {
  platform: string;
  title: string;
  url: string;
  snippet: string;
  published_at?: string;
}

export interface SocialScorecard {
  id: string;
  competitor: string;
  scanned_at: string;
  platforms_covered: string[];
  tone_voice: DimensionScore;
  pricing_clarity: DimensionScore;
  hiring_signal: DimensionScore;
  social_momentum: DimensionScore;
  content_velocity: DimensionScore;
  overall_summary: string;
  sample_posts: SocialPost[];
}

export const api = {
  listBriefs: (limit = 20) => request<BriefSummary[]>(`/briefs?limit=${limit}`),
  getBrief: (id: string) => request<BriefDetail>(`/briefs/${id}`),
  getBriefMarkdown: (id: string) => request<{ markdown: string }>(`/briefs/${id}/markdown`),
  runPipeline: (publishToTelegram = false, targets?: Competitor[]) =>
    request<BriefDetail>(`/briefs/run`, {
      method: "POST",
      body: JSON.stringify({
        publish_to_telegram_chat: publishToTelegram,
        // Omit entirely (not just []) when nothing is configured yet, so the
        // backend falls back to TRACKED_COMPETITORS from .env instead of
        // running with zero competitors.
        ...(targets && targets.length > 0 ? { targets } : {}),
      }),
    }),
  listCompetitors: () => request<Competitor[]>(`/competitors`),
  discoverCompetitors: (company: string) =>
    request<CompetitorSuggestion[]>(`/competitors/discover`, {
      method: "POST",
      body: JSON.stringify({ company }),
    }),
  upsertCompetitor: (c: Competitor) =>
    request<{ ok: boolean }>(`/competitors`, { method: "POST", body: JSON.stringify(c) }),
  removeCompetitor: (name: string) =>
    request<{ ok: boolean }>(`/competitors/${encodeURIComponent(name)}`, { method: "DELETE" }),
  graphSnapshot: () => request<GraphEdge[]>(`/graph/snapshot`),
  repeatPriceChangers: (since: string, n = 2) =>
    request<{ competitor: string; changes: number }[]>(`/graph/repeat-price-changers?since=${since}&n=${n}`),
  socialScan: (competitors: string[], platforms?: string[]) =>
    request<SocialScorecard[]>(`/social/scan`, {
      method: "POST",
      body: JSON.stringify({ competitors, ...(platforms && platforms.length > 0 ? { platforms } : {}) }),
    }),
};
