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
  title: "Ask The Eagle_",
  description:
    "A multilingual voice assistant for the U.A. Whitaker College of Engineering at Florida Gulf Coast University. Ask about courses, faculty, advising, and campus life in your language.",
  icons: { icon: "/logoForIcon.png" },
};

// Set the theme before first paint so there's no flash of the wrong mode.
// Honors a saved choice, otherwise the OS preference; defaults to dark.
const themeInit = `
(function(){try{
  var t = localStorage.getItem('eagle-theme');
  if(t!=='light' && t!=='dark'){
    t = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  document.documentElement.setAttribute('data-theme', t);
}catch(e){
  document.documentElement.setAttribute('data-theme','dark');
}})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={spaceMono.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body>{children}</body>
    </html>
  );
}