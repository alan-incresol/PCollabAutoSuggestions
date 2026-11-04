const base = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export type EntityType = "vendor" | "material";

export type Candidate = {
  id: string;
  optionId: string | null;
  rank: number;
  label: string;
  detail: string;
  sources: string[];
  lexicalRank: number | null;
  vectorRank: number | null;
  lexicalScore: number | null;
  vectorScore: number | null;
  fusedScore: number;
  vectorFields: string[];
  specTokens: string[];
  missingQuerySpecs: string[];
  sentToJev: boolean;
};

export type JevOption = {
  optionId: string;
  label: string;
  probability: number;
  candidateId: string | null;
};

export type MatchResponse = {
  query: string;
  luceneQuery: string;
  vectorQuery: string;
  normalizedQuery: string;
  entityType: EntityType;
  collectionName: string;
  luceneIndex: string;
  vectorIndex: string;
  candidateLimit: number;
  confidenceThreshold: number;
  candidates: Candidate[];
  luceneCandidates: Candidate[];
  vectorCandidates: Candidate[];
  jev: {
    model: string | null;
    choice: string | null;
    choiceLabel: string | null;
    confidence: number | null;
    accepted: boolean;
    selectedCandidateId: string | null;
    probabilities: JevOption[];
    usage: { input_tokens?: number; output_tokens?: number } | null;
    error: string | null;
  };
  retrievalErrors: { source: string; message: string }[];
  timingMs: Record<string, number>;
};

async function readError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* response was not JSON */
  }
  return text || `Request failed (${res.status})`;
}

export async function matchEntity(
  query: string,
  entityType: EntityType,
  orgId: string,
  orgOpuId: string,
  signal?: AbortSignal,
): Promise<MatchResponse> {
  const res = await fetch(`${base}/match`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      entityType,
      orgId,
      orgOpuId,
    }),
    signal,
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json() as Promise<MatchResponse>;
}
