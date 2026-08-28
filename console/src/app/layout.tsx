import type { Metadata, Viewport } from "next";
import { Sora, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const sora = Sora({
  subsets: ["latin"],
  variable: "--font-sora",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Airlock reviewer console",
  description:
    "Four gates read a generated asset against a named source of truth, and no gate may say PASS unless Grafana can prove it is healthy and calibrated.",
};

export const viewport: Viewport = {
  themeColor: "#0b0c0e",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sora.variable} ${plexMono.variable}`}>
      <body>
        <a
          href="#pipeline"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-[3px] focus:border focus:border-amber focus:bg-hull focus:px-3 focus:py-2 focus:font-mono focus:text-[12px] focus:text-amber"
        >
          Skip to the pipeline
        </a>
        {children}
      </body>
    </html>
  );
}
