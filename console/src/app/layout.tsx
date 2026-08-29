import type { Metadata, Viewport } from "next";
import { Roboto, Roboto_Mono } from "next/font/google";
import "./globals.css";

// One family for the whole console, the one YouTube Studio sets its interface
// in. Self-hosted by next/font, so nothing is fetched from Google at runtime.
const roboto = Roboto({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-roboto",
  display: "swap",
});

// Ids, rule numbers, timestamps and the calibration lines read out of Grafana.
const robotoMono = Roboto_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-roboto-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Airlock reviewer console",
  description:
    "Four gates read a generated asset against a named source of truth, and no gate may say PASS unless Grafana can prove it is healthy and calibrated.",
};

export const viewport: Viewport = {
  themeColor: "#f9f9f9",
  colorScheme: "light",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${roboto.variable} ${robotoMono.variable}`}>
      <body>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-[3px] focus:border focus:border-accent focus:bg-surface focus:px-3 focus:py-2 focus:font-mono focus:text-[12px] focus:text-accent"
        >
          Skip to the content
        </a>
        {children}
      </body>
    </html>
  );
}
