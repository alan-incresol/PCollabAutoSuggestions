"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  suggestVendors,
  searchVendors,
  type SearchResponse,
} from "@/lib/api";

const FIELD_OPTIONS: { id: string; label: string }[] = [
  { id: "city", label: "City" },
  { id: "gstin", label: "GSTIN" },
  { id: "pointOfContactName", label: "Point of contact" },
  { id: "contactEmail", label: "Contact email" },
  { id: "vendorCode", label: "Vendor code" },
  { id: "erpSyncMsg", label: "ERP sync message" },
  { id: "companyName", label: "Company name" },
];

function getPath(obj: unknown, path: string[]): unknown {
  let cur: unknown = obj;
  for (const p of path) {
    if (Array.isArray(cur)) {
      // Walk into the first element of the array
      if (cur.length === 0) return undefined;
      cur = cur[0];
    }
    if (cur === null || cur === undefined || typeof cur !== "object") {
      return undefined;
    }
    cur = (cur as Record<string, unknown>)[p];
  }
  return cur;
}

function summaryLine(doc: Record<string, unknown>): string {
  const code = doc.vendorCode;
  const gstin = getPath(doc, [
    "vendorDetails",
    "companyOverviewDetails",
    "gstin",
  ]);
  const parts = [
    code != null ? `Code: ${String(code)}` : null,
    gstin != null ? `GSTIN: ${String(gstin)}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Document";
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [confirmedQuery, setConfirmedQuery] = useState<string | null>(null);

  const suggestAbortRef = useRef<AbortController | null>(null);
  const searchAbortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fieldsSelected = selected.size > 0;

  const toggleField = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setResult(null);
    setConfirmedQuery(null);
    setSuggestions([]);
  }, []);

  // Fetch suggestions as user types (skip when a suggestion is already confirmed)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    suggestAbortRef.current?.abort();

    if (confirmedQuery || !query.trim() || !fieldsSelected) {
      if (!confirmedQuery) {
        setSuggestions([]);
        setShowSuggestions(false);
        setLoading(false);
      }
      return;
    }

    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      const ac = new AbortController();
      suggestAbortRef.current = ac;
      try {
        const data = await suggestVendors(
          query.trim(),
          Array.from(selected),
          ac.signal,
        );
        if (!ac.signal.aborted) {
          setSuggestions(data.suggestions);
          setShowSuggestions(true);
        }
      } catch (e) {
        if (ac.signal.aborted) return;
        setSuggestions([]);
        setError(e instanceof Error ? e.message : "Suggest failed");
      } finally {
        if (!ac.signal.aborted) setLoading(false);
      }
    }, 280);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      suggestAbortRef.current?.abort();
    };
  }, [query, selected, fieldsSelected, confirmedQuery]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const selectSuggestion = useCallback(
    async (value: string) => {
      // Cancel any in-flight suggest calls first
      suggestAbortRef.current?.abort();
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }

      setQuery(value);
      setShowSuggestions(false);
      setSuggestions([]);
      setConfirmedQuery(value);
      setLoading(true);
      setError(null);

      const ac = new AbortController();
      searchAbortRef.current?.abort();
      searchAbortRef.current = ac;
      try {
        const data = await searchVendors(
          value,
          Array.from(selected),
          ac.signal,
        );
        if (!ac.signal.aborted) setResult(data);
      } catch (e) {
        if (ac.signal.aborted) return;
        setResult(null);
        setError(e instanceof Error ? e.message : "Search failed");
      } finally {
        if (!ac.signal.aborted) setLoading(false);
      }
    },
    [selected],
  );

  const clearSearch = useCallback(() => {
    setQuery("");
    setSuggestions([]);
    setShowSuggestions(false);
    setResult(null);
    setConfirmedQuery(null);
    setError(null);
    inputRef.current?.focus();
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    setResult(null);
    setConfirmedQuery(null);
    setError(null);
  };

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--foreground)]">
          AutoSuggestions
        </h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Select fields first, then type to get suggestions from Atlas Search
          autocomplete on{" "}
          <code className="rounded bg-[var(--surface)] px-1 py-0.5 text-xs">
            omOrgVendorDetails
          </code>
          .
        </p>
      </header>

      {/* Step 1: Field selection */}
      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5 shadow-sm">
        <fieldset>
          <legend className="text-sm font-medium text-[var(--muted)]">
            1. Choose fields to search in
          </legend>
          <div className="mt-3 flex flex-wrap gap-2">
            {FIELD_OPTIONS.map((f) => {
              const on = selected.has(f.id);
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => toggleField(f.id)}
                  className={`rounded-full border px-3 py-1 text-sm transition ${
                    on
                      ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--foreground)]"
                      : "border-[var(--border)] text-[var(--muted)] hover:border-[var(--muted)]"
                  }`}
                >
                  {f.label}
                </button>
              );
            })}
          </div>
        </fieldset>

        {/* Step 2: Search input (only after fields are selected) */}
        <div className="mt-5">
          <label className="block text-sm font-medium text-[var(--muted)]">
            2. Search
          </label>
          <div className="relative mt-2">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={handleInputChange}
              onFocus={() => {
                if (suggestions.length > 0 && !confirmedQuery) {
                  setShowSuggestions(true);
                }
              }}
              disabled={!fieldsSelected}
              placeholder={
                fieldsSelected
                  ? "Start typing…"
                  : "Select at least one field above"
              }
              autoComplete="off"
              className={`w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-[var(--foreground)] outline-none ring-[var(--accent)] placeholder:text-[var(--muted)] focus:ring-2 ${
                !fieldsSelected ? "cursor-not-allowed opacity-50" : ""
              }`}
            />
            {query && (
              <button
                type="button"
                onClick={clearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-[var(--muted)] hover:text-[var(--foreground)]"
              >
                &#x2715;
              </button>
            )}

            {/* Suggestions dropdown */}
            {showSuggestions && suggestions.length > 0 && !confirmedQuery && (
              <div
                ref={dropdownRef}
                className="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded-md border border-[var(--border)] bg-[var(--surface)] shadow-lg"
              >
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => selectSuggestion(s)}
                    className="w-full px-3 py-2 text-left text-sm text-[var(--foreground)] hover:bg-[var(--accent)]/10 transition"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3 text-sm text-[var(--muted)]">
          {loading && <span>Searching…</span>}
          {!loading && confirmedQuery && result && (
            <span>
              {result.count} result{result.count === 1 ? "" : "s"} for &quot;{confirmedQuery}&quot;
            </span>
          )}
          {!loading &&
            !confirmedQuery &&
            query.trim() &&
            fieldsSelected &&
            suggestions.length > 0 && (
              <span>{suggestions.length} suggestion{suggestions.length === 1 ? "" : "s"}</span>
            )}
        </div>
      </section>

      {error && (
        <p className="mt-4 rounded-md border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      )}

      {/* Documents shown only after selecting a suggestion */}
      {result && result.documents.length > 0 && (
        <ul className="mt-6 space-y-3">
          {result.documents.map((doc, i) => (
            <li
              key={i}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <p className="text-sm font-medium text-[var(--foreground)]">
                {summaryLine(doc)}
              </p>
              <pre className="mt-3 max-h-64 overflow-auto rounded bg-[var(--background)] p-3 text-xs leading-relaxed text-[var(--muted)]">
                {JSON.stringify(doc, null, 2)}
              </pre>
            </li>
          ))}
        </ul>
      )}

      {result && result.documents.length === 0 && confirmedQuery && (
        <p className="mt-6 text-sm text-[var(--muted)]">No matches.</p>
      )}
    </main>
  );
}
