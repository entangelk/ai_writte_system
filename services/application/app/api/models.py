"""HTTP 요청/응답 모델 + 그 검증에 쓰이는 제약·상수.

`main.py` 에서 추출했다(공유 prelude 추출, 2026-08-06). **본문은 byte-동일**이고
정의 순서도 원본 그대로다 — pydantic 이 필드 annotation 을 클래스 생성 시점에
해석하므로 순서를 흩뜨리면 조용히 깨진다.

의존 방향은 단방향이다: `errors` → `models` → `env`. 이 모듈이 `errors`·`dependencies`
를 import 하면 추출이 없앤 순환이 되돌아온다.
"""

from __future__ import annotations

from datetime import datetime
from pydantic import (
    StrictInt,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)
from services.application.app.context_search.models import (
    ContextNeed,
    ContextSearchPurpose,
)
from services.application.app.core_sot.models import (
    BlockKind,
)
from services.application.app.writing.models import (
    OutputLength,
    WritingIntent,
    WritingOutputType,
    WritingTaskType,
)
from typing import Annotated

from ..env import _env_int, draft_raw_text_max_chars


# Fixed retrieval needs for a continue_scene generation (Phase 5.1). Mongo-served
# needs (current/recent scene) require a current_position; when absent they yield
# empty sections and generation proceeds with whatever context was retrieved.
_WRITING_CONTINUE_SCENE_NEEDS = (
    ContextNeed.CURRENT_SCENE,
    ContextNeed.RECENT_SCENES,
    ContextNeed.CANONICAL_MEMORY,
)


class AutoPromotePartialResponse(BaseModel):
    # SoT v1.7.35 D1=B: 503 raised *after* some candidates were already promoted.
    # Canonical mints are append-only and are not rolled back, so hiding them
    # behind a bare error body would make the response disagree with the stored
    # state. Same shape as the success envelope plus the failure reason; the
    # partial-envelope precedent is WritingAcceptAnalysisPartial (accept 502).
    #
    # Returned via JSONResponse, so this model is responses={} documentation only
    # and the exact-key regression is its runtime lock (same pattern as the
    # writing partials). ``promoted`` stays untyped item-wise because the success
    # arm of this endpoint is an untyped dict today — a narrower model here would
    # document a wire shape the endpoint does not actually promise.
    auto_promotion_threshold: float | None
    promoted: list[dict[str, object]]
    promotion_error: str


class LoginRequest(BaseModel):
    username: str
    password: str
    # C-6. Present only when the account must replace an administrator-set
    # password. Optional so the ordinary login body is unchanged; supplying it
    # when no change is required is refused rather than silently ignored (see
    # the handler), because "my password changed" must never be a no-op.
    new_password: str | None = None


class SignupRequest(BaseModel):
    # Self-service signup request (2026-08-22): creates a *pending* row an
    # administrator must approve. No password confirmation field — that is a
    # client-side concern; the server would only re-compare two strings it was
    # handed by the same untrusted party.
    username: str
    password: str


class SignupResponse(BaseModel):
    username: str
    status: str


class UserPayload(BaseModel):
    # Deliberately no password_hash: the wire model is the reason a hash cannot
    # leak by someone later returning the domain object directly.
    id: str
    username: str
    is_admin: bool


class LoginResponse(BaseModel):
    user: UserPayload


class LogoutResponse(BaseModel):
    ok: bool


class QuotaWindowPayload(BaseModel):
    """한 창(일 또는 주)의 상태. ``limit=None`` 은 그 창이 무제한이라는 뜻이다."""

    limit: int | None
    used: int
    remaining: int | None
    resets_at: datetime


class MyQuotaResponse(BaseModel):
    """회원이 보는 자기 사용량 (Slice 8.4 W5=B, operation 76).

    ``remaining`` 이 **표시 단위**다(8.2 §0.2 — 두 창을 모두 통과해야 하므로 작은
    쪽이 실제 잔여다). 창별 값을 함께 주는 것은 "왜 20회가 아니라 3회인가"의 답이
    거기 있기 때문이고, 그 답이 없으면 지원 대화가 성립하지 않는다.

    ``status`` 는 한도와 **다른 축**이다(8.1 P5): ``suspended`` 는 잔여가 남아
    있어도 막히며 푸는 사람이 다르다(관리자). 화면이 그 둘을 같은 말로 그리면
    "관리자에게 문의"가 사라진다.
    """

    remaining: int | None
    unlimited: bool
    status: str
    daily: QuotaWindowPayload
    weekly: QuotaWindowPayload


class AdminQuotaPendingPayload(BaseModel):
    """8.5-a — 아직 발효하지 않은 예약 변경만 실은다(P6).

    지나간 예약(``effective_at`` 이 지난 pending)은 어디에도 "대기 중"으로 보이면
    안 된다 — 검증 H2. 이 모델에 실리기 직전에 발효 여부로 거른다.
    """

    daily_limit: int | None
    weekly_limit: int | None
    status: str
    effective_at: datetime


class AdminQuotaPolicyPayload(BaseModel):
    """8.5-a — 관리자가 보는 회원 정책·사용량 요약 (operation 80).

    ``remaining``/``daily``/``weekly`` 는 ``/me/quota`` 와 **같은 snapshot 정의**다 —
    관리자 화면이 회원 화면과 다른 산식을 말하면 지원 대화가 성립하지 않는다.
    """

    user_id: str
    username: str
    is_active: bool
    status: str
    unlimited: bool
    remaining: int | None
    daily: QuotaWindowPayload
    weekly: QuotaWindowPayload
    has_pending: bool


class AdminQuotaPolicyListResponse(BaseModel):
    policies: list[AdminQuotaPolicyPayload]


class AdminQuotaPolicyDetailResponse(AdminQuotaPolicyPayload):
    """8.5-a — 상세 (operation 81).

    ``stored_*`` 는 **진단용 원본 행**이고 유효 한도는 부모의 ``daily``/``weekly``
    이다 — 둘을 갈라 놓는 것이 이 endpoint 의 존재 이유다(H2: ``policy.limits`` 를
    그대로 내놓으면 만료된 예약이 "아직 대기 중"으로 보인다). 정책 행이 없는 회원은
    ``stored_*`` 가 ``None`` 이고 유효 한도는 코드 기본 해석이다.
    """

    stored_daily_limit: int | None
    stored_weekly_limit: int | None
    pending: AdminQuotaPendingPayload | None
    updated_at: datetime | None


class AdminQuotaLimitsChangeRequest(BaseModel):
    """8.5-b — 한도 변경(D2=ⓐ: 발효는 도메인 P6). 둘 중 하나만 바꿀 수 있고
    ``None`` 은 그 창의 무제한이다. **둘 다 미지정은 400**(브리프 §5).

    ``StrictInt`` — 검증 B1(2026-08-23, 오너 ⓐ): lax coercion 은 ``"77"``을
    77 로, ``true`` 를 **1 로 변환해 축소 예약까지 만들었다**. 숫자 문자열·
    불·소수는 전부 422 로 차단한다(음수·미지정은 라우터의 400 과 갈린다)."""

    reason: str
    daily_limit: StrictInt | None = None
    weekly_limit: StrictInt | None = None


class AdminQuotaSuspendRequest(BaseModel):
    """8.5-b — 정지·해제(즉시). 사유는 감사 행에 그대로 남는다(D3=ⓑ)."""

    reason: str


class AdminUserPayload(BaseModel):
    # Same no-password_hash reason as UserPayload, and one field more: the admin
    # list is the only surface where whether an account is disabled is the point.
    id: str
    username: str
    is_admin: bool
    is_active: bool
    # Signup approval axis, separate from ``is_active`` (see auth.models.User).
    # A pending row is stored with ``is_active=True``, so without this field the
    # admin list showed a signup request as "활성" — an account that cannot sign
    # in at all, labelled the same as one that can (owner 2026-08-27, dogfood).
    status: str


class AdminSignupPayload(BaseModel):
    # One pending signup request, as the admin approval queue shows it.
    # ``requested_at`` is the row's created_at — re-request over a rejected row
    # overwrites it, so it is genuinely "when this request was made".
    id: str
    username: str
    requested_at: datetime


class AdminSignupListResponse(BaseModel):
    requests: list[AdminSignupPayload]


class AdminUserListResponse(BaseModel):
    users: list[AdminUserPayload]


class CreateUserRequest(BaseModel):
    # The admin supplies the initial password, exactly as scripts/create_user.py
    # does. Generating and delivering a temporary one needs a channel this
    # deployment does not have.
    username: str
    password: str
    is_admin: bool = False


class ProjectPayload(BaseModel):
    id: str
    name: str
    archived: bool


class ProjectListResponse(BaseModel):
    projects: list[ProjectPayload]


NonBlankBriefString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"\S")
]

# 설명창 스칼라 필드(전제·장르·어조·시점)의 길이 상한 — 오너 지적(2026-08-27, "프로젝트
# 설명창에는 별도 제한이 없는 걸로 알고 있다")으로 D5-2 슬라이스에서 추가. 이 필드들은
# 생성 프롬프트의 <project_brief> 에 매번 렌더되므로 무제한이면 검색 조각 예산을 잠식한다.
# 1000자 = 문체 예시(PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS 기본값)와 같은 값. 배열 항목
# (constraints·style_rules·선호/금지 패턴)은 이번 범위 밖이다.
BriefTextField = Annotated[
    str, StringConstraints(
        strip_whitespace=True, min_length=1, pattern=r"\S", max_length=1000
    )
]


class AccessGrantCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # C-5: required, and non-blank. "왜 봤는가" is the whole value of the audit
    # record, and a blank string would satisfy a plain `str` while recording
    # nothing. The service re-checks so non-HTTP callers cannot skip it.
    reason: NonBlankBriefString


class AccessGrantPayload(BaseModel):
    id: str
    project_id: str
    admin_user_id: str
    reason: str
    created_at: datetime
    expires_at: datetime


class AccessGrantCreateResponse(BaseModel):
    grant: AccessGrantPayload


class AccessLogEntryPayload(BaseModel):
    grant_id: str
    admin_user_id: str
    method: str
    path: str
    at: datetime
    reason: str


class AccessLogResponse(BaseModel):
    entries: list[AccessLogEntryPayload]


class SceneNotePayload(BaseModel):
    """한 Scene 의 현재 메모(장면 메모 Slice 1).

    ``body is None`` 은 **메모 없음**이고 ``body == ""`` 는 **빈 메모 저장됨**이다 —
    저장 계약(SoT v1.8.11)이 그 둘을 구분하므로 읽기 표면도 구분해야 한다. 404 로
    답하지 않는 이유는 장면 없음(404)과 뒤섞이기 때문이다: 드로어가 메모 없는 장면을
    열 때마다 오류를 받게 된다.
    """

    draft_id: str
    body: str | None
    updated_at: datetime | None


class SceneNoteListItemPayload(BaseModel):
    """메모 목록 한 행. **본문 전문은 싣지 않는다.**

    상한이 12000자라 전문을 실으면 장면 200개에서 최악 240만 자(한국어 UTF-8 ≈7.2MB)가
    된다. 대신 ``body_preview`` 를 싣고 전문은 단건 GET 이 준다. ``truncated`` 는 화면이
    "더 보기"를 낼지 판단하는 신호다.

    ``chapter_archived`` 가 함께 있는 이유: 장을 보관해도 자식 Scene 의 ``archived`` 는
    바뀌지 않는데(장면 개별 보관과 구분되는 성질), 쓰기는 두 축 모두에서 막힌다. 한
    축만 실으면 화면이 "읽기 전용"을 잘못 표시한다.
    """

    draft_id: str
    scene_title: str
    scene_archived: bool
    chapter_id: str
    chapter_title: str
    chapter_archived: bool
    body_preview: str
    truncated: bool
    updated_at: datetime


class SceneNoteListResponse(BaseModel):
    notes: list[SceneNoteListItemPayload]


class ActivityEventPayload(BaseModel):
    """Phase 9 (A3=B) — 고정 코어 + 짧은 값 변화.

    ``before``/``after`` 는 **라벨**이다(이름·제목·상태). 본문은 여기 오지 않으며
    그 이력은 이미 ``draft_versions``+``source_snapshots`` 에 있다 — 두 정본을 만드는
    것이 A3=D 를 기각한 이유다.
    """

    id: str
    actor_user_id: str
    action: str
    target_type: str
    target_id: str
    at: datetime
    before: str | None = None
    after: str | None = None


class ActivityLogResponse(BaseModel):
    events: list[ActivityEventPayload]


class PersonalActivityEventPayload(ActivityEventPayload):
    """통합 활동 한 행 (Slice 9.2 P1=ⓐ, ``GET /me/activity``).

    project-scoped 응답과 **한 필드만 다르다** — ``project_id``. 그쪽은 주소가 이미
    프로젝트를 말하므로 넣지 않았고, 통합에서는 그것이 없으면 **행을 해석할 수 없다**
    (어느 원고의 저장인지 모른다). 상속으로 둔 것은 두 표현이 갈라지지 않게 하려는
    것이다 — 코어 필드가 늘면 양쪽이 함께 는다.
    """

    project_id: str


class PersonalActivityLogResponse(BaseModel):
    events: list[PersonalActivityEventPayload]


class AdminProjectPayload(BaseModel):
    # D8-5b. One field more than the public payload: `owner_id`, which is the
    # whole point of an administrator's list (whose project is this). The public
    # `_project_payload` deliberately still omits it — exposing ownership on the
    # product surface is a separate, deferred decision (D8-2c).
    id: str
    name: str
    archived: bool
    owner_id: str | None


class AdminProjectListResponse(BaseModel):
    projects: list[AdminProjectPayload]


class PurgeProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: NonBlankBriefString


class AdminAuditEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    operation_id: str
    admin_user_id: str
    action: str
    target_type: str
    target_project_id: str
    reason: str
    outcome: str
    at: datetime
    error_kind: str | None


class AdminAuditEventListResponse(BaseModel):
    events: list[AdminAuditEventPayload]


PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS = 3


PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS = 1000


def _project_brief_style_example_limits() -> tuple[int, int]:
    max_items = _env_int(
        "PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS",
        PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS,
    )
    max_chars = _env_int(
        "PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS",
        PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS,
    )
    for name, value in (
        ("PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS", max_items),
        ("PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS", max_chars),
    ):
        if value < 1:
            raise ValueError(f"{name} must be at least 1")
    return max_items, max_chars


def _writing_output_length_tokens() -> dict[OutputLength, int]:
    # 문체/분량 슬라이스 증분 2 (D3=A). The SERVER owns the preset→output-token
    # mapping; the confirmed defaults are 1024/2048/4096 and each is env-adjustable
    # with fail-loud validation (mirrors `_project_brief_style_example_limits`,
    # increment 1's sibling precedent). `short` defaults to the existing
    # WRITING_GENERATE_MAX_TOKENS so operators who already tuned it keep that value.
    presets = {
        OutputLength.SHORT: _env_int(
            "WRITING_OUTPUT_LENGTH_SHORT",
            _env_int("WRITING_GENERATE_MAX_TOKENS", 1024),
        ),
        OutputLength.MEDIUM: _env_int("WRITING_OUTPUT_LENGTH_MEDIUM", 2048),
        OutputLength.LONG: _env_int("WRITING_OUTPUT_LENGTH_LONG", 4096),
    }
    for length, value in presets.items():
        if value < 1:
            raise ValueError(
                f"WRITING_OUTPUT_LENGTH_{length.name} must be at least 1"
            )
    return presets


class ProjectBriefVersionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: NonBlankBriefString
    project_id: NonBlankBriefString
    version_number: Annotated[int, Field(ge=1)]
    premise: NonBlankBriefString | None
    genre: NonBlankBriefString | None
    tone: NonBlankBriefString | None
    pov: NonBlankBriefString | None
    constraints: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    style_rules: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    preferred_patterns: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    forbidden_patterns: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    style_examples: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )


class ProjectBriefGetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: ProjectBriefVersionPayload | None


class ProjectBriefPutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: ProjectBriefVersionPayload
    idempotent_replay: bool


class ProjectBriefVersionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    versions: list[ProjectBriefVersionPayload]


class DraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    chapter_id: str
    title: str
    archived: bool
    position: int = Field(ge=1)


class ScenePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    chapter_id: str
    title: str
    archived: bool
    position: int = Field(ge=1)


class ChapterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    title: str
    archived: bool
    position: int = Field(ge=1)
    scenes: list[ScenePayload]


class ChapterListResponse(BaseModel):
    chapters: list[ChapterPayload]


class DraftListResponse(BaseModel):
    drafts: list[DraftPayload]


class DraftVersionMetaPayload(BaseModel):
    # idempotency_key is intentionally absent: an internal save token, not part
    # of the public read surface (mirrors _version_meta_payload).
    id: str
    project_id: str
    draft_id: str
    version_number: int
    snapshot_id: str


class DraftVersionListResponse(BaseModel):
    versions: list[DraftVersionMetaPayload]


class SnapshotDetailPayload(BaseModel):
    id: str
    project_id: str
    draft_id: str
    version_id: str
    raw_text: str
    content_hash: str


class SourceBlockDetailPayload(BaseModel):
    id: str
    project_id: str
    snapshot_id: str
    block_index: int
    kind: BlockKind
    start_offset: int
    end_offset: int
    text: str


class DraftVersionDetailResponse(BaseModel):
    draft_version: DraftVersionMetaPayload
    snapshot: SnapshotDetailPayload
    blocks: list[SourceBlockDetailPayload]


class SavedDraftVersionPayload(BaseModel):
    id: str
    version_number: int
    snapshot_id: str


class SavedSnapshotPayload(BaseModel):
    id: str
    content_hash: str


class SavedSourceBlockPayload(BaseModel):
    id: str
    kind: BlockKind
    start_offset: int
    end_offset: int


class SaveDraftResponse(BaseModel):
    draft_version: SavedDraftVersionPayload
    snapshot: SavedSnapshotPayload
    blocks: list[SavedSourceBlockPayload]
    idempotent_replay: bool


class DraftVersionExportResponse(BaseModel):
    format: str
    filename: str
    content_type: str
    body: str
    project_id: str
    draft_id: str
    version_id: str
    version_number: int
    snapshot_id: str
    content_hash: str


class ProjectExportUnitModel(BaseModel):
    draft_id: str
    title: str
    chapter_id: str | None
    chapter_title: str | None
    chapter_position: int | None
    position: int | None
    version_id: str
    version_number: int
    snapshot_id: str
    content_hash: str


class ProjectExportManifest(BaseModel):
    project_id: str
    format: str
    include_archived: bool
    units: list[ProjectExportUnitModel]


class ProjectExportResponse(BaseModel):
    format: str
    filename: str
    content_type: str
    body: str
    project_id: str
    include_archived: bool
    manifest: ProjectExportManifest | None


# Project/draft naming constraint (SoT v1.6.95, D3=A). Validation lives at the
# HTTP boundary: every client reaches Core SOT through it, so rejecting here
# closes the blank-name hole without changing the Core SOT contract. Whitespace
# is stripped BEFORE min_length runs, so "  x  " is stored as "x" and a
# whitespace-only name is a 422 rather than a blank name in the canonical store.
NonBlankName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateProjectRequest(BaseModel):
    name: NonBlankName


class PutProjectBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version_id: NonBlankBriefString | None
    idempotency_key: NonBlankBriefString
    premise: BriefTextField | None
    genre: BriefTextField | None
    tone: BriefTextField | None
    pov: BriefTextField | None
    constraints: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    style_rules: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    preferred_patterns: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    forbidden_patterns: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )
    style_examples: list[NonBlankBriefString] = Field(
        json_schema_extra={"uniqueItems": True}
    )

    @field_validator(
        "constraints", "style_rules", "preferred_patterns",
        "forbidden_patterns", "style_examples",
    )
    @classmethod
    def reject_normalized_duplicates(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("brief arrays must not contain duplicates")
        return value

    @field_validator("style_examples")
    @classmethod
    def enforce_style_example_limits(cls, value: list[str]) -> list[str]:
        max_items, max_chars = _project_brief_style_example_limits()
        if len(value) > max_items:
            raise ValueError(f"style_examples must contain at most {max_items} items")
        if any(len(example) > max_chars for example in value):
            raise ValueError(
                f"style_examples entries must contain at most {max_chars} characters"
            )
        return value


class CreateAnalysisJobRequest(BaseModel):
    snapshot_id: str
    idempotency_key: str


class CreateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonBlankName
    chapter_id: NonBlankName


class CreateChapterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonBlankName


class ChapterOrderPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordered_chapter_ids: list[NonBlankName] = Field(
        json_schema_extra={"uniqueItems": True}
    )


class ChapterOrderPutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapters: list[ChapterPayload]


class SceneOrderPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordered_draft_ids: list[NonBlankName] = Field(
        json_schema_extra={"uniqueItems": True}
    )


class SceneOrderPutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenes: list[ScenePayload]


class RenameProjectRequest(BaseModel):
    name: NonBlankName


class RenameDraftRequest(BaseModel):
    title: NonBlankName


class SaveDraftRequest(BaseModel):
    raw_text: str
    idempotency_key: str

    @field_validator("raw_text")
    @classmethod
    def enforce_raw_text_limit(cls, value: str) -> str:
        # D5-2(오너 2026-08-27, "전 경로 4000자"): 유닛 본문 상한. accept 합성 경로는
        # writing/accept.py 가 같은 상수로 provider 호출 앞에 잰다 — 두 축이 같은 env 를
        # 읽는 것이 이 헬퍼가 app/env.py 에 있는 이유다(도메인이 api/ 를 import 못 한다).
        # ★ strip 전 길이로 잰다 — 이 경로가 저장하는 값이 strip 되지 않은 원문 그대로이기
        # 때문이다. accept 축은 strip 후 패치/씨앗을 재는데 그쪽도 같은 원리다(그 경로가
        # 그렇게 저장한다). 각 축은 자기가 저장하는 것을 잰다(2026-08-27 검증 보강 3).
        limit = draft_raw_text_max_chars()
        if len(value) > limit:
            raise ValueError(f"raw_text must contain at most {limit} characters")
        return value


class CreateSourceRefRequest(BaseModel):
    start_offset: int
    end_offset: int


class ContextPositionBody(BaseModel):
    draft_id: str
    version_id: str


class ApplyProposalBody(BaseModel):
    candidate_id: str
    action: str
    matched_memory_id: str | None = None


class ApplyMemoryRequest(BaseModel):
    proposals: list[ApplyProposalBody]


class ReconcileCharacterRequest(BaseModel):
    action: str


class EditCandidateRequest(BaseModel):
    payload: dict[str, object]


# 입력 ContextPackage 예산의 기본값(오너 지시 ④, 2026-07-28). 4096은 **동기 생성 시절 응답
# 속도** 때문에 고른 값이었고, 생성이 백그라운드 job + 푸시로 바뀌면서(v1.7.27) 그 제약이
# 사라졌다는 것이 오너의 근거다.
#
# **K-1(a)와 같이 올려야 하는 이유**: 회계가 `len/4`에서 `len/1.7`로 정직해지면서 같은 숫자가
# 뜻하는 실제 분량이 **절반**이 됐다(4096 회계 ≈ 실제 8,900 tok → ≈ 3,830 tok). 8192로 올리면
# 실효 분량이 종전과 비슷해지고(≈ 7,660 tok) 숫자는 정직해진다 — 즉 이 값은 확장이라기보다
# **회계 수정의 짝**이다.
#
# **★ 창 여유 — 이 값이 report 경로에 안전하다는 뜻은 아니다**(독립 검증 H1이 잡은 정정,
# 2026-07-30). 예산을 꽉 채운 프로젝트의 report 호출은 항목만이 아니라 **후보 산문까지** 싣는다.
# **2026-07-31 실측**(`scripts/report_budget_measure.py`, 베타 창 16384, 후보 = `long` 상한):
#
#   컨텍스트 8,358 + system 465 + 후보 산문 4,159 + 래퍼 94 + 출력 상한 6,144 = **19,220 > 16,384**
#
# 즉 창 16384에서 **2,836 넘는다**(종전 외삽치 −1,914보다 나쁘다 — 실제 렌더링이 외삽값보다
# 컸다). 후보 산문을 빼고 보면 "들어간다"로 오독하게 되는데, report는 그 산문을 대상으로 하는
# 호출이라 항상 함께 실린다. 통과하는 최대 예산은 실측 **5120**(여유 +386)이었다.
#
# **그래서 이 초과는 조용히 잘리지 않고 K-3 가드가 400으로 거부한다**(실측 delta 0: 가드가
# 보고한 input 13,076이 위 계산과 같다). 근본 해결은 **R-a**(report 전용 예산)이고, 형태와
# 숫자는 오너 결정 대기다(브리프 §2-5 — 상수 · 창에서 유도 · 출력 프리셋별의 세 갈래).
# 창 8192 배포에서는 더 일찍 걸리므로 알파는 `LLAMA_CTX_SIZE=16384`가 전제다(HANDOFF 함정).
# **이 경계는 예산을 꽉 채우는 프로젝트에서만 만난다** — 베타 프로브(회계 2,876)로는 닿지
# 않아 `--seed`가 그 재현 데이터를 만든다.
#
# 여섯 개 요청 모델이 같은 기본값을 쓴다. 리터럴을 복제하면 하나만 놓쳐도 endpoint마다 다른
# 예산이 되므로 상수로 둔다.
DEFAULT_CONTEXT_BUDGET_TOKENS = 8192


class ContextSearchHttpRequest(BaseModel):
    idempotency_key: str
    query: str
    needs: list[str]
    purpose: str = ContextSearchPurpose.WRITING_CONTEXT.value
    current_position: ContextPositionBody | None = None
    max_tokens: int = DEFAULT_CONTEXT_BUDGET_TOKENS


class WritingGenerateRequest(BaseModel):
    request_id: str
    instruction: str
    task_type: str = WritingTaskType.CONTINUE_SCENE.value
    draft_excerpt: str = ""
    # Retrieval query for the internal context search; defaults to the instruction.
    query: str | None = None
    current_position: ContextPositionBody | None = None
    # R-a(오너 2026-07-31): 생성이 끝나면 같은 패키지로 self-report가 돌고 그쪽이 창을
    # 구속하므로, 이 값은 **상한**이다 — 서버가 창에 맞춰 줄일 수 있으나 늘리지는 않는다.
    max_tokens: int = Field(
        default=DEFAULT_CONTEXT_BUDGET_TOKENS,
        description=(
            "Ceiling on the context-package (input) budget in tokens. The server "
            "may reduce it to fit the model's context window (R-a); never increased. "
            "Distinct from output_length (output tokens)."
        ),
    )
    # 증분 2 (D3=A): output-length preset (short|medium|long). The server maps it
    # to output tokens (1024/2048/4096 by default). Distinct from ``max_tokens``,
    # which is the input ContextPackage budget. Legacy clients omit it → short.
    # `long` (4096) is single-generate only; it is not a knob on revise-and-gate.
    output_length: str = OutputLength.SHORT.value


class WritingGateRequest(BaseModel):
    request_id: str
    instruction: str
    candidate_text: str
    task_type: str = WritingTaskType.CONTINUE_SCENE.value
    draft_excerpt: str = ""
    query: str | None = None
    current_position: ContextPositionBody | None = None
    max_tokens: int = DEFAULT_CONTEXT_BUDGET_TOKENS


class WritingReportRequest(BaseModel):
    request_id: str
    instruction: str
    candidate_text: str
    task_type: str = WritingTaskType.CONTINUE_SCENE.value
    draft_excerpt: str = ""
    query: str | None = None
    current_position: ContextPositionBody | None = None
    # R-a(오너 2026-07-31): 후보 산문을 곧바로 싣는 report 다리가 창을 구속하므로 이 값은
    # **상한**이다 — 서버가 창에 맞춰 줄일 수 있으나 늘리지는 않는다.
    max_tokens: int = Field(
        default=DEFAULT_CONTEXT_BUDGET_TOKENS,
        description=(
            "Ceiling on the context-package (input) budget in tokens. The server "
            "may reduce it to fit the model's context window alongside the candidate "
            "prose and report output (R-a); never increased."
        ),
    )


class WritingReviseFindingRequest(BaseModel):
    type: str
    severity: str
    message: str
    evidence: str
    recommended_decision: str


class WritingReviseRequest(BaseModel):
    request_id: str
    instruction: str
    candidate_text: str
    finding: WritingReviseFindingRequest
    task_type: str = WritingTaskType.CONTINUE_SCENE.value
    query: str | None = None
    current_position: ContextPositionBody | None = None
    # R-a(오너 2026-07-31, v1.7.66): 루프의 report 다리(출력 상한 6144 + 후보 산문)가 창을
    # 구속하므로 이 값은 **상한**이다 — 서버가 창에 맞춰 줄일 수 있으나 늘리지는 않는다.
    # 진입 시 1회 유도하며 그 값이 패키지 예산과 merge 상한을 함께 묶는다.
    max_tokens: int = Field(
        default=DEFAULT_CONTEXT_BUDGET_TOKENS,
        description=(
            "Ceiling on the context-package (input) budget in tokens. The server "
            "may reduce it once at loop entry to fit the model's context window "
            "alongside the candidate prose and report output (R-a); never increased. "
            "The derived value also bounds package growth from retrieve_more merges."
        ),
    )
    # Phase 5.9 L9 B (P2=B opt-in, 2026-07-13): persist this loop's audit only
    # when requested. None → env default (WRITING_LOOP_AUDIT_DEFAULT, off).
    persist_audit: bool | None = None


class NextUnitBody(BaseModel):
    # SoT v1.8.9: start_next_unit always creates the next Scene in the current
    # Chapter. `goal` is a required-but-nullable generation hint.
    # extra="forbid" matches the catalog's additionalProperties:false.
    model_config = ConfigDict(extra="forbid")
    title: str
    goal: str | None


class ObservabilityKpiSitePayload(BaseModel):
    call_site: str
    calls: int
    success: int
    provider_error: int
    parse_error: int
    total_tokens: int
    # The row count the token total was built from — ``provider_error`` rows are
    # excluded because their 0 means "unknown" (SoT v1.7.42).
    tokens_counted_from: int
    avg_latency_ms: int
    # Workflows this site served, and how many took more than one call. Not
    # named "repairs": a second row is a retry at a repair-shaped site but a
    # designed extra round inside the writing loop.
    correlations: int
    multi_call_correlations: int
    # K-3 창 헤드룸 경고(오너 2026-07-30): `창 − 입력 − 출력상한`이 창의 10% 미만인 호출 수와
    # **그 판정이 가능했던 행 수**(분모). 저장된 플래그가 아니라 원천 세 값에서 읽기 시점에
    # 파생한다(v1.7.59: 헤드룸은 저장하지 않는다). 분모가 함께 있어야 "빠듯한 호출이 없었다"와
    # "창을 아는 호출이 없었다"를 구분할 수 있다.
    thin_headroom_calls: int
    headroom_considered: int


class ObservabilityKpiTotalsPayload(BaseModel):
    calls: int
    success: int
    provider_error: int
    parse_error: int
    total_tokens: int
    tokens_counted_from: int
    thin_headroom_calls: int
    headroom_considered: int


class ObservabilityKpiGatePayload(BaseModel):
    scored_calls: int
    # Null, not 0.0, when nothing carried a score (SoT v1.7.47 known gap: loop
    # gate calls have none).
    avg_quality_score: float | None


class ObservabilityKpiLoopPayload(BaseModel):
    runs_considered: int
    non_convergence_rate: float | None


class ObservabilityKpiResponse(BaseModel):
    project_id: str
    totals: ObservabilityKpiTotalsPayload
    # A list, not a map keyed by call_site: the literals grow (5→8 in 증분 C,
    # more with Phase 7) and keying by them would change the generated frontend
    # type on every new site (owner decision 2026-07-26, D2=A).
    sites: list[ObservabilityKpiSitePayload]
    gate: ObservabilityKpiGatePayload
    loop: ObservabilityKpiLoopPayload


class AdminObservabilityKpiResponse(BaseModel):
    # D8-5c. Same four sections as the per-project read-out, and deliberately a
    # separate model: the two differ in exactly one field, and merging them would
    # force ``project_id`` to be nullable on a payload where it is always present.
    #
    # ``projects_considered`` replaces it — how many projects contributed a
    # record. It is the project axis this fold would otherwise lose, reported the
    # way every other counter-intuitive number here is (with its denominator),
    # and it names no project: which projects exist is the admin projects slice.
    projects_considered: int
    totals: ObservabilityKpiTotalsPayload
    sites: list[ObservabilityKpiSitePayload]
    gate: ObservabilityKpiGatePayload
    loop: ObservabilityKpiLoopPayload


class WritingAcceptRequest(BaseModel):
    request_id: str
    draft_id: str
    base_version_id: str
    idempotency_key: str
    instruction: str
    candidate_text: str
    task_type: str = WritingTaskType.CONTINUE_SCENE.value
    output_type: str = WritingOutputType.DRAFT_PATCH.value
    draft_excerpt: str = ""
    query: str | None = None
    current_position: ContextPositionBody | None = None
    # R-a(오너 2026-07-31, v1.7.66): accept도 report 다리(reporter.enrich)를 지나므로 이 값은
    # **상한**이다 — 서버가 창에 맞춰 줄일 수 있으나 늘리지는 않는다(후보 산문 추정 기반).
    max_tokens: int = Field(
        default=DEFAULT_CONTEXT_BUDGET_TOKENS,
        description=(
            "Ceiling on the context-package (input) budget in tokens. The server "
            "may reduce it to fit the model's context window alongside the candidate "
            "prose and report output (R-a); never increased."
        ),
    )
    # W3 Writing intent (§3.1). Legacy clients omit both → append_current/null.
    intent: str = WritingIntent.APPEND_CURRENT.value
    next_unit: NextUnitBody | None = None
