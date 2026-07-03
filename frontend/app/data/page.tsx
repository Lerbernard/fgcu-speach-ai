"use client";

// Ask the Eagle usage dashboard. Route: app/data/page.tsx
// Password-gated: the password is verified server-side by the /admin endpoints,
// so the Supabase data is never exposed without it. Set ADMIN_PASSWORD on the
// backend (Hugging Face Space secret, or your local .env) to enable this page.

import { useState, useEffect, useMemo, useCallback, useRef, Fragment, type FormEvent } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";
const PAGE_SIZE = 50;

type LogRow = {
  created_at: string;
  client_id: string;
  message_id?: string;
  question: string;
  answer: string;
  language: string;
  rating?: number | null;
  platform?: string;
  browser?: string;
  mode?: string;
  corrected_question?: string;
};
type IssueRow = { created_at: string; client_id: string; description: string; mode?: string; platform?: string; browser?: string };

// Give each anonymous device a friendly label like "Windows 1" / "iPhone 2":
// group distinct client_ids by platform and number them by first-seen order.
function deriveDeviceNames(rows: LogRow[]): Map<string, string> {
  const info = new Map<string, { platform: string; ts: number }>();
  for (const r of rows) {
    const cid = r.client_id || "unknown";
    const ts = new Date(r.created_at).getTime() || 0;
    const plat = r.platform && r.platform !== "Unknown" ? r.platform : "";
    const cur = info.get(cid);
    if (!cur) info.set(cid, { platform: plat || "Unknown", ts });
    else {
      if (ts < cur.ts) cur.ts = ts;
      if (plat && cur.platform === "Unknown") cur.platform = plat;
    }
  }
  const byPlatform = new Map<string, { cid: string; ts: number }[]>();
  for (const [cid, v] of info) {
    if (!byPlatform.has(v.platform)) byPlatform.set(v.platform, []);
    byPlatform.get(v.platform)!.push({ cid, ts: v.ts });
  }
  const names = new Map<string, string>();
  for (const [platform, arr] of byPlatform) {
    arr.sort((a, b) => a.ts - b.ts);
    arr.forEach((x, i) => names.set(x.cid, `${platform} ${i + 1}`));
  }
  return names;
}

function uniqueSorted(vals: (string | undefined)[]): string[] {
  return Array.from(new Set(vals.map((v) => v || "Unknown"))).sort();
}

function countBy(rows: LogRow[], key: (r: LogRow) => string): [string, number][] {
  const m = new Map<string, number>();
  for (const r of rows) {
    const k = key(r);
    m.set(k, (m.get(k) || 0) + 1);
  }
  return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
}

// Windowed page list with ellipses, e.g. [1, "…", 5, 6, 7, "…", 20]. current is 0-indexed.
function pageList(current: number, total: number): (number | "…")[] {
  const cur = current + 1;
  const want = new Set<number>([1, total, cur, cur - 1, cur + 1]);
  const sorted = [...want].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  let prev = 0;
  for (const p of sorted) {
    if (p - prev > 1) out.push("…");
    out.push(p);
    prev = p;
  }
  return out;
}

const SunIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
);
const MoonIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="none">
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
);
const BackArrow = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" />
  </svg>
);
const ThumbUp = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
  </svg>
);
const ThumbDown = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
  </svg>
);

function MultiFilter({ title, options, selected, onToggle }: {
  title: string; options: string[]; selected: string[]; onToggle: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);
  return (
    <div className="dash-mf" ref={ref}>
      <button type="button" className={`dash-mf-btn${selected.length ? " on" : ""}`} onClick={() => setOpen((o) => !o)}>
        {title}{selected.length > 0 ? ` · ${selected.length}` : ""}
        <span className="dash-mf-caret">▾</span>
      </button>
      {open && (
        <div className="dash-mf-panel">
          {options.length === 0 ? (
            <div className="dash-mf-empty">None</div>
          ) : (
            options.map((o) => (
              <label key={o} className="dash-mf-opt">
                <input type="checkbox" checked={selected.includes(o)} onChange={() => onToggle(o)} />
                <span>{o}</span>
              </label>
            ))
          )}
        </div>
      )}
    </div>
  );
}

const CAL_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];
const CAL_WD = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const pad2 = (n: number) => String(n).padStart(2, "0");
const fmtDay = (ymd: string) => { const [y, m, d] = ymd.split("-").map(Number); return `${CAL_MONTHS[m - 1]} ${d}, ${y}`; };

function DateRangeFilter({ start, end, onChange }: {
  start: string; end: string; onChange: (s: string, e: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => {
    const b = start ? new Date(start + "T12:00:00") : new Date();
    return { y: Math.max(2026, b.getFullYear()), m: b.getMonth() };
  });
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const label = !start ? "All dates"
    : (!end || end === start) ? fmtDay(start)
    : `${fmtDay(start)} → ${fmtDay(end)}`;

  function pick(d: string) {
    if (!start || (start && end)) onChange(d, "");     // begin a new selection
    else if (d < start) onChange(d, start);            // second click before start -> swap
    else onChange(start, d);                            // second click (same day -> single day)
  }

  const lead = new Date(view.y, view.m, 1).getDay();
  const days = new Date(view.y, view.m + 1, 0).getDate();
  const cells: (string | null)[] = [];
  for (let i = 0; i < lead; i++) cells.push(null);
  for (let d = 1; d <= days; d++) cells.push(`${view.y}-${pad2(view.m + 1)}-${pad2(d)}`);
  const lo = start && end ? (start < end ? start : end) : start;
  const hi = start && end ? (start < end ? end : start) : start;

  return (
    <div className="dash-mf" ref={ref}>
      <button type="button" className={`dash-mf-btn${start ? " on" : ""}`} onClick={() => setOpen((o) => !o)}>
        {label}<span className="dash-mf-caret">▾</span>
      </button>
      {open && (
        <div className="dash-mf-panel dash-cal-panel">
          <div className="dash-cal-head">
            <div className="dash-cal-row">
              <button type="button" className="dash-cal-arrow" disabled={view.y <= 2026} onClick={() => setView((v) => ({ ...v, y: Math.max(2026, v.y - 1) }))} aria-label="Previous year">‹</button>
              <span className="dash-cal-lbl">{view.y}</span>
              <button type="button" className="dash-cal-arrow" onClick={() => setView((v) => ({ ...v, y: v.y + 1 }))} aria-label="Next year">›</button>
            </div>
            <div className="dash-cal-row">
              <button type="button" className="dash-cal-arrow" disabled={view.y <= 2026 && view.m === 0} onClick={() => setView((v) => v.m > 0 ? { ...v, m: v.m - 1 } : (v.y > 2026 ? { y: v.y - 1, m: 11 } : v))} aria-label="Previous month">‹</button>
              <span className="dash-cal-lbl">{CAL_MONTHS[view.m]}</span>
              <button type="button" className="dash-cal-arrow" onClick={() => setView((v) => v.m < 11 ? { ...v, m: v.m + 1 } : { y: v.y + 1, m: 0 })} aria-label="Next month">›</button>
            </div>
          </div>
          <div className="dash-cal-grid">
            {CAL_WD.map((w) => <span key={w} className="dash-cal-wd">{w}</span>)}
            {cells.map((c, i) => c === null
              ? <span key={`b${i}`} />
              : (
                <button type="button" key={c}
                  className={`dash-cal-day${lo && hi && c >= lo && c <= hi ? " in" : ""}${c === start || c === end ? " sel" : ""}`}
                  onClick={() => pick(c)}>{Number(c.slice(-2))}</button>
              ))}
          </div>
          <div className="dash-cal-foot">
            <button type="button" className="dash-fchip dash-fchip-clear" onClick={() => onChange("", "")}>Clear</button>
            <button type="button" className="dash-fchip" onClick={() => setOpen(false)}>Done</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DataDashboard() {
  const [password, setPassword] = useState("");
  const [authed, setAuthed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [rows, setRows] = useState<LogRow[]>([]);
  const [issues, setIssues] = useState<IssueRow[]>([]);
  const [tab, setTab] = useState<"logs" | "issues">("logs");

  const [search, setSearch] = useState("");
  const [fLangs, setFLangs] = useState<string[]>([]);
  const [fPlatforms, setFPlatforms] = useState<string[]>([]);
  const [fBrowsers, setFBrowsers] = useState<string[]>([]);
  const [fRatings, setFRatings] = useState<string[]>([]);
  const [fModes, setFModes] = useState<string[]>([]);
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [fDevices, setFDevices] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const [mounted, setMounted] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  const load = useCallback(async (pw: string) => {
    setLoading(true);
    setError("");
    try {
      const [lr, ir] = await Promise.all([
        fetch(`${API_BASE}/admin/logs`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password: pw, limit: 3000 }),
        }),
        fetch(`${API_BASE}/admin/issues`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password: pw, limit: 1000 }),
        }),
      ]);
      if (lr.status === 401) {
        setError("Wrong password.");
        setAuthed(false);
        try { sessionStorage.removeItem("eagle_admin_pw"); } catch {}
        setLoading(false);
        return;
      }
      if (!lr.ok) throw new Error("fetch");
      const ld = await lr.json();
      const id = await ir.json().catch(() => ({ rows: [] }));
      setRows(ld.rows || []);
      setIssues(id.rows || []);
      setAuthed(true);
      try { sessionStorage.setItem("eagle_admin_pw", pw); } catch {}
    } catch {
      setError("Couldn't reach the backend. Is it running, and is ADMIN_PASSWORD set?");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    let saved = "";
    try { saved = sessionStorage.getItem("eagle_admin_pw") || ""; } catch {}
    if (!saved) return;
    // Defer the state update out of the effect body so it doesn't trip the
    // react-hooks/set-state-in-effect lint rule (cascading renders).
    const id = setTimeout(() => { setPassword(saved); load(saved); }, 0);
    return () => clearTimeout(id);
  }, [load]);

  // Read the theme the no-flash script applied, and mark mounted so the
  // interactive UI only renders client-side. That avoids extension-induced
  // hydration mismatches on the password form (password managers rewrite it).
  useEffect(() => {
    const id = setTimeout(() => {
      const cur = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
      setTheme(cur);
      setMounted(true);
    }, 0);
    return () => clearTimeout(id);
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (password.trim()) load(password.trim());
  }
  function logout() {
    try { sessionStorage.removeItem("eagle_admin_pw"); } catch {}
    setAuthed(false);
    setPassword("");
    setRows([]);
    setIssues([]);
  }
  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("eagle-theme", next); } catch {}
    setTheme(next);
  }

  const deviceNames = useMemo(() => deriveDeviceNames(rows), [rows]);
  const langs = useMemo(() => uniqueSorted(rows.map((r) => r.language)), [rows]);
  const platforms = useMemo(() => uniqueSorted(rows.map((r) => r.platform)), [rows]);
  const browsers = useMemo(() => uniqueSorted(rows.map((r) => r.browser)), [rows]);
  const devices = useMemo(
    () => Array.from(new Set(deviceNames.values())).sort(),
    [deviceNames]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rk = (r: LogRow) => (r.rating === 1 ? "up" : r.rating === -1 ? "down" : "none");
    return rows.filter((r) => {
      if (fLangs.length && !fLangs.includes(r.language || "Unknown")) return false;
      if (fPlatforms.length && !fPlatforms.includes(r.platform || "Unknown")) return false;
      if (fBrowsers.length && !fBrowsers.includes(r.browser || "Unknown")) return false;
      if (fDevices.length && !fDevices.includes(deviceNames.get(r.client_id || "unknown") || "")) return false;
      if (fRatings.length && !fRatings.includes(rk(r))) return false;
      if (fModes.length && !fModes.includes(r.mode || "unknown")) return false;
      if (dateStart || dateEnd) {
        const d = (r.created_at || "").slice(0, 10);
        const lo = dateStart && dateEnd ? (dateStart < dateEnd ? dateStart : dateEnd) : (dateStart || dateEnd);
        const hi = dateStart && dateEnd ? (dateStart < dateEnd ? dateEnd : dateStart) : (dateStart || dateEnd);
        if (lo && d < lo) return false;
        if (hi && d > hi) return false;
      }
      if (q && !(`${r.question || ""}`.toLowerCase().includes(q) || `${r.answer || ""}`.toLowerCase().includes(q) || `${r.corrected_question || ""}`.toLowerCase().includes(q)))
        return false;
      return true;
    });
  }, [rows, search, fLangs, fPlatforms, fBrowsers, fDevices, fRatings, fModes, dateStart, dateEnd, deviceNames]);

  const stats = useMemo(() => {
    const up = rows.filter((r) => r.rating === 1).length;
    const down = rows.filter((r) => r.rating === -1).length;
    const voice = rows.filter((r) => r.mode === "voice").length;
    const text = rows.filter((r) => r.mode === "text").length;
    const corrected = rows.filter((r) => r.corrected_question && r.corrected_question !== r.question).length;
    return {
      total: rows.length,
      devices: new Set(rows.map((r) => r.client_id || "unknown")).size,
      up, down, voice, text, corrected,
      byLang: countBy(rows, (r) => r.language || "Unknown").slice(0, 8),
      byPlatform: countBy(rows, (r) => r.platform || "Unknown"),
      byBrowser: countBy(rows, (r) => r.browser || "Unknown"),
    };
  }, [rows]);

  function resetFilters() {
    setSearch(""); setFLangs([]); setFPlatforms([]); setFBrowsers([]); setFRatings([]); setFDevices([]); setFModes([]);
    setDateStart(""); setDateEnd("");
    setPage(0);
  }
  function toggleIn(setter: (updater: (prev: string[]) => string[]) => void, v: string) {
    setter((prev) => (prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v]));
    setPage(0);
  }

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const paged = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  function exportCsv() {
    const esc = (s: string) => `"${String(s ?? "").replace(/"/g, '""')}"`;
    const header = ["time", "device", "platform", "browser", "language", "rating", "question", "answer"];
    const lines = [header.join(",")];
    for (const r of filtered) {
      const rating = r.rating === 1 ? "up" : r.rating === -1 ? "down" : "";
      lines.push([
        esc(r.created_at),
        esc(deviceNames.get(r.client_id || "unknown") || ""),
        esc(r.platform || ""),
        esc(r.browser || ""),
        esc(r.language || ""),
        esc(rating),
        esc(r.question || ""),
        esc(r.answer || ""),
      ].join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ask-the-eagle-logs-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const fmt = (iso: string) => {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  };

  // Render client-only: until mounted, emit just the shell so the server HTML
  // can't mismatch what the browser (or a password-manager extension) produces.
  if (!mounted) {
    return <div className="dash-wrap"><Style /></div>;
  }

  // ── login gate ──
  if (!authed) {
    return (
      <div className="dash-wrap dash-center">
        <Style />
        <form className="dash-login" onSubmit={submit}>
          <div className="dash-logo-badge">
            <img className="dash-logo dash-logo-e-light" src="/eLight.png" alt="Ask the Eagle" />
            <img className="dash-logo dash-logo-e-dark" src="/eDark.png" alt="Ask the Eagle" />
          </div>
          <h1>Ask the Eagle</h1>
          <p className="dash-dim dash-login-sub">Usage dashboard — admin access</p>
          <div className="dash-pw">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              autoFocus
            />
          </div>
          <button type="submit" disabled={loading || !password.trim()}>
            {loading ? "Checking…" : "Unlock"}
          </button>
          {error && <p className="dash-error">{error}</p>}
        </form>
      </div>
    );
  }

  // ── dashboard ──
  return (
    <div className="dash-wrap">
      <Style />
      <Link href="/" className="dash-back dash-back-fixed"><BackArrow />Back to website</Link>
      <div className="dash-toggle-fixed">
        <button type="button" className="theme-toggle" onClick={toggleTheme} aria-label="Toggle light/dark">
          <span className="theme-thumb">{theme === "dark" ? <MoonIcon /> : <SunIcon />}</span>
        </button>
        <button className="dash-btn dash-btn-ghost" onClick={() => load(password)} disabled={loading}>
          {loading ? "…" : "Refresh"}
        </button>
        <button className="dash-btn dash-btn-ghost" onClick={exportCsv}>CSV</button>
        <button className="dash-btn dash-btn-danger" onClick={logout}>Log out</button>
      </div>
      <header className="dash-head">
        <div className="dash-head-left">
          <div>
            <h1>Ask the Eagle — Data</h1>
          </div>
        </div>
      </header>

      <section className="dash-cards">
        <div className="dash-kpis">
          <div className="dash-card"><span className="dash-num">{stats.total.toLocaleString()}</span><span className="dash-label">Questions</span></div>
          <div className="dash-card"><span className="dash-num">{stats.devices}</span><span className="dash-label">Devices</span></div>
          <div className="dash-card"><span className="dash-num dash-up">{stats.up}</span><span className="dash-label dash-label-ico"><ThumbUp /> Helpful</span></div>
          <div className="dash-card"><span className="dash-num dash-down">{stats.down}</span><span className="dash-label dash-label-ico"><ThumbDown /> Not helpful</span></div>
          <div className="dash-card"><span className="dash-num">{stats.voice}<span className="dash-split">/{stats.text}</span></span><span className="dash-label">Voice / Text</span></div>
        </div>
        <div className="dash-wides">
          <div className="dash-card dash-card-wide">
            <span className="dash-label">Top languages</span>
            <div className="dash-chips">
              {stats.byLang.map(([k, n]) => <span key={k} className="dash-chip">{k} <b>{n}</b></span>)}
            </div>
          </div>
          <div className="dash-card dash-card-wide">
            <span className="dash-label">Platforms</span>
            <div className="dash-chips">
              {stats.byPlatform.map(([k, n]) => <span key={k} className="dash-chip">{k} <b>{n}</b></span>)}
            </div>
          </div>
          <div className="dash-card dash-card-wide">
            <span className="dash-label">Browsers</span>
            <div className="dash-chips">
              {stats.byBrowser.map(([k, n]) => <span key={k} className="dash-chip dash-chip-alt">{k} <b>{n}</b></span>)}
            </div>
          </div>
        </div>
      </section>

      <div className="dash-tabs">
        <button className={tab === "logs" ? "on" : ""} onClick={() => setTab("logs")}>Questions ({rows.length})</button>
        <button className={tab === "issues" ? "on" : ""} onClick={() => setTab("issues")}>Reports ({issues.length})</button>
      </div>

      {tab === "logs" && (
        <>
          <section className="dash-filters">
            <input className="dash-search" placeholder="Search question or answer…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} />
            <DateRangeFilter start={dateStart} end={dateEnd} onChange={(s, e) => { setDateStart(s); setDateEnd(e); setPage(0); }} />
            <MultiFilter title="Devices" options={devices} selected={fDevices} onToggle={(v) => toggleIn(setFDevices, v)} />
            <MultiFilter title="Platforms" options={platforms} selected={fPlatforms} onToggle={(v) => toggleIn(setFPlatforms, v)} />
            <MultiFilter title="Browsers" options={browsers} selected={fBrowsers} onToggle={(v) => toggleIn(setFBrowsers, v)} />
            <MultiFilter title="Languages" options={langs} selected={fLangs} onToggle={(v) => toggleIn(setFLangs, v)} />
            <MultiFilter title="Rating" options={["up", "down", "none"]} selected={fRatings} onToggle={(v) => toggleIn(setFRatings, v)} />
            <MultiFilter title="Type" options={["voice", "text"]} selected={fModes} onToggle={(v) => toggleIn(setFModes, v)} />
            <span className="dash-dim dash-count">{filtered.length} shown</span>
          </section>

          {(() => {
            const chips: { label: string; clear: () => void }[] = [];
            if (search) chips.push({ label: `Search: "${search}"`, clear: () => { setSearch(""); setPage(0); } });
            fDevices.forEach((v) => chips.push({ label: `Device: ${v}`, clear: () => toggleIn(setFDevices, v) }));
            fPlatforms.forEach((v) => chips.push({ label: `Platform: ${v}`, clear: () => toggleIn(setFPlatforms, v) }));
            fBrowsers.forEach((v) => chips.push({ label: `Browser: ${v}`, clear: () => toggleIn(setFBrowsers, v) }));
            fLangs.forEach((v) => chips.push({ label: `Lang: ${v}`, clear: () => toggleIn(setFLangs, v) }));
            fRatings.forEach((v) => chips.push({ label: `Rating: ${v}`, clear: () => toggleIn(setFRatings, v) }));
            fModes.forEach((v) => chips.push({ label: `Type: ${v}`, clear: () => toggleIn(setFModes, v) }));
            if (dateStart) chips.push({ label: `Dates: ${fmtDay(dateStart)}${dateEnd && dateEnd !== dateStart ? " → " + fmtDay(dateEnd) : ""}`, clear: () => { setDateStart(""); setDateEnd(""); setPage(0); } });
            if (chips.length === 0) return null;
            return (
              <div className="dash-active-filters">
                <span className="dash-dim">Active:</span>
                {chips.map((f, i) => (
                  <button key={i} className="dash-fchip" onClick={f.clear}>{f.label} ✕</button>
                ))}
                <button className="dash-fchip dash-fchip-clear" onClick={resetFilters}>Clear all</button>
              </div>
            );
          })()}

          <div className="dash-tablewrap">
            <table className="dash-table">
              <thead>
                <tr><th>Time</th><th>Device</th><th>Browser</th><th>Lang</th><th>Rate</th><th>Question</th></tr>
              </thead>
              <tbody>
                {paged.map((r, i) => {
                  const gIdx = safePage * PAGE_SIZE + i;
                  return (
                  <Fragment key={gIdx}>
                    <tr className="dash-row" onClick={() => setExpanded(expanded === gIdx ? null : gIdx)}>
                      <td className="dash-nowrap dash-dim">{fmt(r.created_at)}</td>
                      <td className="dash-nowrap">{deviceNames.get(r.client_id || "unknown") || "—"}</td>
                      <td className="dash-nowrap dash-dim">{r.browser || "—"}</td>
                      <td className="dash-nowrap">{r.language || "—"}</td>
                      <td className="dash-nowrap">{r.rating === 1 ? <span className="dash-up"><ThumbUp /></span> : r.rating === -1 ? <span className="dash-down"><ThumbDown /></span> : ""}</td>
                      <td className="dash-q">{r.question}</td>
                    </tr>
                    {expanded === gIdx && (
                      <tr className="dash-detail">
                        <td colSpan={6}>
                          <div><b>Q:</b> {r.question}</div>
                          {r.corrected_question && <div><b>Corrected:</b> {r.corrected_question}</div>}
                          <div><b>A:</b> {r.answer}</div>
                          <div className="dash-dim dash-meta">{r.mode || "?"} · {r.platform || "?"} · {r.browser || "?"} · {r.language} · {fmt(r.created_at)}</div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                  );
                })}
                {filtered.length === 0 && <tr><td colSpan={6} className="dash-empty">No matching questions.</td></tr>}
              </tbody>
            </table>
          </div>
          {pageCount > 1 && (
            <div className="dash-pager">
              <button className="dash-page-btn" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={safePage === 0}>‹</button>
              {pageList(safePage, pageCount).map((it, k) =>
                it === "…" ? (
                  <span key={`gap-${k}`} className="dash-page-gap">…</span>
                ) : (
                  <button key={it} className={`dash-page-btn${it - 1 === safePage ? " on" : ""}`} onClick={() => setPage(it - 1)}>{it}</button>
                )
              )}
              <button className="dash-page-btn" onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))} disabled={safePage >= pageCount - 1}>›</button>
            </div>
          )}
        </>
      )}

      {tab === "issues" && (
        <div className="dash-tablewrap">
          <table className="dash-table">
            <thead><tr><th>Time</th><th>Device</th><th>Platform</th><th>Browser</th><th>Type</th><th>Report</th></tr></thead>
            <tbody>
              {issues.map((r, i) => (
                <tr key={i}>
                  <td className="dash-nowrap dash-dim">{fmt(r.created_at)}</td>
                  <td className="dash-nowrap">{deviceNames.get(r.client_id || "unknown") || "—"}</td>
                  <td className="dash-nowrap dash-dim">{r.platform || "—"}</td>
                  <td className="dash-nowrap dash-dim">{r.browser || "—"}</td>
                  <td className="dash-nowrap dash-dim">{r.mode || "—"}</td>
                  <td>{r.description}</td>
                </tr>
              ))}
              {issues.length === 0 && <tr><td colSpan={6} className="dash-empty">No reports yet.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Style() {
  return (
    <style>{`
      .dash-wrap { max-width: 1100px; margin: 0 auto; padding: 64px 18px 80px; min-height: 100vh; color: var(--text);
        font-family: var(--font-space-mono), ui-monospace, SFMono-Regular, Menlo, "Courier New", monospace; }
      .dash-center { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; }

      .dash-back { display: inline-flex; align-items: center; gap: 6px; text-decoration: none; color: var(--text-dim);
        font-size: 13.5px; font-weight: 500; letter-spacing: .02em; background: var(--panel);
        border: 1px solid var(--panel-brd); border-radius: 999px; padding: 9px 16px; width: fit-content;
        backdrop-filter: blur(8px); transition: color .2s, border-color .2s, background .2s, transform .15s; }
      .dash-back svg { display: block; flex-shrink: 0; }
      .dash-back:hover { color: var(--text); border-color: var(--accent); transform: translateX(-2px); }
      .dash-back-fixed { position: fixed; top: 20px; left: 20px; z-index: 50; }
      .dash-toggle-fixed { position: fixed; top: 20px; right: 20px; z-index: 50; display: flex; align-items: center; gap: 8px; }

      .dash-login { background: var(--panel); border: 1px solid var(--panel-brd); border-radius: 18px; padding: 34px 30px;
        width: 340px; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 12px;
        backdrop-filter: blur(14px); box-shadow: 0 24px 70px rgba(0,0,0,.22); }
      .dash-login h1 { font-size: 22px; margin: 6px 0 0; letter-spacing: .5px; color: var(--text); }
      .dash-login-sub { margin: 0 0 4px; font-size: 13px; }
      .dash-logo-badge { display: flex; align-items: center; justify-content: center; }
      .dash-logo { width: 76px; height: 76px; object-fit: contain; }
      /* light default shows edark (dark glyph); dark mode shows elight (light glyph) */
      .dash-logo-e-light { display: none; } .dash-logo-e-dark { display: block; }
      :root[data-theme="dark"] .dash-logo-e-light { display: block; }
      :root[data-theme="dark"] .dash-logo-e-dark { display: none; }

      .dash-pw { display: flex; align-items: center; gap: 8px; width: 100%; background: var(--bg);
        border: 1px solid var(--panel-brd); border-radius: 8px; padding: 0 11px; color: var(--text-dim); }
      .dash-pw input { flex: 1; background: transparent; border: none; color: var(--text); padding: 11px 0; font: inherit; outline: none; }
      .dash-pw:focus-within { border-color: var(--accent); color: var(--accent); }
      .dash-pw input:-webkit-autofill, .dash-pw input:-webkit-autofill:hover, .dash-pw input:-webkit-autofill:focus {
        -webkit-text-fill-color: var(--text); -webkit-box-shadow: 0 0 0 1000px var(--bg) inset;
        box-shadow: 0 0 0 1000px var(--bg) inset; caret-color: var(--text); transition: background-color 9999s ease-in-out 0s; }

      .dash-search, select { background: var(--bg); border: 1px solid var(--panel-brd); color: var(--text);
        border-radius: 8px; padding: 9px 11px; font: inherit; }
      .dash-login button, .dash-btn { background: var(--accent); color: var(--cta-ink); border: none; border-radius: 8px;
        padding: 9px 14px; font: inherit; font-weight: 700; cursor: pointer; }
      .dash-login button { width: 100%; }
      .dash-btn-ghost { background: transparent; color: var(--text); border: 1px solid var(--panel-brd); font-weight: 400; }
      .dash-btn-danger { background: #e5534b; color: #fff; border: 1px solid #e5534b; font-weight: 700; }
      .dash-btn-danger:hover { background: #d0463e; border-color: #d0463e; }
      .dash-login button:disabled { opacity: .5; cursor: default; }
      .dash-error { color: #e5534b; font-size: 13px; margin: 0; }
      .dash-dim { color: var(--text-dim); }

      .dash-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }
      .dash-head-left { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }
      .dash-head h1 { font-size: 20px; margin: 0 0 2px; }
      .dash-head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
      .dash-cards { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; align-items: flex-start; }
      .dash-kpis { display: flex; flex-direction: column; gap: 10px; flex: 1 1 190px; }
      .dash-wides { display: flex; flex-wrap: wrap; gap: 10px; flex: 3 1 340px; align-content: flex-start; }
      .dash-card { background: var(--panel); border: 1px solid var(--panel-brd); border-radius: 12px; padding: 14px 16px; display: flex; flex-direction: row; align-items: center; gap: 12px; }
      .dash-card-wide { min-width: 180px; flex: 1 1 180px; flex-direction: column; align-items: flex-start; gap: 6px; }
      .dash-num { font-size: 24px; font-weight: 700; line-height: 1; flex-shrink: 0; }
      .dash-split { color: var(--text-dim); font-weight: 700; }
      .dash-label-ico { display: inline-flex; align-items: center; gap: 5px; }
      .dash-label-ico svg { flex-shrink: 0; }
      .dash-up { color: var(--accent); } .dash-down { color: #e5534b; }
      .dash-label { font-size: 12px; color: var(--text-dim); }
      .dash-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
      .dash-chip { background: var(--bg); border: 1px solid var(--panel-brd); border-radius: 999px; padding: 3px 9px; font-size: 12px; }
      .dash-chip b { color: var(--accent); } .dash-chip-alt b { color: var(--accent-2); }
      .dash-tabs { display: flex; gap: 6px; margin-bottom: 12px; }
      .dash-tabs button { background: transparent; border: 1px solid var(--panel-brd); color: var(--text-dim); border-radius: 8px; padding: 7px 14px; font: inherit; cursor: pointer; }
      .dash-tabs button.on { color: var(--text); border-color: var(--accent); }
      .dash-filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
      .dash-mf { position: relative; }
      .dash-mf-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--bg); border: 1px solid var(--panel-brd);
        color: var(--text); border-radius: 8px; padding: 9px 11px; font: inherit; cursor: pointer; }
      .dash-mf-btn:hover { border-color: var(--accent); }
      .dash-mf-btn.on { border-color: var(--accent); color: var(--accent); }
      .dash-mf-caret { font-size: 10px; color: var(--text-dim); }
      .dash-mf-panel { position: absolute; z-index: 30; top: calc(100% + 4px); left: 0; min-width: 180px; max-height: 260px;
        overflow-y: auto; background: var(--panel); border: 1px solid var(--panel-brd); border-radius: 10px; padding: 6px;
        display: flex; flex-direction: column; gap: 2px; box-shadow: 0 14px 34px rgba(0,0,0,.28); backdrop-filter: blur(14px); }
      .dash-mf-opt { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 13px; }
      .dash-mf-opt:hover { background: var(--bg); }
      .dash-mf-opt input { accent-color: var(--accent); width: 15px; height: 15px; cursor: pointer; flex-shrink: 0; }
      .dash-mf-empty { padding: 8px; color: var(--text-dim); font-size: 12px; }
      .dash-cal-panel { min-width: 258px; max-height: none; overflow: visible; }
      .dash-cal-head { display: flex; flex-direction: column; gap: 5px; padding: 0 2px 8px; }
      .dash-cal-row { display: flex; align-items: center; gap: 6px; }
      .dash-cal-arrow { background: transparent; border: 1px solid var(--panel-brd); color: var(--text); border-radius: 6px; width: 30px; height: 28px; cursor: pointer; font-size: 15px; line-height: 1; flex-shrink: 0; }
      .dash-cal-arrow:hover:not(:disabled) { border-color: var(--accent); }
      .dash-cal-arrow:disabled { opacity: .3; cursor: default; }
      .dash-cal-lbl { flex: 1; text-align: center; font-size: 14px; font-weight: 700; }
      .dash-cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }
      .dash-cal-wd { font-size: 10px; color: var(--text-dim); text-align: center; padding: 2px 0; }
      .dash-cal-day { background: transparent; border: none; color: var(--text); border-radius: 6px; height: 28px; cursor: pointer; font: inherit; font-size: 12px; }
      .dash-cal-day:hover { background: var(--bg); }
      .dash-cal-day.in { background: var(--accent-soft, rgba(15,155,99,.16)); }
      .dash-cal-day.sel { background: var(--accent); color: var(--cta-ink); font-weight: 700; }
      .dash-cal-foot { display: flex; justify-content: space-between; gap: 6px; margin-top: 8px; }
      .dash-active-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: -2px 0 14px; font-size: 12px; }
      .dash-fchip { display: inline-flex; align-items: center; gap: 6px; background: var(--panel); border: 1px solid var(--panel-brd);
        color: var(--text); border-radius: 999px; padding: 4px 11px; font: inherit; font-size: 12px; cursor: pointer; }
      .dash-fchip:hover { border-color: var(--accent); }
      .dash-fchip-clear { color: #e5534b; border-color: rgba(229,83,75,.4); }
      .dash-fchip-clear:hover { border-color: #e5534b; }
      .dash-search { flex: 1; min-width: 180px; }
      .dash-count { margin-left: auto; font-size: 13px; }
      .dash-tablewrap { overflow-x: auto; border: 1px solid var(--panel-brd); border-radius: 12px; }
      .dash-table { width: 100%; border-collapse: collapse; font-size: 13px; }
      .dash-table th { text-align: left; padding: 10px 12px; background: var(--panel); color: var(--text-dim); font-weight: 400; position: sticky; top: 0; border-bottom: 1px solid var(--panel-brd); }
      .dash-table td { padding: 9px 12px; border-bottom: 1px solid var(--panel-brd); vertical-align: top; }
      .dash-row { cursor: pointer; } .dash-row:hover td { background: var(--panel); }
      .dash-nowrap { white-space: nowrap; }
      .dash-q { max-width: 480px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .dash-detail td { background: var(--bg); }
      .dash-detail div { margin: 3px 0; line-height: 1.5; }
      .dash-meta { font-size: 12px; margin-top: 6px; }
      .dash-empty { text-align: center; color: var(--text-dim); padding: 28px; }
      .dash-pager { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
      .dash-page-btn { min-width: 34px; height: 34px; padding: 0 10px; background: var(--panel); border: 1px solid var(--panel-brd);
        color: var(--text); border-radius: 8px; cursor: pointer; font: inherit; font-size: 13px; }
      .dash-page-btn:hover:not(:disabled) { border-color: var(--accent); }
      .dash-page-btn.on { background: var(--accent); color: var(--cta-ink); border-color: var(--accent); font-weight: 700; }
      .dash-page-btn:disabled { opacity: .4; cursor: default; }
      .dash-page-gap { min-width: 20px; text-align: center; color: var(--text-dim); user-select: none; }
    `}</style>
  );
}