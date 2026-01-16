import { NextResponse } from "next/server";

export async function GET() {
  // TODO: call your FastAPI /auth/google/start to get the Google consent URL (with state+PKCE)
  // For now, keep this as a placeholder so the route exists.
  return NextResponse.json(
    { error: "Not wired yet. Implement FastAPI /auth/google/start and redirect here." },
    { status: 501 }
  );
}
