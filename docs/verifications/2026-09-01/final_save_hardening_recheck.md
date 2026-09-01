# final-save 보강(66ece84·30a9194) 재검증

## Subject metadata

- 날짜: 2026-09-01
- 요청자: 오너("보강한거 재검증해줘" — 선행 검증 [`final_save_analysis_checkpoint.md`](final_save_analysis_checkpoint.md)의 불합격에 대한 보강 커밋 재검증)
- 검증자: Claude Code 세션(선행 검증과 같은 세션, 이번 라운드는 보강 커밋이 대상 — 구현은 별도 세션)
- 대상: 보강 커밋 `66ece84`(B1·B2·B5·B6·B7·B8·B9·H1·H6)·`30a9194`(역배선 B3·D5 브리프·프로브 전환·schema.d.ts 재생성) — 선행 검증의 차단 9건·하드닝 6건 폐쇄 주장
- 정본: [`docs/plans/final-save-analysis-decisions.md`](../../plans/final-save-analysis-decisions.md)(**Partially resolved** — D1~D4 확정, **D5 partial HTTP 얼굴 결정 대기**)
- 검증 소스: HEAD `30a9194`, 트리 clean(변이 전·후 매번 `git status --short` 확인)
- 환경: 선행 검증과 동일(WSL2·호스트 pytest·test-mongo 27020 up). 백그라운드 전수로 긴 suite 종료값까지 측정 — 구현자 세션은 "약 30초 뒤 장기 프로세스 강제 종료"로 전수를 못 돌렸다고 기록(work_log 세션 5)

## Scope

1. 선행 B1~B9·H1·H6의 폐쇄 실측(코드 diff + suite + 요청 실행)
2. 프로브 전환본(런타임 패치 제거·S1~S13 직접 검증)의 실효성
3. 구현자 주장 재현(quota wiring 8/220·활동 라벨 6/39·typecheck 8) + 선행 실패 suite 전부
4. 생성물 동기화: `openapi.json`(비추적 확인)·`schema.d.ts` byte 대조·유료/무료 경로 응답 선언
5. 변이 4종(신규 잠금이 물리는가 — dedupe 행·B2 수정·H1 재조회·CSS 토큰)
6. 백엔드·프런트 전수

## Methodology

- 프로브·suite·변이 프로토콜은 선행 기록과 동일(요약 count 줄로 판독, 변이마다 복원 확인).
- 유료/무료 응답 선언은 생성된 OpenAPI 문서를 직독해 양방향(선언돼야 할 것·되지 말아야 할 것) 확인.

## Findings

### 1. 백엔드 차단 9건 중 7건·H1 폐쇄 확인

| 선행 결함 | 폐쇄 실측 |
|---|---|
| B1 dedupe 무매핑 | `dedupe.py`에 `draft_finalize`=(BODY, `idempotency_key`) 행 추가. `DedupeMappingTest` green. 변이 M-A(행 제거) → **1 failed 재현** |
| B2 성공 경로 500 | `self._require_active_project_and_draft(...)` 문장형 + `draft = self._require_draft(...)`. mypy 가드 green. 변이 M-B(되돌리기) → 프로브 rc=1 재현 |
| B3 402/429 미선언 | finalize = `_BILLABLE_400_404_409_502_CONFIG`(402·429·502 포함), 생성 스펙 직독 확인. 변이 이력: 66ece84에서 **일반 저장에 billable 선언을 붙이는 역배선**을 저질렀으나 30a9194에서 focused wiring guard가 잡아 바로잡음(구현자 기록과 일치) |
| B6 조립 지점 5곳 | `register_drafts(..., analysis=None, runner=None, llm_call_audit=None)` 기본인자로 호환. `test_chapter_hierarchy.py` 5셀 green |
| B7 라벨표 | `draft_finalized: "원고 최종 저장"` + 주석 26→27. `test_activity_ui_labels.py` green |
| B8 봉투 키 핀 | `SpineEnvelopeKeyTest`에 4필드 추가, green |
| B9 tier 행렬 | 73/99→**74/100** 갱신, `CombinedBoundaryMatrixTest` green |
| H1 봉투 낡은 상태 | runner 예외 시 `analysis.get_job` 재조회. 변이 M-C(재조회 제거) → 프로브 **S6 셀 1개 기명 재실패** — 기명 잠금 |
| H6 "분석 완료" 오표시 | `latestSnapshotId === null → "미실행"` 분기 추가(단, §4 R2 참조 — 이 수정이 새 회귀를 만들었다) |

- 주장 수치 재현: quota wiring + 라벨 + typecheck 합쳐 **52 passed / 272 subtests**(구현자가 파일 일부만 돌린 8/220·6/39·8의 상위집합, 전부 green). 선행 실패 suite 재실행: `test_chapter_hierarchy`·`test_activity_actions`·`test_billable_actions` **35 passed / 197 subtests**, `SpineEnvelopeKeyTest`+`CombinedBoundaryMatrixTest` **17 passed / 504 subtests** — 전부 green.
- 생성물: `frontend/openapi.json`은 **비추적** 빌드 산물(`git ls-files` 공백 확인 — 선행 기록의 "openapi.json 커밋본" 서술 정정), 정본은 `schema.d.ts`이고 재생성과 **byte-identical**.

### 2. ★하지만 프런트는 여전히 red 2셀 — 그중 하나는 실앱 회귀

구현자 환경이 vitest를 못 돌렸으므로 이 수치가 첫 실측이다(전수 §5).

- **R1(차단) — 디자인 토큰 semantic 라우팅 셀.** B5 폐쇄로 `var(--danger-600)`을 썼는데 `--danger-600`은 **프리미티브**라 "routes screens through semantic tokens" 가드에 걸린다(`expected ['--danger-600'] to deeply equal []`). 선행 검증의 하드닝 권고가 이 방향을 제시했던 점을 바로잡는다 — 올바른 폐쇄는 semantic 토큰을 정의해 타는 것(예: `:root`에 `--status-danger: var(--danger-600)` 정의 후 사용). 원본 코드의 `var(--status-danger, …)`가 **이름은** 맞았고, 정의와 리터럴 폴백만 빠져 있었다.
- **R2(차단) — 수동 분석 성공 후 상태 바가 "분석 필요"에 갇힘(실앱 회귀).** H6 수정에서 라벨 우선순위를 `draft.analysis_*` 필드로 옮겼는데, **수동 분석 경로는 그 필드를 갱신하지 않는다**(`AnalysisTrigger`는 `onStatusChange`만 보고 — `DraftEditor.tsx:934`, draft 재조회 없음). 수동 분석이 최신 snapshot에서 `succeeded`로 끝나도 화면은 "필요"를 보인다 — 확정 계약 "최신 snapshot에 succeeded job이면 분석 완료" 위반. 갱신된 pin 셀(`분석 필요`→`분석 완료` 2단)이 이 회귀를 정확히 잡고 있어 **여전히 red**다. 폐쇄 방향: 수동 분석 완료 시 `draft.analysis_status/analysis_snapshot_id`를 갱신하거나(=라벨 우선순위 유지) 라벨을 실행 상태(`analysisStatus`)와 draft 필드의 조합으로 복원.
- 변이 M-D(CSS를 `var(--status-danger, #a43b2c)`로 되돌림) → 선행의 토큰 2셀이 재실패 — 그 가드들이 여전히 물린다는 확인.

### 3. B4 잔여 — 계약 행렬의 잠금이 suite 밖에 있다

finalize 동작 분기는 여전히 **pytest suite에 셀이 없다**(`grep -rn finalize tests/` — 무관한 `SelfReport.FINALIZE`만 존재). 잠금은 커밋된 프로브가 홀로 담당한다: 변이 M-B(B2 되돌림)·M-C(H1 재조회 제거)가 프로브를 각각 rc=1·기명 셀 실패로 물었다. 다만:

- 프로브는 pytest가 수집하지 않으므로 전수의 green bar가 finalize 계약 위반을 모른다.
- M-B의 잠금 형태가 **기명 단정이 아닌 크래시**(500 응답의 비-JSON 본문을 `response.json()`에서 파싱해 `JSONDecodeError`)다 — 셀 전환 시 상태코드 단정을 파싱 앞에 두길 권한다(하드닝).

### 4. D5(구 H2) — 오너 결정 대기 중

`30a9194`가 결정 브리프를 계획 문서에 추가했다(A=200+payload 권장 / B=502 partial). 현재 구현은 A 형태. 결정 전까지 HTTP 계약·회귀 셀 확정이 불가하며, 502 선언이 이미 스펙에 포함돼 있으므로(D5=B 채택 시 필요, A 채택 시 불필요한 얼굴) D5 결과에 따라 선언 정리도 함께 해야 한다.

## Issues / Risks

### Blocking (조건)

1. **R1** — `--danger-600` 프리미티브 직접 사용으로 designTokens semantic 라우팅 셀 red. semantic 토큰 정의로 폐쇄.
2. **R2** — 수동 분석 성공 후 "분석 필요" 고정(실앱 회귀, 계약 위반 표시). 상태 갱신 경로 폐쇄.
3. **B4 잔여** — finalize 계약 분기의 pytest 셀 부재(프로브는 잠금 중이나 suite 밖). 셀 편입 또는 오너의 프로브 승인 명시.
4. **D5 미확정** — A/B 결정이 있어야 HTTP 계약·회귀 셀·502 선언이 고정된다.

### Hardening (비차단)

- H6의 `미실행` 분기(저장 이력 없는 장면)를 고정하는 셀이 없다 — pin 셀은 "필요" 시나리오만 담당.
- 프로브 M-B 잠금 형태(기명 단정화) — §3.
- SoT v1.8.13 변경이력·CHANGELOG 반영 미갱신(구현자 명시 잔여 "전체 문서·SoT 정합성"의 연장).

## 전수 (이 세션 실측)

- 프런트 전수: **3 failed / 382 passed (385), exit 1** — `designTokens` semantic 라우팅(R1) + `DraftEditor` 상태 바(R2) + `App.test.tsx` 관리자 라우팅 1건. 셋째는 **단독 재실행 28/28 green**으로 백엔드 전수 동시실행 부하에서의 `waitFor` 시간 초과 플레이크 — 이 슬라이스 비귀속. 슬라이스 귀속 실패는 R1·R2 정확히 2셀.
- 백엔드 전수: **7 failed / 2667 passed / 1 skipped / 3107 subtests**(39:50) — 7 failed·SUBFAILED **전부 `test_docs_indexes`가 이 검증 기록의 미등재를 잡은 것**(기록 1건 미도달 + 건수 4곳 266≠267 + 분포 합). **제품 셀 실패 0** — 선행 검증의 11 failed는 전부 소멸했다. 등재·건수 갱신 뒤 `test_docs_indexes` 단독 green 확인(아래 Reproduction 뒤 단계).

## Verdict

**조건부 합격** — 조건: 프런트 red 2셀(R1 semantic 토큰·R2 수동 분석 후 상태 갱신 실앱 회귀) 폐쇄 + finalize 계약 분기의 suite 편입(B4) + D5(A/B) 오너 확정. 백엔드 차단 7건·H1은 실측 폐쇄(변이 재실패 포함) — D4=A 실행 경로 전체가 요청 실행으로 검증됐다(프로브 41단정 전부 통과).

## Outstanding items

- D5 오너 결정(브리프 `final-save-analysis-decisions.md` §D5) — 결정 즉시 HTTP 계약 고정·셀 작성·(A의 경우) 502 선언 제거 여부 정리.
- R1·R2 수정 + B4 셀 편입 후 3차 재검증(회귀 프로브 S1~S13 + 전수 기대치 재계산).
- SoT v1.8.13·CHANGELOG·tier/operation 수 문서 정합성(구현자 잔여 목록).

## Reproduction

```bash
docker compose -f docker-compose.test.yml up -d
# 1) 프로브(패치 없이 현재 코드) — 41단정 전부 통과 시 rc=0
python3 docs/verifications/2026-09-01/repro_final_save_flow.py
# 2) 선행 실패 suite + 주장 suite
python3 -m pytest tests/test_quota_enforcement_api.py tests/test_activity_ui_labels.py \
  tests/test_typecheck.py tests/test_chapter_hierarchy.py tests/test_activity_actions.py \
  tests/test_billable_actions.py -q
# 3) 프런트 red 2셀 (R1·R2 — 파이프 없이 exit code 확인)
cd frontend && npx vitest run src/designTokens.test.ts src/drafts/DraftEditor.test.tsx
# 4) 유료/무료 응답 선언 직독
python3 -c "import json; s=json.load(open('frontend/openapi.json')); \
print(sorted(s['paths']['/projects/{project_id}/drafts/{draft_id}/finalize']['post']['responses'])); \
print(sorted(s['paths']['/projects/{project_id}/drafts/{draft_id}/versions']['post']['responses']))"
```
