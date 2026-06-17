"use client";

import Link from "next/link";

// Native names of the 21 supported languages, shown on the welcome page so
// visitors can see their language is covered.
const SUPPORTED = [
  "English", "Español", "Português", "Français", "Deutsch", "Italiano",
  "Русский", "Українська", "Polski", "Ελληνικά", "Nederlands", "Svenska",
  "Türkçe", "中文", "Tagalog", "हिन्दी", "தமிழ்", "한국어", "日本語",
  "العربية", "עברית",
];

export default function Welcome() {
  return (
    <main className="welcome">
      <div className="aurora" aria-hidden="true" />

      <div className="content">
        <span className="eyebrow">U.A. Whitaker College of Engineering</span>

        <h1>
          Ask the Eagle
        </h1>

        <p className="lede">
          A multilingual voice assistant for the U.A. Whitaker College of
          Engineering at Florida Gulf Coast University. Ask about courses,
          faculty, advising, and campus life, and get answers in your own
          language.
        </p>

        <ul className="features">
          <li>
            <span className="dot" />
            Speak naturally in 21 languages
          </li>
          <li>
            <span className="dot" />
            Ask about courses, professors, and advising
          </li>
          <li>
            <span className="dot" />
            Hear answers spoken back to you
          </li>
        </ul>

        <Link href="/assistant" className="cta">
          <span className="cta-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="2" width="6" height="11" rx="3" />
              <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
              <line x1="12" y1="18" x2="12" y2="22" />
              <line x1="8" y1="22" x2="16" y2="22" />
            </svg>
          </span>
          Start talking
          <span className="arrow" aria-hidden="true">→</span>
        </Link>

        <p className="hint">Works best with your microphone enabled</p>

        <div className="langs">
          <span className="langs-label">{SUPPORTED.length} languages supported</span>
          <div className="langs-list">
            {SUPPORTED.map((l) => (
              <span key={l} className="lang-chip">{l}</span>
            ))}
          </div>
        </div>
      </div>

      <footer className="foot">Florida Gulf Coast University</footer>
    </main>
  );
}