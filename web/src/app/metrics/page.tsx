"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchJson, getLatestPipelineRun, PipelineRunOut } from "@/lib/api";

const LS_USER_ID = "inboxsherpa_user_id";

type MetricsOut = {
  user_id: string;
  tz_name: string;
  day: string; // YYYY-MM-DD
  messages_processed_today: number;
  clusters_today: number;
  actions_accepted_today: number;
  actions_rejected_today: number;
};

export default function MetricsPage() {
  const [userId, setUserId] = useState<string>("");
  const [data, setData] = useState<MetricsOut | null>(null);
  const [latestRun, setLatestRun] = useState<PipelineRunOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(LS_USER_ID);
    if (saved) setUserId(saved);
  }, []);

  useEffect(() => {
    if (!userId) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  async function load() {
    setErr(null);
    setLoading(true);
    try {
      const m = await fetchJson<MetricsOut>(`/metrics?user_id=${encodeURIComponent(userId)}`);
      setData(m);

      // Optional: show last pipeline run if you implemented /pipeline/latest
      try {
        const r = await getLatestPipelineRun({ user_id: userId, run_kind: "clustering_v1" });
        setLatestRun(r);
      } catch {
        // If you haven't wired the endpoint yet, silently ignore
        setLatestRun(null);
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
      setData(null);
      setLatestRun(null);
    } finally {
      setLoading(false);
    }
  }

  if (!userId) {
    return (
      <main className="p-6 max-w-3xl mx-auto">
        <h1 className="text-2xl font-semibold">Metrics</h1>
        <p className="text-gray-700 mt-2">
          No connected Gmail account yet. Go back and click <b>Connect Gmail</b>.
        </p>
        <Link className="inline-block mt-4 border rounded-lg px-4 py-2" href="/">
          Back to Connect
        </Link>
      </main>
    );
  }

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <header className="mb-5">
        <h1 className="text-2xl font-semibold">Metrics</h1>
        <p className="text-gray-600 mt-1">
          User: <span className="font-mono text-sm">{userId}</span>
        </p>

        <div className="mt-3 flex gap-2">
          <button
            className="border rounded-lg px-4 py-2 font-medium disabled:opacity-50"
            disabled={loading}
            onClick={() => void load()}
          >
            {loading ? "Refreshing..." : "Refresh"}
          </button>

          <Link className="border rounded-lg px-4 py-2" href="/digest">
            Back to Digest
          </Link>
        </div>
      </header>

      {err && <div className="border rounded-lg p-3 bg-red-50 text-red-800 mb-6">{err}</div>}

      {!data && !err && (
        <div className="text-gray-600">{loading ? "Loading..." : "No data yet."}</div>
      )}

      {data && (
        <div className="space-y-3">
          <div className="border rounded-2xl p-4 bg-white">
            <div className="text-sm text-gray-600">Timezone</div>
            <div className="text-lg font-semibold">{data.tz_name}</div>
          </div>

          <div className="border rounded-2xl p-4 bg-white">
            <div className="text-sm text-gray-600">Day</div>
            <div className="text-lg font-semibold">{data.day}</div>
          </div>

          <div className="border rounded-2xl p-4 bg-white">
            <div className="text-sm text-gray-600">Messages processed today</div>
            <div className="text-lg font-semibold">{data.messages_processed_today}</div>
          </div>

          <div className="border rounded-2xl p-4 bg-white">
            <div className="text-sm text-gray-600">Clusters today</div>
            <div className="text-lg font-semibold">{data.clusters_today}</div>
          </div>

          <div className="border rounded-2xl p-4 bg-white">
            <div className="text-sm text-gray-600">Actions</div>
            <div className="text-lg font-semibold">
              Accepted: {data.actions_accepted_today} · Rejected: {data.actions_rejected_today}
            </div>
          </div>

          {latestRun && (
            <div className="border rounded-2xl p-4 bg-white">
              <div className="text-sm text-gray-600">Latest pipeline run</div>
              <div className="mt-1 text-sm">
                <div>
                  <span className="text-gray-600">kind:</span>{" "}
                  <span className="font-medium">{latestRun.run_kind}</span>
                </div>
                <div>
                  <span className="text-gray-600">digest_date:</span>{" "}
                  <span className="font-medium">{latestRun.digest_date}</span>
                </div>
                <div>
                  <span className="text-gray-600">started:</span>{" "}
                  <span className="font-medium">{latestRun.started_at}</span>
                </div>
                <div>
                  <span className="text-gray-600">finished:</span>{" "}
                  <span className="font-medium">{latestRun.finished_at ?? "—"}</span>
                </div>
                <div>
                  <span className="text-gray-600">duration_ms:</span>{" "}
                  <span className="font-medium">{latestRun.duration_ms ?? "—"}</span>
                </div>
              </div>
            </div>
          )}

          {!latestRun && (
            <div className="text-xs text-gray-500">
              No pipeline run data (or /pipeline/latest isn’t wired yet).
            </div>
          )}
        </div>
      )}
    </main>
  );
}
