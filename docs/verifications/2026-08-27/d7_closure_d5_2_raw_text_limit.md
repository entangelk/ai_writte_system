# D7 폐쇄 + D5-2 유닛 본문 4000자 상한 — 독립 검증

- 일자: 2026-08-27
- 요청자: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- 검증자: Claude Code (독립 검증 세션 — 피검증 슬라이스 비생산)
- 대상: 2026-08-27 세션 1~3 부채 처리 — D7(기존 빨간 셀 폐쇄, `04e0b7b`), D5 실측·정정(`aa4529e`·`40c4524`), D5-2 시행(`3a8fa28`·`5085e42`·`7dae1b3`), 세션 기록(`bfd0335`)
- 정본 참조: `docs/system-contract-sot.md` **v1.8.7**(2026-08-27행 — 이 슬라이스가 본체), W0 계약 §3.3(replay 순서)
- 소스: 커밋 `04e0b7b`…`bfd0335`(HEAD, 트리 clean — 세션 3 마감 상태 그대로)

## 범위

1. **D7**: `WritingErrorContractDeclarationTest` lock-list 등재 + 개수핀 13→14, `test_application_api.py` 124 passed 주장
2. **D5-2 저장 스키마 축**: `SaveDraftRequest.raw_text` 검증 422, env 조정성(`DRAFT_RAW_TEXT_MAX_CHARS`), 기동 fail-loud
3. **D5-2 채택 합성 축**: accept(append 합성·start_next_unit 씨앗)이 **provider 호출(enrich·gate) 앞에** 상한 시행 → 400
4. **"전 경로" 주장**: `raw_text`를 쓰는 경로 전수 스윕(save_draft·start_next_unit 호출지 전수)
5. **프론트**: 카운터 90% 임박 경고·초과 저장 차단·maxLength 부재(no-maxLength 셀 존재)
6. **설명창 스칼라 1000자**: `BriefTextField`(premise·genre·tone·pov)
7. **실측 정정(40c4524)**: "원고는 매 생성 검색 조각으로 프롬프트에 실린다"의 코드 정합성
8. **실DB 영향 0건 주장**: mongosh 직접 재조사(씨드 24,070자 1건·브리프 초과 0건)
9. **기록 산출물**: SoT v1.8.7·README·HANDOFF(마감 메모·메모장 등재)·work_log·**CHANGELOG**

## 방법론 (재현 가능 명령)

환경: WSL2 호스트 python3(fastapi·pytest 설치됨), 저장소 루트 `/mnt/f/devel/ai_writte_system`에서 실행. 전수는 test-mongo ON(`docker compose -f docker-compose.test.yml up -d` → healthy 대기 후 `python3 -m pytest -q`, 종료 후 `down` — 검증자가 잠시 기동·철거해 원 상태 복원).

- 경계 매트릭스: 정본 v1.8.7행·`accept.py`·`models.py`·`env.py` 정독으로 "발동해야 할 분기/발동하지 않아야 할 분기" 열거 → 각 분기의 잠금 셀 대조. 쓰기 경로 스윕은 `grep -rn "save_draft\|start_next_unit"` 전수.
- 수이트: `python3 -m pytest tests/test_draft_raw_text_limit.py tests/test_project_brief.py -q` / `python3 -m pytest tests/test_application_api.py -q` / 전수 `python3 -m pytest -q` / 프론트 `cd frontend && npx vitest run && npx tsc --noEmit`.
- 뮤테이션 V1~V6: 매번 `git status --short` 빈 것 확인(전부 커밋된 트리) → python 스크립트로 최소 변이 → 대상 클래스만 재실행, 요약 라인+`FAILED|SUBFAILED` 판독 → `git checkout -- <절대경로>` 원복 → clean 재확인. 적용 diff 는 아래 표에 원문 기재.
- DB: `docker exec ai_writte_system-mongo-1 mongosh --quiet ai_writing_system` — `$strLenCP`로 초과 문서 카운트·상위 5건 길이·씨드의 draft/project/영수증·브리프 4필드 초과 검사.
- 문서: `git show bfd0335 --stat`·SoT diff 정독, CHANGELOG 헤드·`grep -n` , HANDOFF `grep -n "메모장\|D5-2"`, work_log 세션 2·3 절 정독.

## 발견

### 1. D7 (04e0b7b) — 주장 그대로

- `tests/test_application_api.py:3099`–3101에 `("/projects/{project_id}/writing/scratch/{scratch_id}", "delete")` 등재, 집합 `{401,403,404,503}`(형제 경로와 동일). 개수핀 `assertEqual(len(self.EXPECTED), 14)`(3125행 부근).
- 실측 `test_application_api.py` — **124 passed · 498 subtests**(19.36초) — 세션 2 기록(192행)과 수 일치. 빨간 셀 0 확인.

### 2. 저장 스키마 축 (422) — 성립

`api/models.py:698`–`704` `enforce_raw_text_limit` field_validator, 상수 `env.py:38`–`41` `draft_raw_text_max_chars()`(기본 4000·env override·`<1`이면 ValueError). 기동 fail-loud는 `main.py:1665` `draft_raw_text_max_chars()` 호출. 셀: 경계(4000 통과)/초과(4001→422+메시지 "4000")/env 양방향(10 통과·11 거부)/무효 env 기동 거부(0·비정수, subtest).

### 3. 채택 합성 축 (400, provider 앞) — 성립

`accept.py:100`–`102` `_enforce_raw_text_limit` 호출이 `enrich`(103–104행)·`gate.evaluate`(127행) **양쪽 앞**. append는 `_append_patch(base, text)` 합성 결과를(158행의 실제 저장 합성과 동일 함수), start_next_unit은 씨앗 본문을 측정(176–179행). `WritingIntent`는 두 값뿐(`models.py:23`–`28`)이라 분기 전수. 스파이 셀 `(reporter.calls, gate.calls) == (0, 0)`이 유료 호출 0을 잠금. NotFound는 조용히 넘겨 §3.3 순서 보존(전용 셀 `test_a_missing_base_still_reports_not_found_not_the_limit`).
반증 시도 ①"enrich가 text를 바꾸면 측정≠저장": `report.py:135` `replace(candidate, **report)` — 보고서 4필드만 갈고 `text` 불변. 기각. ②"다른 쓰기 경로": `save_draft` 호출 전수 = `routers/drafts.py:319`(SaveDraftRequest→422) + `accept.py:159`; `start_next_unit` = `accept.py:135` 유일. **세 경로 모두 상한 안쪽 — "전 경로" 성립.**

### 4. 프론트 — 성립

`DraftEditor.tsx`: `[...rawText].length`(코드포인트=Python len 미러)·`overLimit` 이중 차단(제출 핸들러 조기반환 273–278행 + 버튼 disabled 626–629행)·`RAW_TEXT_WARN_CHARS = floor(4000*0.9)`(tokenEstimate.ts). **maxLength 부재** — 잠금 셀 실존(`DraftEditor.test.tsx:148`–`151`, under 방향 "maxLength 추가 시 문다"). 5085e42의 짧은 본문 과잉방지 앵커("6자" 경고 없음·버튼 활성)도 확인.

### 5. 설명창 스칼라 1000자 — 성립

`models.py` `BriefTextField`(strip·min 1·`\S`·max 1000)가 `PutProjectBriefRequest`의 premise·genre·tone·pov 4필드에 적용. 셀: 경계 1000 통과/1001 거부/4필드 subtest 전수.

### 6. 실측 정정(40c4524) — 코드 정합

`context_search/service.py`: `_split_scene_blocks`(마지막 HEADING/SCENE_MARKER 이후 문단 전부; 표식 없으면(boundary=-1) **유닛 전체**) + `DEFAULT_RECENT_SCENE_BLOCK_LIMIT = 5`(91행) + `DEFAULT_CONTEXT_BUDGET_TOKENS = 8192`(`api/models.py:766`) + `_apply_budget` 편집. SoT v1.8.7행의 서술과 코드 일치 — 세션 1 보고("안 실린다")가 틀렸고 정정(40c4524)이 옳다는 오너 판단이 구조와 일치함을 재확인.

### 7. 실DB — 독립 재현

mongosh 직접 쿼리: `source_snapshots` 4000자 초과 **정확히 1건·24,070자**(차상위 762자 — work_log 서술과 동일). 그 문서는 draft 제목 **"예산 포화 측정용 장면"**·프로젝트 "alpha R-c 32768 saturation probe"·버전 멱등키 **`report-budget-measure-v1`** — 씨드 확정, 오너 콘텐츠 아님. 해당 draft의 accept 영수증 **0건**. 브리프 4필드 1000자 초과 **0건 / 전체 2건**.

### 8. 수이트·스택·문서 — 수치 전부 재현

- 백엔드 전수(test-mongo ON): **2526 passed · 4 skipped · 2841 subtests**(220초) — 주장과 수 일치. skip 4 = 알파 관례.
- 프론트 전수: **373 passed / 34 files** + `tsc --noEmit` clean — 일치.
- 스택: 10컨테이너 전부 Up, healthcheck 정의분 전부 healthy, test-mongo 잔존 없음(검증자가 기동·철거해 원상 복원).
- SoT `v1.8.6→v1.8.7` 상단 변경이력 등재 + README 버전칸 v1.8.7 — 일치. HANDOFF 세션 3 마감 메모·메모장 "다음 계획" 등재(350행, 오너 발언 원문 동반)·자료 축 유예(181행) 확인. 인용 좌표 스팟체크 4곳(`WritingPanel.tsx:341`·`api/models.py:43`·`accept.py:150`·`extractor.py:73`) 전부 생존 — `extractor.py:73`은 `content=snapshot.raw_text`로 자료 축 유예의 근거 좌표로 정확.

### 9. 뮤테이션 — 6종 전부 물었고 셀 페어링은 작업 AI M계열과 일치

| # | 적용 diff (원문) | 방향 | 재실패 셀 |
|---|---|---|---|
| V1 | lock-list 새 항목에서 `{"401","403","404","503"}` → `{"401","403","404"}` | over | `SUBFAILED(path='/projects/{project_id}/writing/scratch/{scratch_id}', method='delete')` — 작업 AI 보고 좌표와 동일 |
| V2 | `if len(value) > limit:` → `if False and len(value) > limit:`(models) | under | `one_over_the_limit_is_rejected` + `env_adjustable`(M1과 동일 페어) |
| V3 | `self._enforce_raw_text_limit(...)` 호출 앞 `pass`+`if False:` 봉쇄(accept) | under | `append_past…` + `seed_past…`(provider 0 단정 포함) — M3(수선 후)과 동일 |
| V4 | `if len(value) > limit:` → `if len(value) >= limit:`(models) | over | `exactly_at_the_limit_saves` + `env_adjustable` |
| V5 | `BriefTextField`에서 `max_length=1000` 제거 | under | `premise_past_1000` + 4필드 subtest 전체(계 5 failed) |
| V6 | `DraftEditor.tsx` 제출 조기반환에서 `\|\| overLimit` 제거 + 버튼 `disabled`에서 `\|\| overLimit` 제거 | under | `keeps_save_disabled…` + `blocks_saving_a_freshly_typed…`(M7과 동일 페어) |

매 뮤테이션 전 `git status --short` 빈 것 확인, 후 절대경로 원복 + clean 확인(6/6). 작업 AI의 M1–M8 표(work_log 세션 3)는 본 검증의 V1·V2·V3·V4·V5·V6가 그 중 6개를 독립 재현 — M3의 "무효 통과 발견·수선"(7dae1b3)도, 수선된 셀(메시지 "at most 4000 characters" 단정 포함)이 V3에서 상한 이유로 재실패함으로써 유효하게 복원됐음을 입증.

## 이슈 / 위험

### 블로킹 (계약 의무)

1. **CHANGELOG 미갱신 — D5-2(세션 2·3) 행 부재 + 세션 1 행의 근거 문구가 정정 전 주장인 채 잔존.**
   `records-and-handoff.md` §CHANGELOG("major design or feature changes 시 갱신")과 §33행(오너 결정이 major feature change를 이끌면 CHANGELOG에 그 결정을 기록)의 의무 대상이다: D5-2는 오너 결정 주도의 기능 변화이며 SoT 버전을 올렸다(v1.8.1·v1.8.2·v1.8.3·v1.8.4는 전부 CHANGELOG 행을 받았다). 그런데 최신 행은 "2026-08-27 (세션 1)"에 머물러 있다. 더 심각한 쪽: 그 세션 1 행은 *"**본문은 생성 프롬프트에 통째로 실리지 않으므로**(브리프 §6)"* 를 4000자 결정의 근거로 적고 있는데, 이 문장은 같은 날 세션 2(40c4524)에서 **반증·정정된 주장**이고 SoT v1.8.7이 "종전 서술은 문자적 사실일 뿐이었다"고 명시한다. 최상위 요약면이 정본과 모순된 채로 남아, 다음 세션이 CHANGELOG에서 출발하면 뒤집힌 근거를 읽게 된다. — 이것이 본 검증의 유일 블로킹 발견이며 아래 판정 조건이다.

### 보강 권고 (비차단)

1. **상한 검사가 replay 조회 앞에서 400을 던진다**(accept.py:100 vs 114행). §3.3은 "replay lookup precedes stale-base and Gate"인데, 상한 이전에 성공한 accept(또는 env 하향 운용 당시의 유효 accept)를 같은 멱등키로 재시도하면 저장된 replay 반환 대신 400이 난다. 현재 실DB에 해당 사례 0(유일 초과 문서의 영수증 0건 — 실측)이므로 현행 데이터로는 발화 불가능하나, `_validate`가 이미 replay 앞에 있는 선례와 같은 부류의 설계 선택이다. 이 순서를 잠그는 셀 또는 의도 문서화가 있으면 다음 검증자가 추측하지 않는다.
2. **프론트 `RAW_TEXT_MAX_CHARS = 4000` 하드코딩 미러** — 서버 env override 시 사전 안내 임계만 어긋난다(차단은 서버 422·400이 최후 방어라 기능 영향 없음. 코드 주석에 이미 명시됨).
3. **측정 시점 비대칭**: 저장 축은 strip 전 `len(value)`, accept 축은 strip 후로 잰다. 공백 경계값에서 두 축 판정이 갈릴 수 있으나 양축 모두 4000자 초과 본문을 거부하는 계약 자체는 무변.
4. **설명창 1000자의 프론트 사전 안내 부재** — 서버 422만난다. 원고 카운터에 대응하는 UX가 필요한지는 오너 취사.

## 판정

**조건부 합격** — 조건: CHANGELOG에 2026-08-27 세션 2·3(D7 폐쇄·D5-2 시행) 행을 추가하고, 세션 1 행의 "본문은 생성 프롬프트에 통째로 실리지 않으므로" 근거 문구에 40c4524 정정을 반영(정정 주석 또는 문장 교체)할 것.

근거: 코드·계약·가드·수치 주장은 전부 독립 재현됐다 — 경계 매트릭스에 빈 칸 없음(경계/초과/env 양방향/무효 env/프로바이더 0회/NotFound 순서/짧은 본문 과잉방지/no-maxLength 전부 명명 셀 존재, 뮤테이션 6종 전부 양방향으로 물음), "전 경로"는 쓰기 경로 전수 스윕으로 성립, 실DB 영향 0건·씨드 판정·스택 상태 재현. 유일한 미달이 기록 산출물(CHANGELOG)의 누락·모순 잔존이며, 이는 문서 커밋 하나로 닫힌다.

## 미해결 항목 (운영 상태 — 결함 아님)

- 위 조건(CHANGELOG) 미결 — 오너 또는 다음 세션에서 문서 반영 후 승격 가능.
- D6 `unit_kind` 존치 판단(유지·제거·계층화) — 오너 대기 중.
- 신버전 빌드 육안 대조·AdSense 심사 상태 — 오너 몫.
- 씨드 장면(24,070자) 방치 여부 — 오너 결정 대기(방치 가능, 정리 원하면 파기).
- 검증 기록 이건의 등재로 `test_docs_indexes` 판정 열 전수 셀이 subtest +1 — 다음 백엔드 전수 기대값 **2526 / 4 / 2842**.

## 재현

```bash
cd /mnt/f/devel/ai_writte_system
git status --short          # 빈 것 확인(전 커밋 상태)
# focused
python3 -m pytest tests/test_draft_raw_text_limit.py tests/test_project_brief.py -q   # 32 passed·25 subtests
python3 -m pytest tests/test_application_api.py -q                                     # 124 passed·498 subtests
# 전수
docker compose -f docker-compose.test.yml up -d   # healthy 대기
python3 -m pytest -q                               # 2526/4/2841
docker compose -f docker-compose.test.yml down
cd frontend && npx vitest run && npx tsc --noEmit   # 373 passed·tsc clean
# DB
docker exec ai_writte_system-mongo-1 mongosh --quiet ai_writing_system --eval \
  'db.source_snapshots.find({$expr:{$gt:[{$strLenCP:"$raw_text"},4000]}},{raw_text:0}).length'  # 1
# 뮤테이션 예(V1): tests/test_application_api.py 새 항목에서 "503" 제거 후
python3 -m pytest "tests/test_application_api.py::WritingErrorContractDeclarationTest" -q
# → SUBFAILED(...scratch_id...); git checkout -- tests/test_application_api.py 후 clean 확인
```
