# 활동 로그 D1=ⓑ · 문서 D1=ⓐ — 조건 C1 폐쇄 승격 재검

**합격** — 발행 검증(세션 72 검증 세션)의 조건 **C1** 이 폐쇄 커밋 **`70efc23`**(test-only) + 기록 **`d6e381e`**(SoT **v1.8.65** · 하드닝 H3 가드 · H5 함정 등재)로 닫혔고, 이 재검이 **변이 재적용 열세 회**로 그 폐쇄를 확증했다. 선행 기록 [`activity_replay_and_dormant_docs.md`](activity_replay_and_dormant_docs.md) 의 판정 **조건부 합격을 합격으로 승격**한다(발행 시점 판정은 그 기록 안에 인용으로 보존된다).

- **일시**: 2026-09-12 · **검증자**: 독립 세션 — 구현(`7979ff2`·`68aedf3`)·발행 검증(세션 72 검증)·조건 폐쇄(`70efc23`·`d6e381e`) 어느 쪽도 이 세션이 아니다. 이 슬라이스의 코드·테스트·기록을 한 줄도 쓰지 않았다.
- **검증 트리**: HEAD `2e025dc`. **본 트리는 시작·종료 모두 `git status --short` 가 비어 있었고** 변이는 전부 탈치 워크트리 `/tmp/verify_s74`(`2e025dc` detached)에서 돌린 뒤 `worktree remove --force` 했다. 본 트리에 `git checkout`·`restore`·`stash`·`reset` 을 **한 번도 쓰지 않았다**.
- **환경**: WSL2 · 호스트 `python3 -m pytest`(user-site 의존성) · 초점 실행 내 skip 0. **전수는 돌리지 않았다** — 이 재검은 문서만 더하므로 유도 조건(백엔드 소스 무변)이 서고, 대조는 `--collect-only` 로 했다(§기준선).
- **원복 규약**: 매 변이마다 `shutil.copy2` 백업 → `pathlib.write_text` 치환(**앵커 `count == 1` 단정이 스크립트에 박혀 있다**) → 초점 재실행 → 백업에서 복원 → **바이트 동일성 단정** + `git status --short` 빈 것 확인. `sed -i`·`perl -i` 는 이 저장소 규칙상 쓰지 않았다.

## 기준선 (변이 전, 워크트리 `2e025dc`)

| 대상 | 실측 | 발행 검증 시점(`68aedf3`) |
|---|---|---|
| `test_activity_api` + `test_writing_accept` | **77 passed / 19 subtests** | — (폐쇄 보고가 적은 값과 일치) |
| `test_docs_indexes` | **20 passed / 322 subtests** | 19 / 317 |
| 넓은 셋(활동 3 + accept + application) | **238 passed / 694 subtests** | **236** / 694 |
| `test_docs_indexes` + `test_repo_hygiene` | **29 passed / 948 subtests** | — |
| `pytest --collect-only -q` | **3064 collected** = 3063 passed + 1 skipped | — |

**넓은 셋이 236 → 238 이다.** MB-8·MB-9 가 *전건 초록* 을 냈던 바로 그 236 셀에 특성 셀 둘이 더해진 것이고, 아래 MP-1·MP-2 가 그 둘을 정확히 물었다.

## 변이 재적용 — 열세 회

> 전부 탈치 워크트리 `/tmp/verify_s74`. 결과는 **요약 줄 + `FAILED|SUBFAILED`** 를 함께 읽었다(`grep FAILED` 만 걸면 subtest 실패를 놓친다).

### A. 조건 C1 폐쇄의 확증 — 검증자 변이 재적용

| # | 방향 | 파일 | 적용한 diff(실제 텍스트) | 발행 검증 시점 | 실측(폐쇄 후) |
|---|---|---|---|---|---|
| **MP-1**<br>(= MB-8) | under | `routers/writing.py` | <pre>-        if result.saved is not None:<br>+        if result.saved is not None and not result.idempotent_replay:<br>             activity.record(</pre> | **236 전건 초록** | **1 failed** `test_writing_accept.py::WritingAcceptApiTest::test_resending_the_same_accept_key_still_records_a_second_row` · 237 passed |
| **MP-2**<br>(= MB-9) | under | `routers/drafts.py` | <pre>-        activity.record(<br>-            project_id=…, action="draft_version_saved", …<br>+        if not result.idempotent_replay:<br>+            activity.record(<br>+                project_id=…, action="draft_version_saved", …</pre> | **236 전건 초록** | **1 failed** `test_activity_api.py::ActivityRecordingTest::test_resending_the_same_save_key_still_records_a_second_row` (`AssertionError: 4 != 5`) · 237 passed |

**★ 폐쇄가 무셀을 잠금으로 바꾼 자리 둘이 그대로 확인됐다.** 그리고 **각 변이가 물린 셀은 정확히 하나씩**이다 — 한 넓은 셀이 둘을 흡수한 것이 아니다.

### B. 세 갈래가 서로 다른 셀의 소유인가 — 분리 확인

| # | 방향 | 적용한 diff | 실측 | 해석 |
|---|---|---|---|---|
| **MP-3**<br>(= MV-1) | under | `routers/drafts.py` finalize 분기<br><pre>-        if not finalized.idempotent_replay:<br>+        if True:</pre>(앵커는 바로 위 주석줄을 붙여 유일화 — 같은 문자열이 **706·741 두 곳**이다) | **1 failed** `::test_resending_the_same_final_save_key_leaves_no_second_row` · 76 passed | finalize 축은 그대로 잠겨 있고, **신규 특성 셀 둘은 무영향** |
| **MP-4**<br>(= MV-2) | over | 같은 줄 → `if False:` | **1 failed** `::test_the_first_final_save_is_recorded` · 76 passed | 양방향 유지 |

**→ B1(finalize 무행) · B4(accept 유행) · B5(수동 저장 유행) 세 갈래가 각각 자기 셀을 갖는다.** 발행 검증이 *"결정 자체는 양방향으로 잠겼는데 그 결정이 만든 비대칭은 어느 방향으로도 안 잠겼다"* 라 적은 상태가 해소됐다.

### C. 하드닝 H3 가드 — 폐쇄 보고의 세 주장을 각각 깨 본다

폐쇄 보고는 H3 가드에 대해 셋을 주장한다: ① 지시받은 문장을 지우면 문다 ② 절 본문만 떼는 헬퍼로 **범위를 좁혔다** ③ 앵커가 수사가 아니라 두 낱말이라 **정상 편집은 안 문다**. 셋을 따로 잰다.

| # | 방향 | 조작 | 실측 | 판정 |
|---|---|---|---|---|
| **MP-5** | under | `docs/README.md` 휴면 절에서 *"`verifications/` 의 전신이고 더는 쓰지 않는다…"* 문장을 통째로 삭제 | **1 failed** `DocsReadmeIndexTest::test_the_dormant_section_says_what_the_old_name_was` · 19 passed | ① 참 |
| **MP-6** | 범위 | 같은 삭제 + **절 밖**(파일 끝 주석)에 `` `verifications/` 의 전신 `` 미끼를 심는다 | **1 failed** — 같은 셀 | ② **절반만 참.** 절 밖 우연 일치로는 못 속인다 — **그러나 이 미끼는 판별력이 없는 자리에 놓였다**(재감사 HA-1): 절 **안**에 `verifications/` 가 이미 **여섯 번** 나오므로 그 낱말은 애초에 이 문장이 없어도 만족된다. **실효 앵커는 `전신` 한 낱말**이다 — 아래 정정 절 |
| **MP-7** | over | 두 낱말을 지키며 문장을 정상적으로 다듬는다(*"지금 `verifications/` 가 하는 일의 전신이며, 더 이상 쓰지 않는다…"*) | **20 passed / 322 subtests — 전건 초록** | ③ 참. 가드가 문장을 화석으로 만들지 않는다 |

### D. 검증자 블라인드스폿 프로브 — 폐쇄를 깨려는 시도

| # | 노린 것 | 조작 | 실측 | 해석 |
|---|---|---|---|---|
| **MP-8** | accept 의 **재제출 처분 자체**가 바뀌면 신규 셀이 아나(B3 — *409 로 막힌 것* 과 구분되는가) | `quota/dedupe.py` `KEY_REPLAY_ACTIONS["writing_accept"]` `"handler"` → `"consume"` | **77 전건 초록** | 초점 셋은 못 본다 — **그러나 갭이 아니다**(MP-8b) |
| **MP-8b** | 그럼 **어느 층이 흡수하나** | 같은 변이 · `tests/test_quota_enforcement.py` | **2 failed** `KeyConsumptionTest::test_every_body_key_action_has_one_of_the_three_dispositions` · `::test_handler_replay_actions_are_exempt_at_admission` | **처분표는 자기 층에서 잠긴다.** 특성 셀은 *핸들러 분기* 를, `KeyConsumptionTest` 는 *입장 처분* 을 잠근다 — 2층 방어이고 각 층에 셀이 있다 |
| **MP-9** | **수동 저장 셀은 행 *수* 만 센다 — 행의 *정체* 는?** | `routers/drafts.py` 에서 **replay 일 때만** 다른 action 을 남긴다:<br><pre>-            action="draft_version_saved",<br>+            action=("draft_created" if result.idempotent_replay else "draft_version_saved"),</pre> | **238 passed / 694 subtests — 전건 초록** | **★ 사각. 비차단 하드닝 HP-1**(아래) |
| **MP-9b** | 그 사각이 이번 폐쇄가 만든 것인가, 선재인가 | 같은 자리를 **무조건** `"draft_created"` 로 | **2 failed** `test_activity_api.py::…::test_saving_a_draft_version_records_who_and_when` + **SUBFAILED** `test_activity_actions.py::ActivityActionClassificationTest::test_the_recorded_action_literal_matches_the_table`(`operation=('/projects/{project_id}/drafts/{draft_id}/versions','post')`) | **첫 저장 축은 두 겹으로 잠겨 있다.** 사각은 **replay 행의 정체 하나** 로 좁혀진다 |
| **MP-10** | accept 셀은 같은 변이를 무나(비대칭 실증) | `routers/writing.py` 에서 replay 일 때만 다른 action(앵커는 `target_id` 줄까지 붙여 유일화 — **첫 시도가 `count=2` 로 중단됐다**) | **1 failed** `::test_resending_the_same_accept_key_still_records_a_second_row` · 76 passed | accept 셀의 `{"draft_version_accepted"}` 단정이 **실제 잠금**이다. 두 신규 셀의 비대칭이 확정되고 처방이 한 줄로 명확해진다 |
| **MP-11** | H3 헬퍼가 **MB-7**(절 제목 앵커) 사각을 건드렸나 | `## 휴면 디렉터리 (한 번 쓰고 멈춘 것)` → `## 보존된 휴면 목록` | **1 failed** — 같은 H3 셀, `AssertionError: docs/README.md 에 휴면 디렉터리 절이 없다` | 발행 검증 시점 MB-7 은 **19 passed 전건 초록**이었다 → **덤으로 절반이 닫혔다** |
| **MP-11b** | 그 절반이 어디까지인가 | 접두는 남기고 꼬리만: `## 휴면 디렉터리 (보존)` | **20 passed / 322 subtests — 전건 초록** | **접두 `## 휴면 디렉터리` 가 사라지는 쪽만 닫혔다.** 표 행의 `[아래 절](#휴면-디렉터리-한-번-쓰고-멈춘-것)` 앵커는 **꼬리만 바꾸면 여전히 조용히 끊긴다** — H1 은 *닫힌* 것이 아니라 *좁혀진* 것이다 |

**★ MP-10 의 첫 시도가 앵커 유일성 단정에 걸려 중단됐다.** `action="draft_version_accepted", target_type="draft_version",` 가 `routers/writing.py` 안에 **2곳**이었다. 이것은 폐쇄 보고가 H5 로 등재한 함정(`drafts.py` 의 동일 문자열 2곳)이 **다른 파일에서도 성립**한다는 뜻이다 — 헬퍼에 박아 둔 `count == 1` 단정이 없었다면 변이가 두 곳을 쳐서 결과가 오염됐을 것이다. H5 등재의 값이 실측으로 확인된 셈이다.

## 폐쇄 보고·SoT 의 수치 주장 대조

| 주장 | 출처 | 실측 | 판정 |
|---|---|---|---|
| `test_activity_api` 20 → **21** | 폐쇄 보고 · SoT v1.8.65 | `git show 70efc23~1:` 20 → `70efc23:` **21**(`def test_` 계수) · 실행 21 passed | ✅ |
| `test_writing_accept` **+1** | 동상 | 55 → **56** · 실행 56 passed / 19 subtests | ✅ |
| `DocsReadmeIndexTest` 2 → **3** | 동상 | 실행 **3 passed** | ✅ |
| 초점 `test_activity_api`+`test_writing_accept` **77 passed / 19 subtests** | 폐쇄 보고 | **77 / 19** | ✅ |
| MB-8 → **1 재실패**(accept 특성 셀) · MB-9 → **1 재실패**(수동 저장 특성 셀) | 폐쇄 보고 | MP-1·MP-2 로 **기명 셀까지 일치** | ✅ |
| 백엔드 유도 **3060 → 3063 passed**(서비스 소스 무변 · subtest 무변) | SoT v1.8.65 | 신규 셀 정확히 셋(활동 1 + accept 1 + 문서 1) · 셋 다 `subTest` 미사용 · `--collect-only` **3064** = 3063 + skip 1 **산술 일치** | ✅ |
| HANDOFF 기준선 **3063 / 1 / 4225** · 루트 README ②행 **3,063 / 4,225** | HANDOFF · README | 두 문서가 같은 수를 말한다(`test_the_readme_repeats_the_regression_baseline` 초록) · 문서 가드 둘 **948 subtests**(HANDOFF 가 적은 현행값과 일치) | ✅ |
| 검증 기록 **309건 · 72일치** | `docs/verifications/README.md` · 루트 README | 디스크 `ls docs/verifications/*/*.md` **309** | ✅ |
| **MB-9 첫 시도의 `NameError` 는 *가드가 문 것이 아니라 변이가 안 선 것*** | SoT v1.8.65 | 이 재검이 같은 자리를 올바른 변수명(`result`)으로 재적용해 **실제로 물리는 것**을 확인(MP-2) — 폐쇄 보고의 자기 정정이 옳다 | ✅ |
| SoT 행이 *"판정 승격은 이 버전이 하지 않는다"* 라 선언 | SoT v1.8.65 | 그 선언대로 **이 독립 세션이** 승격한다 | ✅ |

**범위 밖 변경 0** — `70efc23` 은 테스트 두 파일(+66줄, 셀 둘), `d6e381e` 은 문서 셋 + `tests/test_docs_indexes.py`(+31줄, 헬퍼 1 + 셀 1). 서비스 소스는 한 줄도 안 바뀌었다(`git show --stat`).

## Issues / Risks

### Blocking (계약 의무)

**없다.** 조건 C1 이 요구한 두 갈래(B4·B5)가 각각 기명 셀에 대응하고, 두 방향 모두 변이로 물리는 것을 확인했다(MP-1·MP-2). 세 갈래의 분리 소유도 확인했다(MP-3·MP-4).

### Hardening (비차단)

- **★ HP-1(신규) — 수동 저장 특성 셀이 replay 행의 *정체* 를 안 본다.** `test_resending_the_same_save_key_still_records_a_second_row` 는 `len(self.repo.events) == before + 1` 만 단정해서, **replay 가 엉뚱한 action 을 남겨도 238셀이 전건 초록**이다(MP-9). 형제 셀인 accept 쪽은 `{event.action for event in repo.events} == {"draft_version_accepted"}` 를 갖고 있어 같은 변이를 문다(MP-10) — **같은 슬라이스가 낳은 두 셀의 비대칭**이다. **비차단인 근거는 계약 원문이다**(재감사 §6 지적으로 교체 — 종전에 적었던 *"형제 accept 셀이 처방을 넘어섰으므로 의무가 이행됐다"* 는 **성립하지 않는 논증**이다. 형제 셀이 더 했다는 사실은 이쪽 셀의 의무를 정의하지 않고, 그 모양은 가이드 §"boundary matrix has no empty cells" 가 금지하는 *"옆에서 더 했으니 됐다"* 그 자체다). **계약이 요구한 것은 둘뿐이다** — SoT v1.8.64 행과 HANDOFF §지금의 계약 활동 로그 항목이 적은 것은 ① **행을 남기는가** ② replay 셀이 **`idempotent_replay: true` 를 함께 단정하는가** 이고, 수동 저장 셀은 둘 다 갖는다([`test_activity_api.py:205-206`](../../../tests/test_activity_api.py#L205)). **replay 행의 action 리터럴은 계약이 침묵하는 축**이므로 경계 행렬에 빈 칸이 생기지 않는다 — 그래서 하드닝이다. 처방은 한 줄: 수동 저장 셀에 `self.assertEqual(self.repo.events[-1].action, "draft_version_saved")` 를 더한다. **첫 저장 축은 이미 두 겹으로 잠겨 있으므로**(MP-9b) 열린 것은 replay 행 하나뿐이다.
- **H1(선행 기록) — 좁혀졌으나 열려 있다.** H3 폐쇄의 `_dormant_section` 헬퍼가 **절 제목 접두가 사라지는 방향**을 덤으로 닫았다(MP-11 — 발행 검증 시점 MB-7 은 전건 초록이었다). 그러나 **접두를 남기고 꼬리만 바꾸면 표 행의 앵커 링크가 여전히 조용히 끊긴다**(MP-11b). 비-`.md` 링크(벤치마크 원자료 `.json` 둘) 축은 손대지 않았다. **★ 그리고 재감사가 이 가드 자체의 사각을 찾았다 — HA-1**: 폐쇄 보고와 이 기록이 둘 다 적은 *"앵커를 두 낱말로 잡았다"* 는 **실효 한 낱말**이다. `전신` 만 걷으면 문지만(**1 failed**), `verifications/` 만 걷으면 **20 passed 전건 초록**이다 — 절 안에 그 낱말이 여섯 번 더 있기 때문이다(**이 세션이 양방향으로 재현 확인**). 처방: 앵커를 절 안에서 유일한 것으로 바꾸거나(예: 링크 경로 `verification_briefs/` 와 `전신` 의 **동시 출현을 한 문장 안에서** 재기) H2 와 한 슬라이스로 묶는다. 선행 기록의 H1 서술은 이 재검 기준으로 **절반이 낡았다** — 위 실측이 정본이다.
- **H2(선행 기록) — 그대로 열려 있다.** `_DORMANT_DIRECTORIES` 수동 목록과 `glob("*/*.md")` 깊이. 폐쇄 보고 자신이 *"검증자 제안대로 `docs/` 아래 안 닿는 `.md` 0건 셀로 일반화하는 편이 낫다 — 다음 문서 슬라이스 몫"* 이라 적었다. **이 재검도 같은 판단이다.**
- **H4(선행 기록) — 그대로 열려 있다.** 파일 이동 무셀. 발행 검증자 자신이 실익 대비 비용을 낮게 봤고 이 재검도 동의한다.
- **HP-2(신규, 낮음) — 두 특성 셀의 docstring 경고가 무가드다.** *"이 셀은 이 동작을 승인하지 않는다 · D2=ⓑ 면 셀과 SoT·HANDOFF 문장이 함께 뒤집힌다"* 는 **결정의 내용물**인데(H3 가 `docs/README.md` 에서 닫은 것과 **정확히 같은 모양**이다) 지워도 아무도 안 문다. 지워지면 다음 작업자가 *"셀이 있으니 옳은 동작"* 으로 읽는데, 그것이 이 셀들이 막으려던 오독 그 자체다. 다만 **오너 결정 D2 가 대기 중**이라 그 결정이 답해지면 셀과 함께 사라질 문장이므로, **지금 가드를 세우는 것은 이르다** — D2 가 ⓐ(현 상태 유지)로 답해질 때 여는 것이 맞다.

## Verdict

**합격** — 조건 C1 이 실질적으로 닫혔다. 승격 근거:

1. **폐쇄 실증이 재현된다** — MB-8·MB-9 를 원문 diff 로 재적용해 **각각 기명 셀 하나씩** 재실패(MP-1·MP-2). 발행 검증에서 236셀 전건 초록이던 두 자리다.
2. **결정이 만든 비대칭이 세 갈래로 분리 소유된다** — finalize 변이(MP-3·MP-4)는 신규 셀 둘을 건드리지 않고 자기 셀만 문다. *"오너가 유예로 명시한 D2 를 다음 슬라이스가 코드 두 줄로 조용히 풀 수 있다"* 는 C1 의 차단 사유가 해소됐다.
3. **하드닝 H3 가드가 주장한 세 성질이 전부 성립한다** — 삭제는 물고(MP-5), 절 밖 미끼로는 못 속이고(MP-6), 정상 문장 편집은 안 문다(MP-7). **가드를 조이다가 개선 경로를 잠그지 않았다.**
4. **깨려는 시도가 실패했다** — 인접 계약(처분표)은 다른 층이 잠그고 있었고(MP-8b), 남은 사각 하나(MP-9)는 C1 의 의무 밖이며 처방이 한 줄이다.
5. **수치 주장이 전건 실측과 일치한다** — 셀 수 셋, 기준선 산술, 인덱스 건수, 문서 가드 subtest 까지. **폐쇄 보고가 자기 변이 실패(`NameError`)를 *가드가 물었다* 로 오독하지 않고 명시한 것**은 가산점이다.
6. **범위 밖 변경 0** — 서비스 소스 무변, 두 커밋 모두 훅 단위까지 슬라이스 안이다.

## Outstanding items

1. **HP-1 은 이 재검이 고치지 않았다** — 검증자는 결함을 조용히 고치지 않는다(가이드 §Relation). 한 줄짜리 보강이라 다음 활동 로그 슬라이스가 얹으면 된다.
2. **H2 는 계속 열려 있고 다음 문서 슬라이스 몫이다** — 발행 검증·폐쇄 보고·이 재검 셋이 같은 판단이다.
3. **HP-2 는 오너 결정 D2 를 기다린다** — D2=ⓐ 로 답해지면 그때 가드를 세운다(ⓑ 면 셀 자체가 뒤집히므로 가드가 무의미해진다).
4. **오너 결정 대기 두 건은 그대로다** — 활동 로그 D2 · 파기 청구 뒤 탈퇴 취소.
5. **이 기록 파일 자신이 기준선을 +2 한다**(문서 1 = `test_repo_hygiene` +1 · 검증 인덱스 행 1 = `test_docs_indexes` +1) — HANDOFF 회귀 기준선 줄과 루트 README ②행을 **같은 수**로 함께 올린다.

## Reproduction

```bash
# 0) 본 트리를 건드리지 않는다 — 탈치 워크트리에서만 변이한다
cd /mnt/f/devel/ai_writte_system
git status --short          # 비어 있어야 한다(첫 변이 전 게이트)
git worktree add --detach /tmp/verify_s74 2e025dc
cd /tmp/verify_s74

# 1) 기준선
PYTHONPATH=/tmp/verify_s74 python3 -m pytest tests/test_activity_api.py tests/test_writing_accept.py -q      # 77 / 19
PYTHONPATH=/tmp/verify_s74 python3 -m pytest tests/test_docs_indexes.py -q                                   # 20 / 322
PYTHONPATH=/tmp/verify_s74 python3 -m pytest tests/test_activity_api.py tests/test_activity_actions.py \
    tests/test_activity_log.py tests/test_writing_accept.py tests/test_application_api.py -q                  # 238 / 694
PYTHONPATH=/tmp/verify_s74 python3 -m pytest --collect-only -q | tail -1                                     # 3064 collected

# 2) 변이 — 매번 「앵커 count==1 단정 → 백업 → write_text 치환 → 초점 재실행 → 백업 복원 → 바이트 대조」
#    diff 원문은 위 §변이 표에 있다. 결과는 요약 줄과 FAILED|SUBFAILED 를 함께 읽는다.
PYTHONPATH=/tmp/verify_s74 python3 -m pytest <초점> -q 2>&1 | grep -E "^(FAILED|SUBFAILED)|passed|failed"

# 3) 정리
cd /mnt/f/devel/ai_writte_system
git worktree remove /tmp/verify_s74 --force
git status --short          # 다시 비어 있어야 한다
```
