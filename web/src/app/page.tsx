"use client";

export default function Home() {
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

  return (
    <main style={{ padding: 24 }}>
      <h1>InboxSherpa</h1>
      <button
        onClick={connectGmail}
        style={{
          padding: "10px 14px",
          borderRadius: 8,
          border: "1px solid #ccc",
          cursor: "pointer",
          marginTop: 12,
        }}
      >
        Connect Gmail
      </button>
    </main>
  );
}
