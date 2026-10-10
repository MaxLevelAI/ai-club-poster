import type { Metadata, Viewport } from "next";
import "@fontsource/rajdhani/300.css";
import "@fontsource/rajdhani/500.css";
import "@fontsource/rajdhani/600.css";
import "@fontsource/share-tech-mono/400.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "JARVIS ∙ Mission Control",
  description: "Live mission control for the AI Club Instagram agent.",
  robots: { index: false, follow: false },
};
export const viewport: Viewport = { themeColor: "#01040a", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
