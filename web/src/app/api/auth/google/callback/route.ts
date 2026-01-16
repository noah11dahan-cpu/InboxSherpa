import { NextResponse } from "next/server";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");

  if (!code || !state) {
    return NextResponse.json({ error: "Missing code/state" }, { status: 400 });
  }

  // TODO: exchange code -> tokens on FastAPI, store tokens, then redirect to /digest
  // Example pattern:
  // await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/auth/google/exchange`, { method:"POST", body: JSON.stringify({code, state}) })

  return NextResponse.redirect(new URL("/digest", url.origin));
}
