import "./globals.css";

export const metadata = {
  title: "SignalScope AI",
  description: "AI search and explanation engine for tech, research, and sports",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
