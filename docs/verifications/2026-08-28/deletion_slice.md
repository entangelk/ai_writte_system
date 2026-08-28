# 삭제 기능 슬라이스 독립 검증 — 원고 purge·소유자 프로젝트 purge·관리자 아카이브

- **날짜**: 2026-08-28
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줘")
- **검증자**: Claude Code (독립 검증 세션 — 구현 물산이 아니라 검증 전용으로 열린 세션)
- **대상 슬라이스**: work_log 2026-08-28 세션 6 (삭제 기능 슬라이스)
- **검증 소스**: `main` HEAD `adf93d0` (슬라이스 범위 `070f0b9..adf93d0`, 커밋 **8개** — 완료 보고는
  "커밋 10개"라고 했는데 슬라이스 커밋은 8개다. 세션 5 커밋을 일부 포함해 세면 10~11개가 되나
  정확한 10의 구성은 특정 불가. 경미한 보고 불일치로 기록)
- **정본 계약 범위**: `docs/daily_logs/2026-08-28/work_log.md` 세션 6 (오너 결정 D1~D4) ·
  [`docs/plans/auth-d8-6-purge-ui-decisions.md`](../../plans/auth-d8-6-purge-ui-decisions.md)
  (D8-6 D1~D5 전부 A, 2026-08-02 확정 — admin purge의 파괴 그래프·감사·재시도 계약) ·
  `docs/system-contract-sot.md` v1.8.7 · `docs/guides/verification.md`

## Scope

1. 백엔드 3 신규 엔드포인트의 구현·권한·409 조건·파기 그래프
   (`POST /projects/{id}/drafts/{did}/purge` · `POST /projects/{id}/purge` · `POST /admin/projects/{id}/archive`)
2. 인메모리↔mongo 저장소 대칭 (6컬렉션 draft 스코프)
3. 활동 분류표 등재 (canonical 1종·EXCLUDED 2종)·운용 스윝 갱신 (tier 63→65, 총 88→91)
4. 프론트 4표면: 설정탭 삭제(이름 가드·순차)·원고 삭제(체크박스 가드)·관리 카드 보관 전환·타임라인 무링크
5. 전수 재실행 (백엔드 mongo 포함·프론트·tsc·build)
6. Mutation 9종 (구현자 클레임 4종 재현 + 검증자 신규 5종 — 방어 제거 방향 포함)
7. 기록 의무 (SoT 버전 로그·CHANGELOG·HANDOFF·work_log mutation 표)

## Methodology

- 저장소 루트 `/mnt/f/devel/ai_writte_system` (WSL2, `/usr/bin/python3` — fastapi·pymongo·pytest 설치됨).
- 전수: `docker compose -f docker-compose.test.yml up -d test-mongo` → healthy 확인(host pymongo ping `mongodb://localhost:27020/?replicaSet=rs-test`) → `python3 -m pytest -q` → 철수 `docker compose -f docker-compose.test.yml down` (운영 스택 무변).
- 프론트: `cd frontend && npx vitest run` · `npx tsc --noEmit` · `npm run build`.
- 코드 감사: 슬라이스 diff 전수 직독 (`git diff 070f0b9..adf93d0 -- <path>`) + 정본 문서 대조.
- Mutation: 트리 clean 확인 후 각 1회 적용(`Edit`) → 집중 셀 실행 → `git checkout -- <path>` 복원 →
  `git status --short` 빈 출력 + 최종 `git diff HEAD --stat` 0줄로 프리스틴 확인.
  요약 라인(FAILED|SUBFAILED 아님)을 읽어 subtest 누락 방지.
- 몽고 대칭: `python3 -m pytest tests/test_core_sot_mongo.py -q` (Fallback+Transaction 양쪽).

## Findings

### 1. 백엔드 구현 — 클레임과 일치 (오차 없음)

- **draft purge** (`routers/drafts.py:141-183`): 소유자 가드(`_REQUIRE_PROJECT_OWNER`) · 404(NotFound) ·
  409 아카이브 선행(`drafts.py:158-161`) · 409 active 잡 PENDING|RUNNING(`drafts.py:164-176`, enum은
  4상태라 active 정의 정확) · scratch `clear_draft`(`drafts.py:178` → `scratch.py:181` → repo
  `delete_for_draft`) · 활동 행 `draft_purged` before="archived" after="purged"(`drafts.py:179-183`).
- **6컬렉션 파기 대칭**: 인메모리(`core_sot/service.py:231-273`) drafts·versions·snapshots·blocks·
  source_refs(snapshot 경유)·receipts + 멱역 인덱스 2종 정리. mongo(`mongo_repository.py:204-244`)
  같은 6종, 트랜잭션/폴백 양경로. **mongo에 별도 save_requests 컬렉션이 없음을 확인** — 멱등 기록이
  `draft_versions` 문서에 실려(uniq 인덱스 3-tuple, `mongo_repository.py:96-104`) versions 삭제가 곧
  정리다. 인메모리 `_save_request_index` 정리와 비대칭 아님. receipt 몽고 문서에 `draft_id` 필드
  존재(`mongo_repository.py:782`) — `delete_many` 필터가 실제로 매치함.
- **소유자 프로젝트 purge** (`routers/projects.py:297-320`): `execute_project_purge`
  (`routers/admin.py:64-183`)과 **한 벌 공유** — 아카이브 선행 409·감사 requested 선기록 fail-closed·
  이름 이력 선기록·12서비스 파기·outbox enqueue까지 D8-6 그대로. D3 리터럴 `"설정 탭에서 소유자 삭제"`
  코드·테스트·셀 전부 일치.
- **관리자 아카이브** (`routers/admin.py:637-657`): ADMIN 가드·소유자 아카이브와 같은 서비스 호출·같은
  outbox enqueue·활동 행 없음(I3)·멱등 재보관(409 없음, 에러 선언 {401,403,404,503}와 정합).
- 활동 분류(`activity/actions.py`): canonical `draft_purged` 등재(20→21), EXCLUDED에 소유자 purge·
  관리자 아카이브 등재 — 각 사유 주석이 I3·파기-원장-소거 원칙과 정합.
- `activity.record`는 A4=A 격리 경계에서 예외를 삼킨다(`activity/log.py:146-153`) — 파기 후 활동 쓰기
  실패가 요청을 죽이지 않음.

### 2. 테스트 셀 — 충실하나 경계 행렬에 빈 칸 3개 (→ Issues B2~B4)

`test_draft_purge.py`(7셀): 404·409 아카이브·409 잡·204 소멸+형제 보존·재파기 404·활동 행 잔존·
scratch 대칭. `test_owner_project_purge.py`(7셀): 409·204+스파이+outbox+이름·비소유자 403·재파기 404·
관리자 아카이브 3셀(I3 무행·404·purge 도달성). mongo 대칭셀(`test_core_sot_mongo.py:637-680`,
Fallback+Transaction 양쪽): 5축 소멸+형제·프로젝트 보존 — **receipts는 단정하지 않는다**.
운용 스윝: activity 21 핀·admin 에러 계약 17종·tier 65/91 핀 전부 갱신됨.

### 3. 프론트 — 클레임과 일치

- 설정탭(`ProjectSettingsPage.tsx:75-95,129-178`): 이름 완전일치 가드(trim·대소문자 완화 없음 — D8-6
  D2 권고 준수)·`archiveProject`→`purgeProject` 순차·D3 리터럴·성공 시 목록 복귀·멱등 재아카이브.
- 원고 목록(`DraftList.tsx:121-142,229-272`): 체크박스 "삭제하겠습니다" 가드·순차·목록 재로딩.
- 관리 카드(`AdminProjectCard.tsx:44-62,184-196`): "보관으로 전환" → onArchived로 카드 갱신 → purge 면
  오픈. AdminConsole·AdminUserDetail 양쪽 배선.
- 타임라인(`ActivityTimelinePage.tsx:48-57,82-85` + `activityActions.ts:81-99`): 보관 포함 원고 집합
  대조 무링크(F7 처방), 집합 로드 실패 시 종전대로 링크 폴백(주석으로 의도 명시).
- OpenAPI 재생성 4경로 전부 반영(`schema.d.ts:75,92,950,1087`).
- 셀: 설정탭(이름 under/over·순차·리터럴·복귀)·DraftList(체크 under/over·순차·잔류)·타임라인(무링크/
  생존 링크 양방향)·관리 카드(아카이브 호출·면 오픈).

### 4. 전수 재실행 — 클레임 전부 재현

- 백엔드(test-mongo 기동): **2544 passed, 4 skipped, 2894 subtests passed** (4:41) — 보고와 동일.
- `test_core_sot_mongo.py` 단독: **79 passed** — "79/79" 보고와 동일.
- 프론트: **386/386** (34파일) · `tsc --noEmit` clean · `vite build` OK(진입 439.59 kB).

### 5. Mutation 9종 — 6종 물림·**3종 무셀 통과(=빈 칸 실증)**

| # | 방향 | 적용한 diff | 파일:줄 | 결과 |
|---|---|---|---|---|
| B1 | under | active 잡 409 블록(13줄) 통째 제거 | `routers/drafts.py:164-176` | ✋ `test_active_generation_job_is_409` |
| B2 | under | `if not draft.archived:` → `if False and not draft.archived:` | `routers/drafts.py:158` | ✋ `test_unarchived_draft_is_409_and_survives` |
| B3 | under(방어 제거) | 인메모리 `_writing_accept_receipts` 재구성 6줄을 주석 치환 | `core_sot/service.py:269-273` | **통과 — test_draft_purge 7 + test_writing_accept 53 + 조합 60 전부 green** |
| B4 | over | 잡 상태 집합에 `SUCCEEDED`,`FAILED` 추가 | `routers/drafts.py:165-168` | **통과 — test_draft_purge 7 green** |
| B5 | under | mongo `_writing_accept_receipts.delete_many` 3줄 제거 | `core_sot/mongo_repository.py:239-241` | **통과 — test_core_sot_mongo 79 green** |
| F1 | under | `disabled={purgeBusy \|\| !purgeChecked}` → `\|\| false` | `DraftList.tsx:250` | ✋ `permanently deletes a draft behind a checkbox…` |
| F2 | under | `draftIds ?? undefined` → `undefined` | `ActivityTimelinePage.tsx:84` | ✋ `does not link a draft row whose draft no longer exists` |
| F3 | under | 이름 비교 조건 삭제 → `disabled={deleteBusy}` | `ProjectSettingsPage.tsx:159` | ✋ `keeps the permanent purge behind the exact project name` |
| H1 | under | `--action-primary-hover: var(--blue-800)` → `var(--blue-700)` | `styles.css:78` | ✋ `designTokens.test.ts` 1 fail |

구현자가 보고한 mutation(가드 무력화·hover 되돌림)은 F1·F2·H1로 독립 재현해 실제로 물림을 확인했다.
B3·B4·B5는 검증자가 추가한 것으로, **물지 않음 자체가 아래 Blocking 발견의 증거**다.

## Issues / Risks

### Blocking (계약 의무)

- **B1 — SoT 미등재.** 신규 공개 API 3종과 그 계약 리터럴(409 조건 2종·6컬렉션·reason 고정 문자열·
  I3 무행)이 `docs/system-contract-sot.md`에 전혀 없다(버전 로그 마지막 v1.8.7은 이전 슬라이스).
  운용 수 변화(총 88→91, project tier 63→65, 활동 20→21, EXCLUDED 21→23)도 SoT에 기록되지 않았다.
  CLAUDE.md §1은 정본 반영을 "구현과 함께(before or alongside)" 요구하고, v1.8.0은 동일한 누락을
  "추적 부채"로 보고 별도 등재 슬라이스로 폐쇄한 선례다. **수습: v1.8.8 등재 슬라이스.**
- **B2 — receipts 축 잔류 무셀 (B3·B5로 실증).** "6컬렉션 파기"는 이 슬라이스가 스스로 선언한
  계약이나 여섯째 축(writing_accept_receipts)의 소거는 인메모리·mongo 어디에서도 잠기지 않았다.
  receipt가 잔류하면 파기된 원고의 accept 멱역 재생이 죽은 version을 가리키는 고아가 될 수 있다.
  **수습: 파기 후 receipt 소거를 단정하는 셀 양쪽(인메모리·mongo 대칭셀)에 추가.**
- **B3 — 종료 잡 over-strict 무셀 (B4로 실증).** D1("active 생성 잡은 409")의 should-NOT-fire 면 —
  SUCCEEDED·FAILED 잡은 purge를 막지 않는다 — 에 셀이 없다. 가드를 네 상태 전부로 확장해도 전수가
  green이라, 한 번 생성을 돌린 원고는 영구히 삭제 불가가 되는 회귀가 조용히 통과한다.
  **수습: 종료 잡이 붙은 archived 원고 purge → 204 셀 1개.**
- **B4 — Crud 에러 선언 잠금 미등재.** `CrudErrorContractDeclarationTest.EXPECTED`는 여전히 20핀에
  제품 purge 2경로가 없다(`test_application_api.py:2259` 부근). 라우트의 `responses=` 선언 자체는
  현실적({401,403,404,409,503})이지만 그 선언을 잠그는 셀이 없어 언더 방향(선언 삭제)이 무감각하다.
  관리자 트랙은 archive를 17번째로 등록해 관례를 알고 있었음이 드러난다 — 제품 쪽 누락이다.
  **수습: EXPECTED에 2행 추가(핀 20→22).**
- **B5 — 소유자 purge 면이 503 재시도를 제공.** 관리자 면은 503을 `uncertain` 상태로 잠그고 "다시
  시도하지 말고 purge reconciler로 잔류 데이터를 확인하세요"를 안내하지만(`AdminProjectCard.tsx:107-113`),
  설정탭 면은 어떤 실패든 `deleteBusy`만 풀어 버튼을 되살린다(`ProjectSettingsPage.tsx:91-94`). 두 면은
  **같은 `execute_project_purge`**를 타므로 D4=A가 금지한 "거짓 재시도 UX"가 소유자 경로에 열려 있다.
  HANDOFF:223도 "503 후 UI 재시도는 금지한다"를 상설 규칙으로 적는다. 단순 잠금이 곧 정답이 아닌
  것이 함정 — 이 플로우는 archive 단계(파괴 없음·재시도 무해)와 purge 단계(불확정)를 한 버튼에
  묶고 있어 **어느 단계에서 실패했는지 구분이 필요하다. 오너 결정 사항**으로 올린다: (ⓐ 관리자 면과
  같은 uncertain 잠금을 단계 구분과 함께 적용, ⓑ 소유자 면은 이름 가드로 충분하다는 면제를 결정으로
  기록). ⓑ를 택해도 그 결정이 D4=A 옆에 명시돼야 정합이 산다.
- **B6 — 기록 의무 미이행(CLAUDE.md §5 "No exceptions").** ① CHANGELOG 최신 항목이 이날 UI 슬라이스
  (~08-28 도그푸드)에서 멈추고 삭제 슬라이스 항목이 없다 — 신규 API 3종·파괴 기능은 "major feature
  change" 갱신 대상이다. ② HANDOFF 미갱신 — 낡은 운용 수(76 op·활동 20·77 op) 서술이 그대로며
  마지막 자가 검수도 08-27이다. ③ work_log 세션 6의 mutation이 표가 아니라 서술형 tally다("4종"
  주장, 실제 나열 3종, 셀 매핑 없음) — records-and-handoff.md "Mutations go in as a table" 위반.

### Hardening recommendations (비차단)

- **H1** — draft purge에서 scratch 정리가 core 파기 **뒤**에 있다(`drafts.py:177-178`). scratch 삭제
  실패 시 원고는 이미 없고 요청만 500이 되며, draft 스코프를 담는 reconciler는 없다. scratch는
  재생성 무해한 파생물이므로 core 앞으로 옮기는 것이 잔류-안전 방향이다.
- **H2** — 원고 삭제 409의 서버 문구("draft has an active generation job; wait or discard it")가
  한국어 화면에 영어 원문으로 노출된다. 구현 주석에 의도가 명시돼 있으나("문구를 그대로 보여 준다")
  오너가 화면에서 보게 될 첫 사례이니 안내문 번역을 고려할 것.
- **H3** — 타임라인의 무링크 판정이 `listDrafts` 로드 성공에 의존한다(실패 시 전체 링크 폴백). 의도가
  주석으로 명시돼 있으므로 관측 후 재검토 대상으로만 남긴다.

## Verdict

**조건부 합격** — Blocking B1~B6(SoT 미등재, receipts·종료 잡·에러 선언 잠금 무셀 3종, 소유자 면 503 재시도의 오너 결정, CHANGELOG·HANDOFF·mutation 표 기록 의무)가 닫힐 때까지.

하중을 받치는 근거: 핵심 파괴 그래프·권한·409 조건·가드 UX·전수 수치는 전부 독립 재현됐고
구현자 클레임 mutation도 실제로 물렸다. 빈 칸은 전부 "셀·등재 추가" 또는 "오너 결정 기록"으로
닫히는 종류고, 아키텍처를 되돌릴 것은 없다.

## Outstanding items

- 검증 뒤 감사 대상 소스는 프리스틴 (`git status --short` 빈 · `git diff HEAD --stat` 0줄) — mutation 은 전부 복원됐다. 검증자가 커밋하는 것은 이 기록과 인덱스 등재뿐이다.
- test-mongo는 검증자가 기동·철거해 원 상태 복원(운영 스택 무변 — 검증 시작 전에도 구동 중이었다).
- 배포 환경 미반영 (구현자 완료 보고 그대로 — 오너 요청 시 별도).
- 장(유닛) 삭제·unit_kind 존치는 D4대로 별도 슬라이스·오너 브리프 대기 (이 검증 범위 밖).
- 완료 보고 "커밋 10개"는 실제 슬라이스 8개와 불일치 (경미 — 위 메타데이터).

## Reproduction

```bash
# 전수 (백엔드, mongo 포함)
docker compose -f docker-compose.test.yml up -d test-mongo   # healthy 대기
python3 -m pytest -q                                          # 2544 passed, 4 skipped, 2894 subtests
python3 -m pytest tests/test_core_sot_mongo.py -q             # 79 passed
docker compose -f docker-compose.test.yml down

# 프론트
cd frontend && npx vitest run && npx tsc --noEmit && npm run build   # 386/386 · clean · OK

# Mutation (각 1종 — Edit 적용 → 실행 → git checkout -- <path> → status 확인)
python3 -m pytest tests/test_draft_purge.py -q                 # B1/B2/B4 판독
python3 -m pytest tests/test_writing_accept.py -q              # B3 판독
python3 -m pytest tests/test_core_sot_mongo.py -q              # B5 판독
cd frontend && npx vitest run src/drafts/DraftList.test.tsx    # F1
cd frontend && npx vitest run src/projects/ActivityTimelinePage.test.tsx  # F2
cd frontend && npx vitest run src/projects/ProjectSettingsPage.test.tsx   # F3
cd frontend && npx vitest run src/designTokens.test.ts         # H1 (hover)

# 계약 문서 대조
grep -n "purge" docs/system-contract-sot.md                    # 신규 3경로 미등재 확인
grep -n "len(self.EXPECTED), 20" -r tests/test_application_api.py
```
