"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ClusterDetailOut,
  getClusterDetail,
  applySuggestedAction,
} from "@/lib/api";

type ViewFilter = "inbox" | "all";

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
  const [actionBusy, setActionBusy] = useState(false);
  const [view, setView] = useState<ViewFilter>("inbox");

  async function load() {
    setErr(null);
    setLoading(true);
    try {
      if (!clusterId) throw new Error("Missing clusterId in route.");
      if (!user_id || !digest_date)
        throw new Error("Missing user_id or digest_date in URL query params.");

      const out = await getClusterDetail({
        cluster_id: clusterId,
        user_id,
        digest_date,
      });
      setData(out);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clusterId, user_id, digest_date]);

  async function onDecision(params: {
    suggested_action_id: string | undefined;
    decision: "accept" | "reject";
  }) {
    if (!params.suggested_action_id) return;
    if (!user_id) return;

    setErr(null);
    setActionBusy(true);
    try {
      await applySuggestedAction({
        user_id,
        suggested_action_id: params.suggested_action_id,
        decision: params.decision,
      });
      await load(); // refresh cluster detail after applying
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setActionBusy(false);
    }
  }

  const visibleMessages = useMemo(() => {
    if (!data) return [];
    if (view === "all") return data.messages;
    return data.messages.filter((m) => (m.status || "").toLowerCase() === "inbox");
  }, [data, view]);

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
                  {data.summary.suggested_actions.map((a, i) => {
                    const status = a.status ?? "proposed";
                    const actionId = a.id;
                    const isDecided = status !== "proposed";

                    return (
                      <li
                        key={actionId ?? i}
                        className="text-sm text-gray-700 border rounded-xl p-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div>
                              <span className="font-medium">{a.action_type}</span>:{" "}
                              {a.reason}
                            </div>
                            <div className="text-xs text-gray-500 mt-1">
                              Status:{" "}
                              <span className="font-medium">{status}</span>
                            </div>
                          </div>

                          <div className="flex gap-2">
                            <button
                              className="border rounded-lg px-3 py-1 text-sm disabled:opacity-50"
                              disabled={actionBusy || isDecided || !actionId}
                              onClick={(e) => {
                                e.preventDefault();
                                void onDecision({
                                  suggested_action_id: actionId,
                                  decision: "accept",
                                });
                              }}
                            >
                              Accept
                            </button>

                            <button
                              className="border rounded-lg px-3 py-1 text-sm disabled:opacity-50"
                              disabled={actionBusy || isDecided || !actionId}
                              onClick={(e) => {
                                e.preventDefault();
                                void onDecision({
                                  suggested_action_id: actionId,
                                  decision: "reject",
                                });
                              }}
                            >
                              Reject
                            </button>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <div className="mt-4 text-xs text-gray-500">
              Confidence: {Math.round(data.summary.confidence * 100)}%
            </div>
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium">Messages</div>

              <div className="flex gap-2">
                <button
                  className={`border rounded-lg px-3 py-1 text-sm ${
                    view === "inbox" ? "font-medium" : ""
                  }`}
                  onClick={() => setView("inbox")}
                >
                  Inbox only
                </button>
                <button
                  className={`border rounded-lg px-3 py-1 text-sm ${
                    view === "all" ? "font-medium" : ""
                  }`}
                  onClick={() => setView("all")}
                >
                  All
                </button>
              </div>
            </div>

            {visibleMessages.length === 0 && (
              <div className="text-sm text-gray-600">
                {view === "inbox"
                  ? "No inbox messages left in this cluster."
                  : "No messages in this cluster."}
              </div>
            )}

            {visibleMessages.map((m) => (
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
                {m.snippet && (
                  <div className="text-sm text-gray-700 mt-2">{m.snippet}</div>
                )}
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
