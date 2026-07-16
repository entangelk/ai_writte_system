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

export function describeApiError(err: unknown): string {
  if (err instanceof ApiError) {
    return `${err.status}: ${err.detail}`;
  }
  return err instanceof Error ? err.message : String(err);
}
