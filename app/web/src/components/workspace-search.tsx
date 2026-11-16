"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { notesApi, type LiveNote } from "@/lib/notes-api";
import { Icon } from "./ui";

export function WorkspaceSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<LiveNote[]>([]);
  const [focused, setFocused] = useState(false);
  const [selected, setSelected] = useState(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const wrapper = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let active = true;
    setResults([]);
    setSelected(0);
    setError("");
    setPending(!!query.trim());
    if (!query.trim()) return;
    const timer = setTimeout(() => {
      void notesApi
        .search(query.trim())
        .then((response) => {
          if (active) setResults(response.notes.slice(0, 6));
        })
        .catch((e) => {
          if (active)
            setError(e instanceof Error ? e.message : "Search is unavailable.");
        })
        .finally(() => {
          if (active) setPending(false);
        });
    }, 180);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query]);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        document.getElementById("global-search")?.focus();
      }
    };
    const outside = (event: PointerEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setFocused(false);
    };
    window.addEventListener("keydown", shortcut);
    window.addEventListener("pointerdown", outside);
    return () => {
      window.removeEventListener("keydown", shortcut);
      window.removeEventListener("pointerdown", outside);
    };
  }, []);
  function choose(index: number) {
    const note = results[index];
    if (!note || pending) return;
    setFocused(false);
    setQuery("");
    router.push(`/notes?note=${encodeURIComponent(note.slug)}`);
  }
  return (
    <div
      className="search-container"
      ref={wrapper}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node))
          setFocused(false);
      }}
    >
      <Icon name="Search" size={18} />
      <input
        id="global-search"
        role="combobox"
        aria-label="Search notes"
        autoComplete="off"
        aria-expanded={focused && !!query.trim()}
        aria-controls="workspace-search-results"
        aria-activedescendant={
          focused && results[selected]
            ? `workspace-result-${selected}`
            : undefined
        }
        placeholder="Search notes"
        value={query}
        onFocus={() => setFocused(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setFocused(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setFocused(false);
          if (["ArrowDown", "ArrowUp"].includes(event.key) && results.length) {
            event.preventDefault();
            setSelected(
              (index) =>
                (index + (event.key === "ArrowDown" ? 1 : results.length - 1)) %
                results.length,
            );
          }
          if (event.key === "Enter") {
            event.preventDefault();
            choose(selected);
          }
        }}
      />
      <kbd>⌘ K</kbd>
      {focused && !!query.trim() && (
        <div
          className="search-results"
          id="workspace-search-results"
          role="listbox"
          aria-label="Search results"
          aria-busy={pending}
        >
          {pending && (
            <p role="status" className="search-empty">
              Searching notes…
            </p>
          )}
          {error && (
            <p role="alert" className="search-empty">
              {error}
            </p>
          )}
          {!pending && !error && !results.length && (
            <p className="search-empty">No matching notes.</p>
          )}
          {results.map((note, index) => (
            <button
              key={note.slug}
              id={`workspace-result-${index}`}
              role="option"
              aria-selected={selected === index}
              className={selected === index ? "selected" : ""}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(index)}
            >
              <Icon name="FileText" size={17} />
              <span>
                <strong>{note.title || note.slug}</strong>
                <small>{note.description}</small>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
