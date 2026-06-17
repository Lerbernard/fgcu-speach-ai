import type { Metadata } from "next";
import { Space_Mono } from "next/font/google";
import "./globals.css";

// Space Mono for the display wordmark (blocky, techy, minimal). It's self-hosted
// by next/font (no external request, no layout shift). Only the Latin 400/700
// weights we use are bundled; non-Latin titles fall back to the system monospace.
const spaceMono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-space-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Ask the Eagle : FGCU Engineering Assistant",
  description:
    "A multilingual voice assistant for the U.A. Whitaker College of Engineering at Florida Gulf Coast University. Ask about courses, faculty, advising, and campus life in your language.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={spaceMono.variable}>
      <body>{children}</body>
    </html>
  );
}