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

// Request bodies come from the generated OpenAPI types. Response payloads are
// hand-declared: the endpoints are annotated `dict[str, object]`, so OpenAPI
// types them as open objects and generation carries no response shape (see
// work log 2026-07-16 — closing that gap needs backend `response_model`).
export type CreateProjectRequest = components["schemas"]["CreateProjectRequest"];

export interface Project {
  id: string;
  name: string;
  archived: boolean;
}

export function listProjects(): Promise<{ projects: Project[] }> {
  return request("/projects");
}

export function createProject(body: CreateProjectRequest): Promise<Project> {
  return request("/projects", { method: "POST", body: JSON.stringify(body) });
}
