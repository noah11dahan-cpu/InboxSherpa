"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { DigestTodayOut, getDigestToday } from "@/lib/api";

function yyyyMmDdToday(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

const LS_USER_ID = "inboxsherpa_user_id";

export default function DigestPage() {
  const [userId, setUserId] = useState<string>("");
  const [digestDate, setDigestDate] = useState<string>(yyyyMmDdToday());
  const [data, setData] = useState<DigestTodayOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(LS_USER_ID);
    if (saved) setUserId(saved);
  }, []);

  const canRun = useMemo(() => userId.trim().length > 0 && digestDate.length === 10, [userId, digestDate]);

  async function run() {
    setErr(null);
    setLoading(true);
    setData(null);
    try {
      window.localStorage.setItem(LS_USER_ID, userId.trim());
      const out = await getDigestToday({ user_id: userId.trim(), digest_date: digestDate });
      setData(out);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <header className="mb-5">
        <h1 className="text-2xl font-semibold">Today’s Digest</h1>
        <p className="text-gray-600 mt-1">
          Dev mode: enter the user UUID, choose a date, then generate the digest.
        </p>
      </header>

      <div className="flex flex-col md:flex-row gap-3 items-end mb-6">
        <label className="flex flex-col gap-1 w-full md:w-[420px]">
          <span className="text-sm text-gray-700">User ID (UUID)</span>
          <input
            className="border rounded-lg px-3 py-2"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="96cd6791-db08-4723-9b61-36377b9f6c9a"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-sm text-gray-700">Date</span>
          <input
            className="border rounded-lg px-3 py-2"
            type="date"
            value={digestDate}
            onChange={(e) => setDigestDate(e.target.value)}
          />
        </label>

        <button
          className="border rounded-lg px-4 py-2 font-medium disabled:opacity-50"
          disabled={!canRun || loading}
          onClick={run}
        >
          {loading ? "Generating…" : "Generate"}
        </button>
      </div>

      {err && (
        <div className="border rounded-lg p-3 bg-red-50 text-red-800 mb-6">
          {err}
        </div>
      )}

      {!data && !err && (
        <div className="text-gray-600">
          Enter a user ID and click Generate.
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.clusters.map((c) => (
            <Link
              key={c.cluster_id}
              href={`/cluster/${c.cluster_id}?user_id=${encodeURIComponent(data.user_id)}&digest_date=${encodeURIComponent(
                data.digest_date
              )}`}
              className="border rounded-2xl p-4 hover:shadow-sm bg-white"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold">{c.summary.cluster_title || c.title}</div>
                  <div className="text-sm text-gray-600 mt-1">{c.message_count} messages</div>
                </div>
                <div className="text-xs border rounded-full px-2 py-1">
                  {c.summary.urgency}
                </div>
              </div>

              <ul className="mt-3 list-disc pl-5 text-sm text-gray-800">
                {c.summary.summary_bullets.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>

              {c.summary.suggested_actions.length > 0 && (
                <div className="mt-3">
                  <div className="text-sm font-medium">Suggested actions</div>
                  <ul className="mt-2 space-y-2">
                    {c.summary.suggested_actions.map((a, i) => (
                      <li key={i} className="text-sm text-gray-700">
                        <span className="font-medium">{a.action_type}</span>: {a.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="mt-3 text-xs text-gray-500">
                Confidence: {Math.round(c.summary.confidence * 100)}%
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
