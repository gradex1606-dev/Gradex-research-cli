/**
 * POST /api/waitlist — record early-access email.
 *
 * Configure in Vercel (Project → Settings → Environment Variables):
 *   SUPABASE_URL          — e.g. https://xxxx.supabase.co
 *   SUPABASE_ANON_KEY     — anon key with INSERT on `waitlist` table
 *
 * Supabase table (SQL):
 *   create table waitlist (
 *     id uuid primary key default gen_random_uuid(),
 *     email text unique not null,
 *     created_at timestamptz default now()
 *   );
 *   alter table waitlist enable row level security;
 *   create policy "allow anon insert" on waitlist for insert to anon with check (true);
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ ok: false, error: "Method not allowed" });
  }

  let body = req.body;
  if (typeof body === "string") {
    try {
      body = JSON.parse(body);
    } catch {
      return res.status(400).json({ ok: false, error: "Invalid JSON" });
    }
  }

  const email = typeof body?.email === "string" ? body.email.trim().toLowerCase() : "";
  if (!EMAIL_RE.test(email)) {
    return res.status(400).json({ ok: false, error: "Invalid email address" });
  }

  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseKey) {
    return res.status(503).json({
      ok: false,
      error: "Waitlist storage is not configured on the server",
    });
  }

  try {
    const response = await fetch(`${supabaseUrl.replace(/\/$/, "")}/rest/v1/waitlist`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: supabaseKey,
        Authorization: `Bearer ${supabaseKey}`,
        Prefer: "return=minimal",
      },
      body: JSON.stringify({ email }),
    });

    if (response.status === 409) {
      return res.status(200).json({ ok: true, duplicate: true });
    }

    if (!response.ok) {
      const detail = await response.text();
      console.error("Supabase waitlist insert failed:", response.status, detail);
      return res.status(502).json({ ok: false, error: "Failed to save email" });
    }

    return res.status(200).json({ ok: true });
  } catch (err) {
    console.error("Waitlist handler error:", err);
    return res.status(500).json({ ok: false, error: "Server error" });
  }
};
