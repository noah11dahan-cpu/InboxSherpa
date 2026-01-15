export type Urgency = "low" | "medium" | "high";

export type ActionType =
  | "archive_all"
  | "snooze"
  | "reply_with_template"
  | "label_add"
  | "label_remove";

export type SuggestedActionOut = {
  action_type: ActionType;
  reason: string;
  payload?: Record<string, unknown> | null;
};

export type ClusterSummaryOut = {
  cluster_title: string;
  summary_bullets: string[];
  urgency: Urgency;
  suggested_actions: SuggestedActionOut[];
  confidence: number;
};

export type DigestClusterOut = {
  cluster_id: string;
  title: string;
  message_count: number;
  summary: ClusterSummaryOut;
};

export type DigestTodayOut = {
  user_id: string;
  digest_date: string; // YYYY-MM-DD
  clusters: DigestClusterOut[];
};

export type ClusterMessageOut = {
  id: string;
  external_id: string;
  channel: string;
  timestamp: string;
  sender: string;
  subject: string;
  snippet: string | null;
  status: string;
};

export type ClusterDetailOut = {
  user_id: string;
  digest_date: string;
  cluster_id: string;
  title: string;
  message_count: number;
  summary: ClusterSummaryOut;
  messages: ClusterMessageOut[];
};

function apiBaseUrl(): string {
  const v = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!v) {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL is not set. Create web/.env.local (see web/.env.example)."
    );
  }
  return v.replace(/\/+$/, "");
}

async function fetchJson<T>(path: string): Promise<T> {
  const url = `${apiBaseUrl()}${path}`;
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`API ${r.status}: ${text}`);
  }
  return (await r.json()) as T;
}

export function getDigestToday(params: {
  user_id: string;
  digest_date: string; // YYYY-MM-DD
  auto_cluster_if_missing?: boolean;
}): Promise<DigestTodayOut> {
  const q = new URLSearchParams({
    user_id: params.user_id,
    digest_date: params.digest_date,
    auto_cluster_if_missing: String(params.auto_cluster_if_missing ?? true),
  });
  return fetchJson(`/digest/today?${q.toString()}`);
}

export function getClusterDetail(params: {
  cluster_id: string;
  user_id: string;
  digest_date: string; // YYYY-MM-DD
  limit?: number;
}): Promise<ClusterDetailOut> {
  const q = new URLSearchParams({
    user_id: params.user_id,
    digest_date: params.digest_date,
    limit: String(params.limit ?? 200),
  });
  return fetchJson(`/clusters/${params.cluster_id}?${q.toString()}`);
}
