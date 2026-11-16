"use client";
export default function Error({ reset }: { reset: () => void }) {
  return (
    <div className="empty">
      <h1>Let’s take a breath.</h1>
      <p>This page couldn’t load. Your saved demo is still in this browser.</p>
      <button className="button primary" onClick={reset}>
        Try again
      </button>
    </div>
  );
}
