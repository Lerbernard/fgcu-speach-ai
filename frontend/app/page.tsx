"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

// Native names of the 20 supported languages, shown so visitors can see their
// language is covered.
const SUPPORTED = [
  "English", "Español", "Português", "Français", "Deutsch", "Italiano",
  "Русский", "Українська", "Polski", "Ελληνικά", "Nederlands", "Svenska",
  "Türkçe", "中文", "Tagalog", "हिन्दी", "தமிழ்", "한국어", "日本語",
  "العربية",
];

// Real questions the assistant can answer, in several languages, typed out one
// at a time in the prompt. This is the page's signature: it shows what the tool
// does and that it speaks many languages, instead of describing it.
const PROMPTS = [
  "when do fall classes start?",
  "¿quién enseña COP 3003?",
  "wann beginnen die Kurse?",
  "comment contacter mon conseiller ?",
  "what engineering clubs can I join?",
  "수강 신청 마감일이 언제인가요?",
];

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

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  useEffect(() => {
    // Read the theme the no-flash script already applied. Done post-mount
    // (not in render) to avoid a hydration mismatch; the sync setState here is intentional.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(
      (document.documentElement.getAttribute("data-theme") as
        | "light"
        | "dark") || "dark"
    );
  }, []);

  function toggle() {
    // Read the live attribute so the toggle can never get out of sync with
    // what's actually applied (e.g. after navigation or a system change).
    const cur =
      document.documentElement.getAttribute("data-theme") === "light"
        ? "light"
        : "dark";
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    setTheme(next);
    try {
      localStorage.setItem("eagle-theme", next);
    } catch {
      /* storage may be unavailable; theme still applies for this session */
    }
  }

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
    >
      <span className="theme-thumb">
        {theme === "dark" ? <MoonIcon /> : <SunIcon />}
      </span>
    </button>
  );
}

export default function Welcome() {
  const [typed, setTyped] = useState("");

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      timer = setTimeout(() => setTyped(PROMPTS[0]), 0);
      return () => clearTimeout(timer);
    }
    let prompt = 0;
    let chars = 0;
    let deleting = false;

    const tick = () => {
      const full = PROMPTS[prompt];
      if (!deleting) {
        chars++;
        setTyped(full.slice(0, chars));
        if (chars === full.length) {
          deleting = true;
          timer = setTimeout(tick, 1800);
          return;
        }
      } else {
        chars--;
        setTyped(full.slice(0, chars));
        if (chars === 0) {
          deleting = false;
          prompt = (prompt + 1) % PROMPTS.length;
        }
      }
      timer = setTimeout(tick, deleting ? 34 : 68);
    };

    timer = setTimeout(tick, 600);
    return () => clearTimeout(timer);
  }, []);

  return (
    <main className="hero">
      <div className="hero-glow" aria-hidden="true" />

      <div className="hero-top">
        <span className="hero-eyebrow">U.A. Whitaker College of Engineering</span>
        <ThemeToggle />
      </div>

      <div className="hero-center">
        <div className="mark">
          {/* wordmark swaps with theme: dark ink on light, white on dark */}
          <Image
            className="wordmark wordmark-light"
            src="/logo.png"
            alt="Ask the Eagle"
            width={718}
            height={98}
            priority
            style={{ height: "auto" }}
          />
          <Image
            className="wordmark wordmark-dark"
            src="/logo_light.png"
            alt="Ask the Eagle"
            width={718}
            height={98}
            priority
            style={{ height: "auto" }}
          />
        </div>

        <p className="lede">
          A multilingual voice assistant for the U.A. Whitaker College of
          Engineering. Ask about courses, faculty, advising, and campus life, by
          voice or text, and get answers in your own language.
        </p>

        <div className="term" aria-hidden="true">
          <span className="term-tag">ask the eagle</span>
          <span className="term-sep">&#9656;</span>
          <span className="term-text">{typed}</span>
          <span className="term-caret" />
        </div>

        <Link href="/assistant" className="cta">
          <span className="cta-mic" aria-hidden="true">
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="2" width="6" height="11" rx="3" />
              <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
              <line x1="12" y1="18" x2="12" y2="22" />
              <line x1="8" y1="22" x2="16" y2="22" />
            </svg>
          </span>
          Start talking
        </Link>

        <div className="meta">
          <span><i className="meta-dot" />20 languages</span>
          <span><i className="meta-dot" />Voice or text</span>
          <span><i className="meta-dot" />Answers spoken back</span>
        </div>
      </div>

      <div className="langs">
        <span className="langs-label">{SUPPORTED.length} languages supported</span>
        <div className="langs-list">
          {SUPPORTED.map((l) => (
            <span key={l} className="lang-chip">{l}</span>
          ))}
        </div>
      </div>

      <footer className="foot">Not an official Florida Gulf Coast University website</footer>
    </main>
  );
}