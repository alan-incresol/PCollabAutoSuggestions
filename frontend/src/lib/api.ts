const base = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:5000"
).replace(/\/$/, "");

export type SuggestResponse = {
  suggestions: string[];
};

export type SearchResponse = {
  count: number;
  documents: Record<string, unknown>[];
};

export async function suggestVendors(
  query: string,
  fields: string[],
  signal?: AbortSignal,
): Promise<SuggestResponse> {
  const res = await fetch(`${base}/suggest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, fields }),
    signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Suggest failed (${res.status})`);
  }
  return res.json() as Promise<SuggestResponse>;
}

export async function searchVendors(
  query: string,
  fields: string[],
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const res = await fetch(`${base}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, fields }),
    signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Search failed (${res.status})`);
  }
  return res.json() as Promise<SearchResponse>;
}
