"use client";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div style={{ padding: "2rem", fontFamily: "sans-serif" }}>
      <h2>Something went wrong</h2>
      <p style={{ color: "#666" }}>{error.message}</p>
      <button onClick={reset} style={{ marginTop: "1rem", padding: "0.5rem 1rem", cursor: "pointer" }}>
        Try again
      </button>
    </div>
  );
}
