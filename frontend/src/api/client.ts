import type { components } from "./schema";

// Single origin: nginx (deployed) and the Vite dev server (dev) both proxy /api
// to the Application. The API is unauthenticated, so CORS is never opened.
export const API_BASE = "/api";

/** Raised for any non-2xx response; `detail` carries the FastAPI error text. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  return (await response.json()) as T;
}

async function readDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    return JSON.stringify(body.detail ?? body);
  } catch {
    return response.statusText || `HTTP ${response.status}`;
  }
}

// Both request bodies and response payloads come from the generated OpenAPI
// types (SoT v1.6.95 put `response_model` on the Product shell spine, so the
// schema now carries real response shapes). Nothing here is hand-declared: a
// backend payload change fails the type check after `npm run gen:api`.
export type CreateProjectRequest = components["schemas"]["CreateProjectRequest"];
export type Project = components["schemas"]["ProjectPayload"];
export type ProjectListResponse = components["schemas"]["ProjectListResponse"];
export type CreateDraftRequest = components["schemas"]["CreateDraftRequest"];
export type Draft = components["schemas"]["DraftPayload"];
export type DraftListResponse = components["schemas"]["DraftListResponse"];
export type DraftVersion = components["schemas"]["DraftVersionMetaPayload"];
export type DraftVersionListResponse = components["schemas"]["DraftVersionListResponse"];
export type DraftVersionDetail = components["schemas"]["DraftVersionDetailResponse"];
export type DraftVersionExport = components["schemas"]["DraftVersionExportResponse"];
export type SaveDraftRequest = components["schemas"]["SaveDraftRequest"];
export type SaveDraftResponse = components["schemas"]["SaveDraftResponse"];
export type WritingGenerateRequest = components["schemas"]["WritingGenerateRequest"];
export type WritingCandidate = components["schemas"]["WritingCandidatePayload"];
export type WritingGateRequest = components["schemas"]["WritingGateRequest"];
export type WritingGate = components["schemas"]["WritingGatePayload"];
export type WritingGateFinding = components["schemas"]["WritingGateFindingPayload"];
export type WritingReviseRequest = components["schemas"]["WritingReviseRequest"];
export type WritingReviseGateResponse =
  components["schemas"]["WritingReviseGateResponse"];
export type WritingReviseGatePartial =
  components["schemas"]["WritingReviseGatePartial"];
export type WritingLoop = components["schemas"]["WritingLoopPayload"];
export type WritingLoopStage = components["schemas"]["WritingStagePayload"];
export type WritingAcceptRequest = components["schemas"]["WritingAcceptRequest"];
export type WritingAcceptResponse = components["schemas"]["WritingAcceptResponse"];
export type WritingAcceptAnalysisPartial =
  components["schemas"]["WritingAcceptAnalysisPartial"];

export function listProjects(): Promise<ProjectListResponse> {
  return request("/projects");
}

export function createProject(body: CreateProjectRequest): Promise<Project> {
  return request("/projects", { method: "POST", body: JSON.stringify(body) });
}

export function getProject(projectId: string): Promise<Project> {
  return request(`/projects/${projectId}`);
}

export function listDrafts(projectId: string): Promise<DraftListResponse> {
  return request(`/projects/${projectId}/drafts`);
}

export function createDraft(
  projectId: string,
  body: CreateDraftRequest,
): Promise<Draft> {
  return request(`/projects/${projectId}/drafts`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getDraft(projectId: string, draftId: string): Promise<Draft> {
  return request(`/projects/${projectId}/drafts/${draftId}`);
}

export function listDraftVersions(
  projectId: string,
  draftId: string,
): Promise<DraftVersionListResponse> {
  return request(`/projects/${projectId}/drafts/${draftId}/versions`);
}

export function getDraftVersion(
  projectId: string,
  draftId: string,
  versionId: string,
): Promise<DraftVersionDetail> {
  return request(
    `/projects/${projectId}/drafts/${draftId}/versions/${versionId}`,
  );
}

export function saveDraft(
  projectId: string,
  draftId: string,
  body: SaveDraftRequest,
): Promise<SaveDraftResponse> {
  return request(`/projects/${projectId}/drafts/${draftId}/versions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function exportDraftVersion(
  projectId: string,
  draftId: string,
  versionId: string,
  format: "txt" | "markdown",
): Promise<DraftVersionExport> {
  return request(
    `/projects/${projectId}/drafts/${draftId}/versions/${versionId}/export?format=${format}`,
  );
}

export function generateWriting(
  projectId: string,
  body: WritingGenerateRequest,
): Promise<WritingCandidate> {
  return request(`/projects/${projectId}/writing/generate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function gateWriting(
  projectId: string,
  body: WritingGateRequest,
): Promise<WritingGate> {
  return request(`/projects/${projectId}/writing/gate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type WritingReviseGateOutcome =
  | {
      partial: false;
      status: 200;
      data: WritingReviseGateResponse;
      retryable: false;
    }
  | {
      partial: true;
      status: number;
      data: WritingReviseGatePartial;
      retryable: boolean;
    };

export async function reviseAndGateWriting(
  projectId: string,
  body: WritingReviseRequest,
): Promise<WritingReviseGateOutcome> {
  const response = await fetch(
    `${API_BASE}/projects/${projectId}/writing/revise-and-gate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  const data = (await response.json()) as
    | WritingReviseGateResponse
    | WritingReviseGatePartial
    | components["schemas"]["ErrorDetailResponse"];
  if (response.ok) {
    return {
      partial: false,
      status: 200,
      data: data as WritingReviseGateResponse,
      retryable: false,
    };
  }
  if ("candidate" in data) {
    return {
      partial: true,
      status: response.status,
      data,
      retryable: response.status >= 500,
    };
  }
  throw new ApiError(response.status, data.detail);
}

// A normalized accept outcome. The endpoint's load-bearing behaviour is that a
// version can be saved even on a 502 (Analysis job failed after the save): a
// `502 + accepted=true + saved` is a successful write, not a plain error, and
// must never discard the saved version. `acceptWriting` folds the 200 success,
// the 200 non-pass, and the 502 partial into one discriminated result; only a
// true error (400/404/409/422, or a 502 without `saved`) throws ApiError.
export type WritingAcceptOutcome =
  | { accepted: true; savedVersionId: string; analysisFailed: boolean }
  | { accepted: false; gate: WritingGate | null };

export async function acceptWriting(
  projectId: string,
  body: WritingAcceptRequest,
): Promise<WritingAcceptOutcome> {
  const response = await fetch(`${API_BASE}/projects/${projectId}/writing/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (response.ok) {
    const data = (await response.json()) as WritingAcceptResponse;
    if (data.accepted && data.saved !== null) {
      return {
        accepted: true,
        savedVersionId: data.saved.draft_version_id,
        analysisFailed: false,
      };
    }
    return { accepted: false, gate: data.gate };
  }
  if (response.status === 502) {
    const partial = (await response.json()) as Partial<WritingAcceptAnalysisPartial> & {
      detail?: unknown;
    };
    if (partial.accepted === true && partial.saved != null) {
      return {
        accepted: true,
        savedVersionId: partial.saved.draft_version_id,
        analysisFailed: true,
      };
    }
    throw new ApiError(
      502,
      typeof partial.detail === "string"
        ? partial.detail
        : JSON.stringify(partial.detail ?? partial),
    );
  }
  throw new ApiError(response.status, await readDetail(response));
}

export function describeApiError(err: unknown): string {
  if (err instanceof ApiError) {
    return `${err.status}: ${err.detail}`;
  }
  return err instanceof Error ? err.message : String(err);
}
