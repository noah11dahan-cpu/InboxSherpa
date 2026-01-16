"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function GoogleCallbackPage() {
  const router = useRouter();
  const [msg, setMsg] = useState("Finishing Gmail connection...");

  useEffect(() => {
    async function run() {
      const url = new URL(window.location.href);
      const code = url.searchParams.get("code");
      const state = url.searchParams.get("state");
      const error = url.searchParams.get("error");

      if (error) {
        setMsg(`OAuth error: ${error}`);
        return;
      }
      if (!code || !state) {
        setMsg("Missing code/state in callback URL.");
        return;
      }

      const base = process.env.NEXT_PUBLIC_API_BASE_URL!;
      const userId = sessionStorage.getItem("oauth_user_id");
      const codeVerifier = sessionStorage.getItem("oauth_code_verifier");
      const redirectUri = sessionStorage.getItem("oauth_redirect_uri");
      const storedState = sessionStorage.getItem("oauth_state");

      if (!userId || !codeVerifier || !redirectUri || !storedState) {
        setMsg("Missing PKCE data in sessionStorage. Go back and click Connect again.");
        return;
      }
      if (storedState !== state) {
        setMsg("State mismatch. Please try connecting again.");
        return;
      }

      const r = await fetch(`${base}/auth/google/exchange`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code,
          code_verifier: codeVerifier,
          redirect_uri: redirectUri,
          user_id: userId,
          state,
        }),
      });

      if (!r.ok) {
        const t = await r.text();
        setMsg(`Exchange failed: ${t}`);
        return;
      }

      // After successful connect, store user_id so Digest can auto-load (no manual UUID entry)
      localStorage.setItem("inboxsherpa_user_id", userId);

      // clean session storage
      sessionStorage.removeItem("oauth_user_id");
      sessionStorage.removeItem("oauth_code_verifier");
      sessionStorage.removeItem("oauth_redirect_uri");
      sessionStorage.removeItem("oauth_state");

      setMsg("Connected! Loading your real inbox...");
      router.replace("/digest");
    }

    run();
  }, [router]);

  return (
    <main className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-semibold">Gmail Connection</h1>
      <p className="text-gray-700 mt-3">{msg}</p>
    </main>
  );
}