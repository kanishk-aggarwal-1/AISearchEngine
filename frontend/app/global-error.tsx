"use client";

export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <html>
      <body style={{ padding: "2rem", fontFamily: "sans-serif" }}>
        <h2>A critical error occurred</h2>
        <p style={{ color: "#666" }}>{error.message}</p>
        <button onClick={reset} style={{ marginTop: "1rem", padding: "0.5rem 1rem", cursor: "pointer" }}>
          Try again
        </button>
      </body>
    </html>
  );
}
