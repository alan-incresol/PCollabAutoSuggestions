"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  suggestPR,
  searchPR,
  fetchAppConfig,
  type SearchResponse,
  type FieldConfig,
} from "@/lib/api";

function getPath(obj: unknown, path: string[]): unknown {
  let cur: unknown = obj;
  for (const p of path) {
    if (Array.isArray(cur)) {
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

function summaryLine(doc: Record<string, unknown>, fields: FieldConfig[]): string {
  const parts: string[] = [];
  for (const field of fields.slice(0, 3)) {
    const val = getPath(doc, field.path.split("."));
    if (val != null && String(val).trim() !== "") {
      parts.push(`${field.label}: ${String(val)}`);
    }
  }
  return parts.length ? parts.join(" · ") : "Document";
}

export default function Home() {
  const [fieldOptions, setFieldOptions] = useState<FieldConfig[]>([]);
  const [collectionName, setCollectionName] = useState("");
  const [requiresOrgOpuId, setRequiresOrgOpuId] = useState(true);
  const [configLoading, setConfigLoading] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);
  const [orgId, setOrgId] = useState("");
  const [orgOpuId, setOrgOpuId] = useState("");
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
  const searchFields = useMemo(() => Array.from(selected), [selected]);
  const filtersReady =
    orgId.trim() !== "" && (!requiresOrgOpuId || orgOpuId.trim() !== "");

  const collectionNameRef = useRef("");

  const applyConfig = useCallback((config: Awaited<ReturnType<typeof fetchAppConfig>>) => {
    const collectionChanged =
      collectionNameRef.current !== "" &&
      collectionNameRef.current !== config.collectionName;
    collectionNameRef.current = config.collectionName;
    setFieldOptions(config.fields);
    setCollectionName(config.collectionName);
    setRequiresOrgOpuId(config.requiresOrgOpuId);
    if (collectionChanged) {
      setOrgOpuId("");
      setSelected(new Set());
      setQuery("");
      setResult(null);
      setConfirmedQuery(null);
      setSuggestions([]);
      setError(null);
    }
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    let active = true;

    const loadConfig = (initial: boolean) => {
      if (initial) {
        setConfigLoading(true);
        setConfigError(null);
      }
      fetchAppConfig({ signal: ac.signal })
        .then((config) => {
          if (!active) return;
          applyConfig(config);
          setConfigError(null);
        })
        .catch((e) => {
          if (ac.signal.aborted || !active) return;
          if (initial) {
            setFieldOptions([]);
            setCollectionName("");
            collectionNameRef.current = "";
            setRequiresOrgOpuId(true);
          }
          setConfigError(e instanceof Error ? e.message : "Failed to load config");
        })
        .finally(() => {
          if (active && initial) setConfigLoading(false);
        });
    };

    const refreshConfig = () => {
      if (document.visibilityState === "visible") loadConfig(false);
    };

    loadConfig(true);
    document.addEventListener("visibilitychange", refreshConfig);
    window.addEventListener("focus", refreshConfig);
    return () => {
      active = false;
      ac.abort();
      document.removeEventListener("visibilitychange", refreshConfig);
      window.removeEventListener("focus", refreshConfig);
    };
  }, [applyConfig]);

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

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    suggestAbortRef.current?.abort();

    if (confirmedQuery || !query.trim() || !filtersReady) {
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
        const data = await suggestPR(
          query.trim(),
          searchFields,
          orgId.trim(),
          requiresOrgOpuId ? orgOpuId.trim() : undefined,
          { signal: ac.signal },
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
  }, [query, searchFields, filtersReady, confirmedQuery, orgId, orgOpuId, requiresOrgOpuId]);

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
        const data = await searchPR(
          value,
          searchFields,
          orgId.trim(),
          requiresOrgOpuId ? orgOpuId.trim() : undefined,
          { signal: ac.signal },
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
    [searchFields, orgId, orgOpuId, requiresOrgOpuId],
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
          Atlas Search AutoSuggestions
        </h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Atlas Search autocomplete on{" "}
          <code className="rounded bg-[var(--surface)] px-1 py-0.5 text-xs">
            {configLoading ? "…" : collectionName || "unknown collection"}
          </code>
        </p>
      </header>

      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5 shadow-sm">
        {/* Step 1: Org filters */}
        <fieldset>
          <legend className="text-sm font-medium text-[var(--muted)]">
            1. Organisation filters
          </legend>
          <div className={`mt-3 grid grid-cols-1 gap-3 ${requiresOrgOpuId ? "sm:grid-cols-2" : ""}`}>
            <div>
              <label className="mb-1 block text-xs text-[var(--muted)]">Org ID</label>
              <input
                type="text"
                value={orgId}
                onChange={(e) => {
                  setOrgId(e.target.value);
                  setResult(null);
                  setConfirmedQuery(null);
                }}
                placeholder="Enter orgId"
                className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none ring-[var(--accent)] placeholder:text-[var(--muted)] focus:ring-2"
              />
            </div>
            {requiresOrgOpuId && (
              <div>
                <label className="mb-1 block text-xs text-[var(--muted)]">Org OPU ID</label>
                <input
                  type="text"
                  value={orgOpuId}
                  onChange={(e) => {
                    setOrgOpuId(e.target.value);
                    setResult(null);
                    setConfirmedQuery(null);
                  }}
                  placeholder="Enter orgOpuId"
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none ring-[var(--accent)] placeholder:text-[var(--muted)] focus:ring-2"
                />
              </div>
            )}
          </div>
        </fieldset>

        {/* Step 2: Field selection */}
        <fieldset className="mt-5">
          <legend className="text-sm font-medium text-[var(--muted)]">
            2. Choose fields to search in{" "}
            <span className="font-normal">(optional — searches all fields if none selected)</span>
          </legend>
          <div className="mt-3 flex flex-wrap gap-2">
            {configLoading && (
              <p className="text-sm text-[var(--muted)]">Loading fields…</p>
            )}
            {!configLoading && fieldOptions.length === 0 && (
              <p className="text-sm text-[var(--muted)]">No searchable fields configured.</p>
            )}
            {fieldOptions.map((f) => {
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

        {/* Step 3: Search input */}
        <div className="mt-5">
          <label className="block text-sm font-medium text-[var(--muted)]">
            3. Search
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
              disabled={!filtersReady || configLoading || !!configError}
              placeholder={
                configLoading
                  ? "Loading collection config…"
                  : configError
                    ? "Fix backend config to search"
                    : !filtersReady
                  ? requiresOrgOpuId
                    ? "Enter orgId and orgOpuId above first"
                    : "Enter orgId above first"
                  : fieldsSelected
                    ? "Start typing…"
                    : "Start typing… (searching all fields)"
              }
              autoComplete="off"
              className={`w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-[var(--foreground)] outline-none ring-[var(--accent)] placeholder:text-[var(--muted)] focus:ring-2 ${
                !filtersReady || configLoading || !!configError
                  ? "cursor-not-allowed opacity-50"
                  : ""
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
            suggestions.length > 0 && (
              <span>{suggestions.length} suggestion{suggestions.length === 1 ? "" : "s"}</span>
            )}
        </div>
      </section>

      {(error || configError) && (
        <p className="mt-4 rounded-md border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-200">
          {error || configError}
        </p>
      )}

      {result && result.documents.length > 0 && (
        <ul className="mt-6 space-y-3">
          {result.documents.map((doc, i) => (
            <li
              key={i}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <p className="text-sm font-medium text-[var(--foreground)]">
                {summaryLine(doc, fieldOptions)}
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
