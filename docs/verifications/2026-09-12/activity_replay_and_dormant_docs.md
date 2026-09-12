# 활동 로그 D1=ⓑ · 문서 D1=ⓐ — 오너 결정이 남긴 작은 후속 둘 독립 검증

**최종 판정은 합격이다** — 조건 **C1** 은 폐쇄 커밋 `70efc23`(기록 `d6e381e` · SoT v1.8.65)이 특성 셀 둘로 닫았고, 승격 재검([`activity_replay_c1_promotion.md`](activity_replay_c1_promotion.md) — 변이 재적용 열세 회, 재감사 [`activity_replay_c1_promotion_audit.md`](activity_replay_c1_promotion_audit.md) 이 열한 종을 재현해 전건 일치)이 판정을 올렸다. 아래 본문은 발행 시점 그대로다.

> **조건부 합격**(발행 시점 판정 원문) — 조건 **C1**: SoT v1.8.64·HANDOFF·브리프가 새로 *계약으로 적은* 세 갈래 중 **두 갈래(`writing/accept` replay 유행 · 수동 저장 replay 유행)가 무셀이다.** 두 경로의 `activity.record` 를 replay 에서 꺼도(변이 MB-8·MB-9) **236 passed / 694 subtests 전건 초록**이다 — 오너가 **유예로 명시한 D2** 를 다음 슬라이스가 코드에서 조용히 풀 수 있고, 그때 SoT v1.8.64 의 문장은 **이 브리프의 원래 근거가 거짓이 된 것과 똑같은 방식으로** 거짓이 된다. 처방은 §Issues C1(특성 셀 둘, v1.8.61 `WithdrawalCancelAfterPurgeClaimTest` 선례와 같은 모양).

그 밖에는 **구현이 스코프 계약의 전 축에서 성립한다.** D1=ⓑ 의 뜻(*finalize 재전송이 활동 행을 만들지 않는다*)과 D1=ⓐ 의 뜻(*휴면 셋이 인덱스에서 닿는다*)을 **문서 대조가 아니라 실행으로** 재확인했고, 구현자가 보고한 변이 5종은 **diff 를 그대로 재적용해 건수·기명 셀까지 일치**했다. **구현자의 반증 주장(*"`writing/accept` 도 replay 에 활동 행을 남긴다"*)은 참이다** — 내 독립 프로브가 세 경로를 같은 자로 재어 재현했고(finalize 1행 · accept 2행 · 수동 저장 2행), 브리프가 근거로 인용한 2026-08-09 기록 §6-② 의 표도 처음부터 그렇게 적고 있었다. 즉 **브리프 정정은 옳다.** 범위 밖 변경은 없다(두 커밋 4파일·단일 훅 단위까지 확인).

## Subject metadata

- **검증일**: 2026-09-12 (검증 세션 — 세션 72 구현자와 다른 세션)
- **요청자**: 오너 (세션 72 지시 — "작업 다 되면 서브에이전트 스폰해서 독립검증 맡긴 후에 검증기록 확인해서 보강할 부분 보강까지 해줘")
- **검증자**: 구현 세션과 다른 독립 세션. **이 슬라이스의 코드를 한 줄도 쓰지 않았다.**
- **대상**: 커밋 `7979ff2`(활동 로그 D1=ⓑ) · `68aedf3`(문서 D1=ⓐ, HEAD) + 같은 슬라이스의 **미커밋 기록**(SoT v1.8.64 행 · 브리프 정정 셋 + §착수가 반증한 것 · `work_log` 세션 72 · HANDOFF · CHANGELOG · 루트 README).
- **정규 스펙(계약 스코프)**:
  - [`plans/activity-log-replay-and-partial-decisions.md`](../../plans/activity-log-replay-and-partial-decisions.md) — §결정 필요(13행, 오류 진원지) · §추천 · **오너 결정 D1=ⓑ·D2 유예·D3=ⓐ 표** · **§착수가 반증한 것**(구현 세션 신설) · §D1 착수 시.
  - [`plans/docs-directory-dormant-and-restructure-decisions.md`](../../plans/docs-directory-dormant-and-restructure-decisions.md) — 오너 결정 **D1=ⓐ** · §후속 고려 44~45행 · **★ D1 착수 시 함께 적을 한 문장**(63행).
  - [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.8.64** 행 · [`HANDOFF.md`](../../../HANDOFF.md) §지금의 계약 "활동 로그" 항목.
  - 근거로 인용된 선행 기록 [`verifications/2026-08-09/service_activity_log_accept_extension.md`](../2026-08-09/service_activity_log_accept_extension.md) §6-②.
- **환경**: WSL2 · `python3 -m pytest`(초점 실행 내 skip 0) · **전수는 돌리지 않았다** — 같은 트리에서 다른 작업 AI 가 동시에 돌고 있어 겹치면 과부하 타이밍 오탐이 난다는 지시. 대신 `--collect-only` 로 대조했다(아래 §기준선).
- **작업 트리 상태(공유 트리)**:
  - **시작 시점** `git status --short`:
    ```
     M README.md
     M docs/plans/activity-log-replay-and-partial-decisions.md
     M docs/system-contract-sot.md
    ```
  - **종료 시점**(내 기록 파일·인덱스 행을 쓰기 직전) `git status --short`:
    ```
     M CHANGELOG.md
     M HANDOFF.md
     M README.md
     M docs/daily_logs/2026-09-12/work_log.md
     M docs/plans/activity-log-replay-and-partial-decisions.md
     M docs/system-contract-sot.md
     M docs/verifications/2026-09-06/final_save_n1_promotion.md
     M docs/verifications/2026-09-12/account_withdrawal_slice5_promotion.md
     M docs/verifications/2026-09-12/admin_residual_purge_slice4b.md
     M docs/verifications/README.md
    ?? docs/verifications/2026-09-12/final_save_b1_promotion.md
    ?? docs/verifications/2026-09-12/slice4b_closure_promotion.md
    ?? docs/verifications/2026-09-12/slice5_closure_promotion.md
    ```
  - **★ 늘어난 것은 전부 내 소관이 아니다.** 앞 여섯은 세션 72 구현자의 기록 작업이고, 뒤 일곱(`verifications/` 축 넷 + 미추적 셋)은 **번호표 5번을 잡은 다른 작업 AI** 의 승격 재검 기록이다. 검증 중 `frontend/src/drafts/DraftEditor.tsx` 가 잠시 수정 상태로 보였다가 사라졌다(그 AI 의 변이·원복으로 보인다) — **손대지 않았고 기록만 남긴다.**
  - **★ 나는 본 작업 트리의 파일을 하나도 바꾸지 않았다.** 변이는 전부 탈치 워크트리 `/tmp/verify_s72`(`68aedf3` detached)에서 돌렸고 끝난 뒤 `worktree remove --force` 했다. 본 트리에 `git checkout`·`restore`·`stash`·`reset`·`commit` 을 **한 번도 쓰지 않았다.** 내가 만든 것은 이 기록 파일과 인덱스 행·건수 주장뿐이다.

## Scope

| 표면 | 무엇을 보는가 |
|---|---|
| ★ 결정 이행(활동) | `routers/drafts.py` finalize handler 의 `if not finalized.idempotent_replay:` 분기가 **실행으로** D1=ⓑ 의 뜻을 내는가 |
| ★ 반증 주장 | *"`writing/accept` 도 replay 에 활동 행을 남긴다"* · 수동 저장 축도 같은가 — **검증자 자작 프로브**로 재측 |
| ★ 신규 가드 | `test_activity_api.py` 행위 셀 둘 · `test_docs_indexes.py::DocsReadmeIndexTest` 둘이 실제로 잠그는가(변이 10종) |
| 결정 이행(문서) | `docs/README.md` §휴면 디렉터리가 휴면 셋의 `.md` 전부에 닿는가 · 브리프가 지시한 한 문장이 있는가 · 파일을 안 옮겼는가 |
| 가드 사각 | `_LINK_RE` 가 `.md` 만 본다 · `_DORMANT_DIRECTORIES` 수동 목록 · `glob("*/*.md")` 깊이 · 절 앵커 |
| 인접 replay 경로 | `writing/accept`·`drafts/{id}/versions` 를 실수로 함께 끄면 무는 셀이 있는가 |
| 문서 정확성 | SoT v1.8.64 행·`work_log` 세션 72·HANDOFF 기준선·CHANGELOG 의 수치와 주장 |
| 범위 | `git show --stat` + 훅 단위 — 슬라이스와 무관한 줄이 섞였는가 |

## Methodology

1. **사전 점검**: `git status --short`(위 metadata). **트리가 더럽고 커밋해서는 안 되므로** 가이드 §Mutation testing 표의 셋째 행이 아니라 **탈치 워크트리 분기**를 썼다:
   `git -C /mnt/f/devel/ai_writte_system worktree add --detach /tmp/verify_s72 68aedf3`.
2. **계약 스코핑 → 경계 행렬**: 위 정규 스펙을 먼저 읽고 계약이 요구하는 분기(fire / NOT fire)를 표로 세운 뒤 코드를 봤다.
3. **결정 이행 실측(검증자 프로브)**: `probe_replay.py`(자작 — 구현자 셀·하네스 재사용 안 함). 세 경로를 **하나의 앱 조립**에서 같은 방식(같은 `idempotency_key` 2회 POST)으로 돌리고 매 요청 뒤 활동 행 수와 응답 `idempotent_replay` 를 찍는다. `X-Confirm-Duplicate` 유무 양쪽.
4. **초점 실측**(워크트리 `68aedf3`):
   - `python3 -m pytest tests/test_activity_api.py tests/test_docs_indexes.py -q` → **39 passed / 317 subtests**
   - `python3 -m pytest tests/test_activity_api.py -q` → **20 passed** · `tests/test_docs_indexes.py` 단독 → **19 passed / 317 subtests**
   - `python3 -m pytest tests/test_activity_actions.py tests/test_activity_log.py tests/test_final_save_analysis.py tests/test_billable_actions.py -q` → **45 passed / 212 subtests**
   - MB-8·MB-9 용 넓은 셋: `tests/test_activity_api.py tests/test_activity_actions.py tests/test_activity_log.py tests/test_writing_accept.py tests/test_application_api.py` → **236 passed / 694 subtests**
5. **뮤테이션 15종**(재적용 5 + 검증자 자작 10 — 아래 §변이 표). 절차는 매번 동일: 워크트리 `git status --short` 확인(빈) → 변이(파일 백업 후 python `pathlib.write_text` 치환 — `sed -i`/`perl -i` 는 이 저장소 규칙상 금지) → 초점 셀 재실행(**요약 줄 + `FAILED|SUBFAILED` 를 같이 읽는다**) → 백업에서 원복 → `git diff --stat` 빈 것 확인. 파일 추가·삭제형 변이는 `mv`/`rm` 뒤 원위치.
6. **기준선 대조**: 본 트리에서 **읽기 전용** `python3 -m pytest --collect-only -q`.
7. **정리**: `git -C … worktree remove /tmp/verify_s72 --force` → 본 트리 `git status --short` 재확인.

## Findings

### 1. ★ 결정 이행은 사실이다 — 실행으로 확인

**검증자 프로브 실측**(워크트리 `68aedf3`, in-memory 조립, 같은 키 2회 POST):

| 경로 | POST#1 | POST#2 | 활동 행(누적) | actions |
|---|---|---|---|---|
| `drafts/{id}/finalize` | 200 · `replay=false` | 200 · `replay=true` | 1 → **1** | `['draft_finalized']` |
| `writing/accept` | 200 · `replay=false` | 200 · `replay=true` | 1 → **2** | `['draft_version_accepted', 'draft_version_accepted']` |
| `drafts/{id}/versions`(수동 저장) | 200 · `replay=false` | 200 · `replay=true` | 1 → **2** | `['draft_version_saved', 'draft_version_saved']` |

- **D1=ⓑ 의 뜻이 코드에서 성립한다** — finalize 재전송이 행을 만들지 않는다([`routers/drafts.py:706-713`](../../../services/application/app/routers/drafts.py#L706)).
- **의미론도 안전하다**: `core_sot/service.py:1179-1192` 는 *같은 키로 이미 finalize 된* 경우에만 `idempotent_replay=True` 를 낸다(다른 키면 `AlreadyFinalized` → 409, 그 경로도 행 없음). **버전이 실제로 만들어졌는데 replay 로 보고되는 창은 없다** — 즉 이 분기가 첫 저장을 삼킬 구조적 위험이 없다.
- **경합 프로브 추가**: 내부 저장 키(`f"final:{key}"`)를 `POST /versions` 로 **선점**한 뒤 finalize 를 2회 쳐도 결과는 `['draft_version_saved', 'draft_finalized']` — finalize 는 한 번만 남고 재전송은 여전히 무행이다. 우회 창 없음.

**문서 D1=ⓐ**: [`docs/README.md`](../../README.md) §"휴면 디렉터리 (한 번 쓰고 멈춘 것)" 가 휴면 셋의 `.md` **8건 전부**(`verification_briefs/2026-06-24` 3 · `benchmarks/2026-07-15` 1 + `.json` 2 · `live_review_briefs/2026-07-18` 2)를 링크하고, 브리프 63행이 지시한 한 문장(*"`verifications/` 의 전신 — 더는 쓰지 않는다"*)이 `verification_briefs` 줄에 있다. **파일은 옮기지 않았다**(`git show --stat 68aedf3` 가 rename 을 안 낸다). 표 행 하나로 §휴면 절을 문서 지도에 붙였다.

### 2. ★ 구현자의 반증 주장은 **참이다** — 브리프 정정이 옳다

세 갈래로 확인했다.

1. **행위**: 위 표 — `writing/accept` 는 replay 에 **2건**을 남긴다. 브리프 13행의 *"`writing/accept` 는 replay 를 안 남긴다"* 는 **거짓**이다.
2. **코드 대칭**: [`quota/dedupe.py:91-95`](../../../services/application/app/quota/dedupe.py#L91) 의 `KEY_REPLAY_ACTIONS` 에서 `writing_accept`·`draft_finalize` 가 **둘 다 `"handler"`** 이고, [`routers/writing.py:1368-1374`](../../../services/application/app/routers/writing.py#L1368) 의 기록 조건은 `if result.saved is not None:` 뿐이라 replay 에도 실행된다(replay 에도 `saved` 가 실린다).
3. **선행 기록**: 브리프가 근거로 인용한 [`verifications/2026-08-09/service_activity_log_accept_extension.md`](../2026-08-09/service_activity_log_accept_extension.md) §6-② 의 표(182-190행)가 *"`writing/accept`(성공) 3회 POST → 이벤트 3"* 이라 **처음부터 반대로** 적고 있다. 브리프가 자기 근거를 반대로 요약했다는 구현자 진술이 그대로 확인된다.

**수동 저장 축도 정정 표대로다** — `drafts/{id}/versions` 는 [`routers/drafts.py:648-653`](../../../services/application/app/routers/drafts.py#L648)에서 **무조건** 기록하므로 replay 에 2건이다.

→ **브리프 세 곳의 반증 표식과 §착수가 반증한 것 절은 사실에 맞다.** 원문을 지우지 않고 표식으로 정정한 것도 이 저장소의 이력 문서 규칙과 일치한다.

### 3. 경계 행렬 — 계약 분기 ↔ 기명 셀

| # | 계약 조항(출처) | 코드 | 셀 | 판정 |
|---|---|---|---|---|
| B1 | **finalize replay 는 행을 남기지 않는다**(브리프 D1=ⓑ · SoT v1.8.64 · HANDOFF 활동 로그) | `routers/drafts.py:706` | `test_resending_the_same_final_save_key_leaves_no_second_row` | 잠김(MV-1) |
| B2 | **finalize 첫 요청은 여전히 남긴다**(같은 결정의 over 방향 · 브리프 §D1 착수 시 "양방향") | 같은 줄 | `test_the_first_final_save_is_recorded` | 잠김(MV-2) |
| B3 | replay 셀은 **`idempotent_replay: true` 를 함께 단정**해야 한다(SoT v1.8.64 · HANDOFF — 아니면 *409 로 막혔다* 와 구분 불가) | 응답 payload | 같은 replay 셀 `assertTrue(again.json()["idempotent_replay"])` | 잠김 — **그리고 MB-1 이 입장 거부 가설을 깼다**(§4) |
| B4 | **`writing/accept` 는 replay 에 행을 남긴다**(SoT v1.8.64 *"셋으로 가른다"* · HANDOFF *"writing/accept 와 수동 저장은 남긴다(D2 유예)"* · 브리프 §착수가 반증한 것 표) | `routers/writing.py:1368` | **셀 없음** | **C1(차단)** — MB-8 실증 |
| B5 | **수동 저장은 replay 에 행을 남긴다**(같은 세 출처) | `routers/drafts.py:648` | **셀 없음** | **C1(차단)** — MB-9 실증 |
| B6 | 휴면 셋의 `.md` 전부가 `docs/README.md` 에서 닿는다(문서 D1=ⓐ) | `docs/README.md` §휴면 | `test_every_dormant_document_is_reachable_from_the_index` | 잠김(MV-3·MB-6) |
| B7 | 인덱스의 `.md` 링크가 해석된다(= 파일을 옮기고 링크를 안 고치는 과교정 방향) | 같은 절 | `test_every_index_link_resolves` | 잠김(MV-4·MB-6) |
| B8 | 파일은 옮기지 않는다(옛 인용 보존 — 브리프 D1=ⓐ) | — | 셀 없음(상태 단정 불가 축) | 비차단 H4 |
| B9 | 브리프가 지시한 한 문장이 인덱스 줄에 있다(브리프 63행) | `docs/README.md` | **셀 없음** | 비차단 H3 |

**★ B4·B5 가 이 슬라이스의 핵심 사각이다.** 결정 자체(D1)는 양방향으로 잠겼는데, **그 결정이 만든 *비대칭* 은 어느 방향으로도 안 잠겼다.**

### 4. ★ 변이 표 — 재적용 5종(diff 원문)

> 모두 탈치 워크트리 `/tmp/verify_s72`(`68aedf3`)에서. **`services/application/app/routers/drafts.py` 에는 `if not finalized.idempotent_replay:` 가 두 군데(706·741행)** 있어 단순 치환이 2곳을 친다 — 앵커에 바로 위 주석줄을 붙여 유일화했다. 구현자 표에 없는 함정이라 여기 적는다.

| # | 방향 | 파일 | 실제 diff | 실측 결과 | 보고와 일치 |
|---|---|---|---|---|---|
| **MV-1** | under | `routers/drafts.py:706` | <pre>-        if not finalized.idempotent_replay:<br>+        if True:</pre> | **1 failed** `ActivityRecordingTest::test_resending_the_same_final_save_key_leaves_no_second_row` (`AssertionError: 5 != 4`) · 19 passed | ✅ |
| **MV-2** | over | 같은 줄 | <pre>-        if not finalized.idempotent_replay:<br>+        if False:</pre> | **1 failed** `::test_the_first_final_save_is_recorded` (`'draft_created' != 'draft_finalized'`) · 19 passed | ✅ |
| **MV-3** | under | `docs/README.md` | <pre>-[`llm_gateway_f1_f2_live_smoke.md`](verification_briefs/2026-06-24/llm_gateway_f1_f2_live_smoke.md)<br>+`llm_gateway_f1_f2_live_smoke.md`</pre> | **1 failed** `DocsReadmeIndexTest::test_every_dormant_document_is_reachable_from_the_index` · 18 passed / 317 subtests | ✅ |
| **MV-4** | over | `docs/README.md` | <pre>-…](verification_briefs/2026-06-24/llm_gateway_slice_0_6_httpx.md)<br>+…](verification_briefs/2026-06-24/llm_gateway_slice_0_6_httpx_MOVED.md)</pre> | **2 failed** `::test_every_dormant_document_is_reachable_from_the_index` + `::test_every_index_link_resolves` · 17 passed | ✅ |
| **MV-5** | 등가 | 둘 다 | <pre>-        if not finalized.idempotent_replay:<br>+        if finalized.idempotent_replay:<br>+            pass<br>+        else:<br>             activity.record(</pre><br><pre>-**★ 휴면은 폐기가 아니다.**<br>+**★ 휴면이란 버렸다는 뜻이 아니다.**</pre> | **39 passed / 317 subtests** — 전건 초록 | ✅ |

> 구현자 표와 **리터럴만 다르다**(MV-4 의 대체 파일명, MV-5 의 산문 문구). 모양이 같으므로 결과도 같아야 하고, 실제로 같았다.

### 5. ★ 변이 표 — 검증자 블라인드스폿 10종

| # | 노린 사각 | 파일 | 실제 diff / 조작 | 결과 | 해석 |
|---|---|---|---|---|---|
| **MB-1** | replay 셀이 **분기**가 아니라 **입장 거부**를 재는 것 아닌가(지시가 깨 보라 한 가설) | `tests/test_activity_api.py` | <pre>             json={"raw_text": "본문", "idempotency_key": "fk1"},<br>-            headers={"X-Confirm-Duplicate": "1"},<br>         )</pre> | **1 failed** — `AssertionError: 429 != 200` | **가설이 깨졌다.** 헤더를 빼면 셀은 *조용히 통과* 하는 게 아니라 **상태코드 단정에서 시끄럽게 실패**한다(입장이 내는 얼굴은 409 가 아니라 **429**). 즉 헤더는 장식이 아니라 부하 지점이고, 셀은 실제로 handler 분기에 도달한다(MV-1 이 행 수 4→5 로 증명). **B3 잠김 확정.** |
| **MB-2** | `_LINK_RE` 가 `.md` 만 본다 — 휴면 `.json` 링크가 깨져도 조용한가 | `docs/README.md` | <pre>-…](benchmarks/2026-07-15/writing_gate_quality_q4_baseline.json)<br>+…](benchmarks/2026-07-15/GONE_baseline.json)</pre> | **28 passed / 939 subtests — 전건 초록** | **사각 확인.** 휴면 벤치마크의 **원자료 `.json` 둘은 이 절이 유일한 진입점인데 링크 무결성이 무가드**다. 비차단 **H1**(계약상 `.md` 만 보겠다고 `_LINK_RE` 주석이 선언하므로 결함이 아니라 선언된 한계 — 다만 D1=ⓐ 의 값이 *"닿게 한다"* 인데 닿는 대상 둘이 가드 밖이라는 점은 적어 둘 만하다). |
| **MB-3** | 같은 `.json` 이 **사라지면** 아무도 모르나 | `docs/benchmarks/2026-07-15/` | `mv writing_gate_quality_q4_baseline.json /tmp/` | **1 failed** `test_repo_hygiene.py::ForbiddenLiteralsTest::test_binary_skips_are_only_images` | 문다 — 단 **휴면 가드가 아니라 추적 파일 전수 스캔**이 잡는다(읽기 실패가 "바이너리 스킵"으로 새어 계약을 깬다). 안전망이 있다는 사실은 H1 의 심각도를 낮춘다. |
| **MB-4** | `_DORMANT_DIRECTORIES` 에 **네 번째** 디렉터리가 생기면 가드가 발견하나 | 새 경로 | `mkdir -p docs/dormant_probe/2026-09-12 && printf '# 프로브\n\n내용.\n' > …/orphan.md` | **28 passed / 939 subtests — 전건 초록** | **목록은 사람이 고쳐야 한다.** 다만 **그 사실이 문서에 적혀 있다** — `tests/test_docs_indexes.py:33-37` 주석이 *"관행이 다시 필요해지면 새 디렉터리가 아니라 `verifications/` 로 간다 — 그래서 이 목록은 늘지 않는 것이 정상이다"* 라고 이유까지 적는다. **계약상 허용**으로 판단한다(차단 아님). 비차단 **H2**: 그래도 *새 최상위 `docs/` 디렉터리가 어느 인덱스에서도 안 닿는* 상태는 이 슬라이스가 없애려던 바로 그 상태다. |
| **MB-5** | `glob("*/*.md")` 깊이 — 날짜 디렉터리 밖의 `.md` | `docs/benchmarks/` | `printf … > docs/benchmarks/orphan_depth1.md` | **28 passed / 939 subtests — 전건 초록** | 사각. 휴면 디렉터리 **바로 아래**(날짜 하위 디렉터리가 아닌) `.md` 는 도달성 검사 대상이 아니다. 비차단 **H2** 에 합류. |
| **MB-6** | 휴면 `.md` 자체가 **사라지면** | `docs/live_review_briefs/2026-07-18/` | `mv analysis_retry_after_accept.md /tmp/` | **1 failed** `DocsReadmeIndexTest::test_every_index_link_resolves` | 문다. 파일 삭제 방향은 잠겨 있다. |
| **MB-7** | 표 행 → 절로 가는 **앵커** 링크 | `docs/README.md` | <pre>-## 휴면 디렉터리 (한 번 쓰고 멈춘 것)<br>+## 보존된 휴면 디렉터리</pre> | **19 passed / 317 subtests — 전건 초록** | 사각. 표 행의 `[아래 절](#휴면-디렉터리-한-번-쓰고-멈춘-것)` 이 **조용히 끊긴다**(`_LINK_RE` 는 `.md` 없는 앵커-온리 링크를 안 본다). 비차단 **H1** 에 합류. |
| **MB-8** | **인접 replay 경로를 실수로 함께 끄면** — `writing/accept` | `routers/writing.py:1368` | <pre>-        if result.saved is not None:<br>+        if result.saved is not None and not result.idempotent_replay:<br>             activity.record(</pre> | **236 passed / 694 subtests — 전건 초록** | **★ 차단 C1.** SoT v1.8.64·HANDOFF·브리프가 *계약으로 적은* "accept 유행"이 **무셀**이다. |
| **MB-9** | 같은 것 — 수동 저장 | `routers/drafts.py:648` | <pre>-        activity.record(<br>+        if not result.idempotent_replay:<br>+          activity.record(</pre> | **236 passed / 694 subtests — 전건 초록** | **★ 차단 C1.** "수동 저장 유행"도 무셀. |
| **MB-10** | finalize 의 내부 저장 키 선점으로 분기를 우회할 수 있나(구조 프로브) | — | `POST /versions`(key=`final:fk1`) → `POST /finalize`(key=`fk1`) ×2 | `['draft_version_saved', 'draft_finalized']` · #2 `replay=true` 무행 | 우회 없음. 분기가 구조적으로 안전하다. |

**대조 기준선**(변이 전): `test_activity_api` + `test_docs_indexes` = **39 passed / 317 subtests** · 넓은 셋 = **236 passed / 694 subtests** · 문서 가드 셋 = **28 passed / 939 subtests**.

### 6. 문서 정확성

| 주장 | 출처 | 실측 | 판정 |
|---|---|---|---|
| `test_activity_api` 18 → **20 passed** | work_log 세션 72 | 20 passed | ✅ |
| `test_docs_indexes` 17 → **19 passed / 317 subtests** | 동상 | 19 / 317 | ✅ |
| `test_activity_actions`·`test_activity_log`·`test_final_save_analysis`·`test_billable_actions` **45 passed / 212 subtests** | 동상 | 45 / 212 | ✅ |
| 변이 5종 결과(1·1·1·2·39초록) | work_log · SoT v1.8.64 | 전건 재현(§4) | ✅ |
| `draft_finalized` 는 착수 전 **행위 셀이 하나도 없었다** | work_log §Issues | `git grep draft_finalized 7979ff2~1 -- tests/` → 분류표 주석 1줄뿐 | ✅ |
| 착수 시점 `docs/README.md` 는 **어느 링크 가드 밖에도 있었다**(`_assert_links_resolve` 호출 3곳) | work_log §Issues · SoT v1.8.64 | `git show 7979ff2~1:tests/test_docs_indexes.py` → 정의 1 + 호출 3(plans·verifications·루트 README) | ✅ |
| 백엔드 전수 **3060 passed / 1 skipped / 4215 subtests** · 직전 `0769cc9` **3056/1/4215** · 차이 **+4 passed / +0 subtests = 신규 셀 넷** | HANDOFF 회귀 기준선 | 전수는 겹치지 않게 **안 돌렸다**. 대조: 본 트리 `pytest --collect-only -q` → **3061 collected** = 3060 + skip 1 **산술 일치**. 신규 셀도 정확히 넷(활동 2 + 문서 2)이고 넷 다 `subTest` 를 안 써 **+0 subtests** 가 성립한다 | ✅(대조 일치) |
| **종전 기준선의 `4213` 이 틀렸다**(세션 70 유도가 자기 검증 기록 문서의 +2 를 못 셌다) | HANDOFF | 구현 세션이 **두 리비전 통제 대조로 자기 슬라이스가 아닌 앞 슬라이스의 오류를 잡아 고쳤다.** 그 절차(양단 실측 → 문서 가드 둘의 936→938 귀속)는 HANDOFF 가 이미 두 번 적어 둔 함정의 정확한 적용이다 | ✅ **가산점** |
| 프런트 **무변**(488/41 그대로) | work_log · SoT | 두 커밋에 `frontend/` 파일 0 (`git show --stat`). 트리에 잠시 보인 `DraftEditor.tsx` 수정은 **다른 AI** 의 것 | ✅ |
| `schema.d.ts` 무차분 · operation **107 무변** · 응답 스키마 무변 | SoT v1.8.64 | 두 커밋이 `api/models.py`·라우트 선언을 안 건드린다(4파일 전부) | ✅ |
| 브리프 정정 셋의 사실성 | 브리프 · SoT | §2 에서 세 갈래로 확인 | ✅ |

**미완 상태 하나**(결함 아님, §Outstanding): 내 검증 시점에 `work_log` 세션 72 의 §Verification 두 줄이 아직 자리표시자였다가(`BASELINE_PLACEHOLDER`·`VERIFY_PLACEHOLDER`) 검증 중 앞의 하나가 채워졌다. **`VERIFY_PLACEHOLDER` 는 이 기록으로 채워질 자리다.**

### 7. 범위 밖 변경 — 없다

| 커밋 | 파일 | 훅 | 확인 |
|---|---|---|---|
| `7979ff2` | `services/application/app/routers/drafts.py` (19줄) | `@@ -697,12 +697,19 @@` **1개** | 전부 finalize 의 기록 분기(주석 6 + `if` 1 + 재들여쓰기 6 = 13 변경줄, `-6`) |
| `7979ff2` | `tests/test_activity_api.py` (+60) | 1개 | 헬퍼 1 + 셀 2 |
| `68aedf3` | `docs/README.md` (+13) | 2개 | 지도 표 행 1 + §휴면 12 |
| `68aedf3` | `tests/test_docs_indexes.py` (+36) | 2개 | `_DORMANT_DIRECTORIES` 상수 6 + `DocsReadmeIndexTest` 30 |

**세션 70 의 H3 형(인용부호 같은 범위 밖 문자 변경)은 재발하지 않았다.** 서식·인접 코드 손질 0줄.

## Issues / Risks

### Blocking (계약 의무)

**C1 — 새로 계약이 된 "세 갈래" 중 두 갈래가 무셀이다.**

- **무엇이 계약인가**: SoT **v1.8.64** 행이 *"ⓑ 는 두 규칙을 하나로 모으는 것이 아니라 **셋으로 가른다**(finalize 무행 · accept 유행 · 수동 저장 유행)"* 라 적고, **HANDOFF §지금의 계약** "활동 로그" 항목이 *"`drafts/{id}/finalize` 만 … 기록하지 않고, `writing/accept` 와 수동 저장은 **남긴다**(D2 유예)"* 로 같은 말을 코드 만지기 전 필독 자리에 박았으며, 브리프 §착수가 반증한 것의 표가 세 행으로 열거한다.
- **실측**: `routers/writing.py:1368`·`routers/drafts.py:648` 의 기록을 각각 replay 에서 꺼도(**MB-8·MB-9**) **236 passed / 694 subtests 전건 초록**. 두 "유행" 분기는 **어느 방향으로도 안 잠겨 있다.**
- **왜 차단인가**(가이드 §"boundary matrix has no empty cells"): ① 계약이 명시적으로 적은 분기가 기명 셀에 대응하지 않는다. ② **D2 는 오너가 유예로 명시한 축**이다 — 무셀이면 다음 슬라이스가 "규칙을 하나로 모으자"며 코드 두 줄로 **오너 결정을 대신 풀 수 있고 아무 셀도 안 문다**. ③ 그리고 그 순간 SoT v1.8.64 의 문장은 **이 브리프의 원래 근거가 거짓이 된 것과 정확히 같은 방식으로** 거짓이 된다 — 산문으로만 적힌 replay 처분 주장이 한 달 동안 아무도 모르게 틀려 있던 것이 이 슬라이스의 발원이다. 같은 병을 같은 자리에 다시 심는 셈이다.
- **처방**(닫으면 판정이 올라간다): `tests/test_activity_api.py` 에 **특성 셀 둘**을 넣는다. 형태는 이미 이 저장소에 선례가 있다 — SoT **v1.8.61** 이 세운 `test_auth_users.py::WithdrawalCancelAfterPurgeClaimTest`(*"이 셀은 이 동작을 승인하지 않는다 — 결정이 뒤집히면 셀과 문장이 함께 뒤집히는 자리"*)와 같은 모양이다.
  1. `test_resending_the_same_accept_key_still_records_a_second_row` — `writing/accept` 를 같은 `idempotency_key` 로 2회 POST 하고 `assertEqual(len(repo.events), 2)` + 두 번째 응답의 `idempotent_replay is True`. 하네스는 `tests/test_writing_accept.py::WritingAcceptApiTest._setup(activity_repo=…)` 가 이미 있다.
  2. `test_resending_the_same_save_key_still_records_a_second_row` — `drafts/{id}/versions` 를 같은 키로 2회 POST(재전송에 `X-Confirm-Duplicate`) 하고 같은 단정.
  - **두 docstring 에 반드시 적을 것**: 이것은 **D2 유예의 현재 상태를 고정하는 특성 셀**이지 승인이 아니며, **오너가 D2=ⓑ 를 고르면 이 셀들과 SoT v1.8.64 문장·HANDOFF 줄이 *함께* 뒤집힌다**. 그래야 다음 작업자가 "셀이 있으니 옳은 동작"으로 오독하지 않는다.

### Hardening (비차단)

- **H1 — `docs/README.md` 휴면 절의 *비-`.md` 도달 경로가 무가드*다.** ① 벤치마크 원자료 `.json` 둘의 링크가 깨져도 조용하고(MB-2) ② 표 행 → 절로 가는 앵커가 절 제목 변경에 조용히 끊긴다(MB-7). `_LINK_RE` 주석이 *"외부 URL·디렉터리·LICENSE 는 대상이 아니다"* 로 `.md` 한정을 **선언**하므로 결함이 아니라 선언된 한계다. 다만 D1=ⓐ 의 값이 *"닿게 한다"* 인데 닿아야 할 대상 둘이 가드 밖이다. 처방: `DocsReadmeIndexTest` 에 셀 하나 — 이 절 안의 **모든** 상대 링크(확장자 무관 + 앵커-온리는 `##` 제목 슬러그와 대조)를 해석. 파일 *삭제* 방향은 `test_repo_hygiene` 이 이미 덮는다(MB-3).
- **H2 — 휴면 목록의 두 사각.** ① `_DORMANT_DIRECTORIES` 에 없는 새 최상위 `docs/` 디렉터리(MB-4) ② 휴면 디렉터리 바로 아래 깊이의 `.md`(MB-5, `glob("*/*.md")`) 가 어느 인덱스에도 안 닿은 채 조용하다. **목록이 수동인 것 자체는 계약대로**이고 이유가 `tests/test_docs_indexes.py:33-37` 주석에 적혀 있으므로 차단이 아니다. 처방(더 나은 쪽): `docs/` 아래 `.md` 전수를 대상으로 *어느 인덱스에서도 안 닿는 파일 0건* 을 재는 셀 하나 — 그러면 `_DORMANT_DIRECTORIES` 수동 목록 자체가 불필요해진다. 이 슬라이스가 닫은 상태(*"살아 있는 문서 그래프에서 완전히 끊긴 유일한 파일들"*)를 **재발 방지까지** 끌어올리는 자리다.
- **H3 — 브리프가 지시한 한 문장이 무셀.** 브리프 63행의 *"`verifications/` 의 전신 — 더는 쓰지 않는다"* 는 **결정의 내용물**인데 지우면 아무도 안 문다. 처방: `DocsReadmeIndexTest` 에 그 절이 `verifications/` 와 `전신` 을 함께 담는지 재는 한 줄(정책 문서 축에서 이미 쓰는 문언 핀과 같은 형태).
- **H4 — "파일을 옮기지 않는다"가 무셀.** 휴면 파일을 `verifications/` 로 옮기고 링크만 고치면 전건 초록이다(D1=ⓐ 가 ⓑ 로 조용히 바뀐 상태). 처방: 휴면 셋의 경로 8개를 상수로 핀하는 셀. **다만 실익 대비 비용이 크고 옮기는 행위 자체가 눈에 띄므로 우선순위는 낮다.**
- **H5 — `routers/drafts.py` 의 `if not finalized.idempotent_replay:` 중복.** 706행(신규 활동 분기)과 741행(선행 분석 러너 분기)의 문자열이 **완전히 같다.** 변이·리팩터가 앵커로 쓰면 2곳을 친다(내 첫 시도가 그랬다). 코드 결함은 아니지만 **다음 검증자가 같은 자리에서 멈춘다** — HANDOFF 함정 절에 한 줄이면 닫힌다.

> ## 폐쇄 보고 (2026-09-12, 구현 세션 — `70efc23`)
>
> **조건 C1 을 닫았고 하드닝 둘(H3·H5)을 함께 반영했다. 판정 승격은 이 보고가 하지 않는다** — 조건을 닫은 세션이 자기 판정을 올리면 독립성이 사라지므로(v1.8.52·v1.8.57·v1.8.63 선례), 승격은 다음 독립 검증 세션이 재적용으로 판정한다.
>
> - **C1 → 특성 셀 둘**(처방 그대로, v1.8.61 `WithdrawalCancelAfterPurgeClaimTest` 모양):
>   - `tests/test_writing_accept.py::WritingAcceptApiTest::test_resending_the_same_accept_key_still_records_a_second_row` — 같은 키 2회 POST → `idempotent_replay is True` + `len(repo.events) == 2` + action 집합이 `{"draft_version_accepted"}`.
>   - `tests/test_activity_api.py::ActivityRecordingTest::test_resending_the_same_save_key_still_records_a_second_row` — 수동 저장 축 같은 모양(재전송에 `X-Confirm-Duplicate`), `before + 1`.
>   - **두 docstring 이 지시받은 문장을 명시한다** — *"이 셀은 이 동작을 승인하지 않는다 · 오너가 D2=ⓑ 를 고르면 이 셀과 SoT v1.8.64 문장·HANDOFF 줄이 **함께** 뒤집힌다"*. accept 쪽 docstring 은 **왜 셀이어야 하는가**(산문으로만 적힌 replay 처분 주장이 한 달간 틀려 있던 것이 이 슬라이스의 발원)를 함께 적어 다음 작업자가 "셀이 있으니 옳은 동작"으로 오독하지 않게 했다.
>   - **폐쇄 실증 — 검증자 변이 재적용 둘이 이제 문다**: **MB-8**(`routers/writing.py` 의 `if result.saved is not None:` → `… and not result.idempotent_replay:`) → **1 재실패**(accept 특성 셀, 검증 시점 236셀 전건 초록이던 자리) · **MB-9**(수동 저장 `activity.record` 를 `if not result.idempotent_replay:` 로 감쌈) → **1 재실패**(수동 저장 특성 셀). 둘 다 **탈치 워크트리**(`/tmp/mv_slice72` @ `70efc23`)에서 적용·원복했고 본 트리에 `git checkout` 을 쓰지 않았다(공유 트리).
>   - **★ MB-9 첫 시도는 무효였다** — 앵커 변수명을 `saved` 로 잘못 짚어 `NameError` 가 났고, 그것은 *가드가 물었다* 가 아니라 *변이가 안 섰다* 이다. 변수명(`result`)을 확인해 재적용했다. H5 와 같은 뿌리(앵커를 안 세고 치환)라 함정 절에 함께 적었다.
> - **H3 → 가드 한 셀**(`DocsReadmeIndexTest::test_the_dormant_section_says_what_the_old_name_was`): 브리프가 *"함께 적으라"* 고 지시한 문장이 **결정의 내용물**인데 지워도 아무도 안 물던 자리. 절 본문만 떼는 헬퍼(`_dormant_section`)로 범위를 좁히고 — 이 파일은 `verifications/` 를 여러 줄에서 인용한다 — 앵커를 **수사가 아니라 두 낱말**(`verifications/`·`전신`)로 잡았다(문장을 다듬는 정상 편집까지 물면 가드가 문장을 화석으로 만든다).
> - **H5 → HANDOFF 함정 절 두 줄**: ① `routers/drafts.py` 의 `if not …idempotent_replay:` 가 **두 곳**이라 치환 전 `count(...) == 1` 을 단정하라는 것 + **cwd 가 옛 리비전 워크트리에 남으면 `grep`/`sed` 가 옛 파일을 읽어 "쓰기가 반영 안 됐다"는 오진이 난다**(같은 날 실제로 겪었다) ② **같은 트리에서 다른 작업 AI 가 도는 창**의 규칙(개수 주장 가드가 서로의 미커밋 문서 때문에 계속 빨갛다 · 지목 실행으로 자기 실패를 가르고 남의 것은 고치지 않는다 · 경로를 명시해 스테이징한다).
> - **안 닫은 것**: **H1**(비-`.md` 링크·앵커 무가드) · **H2**(`_DORMANT_DIRECTORIES` 수동 목록과 `glob` 깊이 — 검증자 제안대로 *`docs/` 아래 안 닿는 `.md` 0건* 셀로 일반화하는 편이 낫다) · **H4**(파일 이동 무셀 — 검증자 자신이 *실익 대비 비용이 크다* 고 적었다). 셋 다 **비차단**이고 H2 는 이 슬라이스보다 큰 자리라 다음 문서 슬라이스 몫으로 남긴다.
> - 회귀: `test_activity_api` 20→**21** · `test_writing_accept` **+1** · `test_docs_indexes::DocsReadmeIndexTest` 2→**3**. 초점 `test_activity_api`+`test_writing_accept` **77 passed / 19 subtests**.

## Verdict

**합격**(승격 — 2026-09-12 승격 재검 [`activity_replay_c1_promotion.md`](activity_replay_c1_promotion.md) 이 변이 재적용 열세 회로 조건 폐쇄를 확증). 발행 시점 판정 원문:

> **조건부 합격** — **C1**: SoT v1.8.64·HANDOFF·브리프가 새로 계약으로 적은 replay 처분 **세 갈래 중 두 갈래**(`writing/accept` 유행 · 수동 저장 유행)가 **무셀**이다(MB-8·MB-9 각 236 passed 전건 초록). 오너가 유예로 명시한 **D2 를 다음 슬라이스가 코드에서 조용히 풀 수 있는 상태**이고, 그것은 이 브리프의 원래 근거가 거짓이 된 것과 같은 병이다. 특성 셀 둘로 닫힌다(§Issues C1).

근거가 되는 것:

1. **결정 이행은 실행으로 확인됐다** — D1=ⓑ 의 뜻(finalize 재전송 무행)과 D1=ⓐ 의 뜻(휴면 셋 도달)이 둘 다 성립하고, 의미론·우회 창까지 프로브로 닫았다(MB-10, `core_sot` replay 판정 구조).
2. **구현자의 반증 주장은 참이다** — 검증자 자작 프로브·코드 대칭(`KEY_REPLAY_ACTIONS`)·인용 기록 원문 세 갈래로 확인. **브리프 정정은 옳고, 원문 보존 방식도 이 저장소 규칙과 맞다.**
3. **보고된 변이 5종이 diff 재적용으로 건수·기명 셀까지 전건 일치**했고, 지시가 깨 보라 한 가설(*replay 셀이 분기가 아니라 입장 거부를 재는 것 아닌가*)은 **MB-1 이 반증**했다 — 헤더를 빼면 429 로 시끄럽게 실패하므로 셀은 실제로 handler 분기에 도달한다.
4. **범위 밖 변경 0** — 훅 단위까지 확인. 세션 70 의 H3 형 재발 없음.
5. **기준선 서술이 오히려 앞 슬라이스의 오류를 잡았다** — 두 리비전 통제 대조로 `4213`→`4215` 를 정정했고 `--collect-only 3061` 과 산술이 맞는다.

## Outstanding items

1. **C1 을 닫는 것은 구현 세션의 몫이다** — 나는 결함을 고치지 않았다. 닫으면 이 기록의 판정을 **다음 검증 세션이** 승격한다(조건을 닫은 세션이 자기 판정을 못 올린다는 이 저장소 규칙, v1.8.52 선례).
2. **`work_log` 세션 72 §Verification 의 `VERIFY_PLACEHOLDER`** 가 이 기록으로 채워질 자리다.
3. **★ 인덱스 건수는 3자 경합 중이었다.** 내 종료 시점에 같은 트리에서 **다른 작업 AI** 가 승격 재검 기록 셋(`final_save_b1_promotion.md`·`slice4b_closure_promotion.md`·`slice5_closure_promotion.md`)을 **아직 인덱스에 등재하지 않은 채** 만들어 두었고, 그 셋은 각각 선행 기록 하나씩을 조건부 합격 → 합격으로 승격한다. 내가 등재하며 맞춘 수는 **디스크 308건 · 합격 207 · 조건부 합격 96 · 불합격 5 · 31% · 72일치**(= 종전 304/201/98/5 + 그 셋의 신규 3 합격 + 승격 3 + 이 기록 1 조건부). **그 AI 가 자기 행 셋을 등재할 때 이 수를 다시 올리면 안 된다** — 세는 규칙은 언제나 디스크이고, `VerificationsIndexTest::test_every_verification_record_is_reachable_from_the_index` 는 그 셋이 등재될 때까지 빨갛게 남는다(내 변경이 만든 적색이 아니다).
4. **★ subtest 기준선도 같은 경합 위에 있다.** 내가 인덱스를 등재하는 동안 다른 세션이 루트 `README.md` 절차 표 ②행을 **4,215 → 4,221** 로 올렸고(자기 기록 셋 × 문서 2 = +6), **HANDOFF 회귀 기준선 줄은 아직 4215** 라 `test_docs_indexes::test_the_readme_repeats_the_regression_baseline` 이 그 자리에서 빨갛다. **이 한 건은 내 변경이 만든 것이 아니다** — 나는 기준선 줄을 어느 쪽도 건드리지 않았다(내 `README.md` 변경은 건수·판정 분포 세 줄뿐). **그리고 이 기록 파일 자신이 +2 를 더 낸다**(문서 1 = `test_repo_hygiene` +1 · 검증 인덱스 행 1 = `test_docs_indexes` +1 — HANDOFF 가 이미 두 번 적어 둔 통칙). **정본은 HANDOFF 줄이므로**, 마지막에 손대는 세션이 문서 증분을 전부 세어 **HANDOFF 와 README ②행을 같은 수로** 맞춰야 한다.
5. **H1~H5 는 차단이 아니다** — 특히 **H2** 는 이 슬라이스가 닫은 상태를 재발 방지까지 끌어올리는 자리라 값이 크다.

## Reproduction

```bash
# 0) 공유 트리를 건드리지 않는다 — 탈치 워크트리에서만 변이한다
git -C /mnt/f/devel/ai_writte_system worktree add --detach /tmp/verify_s72 68aedf3

# 1) 기준선
cd /tmp/verify_s72
PYTHONPATH=/tmp/verify_s72 python3 -m pytest tests/test_activity_api.py tests/test_docs_indexes.py -q   # 39 passed / 317 subtests
PYTHONPATH=/tmp/verify_s72 python3 -m pytest tests/test_activity_api.py tests/test_activity_actions.py \
    tests/test_activity_log.py tests/test_writing_accept.py tests/test_application_api.py -q            # 236 passed / 694 subtests

# 2) 결정 이행·반증 주장 — 검증자 프로브(세 경로를 같은 자로)
PYTHONPATH=/tmp/verify_s72 python3 <프로브>          # finalize 1행 · accept 2행 · 수동 저장 2행
#   프로브 뼈대: create_app(service=CoreSotService(InMemory…), analysis_service=…,
#   context_search_service=<PASS 고정>, writing_gate_service=<PASS 고정>,
#   activity_log_service=ActivityLogService(InMemoryActivityLogRepository())) + tests.auth_support.authenticate
#   각 경로에 같은 idempotency_key 로 2회 POST 하고 repo.events 길이를 요청마다 찍는다.

# 3) 변이 — 매번: git status --short(빈) → 백업 → python pathlib 치환 → 실행 → 백업 복원 → git diff --stat(빈)
#    ★ sed -i / perl -i 금지(이 저장소 규칙) · ★ drafts.py 의 앵커는 두 군데라 위 주석줄을 붙여 유일화
#    MV-1/2/5·MB-8/9 → services/application/app/routers/{drafts,writing}.py
#    MV-3/4·MB-2/7    → docs/README.md
#    MB-1             → tests/test_activity_api.py
#    MB-3/4/5/6       → 파일 이동·생성(mv / printf)

# 4) 정리 — 본 트리에는 checkout/restore/stash/reset/commit 을 쓰지 않는다
git -C /mnt/f/devel/ai_writte_system worktree remove /tmp/verify_s72 --force
git -C /mnt/f/devel/ai_writte_system status --short

# 5) 기준선 대조(본 트리, 읽기 전용)
python3 -m pytest --collect-only -q      # 3061 collected = 3060 passed + 1 skipped
```
