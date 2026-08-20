"use client";

/**
 * Last-resort boundary: an error thrown by the root layout itself, which
 * replaces the layout entirely. `globals.css` is imported by that layout, so
 * none of it is loaded here — the palette below is inline on purpose, and the
 * hex values are the same ink/chalk/ash/dist tokens from tailwind.config.ts.
 */
export default function GlobalError({
  error, reset,
}: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0, minHeight: "100vh", display: "flex", alignItems: "center",
          justifyContent: "center", background: "#080C10", color: "#E7EEF5",
          fontFamily: "ui-monospace, monospace", padding: "1rem",
        }}
      >
        <div
          style={{
            maxWidth: "34rem", width: "100%", border: "1px solid rgba(255,107,107,0.4)",
            background: "rgba(255,107,107,0.05)", borderRadius: 4, padding: "1.5rem",
          }}
        >
          <div style={{
            fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.18em",
            color: "#FF6B6B", marginBottom: "0.75rem",
          }}>
            QuantDesk failed to start
          </div>
          <p style={{ fontSize: "0.875rem", lineHeight: 1.6, color: "rgba(231,238,245,0.8)", margin: 0 }}>
            The application shell itself could not render. Reloading is safe — nothing is stored
            between sessions.
          </p>
          {error.digest && (
            <p style={{ fontSize: "0.7rem", color: "#7A8CA0", marginTop: "0.75rem" }}>
              Reference: {error.digest}
            </p>
          )}
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: "1.25rem", height: "2.25rem", padding: "0 1rem", borderRadius: 4,
              border: "1px solid rgba(91,141,239,0.5)", background: "rgba(91,141,239,0.1)",
              color: "#E7EEF5", font: "inherit", fontSize: "0.65rem",
              textTransform: "uppercase", letterSpacing: "0.14em", cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
