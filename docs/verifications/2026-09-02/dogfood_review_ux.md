# 2026-09-02 독립 검증 — dogfood 분석·검토 UX 보강 (d02837a)

## Subject metadata

- 검증일: 2026-09-02
- 요청자: 오너 ("검증하고 의심하고 또 의심")
- 검증자: Claude Code (세션 독립 검증)
- 대상: 커밋 `d02837a` "Improve dogfood analysis review UX" (main, 작업 트리 clean)
- 정본 참조: `docs/system-contract-sot.md` **v1.8.15**, `docs/plans/final-save-analysis-decisions.md` §2026-09-02, `docs/plans/frontend-review-inbox-decisions.md` §2026-09-02, `docs/plans/pending-candidate-identity-grouping-decisions.md`
- 환경: WSL2 호스트, python3.12 · pytest 9.0.2 · pydantic 2.12.5 · fastapi 0.127.0 · `elasticsearch` 패키지 설치됨. test-mongo(127.0.0.1:27020) 기동 상태(이 슬라이스 셀은 전부 InMemory라 무관). 개발 스택(application·mongo·gateway 등)은 다운, admin·worker·generation_worker는 mongo 부재로 crashloop — 슬라이스 무관 환경 관측치.

## Scope

1. 슬라이스 3개 구현 축(① finalize 진행 표시·수렴 ③ Scene 목록 finality/분석 상태 ④ 검토함 목록 payload·즉시 승인/거절)의 코드·계약·회귀 전체
2. 2번(중복 후보 identity grouping) 결정 브리프의 구조·사실 전제
3. 작업 로그가 보고한 검증 범위와 실제 재현 가능성(집중 셀 수, "교착" 주장 포함)

## Methodology

- 계약 읽기: SoT v1.8.15 행과 두 계획 문서 증분, `models.py`·`routers/drafts.py`·`routers/analysis.py` 리터럴 대조.
- 실행 재현: `python3 -m pytest tests/test_docs_indexes.py tests/test_chapter_hierarchy.py -q` 등 아래 Reproduction 전체.
- 500 폭발 반경 실증: InMemory 서비스로 `create_app` 조립 + `TestClient(raise_server_exceptions=False)` 프로브(`/tmp` 스크립트, 아래 Reproduction 참조).
- 회귀 귀속: `git worktree add /tmp/wt-head1 5ec69f6` 후 동일 suite 3종 재실행, worktree 제거로 원본 트리 무변경 확인.
- 변이 검증: 트리 clean 확인(사전 게이트 `git status --short` 0줄) 후 변이 → 집중 셀 재실패 확인 → `git checkout -- <path>` 복원 → clean 재확인(매 변이마다).

## Findings

### 1. 슬라이스 코드 축 (frontend 3파일 + backend payload)

- ① 진행 표시: `DraftEditor.tsx:374` finalize 직전 `setAnalysisStatus("running")`, `analysisRunning` 우선순위(`DraftEditor.tsx:215-221`), 응답 수렴은 page reload 없이 `setDraft`/`setVersions`로 완결. SoT 문언과 일치.
- ③ Scene 목록: `DraftList.tsx:11-26` snapshot 동일성으로 finality 3상태·분석 4상태 텍스트 파생, `styles.css` 색은 보조. 백엔드 `_scene_payload`(`routers/drafts.py:128-152`)가 `ScenePayload`(`api/models.py:563-573`)에 맞게 5필드 additive. `analyze:{snapshot_id}` idempotency key는 기존 관례(`drafts.py:101`·`729`·`733`)와 동일.
- ④ 검토함: `routers/analysis.py:802` list item에 `payload` additive(라우트에 `response_model` 없음 — 838-840 — 검증 안전), detail은 source/conflict 유지. `client.ts` `ReviewInboxItem.payload` 이동 일관.
- SoT v1.8.15 "operation 수 무변" 확인(신규 라우트 0).

### 2. 회귀 테스트 (test code as audit subject)

- `DraftEditor.test.tsx:2048` in-flight 셀: pending promise로 요청 중 "분석 진행 중"+버튼 비활성+완료 수렴 양방향 잠금. 기본 `draft` fixture(`DraftEditor.test.tsx:71`)가 analysis 필드 없음 → attention 참인 상태에서 running 우선순위까지 잠금.
- `DraftList.test.tsx:70-118`: 3상태 표시 + "최종 저장 후 수정됨 · 분석 필요" over-strict 방향 잠금.
- `ReviewInbox.test.tsx`: payload 렌더 잠금(name/observation 축).
- `tests/test_chapter_hierarchy.py:457-460`: scene 신규 필드 **presence만** 단정(값 미잠금 — 아래 Blocking 2).
- `tests/test_analysis_apply_api.py:571`: `assertEqual(item["payload"], dict(current.payload))`로 list payload 값 잠금.

### 3. 재현 실행 (검증자 실측)

- 프론트 집중 3파일: **86 passed** (55.8s) — 작업 로그 주장과 일치.
- `npx tsc --noEmit` rc=0, `npm run build` 성공(진입 445.71 kB), `npm run gen:api` 후 **트리 무차이** — schema.d.ts는 최신이며 `DraftPayload`에는 `latest_snapshot_id`가 없음(오직 `ScenePayload`만 수령).
- `tests/test_docs_indexes.py` 단독: **13 passed, 279 subtests**. `tests/test_chapter_hierarchy.py` 단독: **17 passed, 4 subtests**. 작업 로그의 "15 passed, 279 subtests"는 어떤 선택 집합으로도 정확히 재구성되지 않음(279는 docs 단독 subtest 수와 일치, 15는 불명).
- **"교착" 주장 재현 불가**: `ReviewInboxApiTest::test_list_unifies_candidate_with_open_conflict` 단독 **4.2s 통과**, 파일 전체(`tests/test_analysis_apply_api.py`, 38셀)도 교착 없이 23.1s 완료(37 passed, 1 failed — 아래 Blocking 1). 작업 로그에 교착을 일으킨 정확한 명령이 기록되지 않아 제3자 재현 불가.

### 4. 변이 검증 (모두 적용→재실패→`git checkout --`→clean 확인)

| 변이 | 내용 (적용 diff) | 결과 |
|---|---|---|
| M1 | `DraftEditor.tsx` finalize에서 `setAnalysisStatus("running");` 한 줄 삭제 | DraftEditor.test **1 failed** (in-flight 셀) — 물림 |
| M2 | `analysisLabel` 3항 순서를 attention→running으로 원복 | DraftEditor.test **1 failed** — 물림 |
| M3 | `sceneAnalysisLabel`의 `current`에서 `analysis_snapshot_id === latest` 동일성 제거 | DraftList.test **1 failed** (수정 후 오인 셀) — 물림 |
| M4 | `sceneFinalityLabel`이 marker 존재만 보고 `"최종 저장됨"` 고정 | DraftList.test **1 failed** — 물림 |
| M5 | `routers/analysis.py:802`(list payload) 한 줄 삭제 | ReviewInboxApiTest list 셀 **1 failed** — 물림 (첫 시도는 동일 문자열 2곳(`analysis.py:124`·`:802`)로 assert 중단, 파일 무변) |
| M6 | `_scene_payload`의 `analysis_snapshot_id` 출력 삭제 | test_chapter_hierarchy **1 failed** (presence 가드) — 물림 |
| M7 | `_scene_payload` job lookup key를 `analyze-broken:`로 왜곡 (단독) | test_chapter_hierarchy green — 단, 이때의 유일 실패는 변이 전부터 있던 S1-S13 실패(마스킹) |
| M7b | flat `latest_snapshot_id` 출력 삭제(500 중립화) + M7 왜곡 동시 적용 | chapter+final_save+scene_notes **67 passed** — **아무 가드도 물지 않음** |

### 5. 결정 브리프 (`pending-candidate-identity-grouping-decisions.md`)

- 구조: Decision needed / Options 표(`선택지·설명·장점·단점` 4열) / Recommendation + reason / Follow-up / Deferred 전부 구비 — CLAUDE.md 요건 충족.
- 사실 전제 확인: `analysis/compare.py:1-16` 모듈 서두가 명시적으로 "candidate ↔ canonical-memory compare"이며 pending↔pending 대조 경로 없음 — 브리프의 공백 진단은 정확.

## Issues / Risks

### Blocking (판정 결정)

1. **P0 — flat Draft 경로 5종이 500(계약 위반).** `_draft_payload`(`routers/drafts.py:110`)가 이번에 `latest_snapshot_id` 출력을 더했으나 `DraftPayload`(`api/models.py:547-559`, `extra="forbid"`)에는 그 필드가 없다. 실증(프로브, TestClient): `POST /drafts`(장면 생성)·`GET /drafts`(플랫 목록)·`GET /drafts/{id}`(**에디터 로드 — 프론트 `client.ts:487` getDraft가 사용**)·`PATCH /drafts/{id}` 전부 **500** (`ResponseValidationError: extra_forbidden latest_snapshot_id`). 중첩 `GET /chapters`(ScenePayload)만 200. SoT v1.8.15·계획 문서 어디에도 flat DraftPayload 변경은 없다(계약 침묵 + 코드 시행). 기존 suite 실측: `tests/test_scene_notes_api.py` **31 failed**, `tests/test_final_save_analysis.py` **1 failed**(S1-S13), `ReviewInboxApiTest` 1 failed. 부모 `5ec69f6`에서는 48/2/1 전부 통과 — **d02837a 도입 회귀 확정**. M7b로 폭발 반경이 이 한 줄임도 확인(삭제시 67셀 green). 최소 수정은 해당 줄 제거이나, 검증자는 침묵 수정하지 않는다(오너 지시 대기. 필드를 계약에 올리는 방향도 가능하나 그 경우 DraftPayload·OpenAPI·schema.d.ts·SoT 개정이 함께 가야 한다).
2. **계약 요구 분기의 값 수준 잠금 부재.** SoT v1.8.15가 "최신 snapshot analysis job 상태"를 scenes[]에 요구하나, 백엔드 값 파생(job lookup idempotency key·snapshot 일치)을 잠그는 셀이 없다 — M7b에서 key 왜곡이 어떤 suite도 물지 않았다. presence 단정(`test_chapter_hierarchy.py:457-460`)은 필드 존재만 본다. 파생이 깨지면 모든 장면이 조용히 "분석 필요/미실행"으로 표시된다.
3. **검증 범위·보고 정확성.** (a) "교착" 주장이 이 호스트에서 재현되지 않고(4.2s 통과) 작업 로그에 재현 가능한 명령이 없다 — 교착 기록이 유일한 TestClient suite를 스킵한 것을 정당화했고, 그 suite가 P0를 잡았을 자리였다. (b) "15 passed, 279 subtests"는 재구성 불가(docs 단독 = 13/279). (c) 관련 broader suite(scene_notes·final_save 등)가 완료 전 실행되지 않았다.

### Hardening recommendations (비차단)

- 최초 저장 없이 finalize를 바로 누르는 장면(versions=[] → `latestSnapshotId=null`)에서 비행 중 라벨이 "미실행"으로 남는다(버튼은 "최종 저장·분석 중…"). 계획 문서의 "상태 바와 버튼이 동일하게" 문언의 코너 케이스.
- 검토함 payload 필드 라벨 중 `event`·`question`은 렌더 잠금이 없다(모크에만 존재).
- `_scene_payload`가 장면마다 `list_draft_versions` 전체 스캔 + job 조회를 한다(장면 수 × 버전 수 비례). 플랫 목록의 기존 패턴과 같으나 목록 endpoint 특성상 later 최적화 여지.
- 변이 M5 교훈: `"payload": dict(candidate.payload),` 리터럴이 `analysis.py:124`·`:802` 두 곳이라 문자열 변이 시 앵커 주의.

## Verdict

**불합격** — flat `DraftPayload` 응답에 계약 밖 필드(`latest_snapshot_id`)를 추가해 장면 생성·에디터 로드 등 5 경로가 미선언 500을 내는 것("미매핑 500 부채 0건" 공개 API 계약 위반, SoT v1.8.15에 근거 없는 변경)이 확정 근거. 차단 2(값 잠금 부재)·3(검증 범위)이 함께 따른다. 슬라이스의 나머지 축(①③④의 프론트 로직·검토함 payload·문서·브리프)은 자체로는 정상이며 변이 6종이 정상 작동했다.

## Outstanding items

- 차단 1 수정(한 줄 제거 또는 계약 개정 방향 오너 결정) 후 scene_notes 48셀·final_save 2셀·ReviewInboxApiTest 재실측으로 green 확인 필요.
- 2번 identity grouping은 본 검증과 별개로 오너 결정 대기(브리프 권장 C). 브리프의 사실 전제·구조는 이상 없음.
- 이 호스트 개발 스택 다운 상태(admin·worker·generation_worker crashloop — mongo 부재로 추정). 슬라이스 무관하나 실 dogfood 육안 확인 전에 스택 재기동 필요.

## Reproduction

```bash
git status --short                      # clean 확인
python3 -m pytest tests/test_analysis_apply_api.py -q        # 1 failed (source-ref 셀)
python3 -m pytest tests/test_scene_notes_api.py -q           # 31 failed
python3 -m pytest tests/test_final_save_analysis.py -q       # 1 failed
git worktree add /tmp/wt-head1 5ec69f6 && cd /tmp/wt-head1   # 부모에서 동일 3종 → 전부 green
python3 -m pytest tests/test_analysis_apply_api.py tests/test_scene_notes_api.py tests/test_final_save_analysis.py -q
cd - && git worktree remove /tmp/wt-head1
# 500 폭발 반경 프로브(커밋됨): PYTHONPATH=. python3 docs/verifications/2026-09-02/repro_draft_payload_500.py
# POST /drafts · GET /drafts · GET /drafts/{id} · PATCH → 500 / GET /chapters → 200
cd frontend && npx vitest run src/drafts/DraftEditor.test.tsx src/drafts/DraftList.test.tsx src/review/ReviewInbox.test.tsx   # 86 passed
npx tsc --noEmit && npm run build && npm run gen:api && git status --short   # 무차이
```
