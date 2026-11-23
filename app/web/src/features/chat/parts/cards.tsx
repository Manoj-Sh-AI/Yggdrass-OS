"use client";
/**
 * Rich tool outputs inside a tool card. A tool that returns `{ diff }` (a unified diff)
 * gets the diff card; one that returns `{ terminal, exit_code? }` (a command's output,
 * ANSI colours allowed) gets the terminal card, drawn by xterm.js. Everything else stays
 * the JSON block. Colours come only from the token layer: xterm's theme is read from
 * elements styled with token utilities, never from a written value.
 */
import { useEffect, useRef, useState } from "react";
import { type DiffLine, parseDiff, stripAnsi } from "./logic";

const LINE_TONE: Record<DiffLine["kind"], string> = {
  add: "bg-success-surface text-success",
  remove: "bg-danger-surface text-danger",
  hunk: "text-info",
  file: "font-semibold text-text-1",
  context: "text-text-2",
};
const LINE_MARK: Record<DiffLine["kind"], string> = {
  add: "+",
  remove: "-",
  hunk: "",
  file: "",
  context: " ",
};

export function DiffCard({ diff }: { diff: string }) {
  const lines = parseDiff(diff);
  const added = lines.filter((l) => l.kind === "add").length;
  const removed = lines.filter((l) => l.kind === "remove").length;
  return (
    <figure
      aria-label="Changes"
      className="overflow-hidden rounded-sm bg-surface-sunken"
    >
      <figcaption className="flex gap-2 px-2 py-1 text-xs text-text-2">
        <span className="text-success">+{added}</span>
        <span className="text-danger">-{removed}</span>
      </figcaption>
      <pre className="max-h-72 overflow-auto text-xs">
        {lines.map((line, i) => (
          <div
            key={i}
            data-kind={line.kind}
            className={`px-2 font-mono ${LINE_TONE[line.kind]}`}
          >
            <span aria-hidden className="mr-2 select-none text-text-3">
              {LINE_MARK[line.kind]}
            </span>
            {line.text}
          </div>
        ))}
      </pre>
    </figure>
  );
}

/** A token colour as the browser resolves it (xterm needs a colour string). */
function tokenColor(
  className: string,
  property: "color" | "backgroundColor" = "color",
): string {
  const probe = document.createElement("span");
  probe.className = className;
  probe.style.display = "none";
  document.body.appendChild(probe);
  const value = getComputedStyle(probe)[property];
  probe.remove();
  return value;
}

export function TerminalCard({
  output,
  exitCode,
}: {
  output: string;
  exitCode?: number | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    let disposed = false;
    let cleanup = () => {};
    (async () => {
      try {
        const [{ Terminal }, { FitAddon }] = await Promise.all([
          import("@xterm/xterm"),
          import("@xterm/addon-fit"),
        ]);
        await import("@xterm/xterm/css/xterm.css");
        if (disposed || !host.current) return;
        const terminal = new Terminal({
          disableStdin: true, // read-only: output of a command that already ran
          convertEol: true,
          cursorBlink: false,
          rows: Math.min(18, Math.max(3, output.split("\n").length)),
          fontSize: 12,
          theme: {
            background: tokenColor("bg-surface-sunken", "backgroundColor"),
            foreground: tokenColor("text-text-1"),
            red: tokenColor("text-danger"),
            green: tokenColor("text-success"),
            yellow: tokenColor("text-warning"),
            blue: tokenColor("text-info"),
          },
        });
        const fit = new FitAddon();
        terminal.loadAddon(fit);
        terminal.open(host.current);
        fit.fit();
        terminal.write(output);
        setDrawn(true);
        cleanup = () => terminal.dispose();
      } catch {
        setDrawn(false); // no canvas (tests, old browsers): the plain text stays
      }
    })();
    return () => {
      disposed = true;
      cleanup();
    };
  }, [output]);
  return (
    <figure
      aria-label="Terminal output"
      className="overflow-hidden rounded-sm bg-surface-sunken"
    >
      <div ref={host} className={drawn ? "p-1" : "hidden"} />
      {drawn ? null : (
        <pre className="max-h-72 overflow-auto p-2 font-mono text-xs text-text-1">
          {stripAnsi(output)}
        </pre>
      )}
      {exitCode !== undefined && exitCode !== null ? (
        <figcaption
          className={`px-2 py-1 text-xs ${exitCode === 0 ? "text-success" : "text-danger"}`}
        >
          exit {exitCode}
        </figcaption>
      ) : null}
    </figure>
  );
}
