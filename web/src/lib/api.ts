// web/src/lib/api.ts

export type Urgency = "low" | "medium" | "high";

export type ActionType =
  | "archive_all"
  | "snooze"
  | "reply_with_template"
  | "label_add"
  | "label_remove";

export type SuggestionStatus = "proposed" | "accepted" | "rejected";

export type SuggestedActionOut = {
  id: string;
  action_type: ActionType;
  reason: string;
  payload?: Record<string, unknown> | null;

  urgency?: Urgency;
  confidence?: number | null;
  status?: SuggestionStatus;
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

// ✅ Day 11: clustering pipeline runtime (optional UI usage)
export type PipelineRunOut = {
  id: string;
  user_id: string;
  run_kind: string; // e.g. "clustering_v1"
  digest_date: string; // YYYY-MM-DD

  started_at: string; // ISO
  finished_at: string | null; // ISO
  duration_ms: number | null;

  meta: Record<string, unknown> | null;
};

export function apiBaseUrl(): string {
  const v = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!v) {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL is not set. Create web/.env.local (see web/.env.example)."
    );
  }
  return v.replace(/\/+$/, "");
}

export async function fetchJson<T>(path: string): Promise<T> {
  const url = `${apiBaseUrl()}${path}`;
  const r = await fetch(url, { cache: "no-store", mode: "cors" });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`API ${r.status}: ${text || r.statusText}`);
  }
  return (await r.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const url = `${apiBaseUrl()}${path}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    mode: "cors",
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`API ${r.status}: ${text || r.statusText}`);
  }
  return (await r.json()) as T;
}

export function getDigestToday(params: {
  user_id: string;
  digest_date: string; // YYYY-MM-DD
  auto_cluster_if_missing?: boolean;

  // ✅ matches backend: /digest/today has auto_sync_if_missing too
  auto_sync_if_missing?: boolean;
}): Promise<DigestTodayOut> {
  const q = new URLSearchParams({
    user_id: params.user_id,
    digest_date: params.digest_date,
    auto_cluster_if_missing: String(params.auto_cluster_if_missing ?? true),
    auto_sync_if_missing: String(params.auto_sync_if_missing ?? true),
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

export function applySuggestedAction(params: {
  user_id: string;
  suggested_action_id: string;
  decision: "accept" | "reject";
}): Promise<{
  ok: boolean;
  suggested_action_id: string;
  decision: "accept" | "reject";
  previous_status: string;
  new_status: string;
  messages_updated: number;
  message_status_set_to: string | null;
}> {
  return postJson(`/actions/apply`, params);
}

// ✅ Day 11: if you expose a route like GET /pipeline/latest?user_id=...&run_kind=...&digest_date=...
export function getLatestPipelineRun(params: {
  user_id: string;
  run_kind?: string; // default "clustering_v1"
  digest_date?: string; // YYYY-MM-DD (optional)
}): Promise<PipelineRunOut | null> {
  const q = new URLSearchParams({
    user_id: params.user_id,
    run_kind: params.run_kind ?? "clustering_v1",
  });
  if (params.digest_date) q.set("digest_date", params.digest_date);
  return fetchJson(`/pipeline/latest?${q.toString()}`);
}
