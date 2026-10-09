"use client";

export default function AppError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <section className="route-state" role="alert">
      <p className="eyebrow">Attention unavailable</p>
      <h1>The interface could not be rendered.</h1>
      <p>Retry the page. If the problem continues, verify the local API and release integrity.</p>
      <button className="button" onClick={reset}>Try again</button>
    </section>
  );
}
