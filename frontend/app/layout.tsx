import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SignalScope AI",
  description: "AI search and explanation engine for tech, research, and sports",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
