"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ClusterDetailOut, getClusterDetail } from "@/lib/api";

export default function ClusterPage() {
  const params = useParams<{ clusterId: string }>();
  const sp = useSearchParams();

  const clusterId = params?.clusterId;
  const user_id = sp.get("user_id") ?? "";
  const digest_date = sp.get("digest_date") ?? "";

  const backHref = useMemo(() => {
    const q = new URLSearchParams();
    if (user_id) q.set("user_id", user_id);
    if (digest_date) q.set("digest_date", digest_date);
    const qs = q.toString();
    return qs ? `/digest?${qs}` : "/digest";
  }, [user_id, digest_date]);

  const [data, setData] = useState<ClusterDetailOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function run() {
      setErr(null);
      setLoading(true);
      try {
        if (!clusterId) throw new Error("Missing clusterId in route.");
        if (!user_id || !digest_date) throw new Error("Missing user_id or digest_date in URL query params.");

        const out = await getClusterDetail({
          cluster_id: clusterId,
          user_id,
          digest_date,
        });
        setData(out);
      } catch (e: any) {
        setErr(e?.message ?? String(e));
        setData(null);
      } finally {
        setLoading(false);
      }
    }
    run();
  }, [clusterId, user_id, digest_date]);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="mb-4">
        <Link className="underline" href={backHref}>
          Back to Digest
        </Link>
      </div>

      {loading && <div className="text-gray-600">Loading…</div>}

      {err && (
        <div className="border rounded-lg p-3 bg-red-50 text-red-800">
          {err}
        </div>
      )}

      {data && (
        <>
          <header className="mb-5">
            <h1 className="text-2xl font-semibold">{data.summary.cluster_title}</h1>
            <div className="text-sm text-gray-600 mt-1">
              {data.message_count} messages • urgency:{" "}
              <span className="font-medium">{data.summary.urgency}</span>
            </div>
          </header>

          <section className="border rounded-2xl p-4 bg-white mb-6">
            <div className="text-sm font-medium mb-2">Summary</div>
            <ul className="list-disc pl-5 text-sm text-gray-800">
              {data.summary.summary_bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>

            {data.summary.suggested_actions.length > 0 && (
              <div className="mt-4">
                <div className="text-sm font-medium">Suggested actions</div>
                <ul className="mt-2 space-y-2">
                  {data.summary.suggested_actions.map((a, i) => (
                    <li key={i} className="text-sm text-gray-700">
                      <span className="font-medium">{a.action_type}</span>: {a.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-4 text-xs text-gray-500">
              Confidence: {Math.round(data.summary.confidence * 100)}%
            </div>
          </section>

          <section className="space-y-3">
            <div className="text-sm font-medium">Messages</div>
            {data.messages.map((m) => (
              <div key={m.id} className="border rounded-xl p-3 bg-white">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium">{m.subject}</div>
                    <div className="text-sm text-gray-600">{m.sender}</div>
                  </div>
                  <div className="text-xs text-gray-500 whitespace-nowrap">
                    {new Date(m.timestamp).toLocaleString()}
                  </div>
                </div>
                {m.snippet && <div className="text-sm text-gray-700 mt-2">{m.snippet}</div>}
                <div className="text-xs text-gray-500 mt-2">
                  {m.channel} • {m.status} • external_id: {m.external_id}
                </div>
              </div>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
