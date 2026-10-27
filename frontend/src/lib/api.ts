// Empty base keeps requests on this Next server, which proxies to the backend.
// An absolute NEXT_PUBLIC_API_URL is only for calling the API from another host.
const base = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export type SuggestResponse = {
  suggestions: string[];
};

export type SearchResponse = {
  count: number;
  documents: Record<string, unknown>[];
};

export type FieldConfig = {
  id: string;
  label: string;
  path: string;
};

export type AppConfig = {
  collectionName: string;
  searchIndexName: string;
  requiresOrgOpuId: boolean;
  fields: FieldConfig[];
};

export type AutosuggestCollectionOptions = {
  collectionName?: string;
  searchIndexName?: string;
};

type AutosuggestInit = AutosuggestCollectionOptions & { signal?: AbortSignal };

function autosuggestBody(
  query: string,
  fields: string[],
  orgId: string,
  orgOpuId: string | undefined,
  init?: AutosuggestCollectionOptions,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    query,
    fields,
    orgId,
  };
  if (orgOpuId != null && orgOpuId !== "") body.orgOpuId = orgOpuId;
  if (init?.collectionName != null) body.collectionName = init.collectionName;
  if (init?.searchIndexName != null) body.searchIndexName = init.searchIndexName;
  return body;
}

export async function fetchAppConfig(
  init?: { signal?: AbortSignal },
): Promise<AppConfig> {
  const res = await fetch(`${base}/config`, { signal: init?.signal });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Config fetch failed (${res.status})`);
  }
  return res.json() as Promise<AppConfig>;
}

export async function suggestPR(
  query: string,
  fields: string[],
  orgId: string,
  orgOpuId: string | undefined,
  init?: AutosuggestInit,
): Promise<SuggestResponse> {
  const { signal, ...opts } = init ?? {};
  const res = await fetch(`${base}/suggest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(autosuggestBody(query, fields, orgId, orgOpuId, opts)),
    signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Suggest failed (${res.status})`);
  }
  return res.json() as Promise<SuggestResponse>;
}

export async function searchPR(
  query: string,
  fields: string[],
  orgId: string,
  orgOpuId: string | undefined,
  init?: AutosuggestInit,
): Promise<SearchResponse> {
  const { signal, ...opts } = init ?? {};
  const res = await fetch(`${base}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(autosuggestBody(query, fields, orgId, orgOpuId, opts)),
    signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Search failed (${res.status})`);
  }
  return res.json() as Promise<SearchResponse>;
}
