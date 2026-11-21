"use client";
import { useEffect, useState } from "react";
import { applicationApi } from "@/lib/api";
import { Icon } from "./ui";
export function LoginForm() {
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);
  const [password, setPassword] = useState(""),
    [pending, setPending] = useState(false),
    [error, setError] = useState("");
  return (
    <main className="login-page">
      <div className="panel login-panel">
        <span className="brand-mark brand-logo">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/logo-mark.png" alt="" width={48} height={48} />
        </span>
        <span className="eyebrow">YOUR PERSONAL WORKSPACE</span>
        <h1>Welcome to Yggdress</h1>
        <p>Sign in with your personal password.</p>
        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            setPending(true);
            setError("");
            try {
              await applicationApi("auth/login", {
                method: "POST",
                body: JSON.stringify({ password }),
              });
              setPassword("");
              window.location.assign("/today");
            } catch (e) {
              setError(e instanceof Error ? e.message : "Sign-in unavailable.");
              setPending(false);
            }
          }}
        >
          <label>
            Personal password
            <input
              type="password"
              disabled={!ready}
              autoComplete="current-password"
              value={password}
              required
              maxLength={1024}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="button primary" disabled={pending || !ready}>
            {pending ? "Signing in…" : "Sign in"}
            <Icon name="ArrowRight" size={16} />
          </button>
        </form>
        <small>Make a little room for what matters.</small>
      </div>
    </main>
  );
}
