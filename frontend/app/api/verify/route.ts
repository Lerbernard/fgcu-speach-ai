// Vercel serverless route: verifies the Turnstile token with Cloudflare (Vercel
// has normal egress, unlike the HF Space) and mints a session token that the HF
// backend validates by HMAC. Both sides must share the same SESSION_SECRET.
//
// PLACE THIS AT:  frontend/app/api/verify/route.ts
//
// Vercel env vars needed (Project → Settings → Environment Variables):
//   TURNSTILE_SECRET  = your Cloudflare Turnstile *secret* key
//   SESSION_SECRET    = the SAME value you set on the HF Space
// (NEXT_PUBLIC_TURNSTILE_SITEKEY is already set for the widget.)

import crypto from "crypto";

export const runtime = "nodejs"; // Node runtime so `crypto` is available

const SESSION_TTL = 2 * 60 * 60; // seconds — must match the backend's SESSION_TTL

function makeSession(secret: string): string {
  const exp = String(Math.floor(Date.now() / 1000) + SESSION_TTL);
  const sig = crypto.createHmac("sha256", secret).update(exp).digest("hex");
  return `${exp}.${sig}`;
}

export async function POST(req: Request) {
  const sessionSecret = process.env.SESSION_SECRET || "dev-only-change-me";
  const secret = process.env.TURNSTILE_SECRET || "";

  let token = "";
  try {
    const body = await req.json();
    token = body?.token || "";
  } catch {
    /* empty / invalid body */
  }

  // Turnstile not configured → behave like dev (issue a session).
  if (!secret) {
    return Response.json({ session: makeSession(sessionSecret) });
  }
  if (!token) {
    return Response.json({ detail: "Missing Turnstile token" }, { status: 400 });
  }

  try {
    const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ secret, response: token }),
    });
    const data = await r.json();
    if (!data.success) {
      const codes = JSON.stringify(data["error-codes"] || []);
      return Response.json({ detail: `Bot check failed: ${codes}` }, { status: 403 });
    }
    return Response.json({ session: makeSession(sessionSecret) });
  } catch (e) {
    return Response.json({ detail: `Could not reach Turnstile: ${e}` }, { status: 502 });
  }
}