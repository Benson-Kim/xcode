"use client";

export default function GlobalError() {
  return (
    <html lang="en">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          margin: 0,
          display: "grid",
          placeItems: "center",
          minHeight: "100vh",
          textAlign: "center",
        }}
      >
        <main>
          <h1>Something went wrong</h1>
          <p>The app hit an unexpected problem.</p>
          <button type="button" onClick={() => window.location.reload()}>
            Reload the app
          </button>
        </main>
      </body>
    </html>
  );
}
