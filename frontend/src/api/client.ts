import type { components } from "./schema";

// Single origin: nginx (deployed) and the Vite dev server (dev) both proxy /api
// to the Application. Session cookies stay same-origin, so CORS remains closed.
export const API_BASE = "/api";

type UnauthorizedListener = () => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

export function subscribeUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

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
  const response = await fetchApi(path, init);
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  return (await response.json()) as T;
}

async function fetchApi(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  // Auth endpoints handle their own expected 401s. Any other 401 means a
  // previously valid browser session can no longer authorize workspace work.
  if (response.status === 401 && !path.startsWith("/auth/")) {
    for (const listener of unauthorizedListeners) {
      listener();
    }
  }
  return response;
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
export type LoginRequest = components["schemas"]["LoginRequest"];
export type LoginResponse = components["schemas"]["LoginResponse"];
export type LogoutResponse = components["schemas"]["LogoutResponse"];
export type User = components["schemas"]["UserPayload"];
export type AdminUser = components["schemas"]["AdminUserPayload"];
export type AdminProject = components["schemas"]["AdminProjectPayload"];
export type AdminObservabilityKpi =
  components["schemas"]["AdminObservabilityKpiResponse"];
export type AccessGrant = components["schemas"]["AccessGrantPayload"];
export type AccessLogEntry = components["schemas"]["AccessLogEntryPayload"];
export type Project = components["schemas"]["ProjectPayload"];
export type ProjectListResponse = components["schemas"]["ProjectListResponse"];
export type ProjectBrief = components["schemas"]["ProjectBriefVersionPayload"];
export type ProjectBriefGetResponse = components["schemas"]["ProjectBriefGetResponse"];
export type PutProjectBriefRequest = components["schemas"]["PutProjectBriefRequest"];
export type ProjectBriefPutResponse = components["schemas"]["ProjectBriefPutResponse"];
export type ProjectBriefVersionListResponse =
  components["schemas"]["ProjectBriefVersionListResponse"];
export type CreateDraftRequest = components["schemas"]["CreateDraftRequest"];
export type Draft = components["schemas"]["DraftPayload"];
export type DraftListResponse = components["schemas"]["DraftListResponse"];
export type DraftOrderPutRequest = components["schemas"]["DraftOrderPutRequest"];
export type DraftOrderPutResponse = components["schemas"]["DraftOrderPutResponse"];
export type DraftVersion = components["schemas"]["DraftVersionMetaPayload"];
export type DraftVersionListResponse = components["schemas"]["DraftVersionListResponse"];
export type DraftVersionDetail = components["schemas"]["DraftVersionDetailResponse"];
export type DraftVersionExport = components["schemas"]["DraftVersionExportResponse"];
export type ProjectExport = components["schemas"]["ProjectExportResponse"];
export type SaveDraftRequest = components["schemas"]["SaveDraftRequest"];
export type SaveDraftResponse = components["schemas"]["SaveDraftResponse"];
export type WritingGenerateRequest = components["schemas"]["WritingGenerateRequest"];
export type WritingCandidate = components["schemas"]["WritingCandidatePayload"];
export type WritingContextBudget =
  components["schemas"]["WritingContextBudgetPayload"];
// 증분 2c (D5=A): medium/long presets return a 202 job reference instead of a
// candidate. generateWriting therefore returns the union; callers narrow with
// `"job" in produced`. The worker appends the result to scratch (increment 3's
// pad polls GET .../generation-jobs/{job_id} and re-reads scratch).
export type WritingGenerationJob =
  components["schemas"]["WritingGenerationJobPayload"];
export type WritingGenerationJobAccepted =
  components["schemas"]["WritingGenerationJobAcceptedPayload"];
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

export function login(body: LoginRequest): Promise<LoginResponse> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function logout(): Promise<LogoutResponse> {
  return request("/auth/logout", { method: "POST" });
}

export function getCurrentUser(): Promise<User> {
  return request("/auth/me");
}

export function listAdminUsers(): Promise<components["schemas"]["AdminUserListResponse"]> {
  return request("/admin/users");
}

export function createAdminUser(
  body: components["schemas"]["CreateUserRequest"],
): Promise<AdminUser> {
  return request("/admin/users", { method: "POST", body: JSON.stringify(body) });
}

export function deactivateAdminUser(userId: string): Promise<AdminUser> {
  return request(`/admin/users/${encodeURIComponent(userId)}/deactivate`, {
    method: "POST",
  });
}

export function listAdminProjects(): Promise<components["schemas"]["AdminProjectListResponse"]> {
  return request("/admin/projects");
}

export function getAdminObservabilityKpi(): Promise<AdminObservabilityKpi> {
  return request("/admin/observability/kpi");
}

export async function issueProjectAccessGrant(
  projectId: string,
  reason: string,
): Promise<AccessGrant> {
  const response = await request<components["schemas"]["AccessGrantCreateResponse"]>(
    `/admin/projects/${encodeURIComponent(projectId)}/access-grants`,
    { method: "POST", body: JSON.stringify({ reason }) },
  );
  return response.grant;
}

export async function listProjectAccessLog(projectId: string): Promise<AccessLogEntry[]> {
  const response = await request<components["schemas"]["AccessLogResponse"]>(
    `/projects/${encodeURIComponent(projectId)}/access-log`,
  );
  return response.entries;
}

export function listProjects(): Promise<ProjectListResponse> {
  return request("/projects");
}

export function createProject(body: CreateProjectRequest): Promise<Project> {
  return request("/projects", { method: "POST", body: JSON.stringify(body) });
}

export function getProject(projectId: string): Promise<Project> {
  return request(`/projects/${projectId}`);
}

export type ObservabilityKpi = components["schemas"]["ObservabilityKpiResponse"];
export type ObservabilityKpiSite =
  components["schemas"]["ObservabilityKpiSitePayload"];

export function getObservabilityKpi(
  projectId: string,
): Promise<ObservabilityKpi> {
  return request(`/projects/${projectId}/observability/kpi`);
}

export function getProjectBrief(
  projectId: string,
): Promise<ProjectBriefGetResponse> {
  return request(`/projects/${projectId}/brief`);
}

export function putProjectBrief(
  projectId: string,
  body: PutProjectBriefRequest,
): Promise<ProjectBriefPutResponse> {
  return request(`/projects/${projectId}/brief`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function listProjectBriefVersions(
  projectId: string,
): Promise<ProjectBriefVersionListResponse> {
  return request(`/projects/${projectId}/brief/versions`);
}

export interface CanonicalMemory {
  id: string;
  memory_type: string;
  status: string;
  payload: Record<string, unknown>;
  version: number;
}

export function listCanonicalMemory(
  projectId: string,
): Promise<{ memory: CanonicalMemory[] }> {
  return request(`/projects/${projectId}/memory`);
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

export function putDraftOrder(
  projectId: string,
  body: DraftOrderPutRequest,
): Promise<DraftOrderPutResponse> {
  return request(`/projects/${projectId}/draft-order`, {
    method: "PUT",
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

export function exportProject(
  projectId: string,
  format: "txt" | "markdown",
  options: { manifest?: boolean; includeArchived?: boolean } = {},
): Promise<ProjectExport> {
  const query = new URLSearchParams({ format });
  if (options.manifest) {
    query.set("manifest", "true");
  }
  if (options.includeArchived) {
    query.set("include_archived", "true");
  }
  return request(`/projects/${projectId}/export?${query.toString()}`);
}

export function generateWriting(
  projectId: string,
  body: WritingGenerateRequest,
): Promise<WritingCandidate | WritingGenerationJobAccepted> {
  return request(`/projects/${projectId}/writing/generate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// 증분 3 (D6): the result pad polls this to learn when a medium/long async
// generation finishes (or fails), then re-reads the scratch list to surface the
// result. Read-only status; 404 covers both unknown job and wrong project.
export function getGenerationJob(
  projectId: string,
  jobId: string,
): Promise<WritingGenerationJob> {
  return request(
    `/projects/${projectId}/writing/generation-jobs/${encodeURIComponent(jobId)}`,
  );
}

// 재시도 슬라이스 (D4=A): reset a FAILED generation job to PENDING so the worker
// re-claims and re-runs it. Returns the reset job (status pending). 409 if the
// job is not failed, 404 if unknown/wrong project.
export function retryGenerationJob(
  projectId: string,
  jobId: string,
): Promise<WritingGenerationJob> {
  return request(
    `/projects/${projectId}/writing/generation-jobs/${encodeURIComponent(jobId)}/retry`,
    { method: "POST" },
  );
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
  const response = await fetchApi(
    `/projects/${projectId}/writing/revise-and-gate`,
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
  const response = await fetchApi(`/projects/${projectId}/writing/accept`, {
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

// --- Unaccepted candidate recovery (brief D0=B/D1=B/D2=A) ------------------
// The scratch list/discard endpoints return `dict[str, object]` (no
// response_model), so the generated schema carries no shape for them — the
// payloads are hand-declared here, mirroring `_writing_scratch_payload` in
// main.py. This is the pre-dogfood safety net: a generated candidate is
// persisted to `writing_drafts_scratch` so a refresh before accept doesn't lose
// it. Cleared on a saved accept; the draft keeps a bounded newest-first history.

/** One recoverable unaccepted candidate (newest-first in the list). */
export interface ScratchCandidate {
  id: string;
  draft_id: string;
  request_id: string;
  task_type: string;
  output_type: string;
  instruction: string;
  candidate_text: string;
  intent: string | null;
  /** Version the candidate was generated against (async-pad D7); null for
   * records written before the field existed. */
  version_id: string | null;
  created_at: string;
}

export interface ScratchListResponse {
  project_id: string;
  draft_id: string;
  items: ScratchCandidate[];
}

export function listWritingScratch(
  projectId: string,
  draftId: string,
): Promise<ScratchListResponse> {
  return request(
    `/projects/${projectId}/writing/scratch?draft_id=${encodeURIComponent(draftId)}`,
  );
}

// K-4 (프론트 글자수 표시·경고): R-a 유도 예산을 per-preset(short/medium/long) 토큰으로
// 받아 카운터의 경고 기준으로 쓴다 — 고정 상수(8192)가 아니라 배포·출력 프리셋을 따라간다.
export function getWritingContextBudget(
  projectId: string,
): Promise<WritingContextBudget> {
  return request(`/projects/${projectId}/writing/budget`);
}

export function discardWritingScratch(
  projectId: string,
  draftId: string,
): Promise<{ project_id: string; draft_id: string; deleted: number }> {
  return request(
    `/projects/${projectId}/writing/scratch?draft_id=${encodeURIComponent(draftId)}`,
    { method: "DELETE" },
  );
}

// --- Review Inbox (Phase 6 B) ---------------------------------------------
// The review-inbox / gate-finding read endpoints return `dict[str, object]`, so
// the generated schema has no response body for them (SoT: the remaining
// untyped endpoints are hand-declared in their consuming UI slice, as the very
// first Product-shell slice did before the spine got `response_model`). These
// shapes mirror `_review_inbox_payload` / `_gate_finding_payload` in main.py.
// The frontend never recomputes eligibility: it renders each `actions` entry's
// button `disabled` from `eligible` and branches only on `action` — `reason` is
// human display text, never pattern-matched (affordance contract v1.6.67).

/** One review action's availability. `reason` is display text only. */
export interface ReviewAffordance {
  action: string;
  eligible: boolean;
  reason: string | null;
}

/** A review-inbox candidate row (list) — detail adds payload/source_refs/conflicts. */
export interface ReviewInboxItem {
  candidate_id: string;
  job_id: string;
  candidate_type: string;
  status: string;
  confidence: number;
  provenance: string;
  conflict_count: number;
  actions: ReviewAffordance[];
}

/** A resolved (or missing) source_ref pointer for a candidate's evidence quote. */
export interface ReviewSourcePointer {
  source_ref_id: string;
  status: "resolved" | "missing";
  snapshot_id?: string;
  block_id?: string;
  start_offset?: number;
  end_offset?: number;
  quote?: string;
  content_hash?: string;
}

export interface ReviewFieldDiff {
  field: string;
  before: unknown;
  after: unknown;
}

/** A conflict attached to a candidate. `actions` carries the merge/split affordances the
 * detail view submits via `reconcileConflict` — the "read-only, no merge/split yet" state
 * this comment used to describe ended when those actions landed. */
export interface ReviewConflict {
  entry_id: string;
  action: string;
  rationale: string;
  matched_memory: { id: string; payload: Record<string, unknown> } | null;
  diff: ReviewFieldDiff[];
  actions: ReviewAffordance[];
}

export interface ReviewInboxDetailItem extends ReviewInboxItem {
  payload: Record<string, unknown>;
  source_refs: ReviewSourcePointer[];
  conflicts: ReviewConflict[];
}

export interface GateFinding {
  id: string;
  origin: string;
  status: string;
  check: string;
  detail: string;
  query: string;
  purpose: string;
  needs: string[];
  pointer_ids: string[];
  actions: ReviewAffordance[];
}

export interface ReviewInboxListResponse {
  project_id: string;
  items: ReviewInboxItem[];
  gate_findings: GateFinding[];
}

export function listReviewInbox(
  projectId: string,
): Promise<ReviewInboxListResponse> {
  return request(`/projects/${projectId}/analysis/review-inbox`);
}

export function getReviewInboxItem(
  projectId: string,
  candidateId: string,
): Promise<ReviewInboxDetailItem> {
  return request(
    `/projects/${projectId}/analysis/review-inbox/${candidateId}`,
  );
}

export function confirmCandidate(
  projectId: string,
  candidateId: string,
): Promise<void> {
  return request(
    `/projects/${projectId}/analysis/candidates/${candidateId}/confirm`,
    { method: "POST" },
  );
}

export function rejectCandidate(
  projectId: string,
  candidateId: string,
): Promise<void> {
  return request(
    `/projects/${projectId}/analysis/candidates/${candidateId}/reject`,
    { method: "POST" },
  );
}

// Edit re-versions the candidate with the edited payload (server re-validates
// against the candidate_type schema → 400 on invalid, 409 on non-needs_review).
// The payload fields are the taxonomy's exact key set of non-empty strings
// (character=name/observation, event=event, open_question=question). The UI
// navigates away on success, so the response body is unused (void).
export function editCandidate(
  projectId: string,
  candidateId: string,
  payload: Record<string, string>,
): Promise<void> {
  return request(
    `/projects/${projectId}/analysis/candidates/${candidateId}/edit`,
    { method: "POST", body: JSON.stringify({ payload }) },
  );
}

// Reconcile a character conflict — `action` is the affordance literal
// ("merge" | "split"). Eligibility is already declared on the conflict's
// `actions`; the write endpoint remains the authority.
export function reconcileConflict(
  projectId: string,
  entryId: string,
  action: string,
): Promise<void> {
  return request(
    `/projects/${projectId}/analysis/review-queue/${entryId}/reconcile`,
    { method: "POST", body: JSON.stringify({ action }) },
  );
}

export function resolveGateFinding(
  projectId: string,
  findingId: string,
): Promise<void> {
  return request(
    `/projects/${projectId}/analysis/gate-findings/${findingId}/resolve`,
    { method: "POST" },
  );
}

export function dismissGateFinding(
  projectId: string,
  findingId: string,
): Promise<void> {
  return request(
    `/projects/${projectId}/analysis/gate-findings/${findingId}/dismiss`,
    { method: "POST" },
  );
}

export function describeApiError(err: unknown): string {
  if (err instanceof ApiError) {
    return `${err.status}: ${err.detail}`;
  }
  return err instanceof Error ? err.message : String(err);
}

// Human-facing guidance for the writing loop's known failure signatures. A real
// 12B occasionally emits a report/revision the strict parser rejects; the
// backend already retries, so for these the actionable answer is "generate
// again". `retryable` drives whether the panel offers a retry affordance.
export function describeWritingError(err: unknown): {
  message: string;
  retryable: boolean;
} {
  if (err instanceof ApiError) {
    const d = err.detail;
    if (d.includes("invalid_candidate_report") || d.includes("report field")) {
      return {
        message: "AI가 근거 보고서를 형식에 맞게 만들지 못했습니다. 다시 생성해 주세요.",
        retryable: true,
      };
    }
    if (d.includes("invalid_writing_revision")) {
      return {
        message: "AI가 후보를 형식에 맞게 수정하지 못했습니다. 다시 생성하거나 지시를 바꿔 주세요.",
        retryable: true,
      };
    }
    if (d.includes("invalid_gate_result")) {
      return {
        message: "Gate 평가 결과를 해석하지 못했습니다. 다시 생성해 주세요.",
        retryable: true,
      };
    }
    if (err.status === 503) {
      return {
        message: "AI 서비스가 아직 준비되지 않았습니다. 잠시 후 다시 시도해 주세요.",
        retryable: true,
      };
    }
    if (err.status === 504) {
      return {
        message: "AI 응답이 제한 시간 안에 오지 않았습니다. 다시 생성해 주세요.",
        retryable: true,
      };
    }
    if (err.status >= 500) {
      return {
        message: "AI 생성 중 오류가 발생했습니다. 다시 생성해 주세요.",
        retryable: true,
      };
    }
    return { message: `${err.status}: ${err.detail}`, retryable: false };
  }
  return {
    message: err instanceof Error ? err.message : String(err),
    retryable: true,
  };
}

// Analysis trigger (review candidates). The jobs create/run endpoints are
// untyped (dict responses), so these shapes are hand-declared (v1.6.94 precedent
// for review reads). Running a job extracts needs_review candidates for the
// snapshot; they then surface in the Review Inbox.
interface AnalysisJobRef {
  id: string;
  status: string;
  failure_reason?: string | null;
  failure_detail?: string | null;
}

// Analysis anchors candidates to source_refs; without a catalog the extraction
// 400s "source_ref catalog is required". A saved snapshot has none until spans
// are cited, so the test-bed trigger catalogs every block (full-block span; the
// server derives quote/hash from the offsets).
//
// Coverage-based + idempotent so a partial failure self-heals: we create a
// full-span ref only for blocks not already covered (matched by exact offsets).
// A previous run that died after k of N creates leaves k refs; the retry sees
// them, skips those blocks, and creates only the missing ones — instead of the
// old "any refs exist → skip", which would leave the catalog permanently
// incomplete and run extraction against missing anchors. A mid-loop failure
// still throws (the caller surfaces it and can retry to completion); we never
// run the job against a partial catalog.
async function ensureSourceRefCatalog(
  projectId: string,
  draftId: string,
  versionId: string,
  snapshotId: string,
): Promise<number> {
  const existing = await request<{
    source_refs: { start_offset: number; end_offset: number }[];
  }>(`/projects/${projectId}/snapshots/${snapshotId}/source-refs`);
  const covered = new Set(
    existing.source_refs.map((ref) => `${ref.start_offset}:${ref.end_offset}`),
  );
  const detail = await getDraftVersion(projectId, draftId, versionId);
  let created = 0;
  for (const block of detail.blocks) {
    if (block.end_offset <= block.start_offset) continue;
    if (covered.has(`${block.start_offset}:${block.end_offset}`)) continue;
    await request(`/projects/${projectId}/snapshots/${snapshotId}/source-refs`, {
      method: "POST",
      body: JSON.stringify({
        start_offset: block.start_offset,
        end_offset: block.end_offset,
      }),
    });
    created += 1;
  }
  if (existing.source_refs.length + created === 0) {
    // No anchorable spans at all → extraction would 400. Surface a clear signal
    // instead of running into an opaque backend error.
    throw new ApiError(
      422,
      "분석할 본문 블록이 없습니다. 원고에 내용을 채운 뒤 다시 시도하세요.",
    );
  }
  return created;
}

export async function analyzeVersion(
  projectId: string,
  draftId: string,
  versionId: string,
  snapshotId: string,
): Promise<{ jobId: string; candidateCount: number; sourceRefsCreated: number }> {
  const sourceRefsCreated = await ensureSourceRefCatalog(
    projectId,
    draftId,
    versionId,
    snapshotId,
  );
  const created = await request<{ job: AnalysisJobRef }>(
    `/projects/${projectId}/analysis/jobs`,
    {
      method: "POST",
      body: JSON.stringify({
        snapshot_id: snapshotId,
        // D5=A alignment: a per-snapshot deterministic key (mirrors accept's
        // `analysis_job_key`, accept.py) so accept's pending job AND repeat
        // clicks converge on ONE job per snapshot — no orphan jobs, and no
        // duplicate candidates from re-analyzing the same snapshot.
        idempotency_key: `analyze:${snapshotId}`,
      }),
    },
  );
  let job = created.job;
  if (job.status === "failed") {
    job = await request<AnalysisJobRef>(
      `/projects/${projectId}/analysis/jobs/${job.id}/retry`,
      { method: "POST" },
    );
    if (job.status !== "pending") {
      throw new ApiError(409, `분석 재시도 준비에 실패했습니다 (상태: ${job.status}).`);
    }
  }
  const run = await request<{ job: AnalysisJobRef; candidates: unknown[] }>(
    `/projects/${projectId}/analysis/jobs/${created.job.id}/run`,
    { method: "POST" },
  );
  if (run.job.status !== "succeeded") {
    throw new ApiError(
      409,
      run.job.failure_detail ??
        `분석이 완료되지 않았습니다 (상태: ${run.job.status}).`,
    );
  }
  return {
    jobId: created.job.id,
    candidateCount: run.candidates.length,
    sourceRefsCreated,
  };
}
