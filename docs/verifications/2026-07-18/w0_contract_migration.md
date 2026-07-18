# Verification — Writing Workspace V2 W0 계약/migration

## Subject metadata

- 날짜: 2026-07-18
- 요청자: 오너(독립 검증 요청 — “작업 AI가 작업한 거 확인해서 검증하고 의심하고 또 의심해줄래? 계약 자체가 제대로 되었는지, 실제로 UX상 편의가 고려되었는지, 추가 아이디에이션은 없는지”).
- 검증자: Claude(독립 adversarial 검증, `ultracode` session).
- 검증 대상 slice/artifact: W0 계약/migration slice — 신규 `docs/plans/writing-workspace-v2-w0-contract.md`(185행), 신규 `schemas/writing-workspace-v2-w0.schema.json`(275행), SoT v1.7.10 갱신 및 8개 정렬 문서.
- 정본 계약 참조: `docs/system-contract-sot.md` v1.7.10 changelog entry(`system-contract-sot.md:36`), `docs/plans/writing-workspace-v2-w0-contract.md`(W0 contract 자체), `docs/live_review_briefs/2026-07-18/writing_workspace_ux_restructure.md`(D1=A·D2=A·D3=C·D4=A·D5=A·D6=A·전체 C).
- 작업 소스: working tree, uncommitted(커밋 전). `git status`로 `docs/plans/writing-workspace-v2-w0-contract.md`, `schemas/` 신규 + 9개 문서 modified 확인.
- 방법론 스케일: 검증자 직접 정량 검증 + 53-agent 다차원 adversarial 워크플로우(5 dimension × review→적대적 verify + completeness critic).

## Scope

검증한 표면(각각 primary source에서 재도출):

1. **계약 boundary matrix** — W0 계약 §1/§2/§3 prose가 요구하는 모든 should-fire/should-NOT-fire 분기와 literal, 그리고 §4 매트릭스 37행(PB-01..11, OU-01..10, WI-01..16)의 direction·branch·test-name 정합성. 계약 자기모순 탐지.
2. **Schema ↔ 계약 literal 일치** — `schemas/writing-workspace-v2-w0.schema.json`의 19개 `$defs`가 계약 prose literal과 exact match하는지, draft 2020-12 metaschema 유효성, fragment(`#/$defs/...`) 단위 boundary enforcement, 특히 `writingAcceptRequestV2`의 intent↔next_unit discriminator.
3. **기존 runtime 호환성** — 계약이 “기존 runtime과 호환·runtime 무변”으로 참조하는 모든 literal/선례가 실존하고 일치하는지(`writing-accept:{key}`, `analyze:{snapshot_id}`, `_append_patch` 3분기, `continue_scene`/`draft_patch`, `test_lists_preserve_creation_order`, `_id ASCENDING`, save_draft transaction 범위), 그리고 runtime code가 정말 무변인지.
4. **정렬 문서 일관성** — 9개 정렬 문서 + 2개 신규 문서 간 v1.7.10, D-decision label, W-slice, “37행”, “runtime 무변”, “W0 complete/W1 next” 표현의 일관성과 stale 참조.
5. **UX 편의·추가 아이디에이션** — 5개 dogfood 결손에 대한 W0 해소 매핑, position 모델의 UX 함의, 추가로 owner에게 surface할 가치가 있는 빈 구멍/ideation.

out of scope: W0는 문서/schema slice로 runtime code가 없으므로, runtime 코드 수준의 실행 검증(migration runner, OpenAPI 실제 출력, frontend)은 불가능하며 이 기록에서도 수행하지 않는다.

## Methodology

- **독립 정량 검증(검증자 직접)**: 매트릭스 행 수·fire/not-fire 분포 grep 집계; `git diff --stat`·`git diff --check`; trailing whitespace 검사; `python3 -m json.tool` JSON 유효성; `jsonschema` (legacy `RefResolver`)로 fragment 기반 discriminator/constraint/unknown-key 검증(정상 6 + 거부 8 예제); runtime literal grep; `tests/test_application_api.py:165`·`core_sot/mongo_repository.py`·`accept.py` 직독.
- **다차원 adversarial 워크플로우**: contract-matrix / schema-alignment / runtime-compat / doc-alignment / ux-ideation 5 dimension. 각 dimension: review agent가 boundary matrix를 구축하고 finding을 제시 → 각 finding마다 독립 verifier가 **refute를 시도**(`is_real` default=false) → 별도 completeness critic이 5 dimension이 놓친 빈 칸을 탐지. 총 53 agent, 46 done, 7 일시적 에러(rate-limit/safety-classifier).
- **Boundary-matrix 우선**: 계약 prose를 먼저 읽어 required 분기/literal matrix를 구축한 뒤 §4 표가 그 matrix의 모든 칸을 채우는지 확인(CLAUDE.md “boundary matrix has no empty cells”).
- 재현 명령은 하단 “Reproduction” 참조.

## Findings

### Surface 1 — 계약 boundary matrix

매트릭스 산술과 direction 정합성은 정확하다.

- **행 수 정확**: PB=11 + OU=10 + WI=16 = **37행** 정확(`grep -oE '^\| (PB|OU|WI)-[0-9]+ \|'` = 37). fire/not-fire 분포: PB 5 fire/6 not-fire, OU 4 fire/6 not-fire, WI 7 fire/9 not-fire = **16 fire / 21 not-fire**(합 37). 워크플로우와 검증자 직접 집계가 일치.
- **prose ↔ matrix branch 매핑**: 대부분의 prose branch가 매트릭스 행으로 trace됨(워크플로우 CM 매핑표 참조). direction 할당이 일관됨. 예: PB-02 “brief 없음 GET은 404가 아니라 `brief=null`”을 not-fire로 둔 것은 over-strict(잘못 404) guard로 합리적.

하지만 **계약 prose가 명시적으로 요구하는 분기 중 매트릭스에 named 행이 없는 empty cell이 존재**한다.

- **(B1) `docs/plans/writing-workspace-v2-w0-contract.md:76`**: “archived project는 409, missing project는 404다” — `PUT .../draft-order`의 project-state 분기 2개(archived 409, missing 404). OU-01..10 중 어느 행도 이 두 분기를 lock하지 않는다. OU-08(`:158`)은 line 73의 permutation-content(missing draft id) → 409를 다루며 line 76의 project-state와는 **다른 조건·다른 코드**다. PB-11(`:150`)이 ProjectBrief PUT의 archived-project 409를 lock하는 것과 **비대칭**이다. line 19가 매트릭스를 W1~W4의 canonical lock list로 규정하므로, prose-required 분기의 행 부재는 empty cell이다.
- **(B2) `:76`** 의 missing-project reorder → 404: B1과 동일한 행에서 비롯. missing project 404가 framework routing 수준에서 자동 처리될 수 있어(PB-02가 GET brief의 404-vs-200을 명시 lock한 선례와 비교해) 약한 empty cell.
- **(B3) `:46`**: “project 없음/cross-project는 404” — `GET .../brief`의 missing/cross-project 404 분기. PB-02(`:141`)는 반대 방향(existing project + no version → `brief=null`)만, PB-10(`:149`)은 version read isolation만 lock. brief GET 404 분기를 lock하는 PB 행이 없다. B2와 마찬가지로 missing 404는 generic routing일 수 있어 약한 empty cell.

**양방향 가드 점검(under-strict/over-strict)**: empty cell 들은 “이 분기가 구현 누락되거나 잘못된 코드로 바뀌어도 잡을 named test가 계약에 없다”는 뜻이므로 양쪽 방향 모두 미보장이다. CLAUDE.md two-directional regression guard 관점에서, B1/B4(아래)는 under-strict(거부가 누락돼 잘못 accept)와 over-strict(정상 케이스를 잘못 거부) 양쪽 모두를 잠글 named 행이 필요하다.

- **(B4) `:88`**: non-transaction fallback — “project 전체 before-image 복원 또는 commit marker-last를 **회귀로 증명해야 한다**”고 prose가 명시적으로 요구. OU 행 중 이 fallback 경로 회귀를 lock하는 행이 없다(OU-07은 runtime transaction의 atomic reorder, OU-03은 input fail-closed로 서로 다른 분기). fallback은 local/test single-writer 전용이라 심각도는 낮지만, 계약이 “회귀로 증명”을 요구한 이상 named 행이 있어야 한다.

### Surface 2 — Schema ↔ 계약 literal 일치

Schema는 catalog(`$defs` 모음, 최상위 `type` 없음)로 설계됐고, **fragment(`#/$defs/...`) 단위 검증에서 boundary가 정확히 작동**한다.

- **검증자 직접 fragment 검증(`jsonschema` RefResolver)**: `writingAcceptRequestV2` discriminator — `append_current + non-null next_unit` ✅REJECT, `start_next_unit + null next_unit` ✅REJECT, `bad intent` ✅REJECT, `start + next_unit missing goal` ✅REJECT; 정상 `append+null`/`start+full`은 ✅PASS. `projectBriefVersion`: duplicate constraint ✅REJECT(uniqueItems), blank constraint ✅REJECT(`\S` pattern), unknown key ✅REJECT(additionalProperties:false), `version_number 0` ✅REJECT(minimum 1). `projectBriefPutRequest`: missing `idempotency_key` ✅REJECT, unknown key ✅REJECT. 워크플로우 SC-01/SC-02/CM-11과 동일 결론.
- **19개 `$defs` 모두 계약 literal과 exact match, draft 2020-12 유효**(SC-02 confirmed). discriminator의 oneOf+allOf+`unevaluatedProperties:false`가 §3.1 400 binding을 airtight하게 잠근다(SC-01 confirmed).
- **주의점(H-schema-catalog)**: catalog 형태라 **최상위에 `type`/제약이 없다**. consumer가 schema 전체를 OpenAPI `schema:`로 직접 참조하면 어떤 페이로드든 통과한다. schema description이 “Consumers select an exact operation or entity through a `#/$defs/...` fragment”로 명시하므로 설계는 의도적이지만, W0 계약 본문에도 “반드시 fragment로 소비” 경고가 더 명시적이어야 하며, W2/W3 OpenAPI 연동 시 fragment 참조 방식을 잠가야 한다(SC-03/SC-06은 이 맥락의 hardening 후보).
- **(H-uniqueItems)** `:62`/`:39` schema의 `constraints` `uniqueItems`는 raw array에 작동한다. 계약 §1.1 `:40`는 “각 원소를 trim한 뒤 blank/duplicate면 422”를 요구하므로, `["a", " a"]`(trailing space)는 runtime은 422지만 schema `uniqueItems`는 통과시킨다. schema가 runtime trim-then-dedupe를 표현하지 못하는 한계이며, schema ↔ runtime validation의 차이를 계약/Schema 주석에 명시해야 한다(CM-03 confirmed).
- **NO-VERDICT(일시적 에러) 후보 검증자 확인**: `draftV2`가 `additionalProperties:false` + required `[id, project_id, title, archived, unit_kind, position]`. 현재 runtime `Draft`(core_sot/models.py)은 id/project_id/title/archived만 가지므로 schema가 기존 field를 배제하지 않는다(정합). 단 W3에서 Draft에 field가 추가되면 schema도 함께 갱신해야 하는 유지보수 함의(H-draftV2-lock).

### Surface 3 — 기존 runtime 호환성

계약이 참조하는 runtime literal/선례는 **모두 실존하고 일치**하며, **runtime code는 실제로 무변**이다.

- `writing-accept:{idempotency_key}` — `services/application/app/writing/accept.py:72`에 verbatim 존재(RT-01 confirmed).
- `analyze:{snapshot_id}` — `accept.py:21`·`:29`(`analysis_job_key`)에 verbatim 존재(RT-02 confirmed).
- `_append_patch` 3분기(base empty→candidate only / newline end→exact concat / else `\n\n`) — `accept.py:168-173`이 §3.2와 정확 일치, empty-base case 포함(RT-03 confirmed).
- `continue_scene`/`draft_patch` only-supported — `accept.py:139`·`:141`(`only continue_scene is supported` / `only draft_patch is supported`), `models.py:24`/`:31`(RT-04, verify는 일시적 에러였으나 검증자 grep으로 confirmed).
- `test_lists_preserve_creation_order` — `tests/test_application_api.py:165-188`에 실존. project 3개·draft 3개 생성 후 GET list 순서 == 생성 순서를 assert. `_id ASCENDING` 정렬(`core_sot/mongo_repository.py:154`)과 함께 W0 §2.3 “현재 repository list 순서로 읽는다(_id 오름차순)”의 유효한 선례(RT-05 confirmed). **뉘앙스(RT-09/H-precedent)**: 테스트는 행동적 생성-순서 보존을 lock하지, “ObjectId `_id` ascending == 생성 순서”라는 *구현 가정*을 직접 lock하지는 않는다. id 체계가 바뀌면 근거가 약해지므로 §2.3 “이미 잠근 선례” 표현은 약간 과장. hardening 후보.
- **save_draft transaction 범위** — `core_sot/mongo_repository.py:224-285`(`_record_save_transactional`, `session.start_transaction()` 내 version+snapshot+blocks 동시 commit). W0 §3.2 “default Mongo runtime의 원자성 범위는 이 여섯 표면” 주장은 이 기존 transaction 인프라 위에 position shift+Draft+receipt를 더하는 것이므로 근거 유효. 단 RT-08 지적대로 **6-surface 원자성은 start_next_unit을 위한 NEW 요구**(현재 append는 3-surface)이므로, “default Mongo runtime의 원자성 범위는…”이라는 표현은 기존 범위를 기술한다기보다 W3가 구현해야 할 범위를 규정하는 것으로 읽혀야 한다(H-atomicity-phrasing).
- **runtime 진짜 무변** — `git diff --stat`에 `services/`·`frontend/` 파일이 전혀 없음(RT-06 confirmed). worker의 “runtime 무변” 주장은 사실.
- **append save-key-only replay 호환** — 현재 `accept.py:80-87`이 version의 `idempotency_key == save_key`로 replay lookup하므로 §3.3:130 “receipt migration 없이 계속 replay 가능”이 오늘도 성립. 단 **이 read-through를 lock하는 WI 행이 없다(B4-류, 아래 Issues)**.

### Surface 4 — 정렬 문서 일관성

v1.7.10 갱신과 W0-complete/W1-next flip은 **모든 정합 표면에서 일관**된다.

- v1.7.10 stamping이 정확히 SoT header/`:36` changelog/CHANGELOG 최상단 행/schema `x-contract-version`/계약 header에 모두 존재(CD-01 confirmed). stale “현재 v1.7.9”는 action 가능 위치에 없다.
- W0-status flip: UX brief·decisions brief·HANDOFF Current Status·HANDOFF Next Tasks·product-shell·product-readiness-backlog·plans/README(신규 entry 36)가 모두 “W0 complete, W1 next”로 전환(CD-02 confirmed).
- 37행 count가 계약·SoT·CHANGELOG·work log에서 일관(CD-03 confirmed).
- “runtime unchanged / v1.7.8과 동일” 주장이 일관, 모순 위치 없음(CD-04 confirmed).
- W0 scope와 D-decision label(D1=A·D2=A·D3=C·D4=A·D5=A·D6=A·전체 C)이 SoT changelog·계약·CHANGELOG·work log에서 일관(CD-05 confirmed).
- **(H-cross-version)** §2.3:88 “SoT v1.4와 동일하게” — v1.4 시점 fallback 계약을 참조하는데, v1.4 원문이 v1.7.10 체계에서 동일한지 교차 검증되지 않았다(GAP-11). historical anchor이므로 비차단이나 명시적 인용 검증 권장.

### Surface 5 — UX 편의·추가 아이디에이션

- **dogfood 결손 5개 → W0 해소 매핑**: clean하게 매핑됨(UX CM-04 confirmed). 작품 정보 부재→ProjectBrief, append/next 구분→intent discriminator, editor↔review 왕복→W1(saved-target/position 계약이 source deep-link를 enable), overview 부재→W2, ordered export 부재→W4(position이 enable).
- **position 모델 내부 일관(UX CM-05 confirmed)**: §2.1 “archived 포함 연속 순열” + §2.2 “reorder에 archived 포함” + §3.2 “shift도 archived 포함”이 맞물려 archive해도 gap이 생기지 않는다. 검증자가 우려했던 “archive 후 gapped position”은 연속순열 불변식이 방지함.
- **(H-archived-slot)** 다만 함의로, archived가 position 슬롯을 계속 점유하므로 active-only UI 표시와 내부 position이 다를 수 있다. 계약은 일관적이나 W1 UX-relevant. UX-02 partially-correct.
- **intent discriminator hook(UX CM-06 confirmed)**: §3.1 binding이 W1 radio/segmented control(brief D3=C 권고)에 잘 설계됨.
- **(H-no-delete)** ProjectBrief no-DELETE + all-null=cleared(PB-09)가 논리적으로 clean하나 사용자의 “delete” mental model과 충돌 가능(UX-04 confirmed). “시작 정보 지움/온보딩 건너뜀” 표현을 UI에서 명확히 해야.
- **(H-migration-other-label)** migration이 모든 legacy draft를 `unit_kind=other`로 라벨링 → post-migration UI가 기존 원고를 전부 “other”로 표시. 사용자가 chapter/scene으로 재분류해야 하는 부담(UX-05 confirmed). 일회성 onboarding UX 권장.
- **(H-provenance)** ProjectBrief ↔ Draft provenance가 untracked. brief v3에서 생성된 draft가 brief 변경 후에도 그대로(UX CM-03 confirmed). 의도적(append-only 원칙)이나 “이 draft가 어느 brief에서 생성됐는가”를 W2 overview에서 보여줄지 owner 결정 후보.
- **(H-migration-ops)** migration fail-closed per-project(§2.3 step 4)에 operator 진단·재실행 UX가 없다(UX-06 partially-correct). 실패 project 보고는 계약에 있으나 운영 동선은 W3 배포 시 별도.
- **(H-migration-concurrency)** §2.3 migration one-shot idempotent이나, migration 중 write 경쟁·동시 migration에 대한 언급이 없다(GAP-08). unique index 설치 시점이 명시적이지 않다.
- **(H-manifest-terms)** §5가 “saved publication manifest”를 defer하는데 W4(D6=A)는 “별도 manifest”가 필요 — 용어가 중복/혼용되어 W4 설계 시 혼란 위험(GAP-09).

## Issues / Risks

### Blocking(contract obligations — boundary matrix empty cells)

CLAUDE.md “boundary matrix has no empty cells — empty cells are blocking findings” + “If a contract-required lock is missing, the verdict is 조건부 합격 or 불합격 until the lock is added, not 합격 with risks”에 따라, 아래는 verdict을 결정하는 blocking 항목이다. 모두 **문서/매트릭스 수준의 보강**(runtime code 변경 아님, W0은 문서 slice)으로 해결 가능하다.

- **B1 — `:76` archived project reorder → 409, OU 행 없음**: OU matrix에 named not-fire 행 추가 제안(`OrderedUnitApiTest::test_archived_project_reorder_rejected`). PB-11(ProjectBrief archived 409)과의 비대칭 해소.
- **B2 — `:76` missing project reorder → 404, OU 행 없음**: OU matrix에 named 행 추가 **또는** 계약에서 “missing project 404는 framework routing이 자동 처리”로 명시적 분류. 약한 empty cell.
- **B3 — `:46` GET brief missing/cross-project → 404, PB 행 없음**: PB matrix에 named 행 추가 **또는** framework routing 명시적 분류. 약한 empty cell.
- **B4 — `:88` non-transaction fallback before-image/commit-marker-last 회귀, OU 행 없음**: 계약이 “회귀로 증명해야 한다”고 명시하므로 OU matrix에 named fire 행 추가 제안(`OrderedUnitMigrationTest::test_nontransaction_fallback_restores_before_image`).
- **C1 — `:130` append save-key-only legacy record read-through replay, WI 행 없음**(워크플로우 ux CM-02 = GAP-03, verifier가 hardening→**blocking 승격**): §3.3:130이 “W3 구현은 이를 read-through해 동일 response를 구성”이라고 **특정 동작을 명시**하는데, WI-09(START replay)·WI-13/14(START partial)만 있고 APPEND read-through를 lock하는 named 행은 없다. WI-12 “append 호환 유지”가 포괄할 수 있으나 특정 분기를 lock하는지 불명확 → named 행 추가 또는 WI-12 범위를 계약에서 명시.
- **C2 — replay precedence over stale base/Gate(accept path), WI 행 명시적 부재**(GAP-02): §1.2:51·§3.3:126이 “replay lookup은 stale base/Gate보다 먼저”를 요구하나 accept에 대한 named 행이 없음. WI-09/WI-12 부분 커버.
- **C3 — append-intent analysis partial 502 + replay convergence, START(WI-13/14)에만**(GAP-04): §3.2:122 “job 생성 실패는 기존과 같은 502 partial-success... replay로 같은 job 생성에 수렴”이 append에도 적용되나 named 행이 START intent에만 존재.

참고: B1/B4/C1은 “엄격 해석 시 명백한 empty cell”이고, B2/B3/C2/C3은 “WI-12 등 포괄 행 또는 framework routing에 의존”할 여지가 있어 계약에서 명시적 분류하면 닫힐 수 있다. 어느 쪽이든 boundary matrix의 빈 칸을 **named 행 추가 또는 계약 명시적 분류** 둘 중 하나로 닫아야 verdict이 합격으로 올라간다.

### Hardening recommendations(계약을 넘어서는 보강 후보 — non-blocking, slice를 fail시키지 않음)

- H-schema-catalog: catalog fragment 사용 경고를 W0 계약 본문에 명시; W2/W3 OpenAPI fragment 참조 방식 잠금.
- H-uniqueItems: schema `constraints` uniqueItems가 trim-then-dedupe를 못 표현하는 한계를 schema 주석 + 계약 §1.1에 명시(runtime validation과 schema의 역할 분리).
- H-draftV2-lock: W3에서 Draft field 추가 시 `draftV2` schema 동기 갱신 필요를 계약/Schema에 메모.
- H-precedent: §2.3 “잠근 선례”가 ObjectId `_id` ascending == 생성 순서 가정에 의존함을 명시(id 체계 변경 시 회귀 보강).
- H-atomicity-phrasing: §3.2 “default Mongo runtime의 원자성 범위는…”을 “W3가 구현해야 할 6-surface 원자 범위”로 의미를 명확화(현재 append는 3-surface).
- H-archived-slot: archived position 점유 함의를 W1 UX 수용 기준에 명시.
- H-no-delete / H-migration-other-label / H-provenance / H-migration-ops / H-migration-concurrency / H-manifest-terms: 위 Surface 5 항목들. owner 평가 후보.
- H-502-literal / H-analyze-key-start: 502 partial literal, START path의 `analyze:{snapshot_id}` literal이 매트릭스에 직접 pin되지 않음(GAP-06/GAP-07).

### Positive strengths(verified 강점)

37행 산술·schema discriminator·19개 `$defs` exact match·runtime literal 전부 실존+일치·runtime 진짜 무변·v1.7.10 stamping·W0-status flip·D-decision 일관·dogfood 결손 매핑·position 모델 내부 일관·intent hook 설계 — 모두 adversarial verify에서 confirmed(SC-01/02, RT-01~07, CD-01~05, UX CM-04/05/06, CM-11). W0의 핵심 산출물은 구조적으로 건전하다.

## Verdict

**조건부 합격(conditional pass)**.

하중 이유(load-bearing):
1. W0의 핵심 산출물 — 계약 문서·JSON Schema·37행 매트릭스 — 은 구조적으로 건전하고, runtime 호환·문서 정렬·UX 매핑이 다수의 adversarial verify에서 confirmed됨(강점 참조). 계약은 자기모순하지 않고 schema는 fragment 단위에서 boundary를 정확히 enforce한다.
2. **그러나 매트릭스에 verified empty cells가 존재**한다(B1·B4는 명백한 empty cell; B2·B3·C1·C2·C3는 framework-routing/WI-12 포괄 해석에 의존). CLAUDE.md “boundary matrix has no empty cells — empty cells are blocking” + “missing contract-required lock → 조건부 합격 or 불합격, not 합격 with risks”에 따라, 이 empty cells가 named 행으로 채워지거나 계약에서 명시적으로 분류되기 전까지는 합격이 아니다.
3. 다행히 모든 empty cell은 **문서/매트릭스 수준 보강**(named 행 추가 또는 계약 명시적 분류)으로 해결되며, runtime code 변경을 요구하지 않는다(W0은 문서 slice). 따라서 “불합격(계약 자체 결함)”이 아니라 “조건부 합격(매트릭스 coverage 보강 조건)”이 공정하다. 계약의 의미론적 정확성은 높고, 빈 칸은 coverage 누락이지 계약 모순이 아니다.

**합격으로 올리기 위한 조건**: B1·B4는 named 행 추가 필수; B2·B3는 named 행 추가 또는 framework-routing 명시적 분류; C1은 named 행 추가 또는 WI-12 범위 명시화; C2·C3는 named 행 추가 또는 기존 포괄 행의 범위를 계약에서 명시. 이 보강이 이뤄지면 합격(PASS).

이 검증은 owner가 요청한 독립 검증이며, 검증자는 defect를 silent하게 fix하지 않는다(CLAUDE.md). empty cell 보강 방향(행 추가 vs 명시적 분류)은 owner 결정 사항이다.

## Outstanding items

- 검증 대상은 working tree, **uncommitted** 상태. owner가 W0을 커밋하려면 먼저 위 blocking empty cells 보강을 결정하는 것이 권장된다(보강 없이 커밋하면 W2/W3 구현자가 놓칠 수 있는 boundary가 정본에 남는다).
- 검증 과정에서 7개 agent가 일시적 에러(rate-limit/safety-classifier)로 verify를 건너뛰었다(CM-08/SC-03/SC-06/RT-04/RT-07/CD-06/CD-07). 이 중 코드 수준 결론에 영향을 주는 것은 없었고(검증자 직접 grep·직독으로 보충), 나머지는 hardening 후보로 전환됐다.
- runtime은 무변이므로 전체 test suite 재실행은 불필요(worker의 판단과 일치). 다만 W0은 문서/schema slice이므로 runtime 회귀 자체가 발생할 표면이 없다.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# 1. 매트릭스 행 수·분포 (37행, fire 16/not-fire 21)
grep -oE '^\| (PB|OU|WI)-[0-9]+ \|' docs/plans/writing-workspace-v2-w0-contract.md | wc -l
grep -oE '^\| (PB|OU|WI)-[0-9]+ \| fire \|' docs/plans/writing-workspace-v2-w0-contract.md | wc -l
grep -oE '^\| (PB|OU|WI)-[0-9]+ \| not fire \|' docs/plans/writing-workspace-v2-w0-contract.md | wc -l

# 2. runtime 무변 (services/·frontend/ 미포함)
git diff --stat | grep -E "services/|frontend/" && echo CHANGED || echo UNCHANGED

# 3. JSON 유효성 + whitespace
python3 -m json.tool schemas/writing-workspace-v2-w0.schema.json >/dev/null && echo VALID
grep -nE ' +$' docs/plans/writing-workspace-v2-w0-contract.md schemas/writing-workspace-v2-w0.schema.json

# 4. Schema fragment discriminator 검증 (legacy RefResolver)
python3 - <<'PY'
import json, warnings; warnings.filterwarnings("ignore")
from jsonschema import Draft202012Validator, RefResolver
schema = json.load(open("schemas/writing-workspace-v2-w0.schema.json"))
r = RefResolver(base_uri=schema["$id"], referrer=schema)
v = Draft202012Validator({"$ref":"#/$defs/writingAcceptRequestV2"}, resolver=r)
common = {"request_id":"r","draft_id":"d","base_version_id":"b","idempotency_key":"k",
  "instruction":"i","candidate_text":"c","task_type":"continue_scene","output_type":"draft_patch",
  "draft_excerpt":"e","query":None,"current_position":{"draft_id":"d","version_id":"v"},"max_tokens":1}
nu={"title":"t","unit_kind":"chapter","goal":"g"}
for name,p,must in [("append+null",{**common,"intent":"append_current","next_unit":None},True),
  ("start+full",{**common,"intent":"start_next_unit","next_unit":nu},True),
  ("append+nonnull(REJECT)",{**common,"intent":"append_current","next_unit":nu},False),
  ("start+null(REJECT)",{**common,"intent":"start_next_unit","next_unit":None},False)]:
  errs=list(v.iter_errors(p)); ok=len(errs)==0
  print(f"{name}: ok={ok} expect_ok={must} {'PASS' if ok==must else 'WRONG'}")
PY

# 5. 참조 runtime literal 실존
grep -n "writing-accept:\|analyze:{\|def _append_patch\|only continue_scene\|only draft_patch" services/application/app/writing/accept.py
grep -n "test_lists_preserve_creation_order" tests/test_application_api.py
grep -n 'sort("_id", ASCENDING)' services/application/app/core_sot/mongo_repository.py

# 6. empty cell 후보 직접 확인 (§2.2:76, §1.2:46, §2.3:88, §3.3:130 prose vs 매트릭스 행 부재)
sed -n '76p;88p;130p' docs/plans/writing-workspace-v2-w0-contract.md
sed -n '46p' docs/plans/writing-workspace-v2-w0-contract.md
```
