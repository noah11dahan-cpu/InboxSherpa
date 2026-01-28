"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const LS_USER_ID = "inboxsherpa_user_id";

export default function Home() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connectGmail() {
    const base = process.env.NEXT_PUBLIC_API_BASE_URL!;
    const userId = process.env.NEXT_PUBLIC_DEV_USER_ID!;
    if (!userId) {
      alert("Missing NEXT_PUBLIC_DEV_USER_ID in web/.env.local");
      return;
    }

    const r = await fetch(`${base}/auth/google/start?user_id=${encodeURIComponent(userId)}`);
    if (!r.ok) {
      const t = await r.text();
      alert(`Failed to start OAuth: ${t}`);
      return;
    }

    const data = await r.json();

    // store PKCE info for callback page
    sessionStorage.setItem("oauth_state", data.state);
    sessionStorage.setItem("oauth_code_verifier", data.code_verifier);
    sessionStorage.setItem("oauth_user_id", userId);
    sessionStorage.setItem("oauth_redirect_uri", data.redirect_uri);

    window.location.href = data.auth_url;
  }

  async function tryDemo() {
    setLoading(true);
    setError(null);

    try {
      const base = process.env.NEXT_PUBLIC_API_BASE_URL!;
      const r = await fetch(`${base}/demo`, { method: "POST" });

      if (!r.ok) {
        const t = await r.text();
        throw new Error(`Demo failed: ${t}`);
      }

      const data = await r.json();

      // Store user ID for digest page
      localStorage.setItem(LS_USER_ID, data.user_id);

      // Redirect to digest page with the demo date
      router.push(`/digest?digest_date=${data.digest_date}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-white">
      <div className="max-w-4xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            InboxSherpa
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            AI-powered email triage that clusters your inbox and suggests actions.
            Get a daily digest instead of inbox chaos.
          </p>
        </div>

        {/* Feature highlights */}
        <div className="grid md:grid-cols-3 gap-6 mb-12">
          <div className="bg-white rounded-xl p-6 shadow-sm border">
            <div className="text-2xl mb-2">📊</div>
            <h3 className="font-semibold text-gray-900 mb-1">Smart Clustering</h3>
            <p className="text-sm text-gray-600">
              ML groups similar emails into digestible clusters like Promos, Bills, Work
            </p>
          </div>
          <div className="bg-white rounded-xl p-6 shadow-sm border">
            <div className="text-2xl mb-2">⚡</div>
            <h3 className="font-semibold text-gray-900 mb-1">Action Suggestions</h3>
            <p className="text-sm text-gray-600">
              One-click archive, snooze, or label entire clusters at once
            </p>
          </div>
          <div className="bg-white rounded-xl p-6 shadow-sm border">
            <div className="text-2xl mb-2">🔒</div>
            <h3 className="font-semibold text-gray-900 mb-1">Privacy First</h3>
            <p className="text-sm text-gray-600">
              No auto-actions, encrypted tokens, local ML, delete anytime
            </p>
          </div>
        </div>

        {/* CTA buttons */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-8">
          <button
            onClick={tryDemo}
            disabled={loading}
            className="w-full sm:w-auto px-8 py-3 bg-blue-600 text-white font-medium rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Loading Demo..." : "Try Demo"}
          </button>

          <button
            onClick={connectGmail}
            disabled={loading}
            className="w-full sm:w-auto px-8 py-3 bg-white text-gray-700 font-medium rounded-xl border border-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Connect Gmail
          </button>
        </div>

        {error && (
          <div className="max-w-md mx-auto bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm text-center">
            {error}
          </div>
        )}

        {/* Demo explanation */}
        <div className="text-center text-sm text-gray-500 mb-12">
          <p>
            <strong>Try Demo</strong> loads sample emails to show how InboxSherpa works.
            <br />
            <strong>Connect Gmail</strong> syncs your real inbox (requires OAuth setup).
          </p>
        </div>

        {/* How it works */}
        <div className="bg-gray-50 rounded-2xl p-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-6 text-center">
            How It Works
          </h2>
          <div className="flex flex-col md:flex-row gap-4 justify-center items-center text-center">
            <div className="flex-1">
              <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-2 text-blue-600 font-bold">
                1
              </div>
              <p className="text-sm text-gray-600">
                Connect your Gmail or try the demo
              </p>
            </div>
            <div className="text-gray-300 hidden md:block">→</div>
            <div className="flex-1">
              <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-2 text-blue-600 font-bold">
                2
              </div>
              <p className="text-sm text-gray-600">
                AI clusters your messages by topic
              </p>
            </div>
            <div className="text-gray-300 hidden md:block">→</div>
            <div className="flex-1">
              <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-2 text-blue-600 font-bold">
                3
              </div>
              <p className="text-sm text-gray-600">
                Review suggested actions per cluster
              </p>
            </div>
            <div className="text-gray-300 hidden md:block">→</div>
            <div className="flex-1">
              <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-2 text-blue-600 font-bold">
                4
              </div>
              <p className="text-sm text-gray-600">
                Accept or reject with one click
              </p>
            </div>
          </div>
        </div>

        {/* Footer links */}
        <div className="mt-12 text-center text-sm text-gray-500">
          <a href="/metrics" className="hover:text-gray-700 underline">
            Metrics
          </a>
          {" · "}
          <a
            href="https://github.com/noah11dahan-cpu/InboxSherpa"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-gray-700 underline"
          >
            GitHub
          </a>
        </div>
      </div>
    </main>
  );
}
