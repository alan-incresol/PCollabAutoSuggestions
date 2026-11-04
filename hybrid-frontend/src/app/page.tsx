"use client";

import { FormEvent, useMemo, useState } from "react";
import { matchEntity, type Candidate, type EntityType, type MatchResponse } from "@/lib/api";

type ResultView = "lucene" | "vector" | "combined" | "final";

const VIEW_OPTIONS: { id: ResultView; label: string; hint: string }[] = [
  { id: "lucene", label: "Lucene", hint: "Keyword and fuzzy hits" },
  { id: "vector", label: "Vector", hint: "Semantic similarity hits" },
  { id: "combined", label: "Combined", hint: "Fused shortlist" },
  { id: "final", label: "Final", hint: "Chosen match and confidence" },
];

function score(value: number | null, digits = 3): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function scrub(text: string): string {
  return text
    .replace(/\bjev[-\w.]*/gi, "decision model")
    .replace(/\bTYPESAFE[_\w]*/gi, "decision service");
}

export default function Home() {
  const [entityType, setEntityType] = useState<EntityType>("vendor");
  const [orgId, setOrgId] = useState("");
  const [orgOpuId, setOrgOpuId] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MatchResponse | null>(null);
  const [view, setView] = useState<ResultView>("final");

  const material = entityType === "material";
  const filtersReady = orgId.trim() !== "" && (!material || orgOpuId.trim() !== "");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!filtersReady || !query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await matchEntity(query.trim(), entityType, orgId.trim(), orgOpuId.trim());
      setResult({
        ...data,
        luceneCandidates: data.luceneCandidates ?? [],
        vectorCandidates: data.vectorCandidates ?? [],
        candidates: data.candidates ?? [],
      });
      setView("final");
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  const viewCounts = useMemo(() => {
    if (!result) return null;
    return {
      lucene: result.luceneCandidates.length,
      vector: result.vectorCandidates.length,
      combined: result.candidates.length,
      final: result.jev.accepted ? 1 : 0,
    };
  }, [result]);

  return (
    <main className="mx-auto max-w-6xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Hybrid vendor and material match</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Search once, then switch between Lucene hits, vector hits, the combined shortlist, and the
          final match with confidence.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5 shadow-sm"
      >
        <fieldset>
          <legend className="text-sm font-medium text-[var(--muted)]">1. What are you matching?</legend>
          <div className="mt-3 flex gap-2">
            {(["vendor", "material"] as const).map((kind) => (
              <button
                key={kind}
                type="button"
                onClick={() => {
                  setEntityType(kind);
                  setResult(null);
                  setError(null);
                }}
                className={`rounded-full border px-4 py-1.5 text-sm capitalize ${
                  entityType === kind
                    ? "border-[var(--accent)] bg-[var(--accent)]/15"
                    : "border-[var(--border)] text-[var(--muted)]"
                }`}
              >
                {kind}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="mt-5">
          <legend className="text-sm font-medium text-[var(--muted)]">2. Organisation</legend>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block text-xs text-[var(--muted)]">
              Org ID
              <input
                value={orgId}
                onChange={(event) => setOrgId(event.target.value)}
                placeholder="orgId"
                className="mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
            </label>
            <label className="block text-xs text-[var(--muted)]">
              Org OPU ID {material ? "" : "(not used for vendors)"}
              <input
                value={orgOpuId}
                onChange={(event) => setOrgOpuId(event.target.value)}
                placeholder={material ? "Required for materials" : "Optional, ignored for vendors"}
                className="mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
            </label>
          </div>
        </fieldset>

        <label className="mt-5 block text-sm font-medium text-[var(--muted)]">
          3. {material ? "Material description" : "Vendor name"}
          <div className="mt-2 flex gap-2">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              disabled={!filtersReady}
              placeholder={
                filtersReady
                  ? material
                    ? "e.g. maficon wire 100mm"
                    : "e.g. western engineering pvt ltd"
                  : material
                    ? "Enter orgId and orgOpuId first"
                    : "Enter orgId first"
              }
              className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-[var(--foreground)] outline-none focus:ring-2 focus:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!filtersReady || !query.trim() || loading}
              className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[#0c0f14] disabled:opacity-50"
            >
              {loading ? "Matching…" : "Search"}
            </button>
          </div>
        </label>
      </form>

      {error && (
        <p className="mt-4 rounded-md border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-200">
          {scrub(error)}
        </p>
      )}

      {result && viewCounts && (
        <section className="mt-6 space-y-4">
          <div className="space-y-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-xs text-[var(--muted)]">
            <p>
              {result.collectionName} · Lucene `{result.luceneIndex}` · vector `{result.vectorIndex}`
              {" · "}
              {result.timingMs.total ?? 0} ms · Lucene {result.timingMs.lexical ?? 0} · vector{" "}
              {result.timingMs.vector ?? 0} · final {result.timingMs.jev ?? 0}
            </p>
            <dl className="grid gap-1 sm:grid-cols-[7rem_1fr]">
              <dt className="text-[var(--muted)]">User query</dt>
              <dd className="font-mono text-[var(--foreground)]">{result.query}</dd>
              <dt className="text-[var(--muted)]">Lucene query</dt>
              <dd className="font-mono text-[var(--foreground)]">
                {result.luceneQuery || result.query}
                {result.luceneQuery && result.luceneQuery !== result.query
                  ? " · name/description fields; codes still use the user query"
                  : ""}
              </dd>
              <dt className="text-[var(--muted)]">Vector query</dt>
              <dd className="font-mono text-[var(--foreground)]">
                {result.vectorQuery || result.normalizedQuery || result.query}
              </dd>
            </dl>
          </div>

          {result.retrievalErrors.length > 0 && (
            <div className="rounded-md border border-amber-900/50 bg-amber-950/30 px-3 py-2 text-sm text-amber-100">
              {result.retrievalErrors.map((item) => (
                <p key={item.source}>
                  <span className="font-medium capitalize">{item.source} search: </span>
                  {scrub(item.message)}
                </p>
              ))}
            </div>
          )}

          <div className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface)]">
            <div
              role="tablist"
              className="grid grid-cols-2 border-b border-[var(--border)] sm:grid-cols-4"
            >
              {VIEW_OPTIONS.map((option) => {
                const active = view === option.id;
                const count = viewCounts[option.id];
                return (
                  <button
                    key={option.id}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setView(option.id)}
                    className={`border-b-2 px-3 py-3 text-left transition ${
                      active
                        ? "border-[var(--accent)] bg-[#1c2430] text-[var(--accent)]"
                        : "border-transparent text-[var(--muted)] hover:bg-[var(--background)] hover:text-[var(--foreground)]"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2 text-sm font-medium">
                      {option.label}
                      {option.id !== "final" && (
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs ${
                            active
                              ? "bg-[var(--accent)] text-[#0c0f14]"
                              : "bg-[var(--background)] text-[var(--muted)]"
                          }`}
                        >
                          {count}
                        </span>
                      )}
                    </span>
                    <span
                      className={`mt-1 block text-xs ${
                        active ? "text-[var(--foreground)]" : "text-[var(--muted)]"
                      }`}
                    >
                      {option.hint}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="p-4" role="tabpanel">
              {view === "final" ? (
                <FinalView result={result} />
              ) : (
                <CandidateList result={result} view={view} />
              )}
            </div>
          </div>
        </section>
      )}
    </main>
  );
}

function CandidateList({
  result,
  view,
}: {
  result: MatchResponse;
  view: Exclude<ResultView, "final">;
}) {
  const selectedId = result.jev.selectedCandidateId;
  const rows =
    view === "lucene"
      ? result.luceneCandidates
      : view === "vector"
        ? result.vectorCandidates
        : result.candidates;
  const empty =
    view === "lucene"
      ? "Lucene returned no candidates."
      : view === "vector"
        ? "Vector search returned no candidates."
        : "No combined candidates.";

  if (rows.length === 0) {
    return <p className="text-sm text-[var(--muted)]">{empty}</p>;
  }

  return (
    <ul className="space-y-3">
      {rows.map((candidate) => (
        <CandidateCard
          key={`${view}-${candidate.id}`}
          candidate={candidate}
          view={view}
          picked={candidate.id === selectedId}
          material={result.entityType === "material"}
        />
      ))}
    </ul>
  );
}

function CandidateCard({
  candidate,
  view,
  picked,
  material,
}: {
  candidate: Candidate;
  view: Exclude<ResultView, "final">;
  picked: boolean;
  material: boolean;
}) {
  const rank =
    view === "lucene"
      ? candidate.lexicalRank
      : view === "vector"
        ? candidate.vectorRank
        : candidate.rank;
  const primaryScore =
    view === "lucene"
      ? score(candidate.lexicalScore, 2)
      : view === "vector"
        ? score(candidate.vectorScore)
        : score(candidate.fusedScore, 4);
  const primaryLabel =
    view === "lucene" ? "Lucene score" : view === "vector" ? "Vector score" : "Combined score";

  return (
    <li
      className={`rounded-lg border bg-[var(--background)] p-4 ${
        picked ? "border-[var(--good)]" : "border-[var(--border)]"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium">
            <span className="mr-2 text-[var(--muted)]">#{rank ?? "—"}</span>
            {candidate.label}
            {picked && (
              <span className="ml-2 rounded-full bg-[var(--good)]/15 px-2 py-0.5 text-xs text-[var(--good)]">
                Final pick
              </span>
            )}
          </p>
          {candidate.detail && <p className="mt-1 text-sm text-[var(--muted)]">{candidate.detail}</p>}
          {view === "vector" && candidate.vectorFields.length > 0 && (
            <p className="mt-1 text-xs text-[var(--muted)]">
              Matched on {candidate.vectorFields.join(", ")}
            </p>
          )}
          {view === "combined" && (
            <div className="mt-2 flex flex-wrap gap-1">
              {candidate.sources.map((source) => (
                <span
                  key={source}
                  className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs capitalize text-[var(--muted)]"
                >
                  {source === "lexical" ? "lucene" : source}
                </span>
              ))}
              {candidate.sentToJev && (
                <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--muted)]">
                  scored in final
                </span>
              )}
            </div>
          )}
        </div>
        <p className="text-right text-sm">
          <span className="block text-xs text-[var(--muted)]">{primaryLabel}</span>
          <span className="font-medium">{primaryScore}</span>
        </p>
      </div>

      {view === "combined" && (
        <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-[var(--muted)] sm:grid-cols-4">
          <div>
            <dt>Lucene</dt>
            <dd className="text-[var(--foreground)]">
              {candidate.lexicalRank ? `#${candidate.lexicalRank}` : "—"} ·{" "}
              {score(candidate.lexicalScore, 2)}
            </dd>
          </div>
          <div>
            <dt>Vector</dt>
            <dd className="text-[var(--foreground)]">
              {candidate.vectorRank ? `#${candidate.vectorRank}` : "—"} ·{" "}
              {score(candidate.vectorScore)}
            </dd>
          </div>
          <div>
            <dt>Combined</dt>
            <dd className="text-[var(--foreground)]">
              #{candidate.rank} · {score(candidate.fusedScore, 4)}
            </dd>
          </div>
          <div>
            <dt>Spec check</dt>
            <dd
              className={
                candidate.missingQuerySpecs.length ? "text-[var(--warn)]" : "text-[var(--foreground)]"
              }
            >
              {candidate.missingQuerySpecs.length
                ? `Missing ${candidate.missingQuerySpecs.join(", ")}`
                : material
                  ? "Specs present or none in query"
                  : "—"}
            </dd>
          </div>
        </dl>
      )}
    </li>
  );
}

function FinalView({ result }: { result: MatchResponse }) {
  const decision = result.jev;
  const details = useMemo(() => {
    const found = new Map<string, Candidate>();
    for (const candidate of [
      ...result.candidates,
      ...result.luceneCandidates,
      ...result.vectorCandidates,
    ]) {
      if (!found.has(candidate.id)) found.set(candidate.id, candidate);
    }
    return found;
  }, [result]);

  if (decision.error) {
    return <p className="text-sm text-red-200">{scrub(decision.error)}</p>;
  }

  if (result.candidates.length === 0) {
    return <p className="text-sm text-[var(--muted)]">No candidates to score.</p>;
  }

  if (decision.probabilities.length === 0) {
    return <p className="text-sm text-[var(--muted)]">No final scores returned.</p>;
  }

  return (
    <ol className="space-y-3">
      {decision.probabilities.map((option, index) => {
        const candidate = option.candidateId ? details.get(option.candidateId) : undefined;
        const selected = option.optionId === decision.choice;
        const noMatch = option.optionId === "no_match";
        const selectedTone = noMatch ? "border-[var(--warn)]" : "border-[var(--good)]";
        const selectedLabel = noMatch ? "text-[var(--warn)]" : "text-[var(--good)]";
        const selectedBar = noMatch ? "bg-[var(--warn)]" : "bg-[var(--good)]";
        return (
          <li
            key={option.optionId}
            className={`rounded-lg border bg-[var(--background)] p-3 ${
              selected ? selectedTone : "border-[var(--border)]"
            }`}
          >
            <div className="mb-1 flex items-baseline justify-between gap-3">
              <p className="min-w-0 truncate text-sm">
                <span className="mr-2 text-[var(--muted)]">{index + 1}</span>
                {option.label}
                {selected && (
                  <span className={`ml-2 text-xs ${selectedLabel}`}>
                    {noMatch ? "No match selected" : "Selected"}
                  </span>
                )}
              </p>
              <p className="text-sm font-medium">{percent(option.probability)}</p>
            </div>
            {candidate?.detail && (
              <p className="mb-2 truncate text-xs text-[var(--muted)]">{candidate.detail}</p>
            )}
            <div className="h-2 rounded bg-[var(--surface)]">
              <div
                className={`h-2 rounded ${selected ? selectedBar : "bg-[var(--accent)]"}`}
                style={{
                  width: `${Math.max(0, Math.min(100, option.probability * 100))}%`,
                }}
              />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
