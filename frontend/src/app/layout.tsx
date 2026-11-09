import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans_Arabic, Inter_Tight } from "next/font/google";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

// One variable file for the UI face (preloaded). Arabic and mono faces are not preloaded: they render names and
// figures only, and their metric-matched fallbacks keep layout stable while they load.
const interTight = Inter_Tight({ subsets: ["latin"], variable: "--font-inter-tight" });
const plexArabic = IBM_Plex_Sans_Arabic({ subsets: ["arabic"], weight: ["400", "500", "600"], variable: "--font-plex-arabic", preload: false });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex-mono", preload: false });

export const metadata: Metadata = {
  title: { default: "Namaa", template: "%s · Namaa" },
  description: "Satellite-informed green infrastructure management for Saudi municipalities.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f4ee" },
    { media: "(prefers-color-scheme: dark)", color: "#0e1411" },
  ],
};

// Applies a saved theme choice before first paint (no flash, no layout shift). "system" removes the attribute.
const themeScript = `try{var t=localStorage.getItem("namaa-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${interTight.variable} ${plexArabic.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
