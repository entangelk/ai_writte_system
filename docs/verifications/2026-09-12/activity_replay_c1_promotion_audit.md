# 조건 C1 승격 재검(`432f790`) 재감사 — 승격의 자격과 변이 표 재현

**조건부 합격** — 조건 **AC1**: 이 커밋이 인덱스에서 선행 기록 [`activity_replay_and_dormant_docs.md`](activity_replay_and_dormant_docs.md) 의 판정 열을 **합격**으로 올렸는데 **그 기록 본문의 판정 첫 줄은 여전히 `**조건부 합격** — 조건 C1:` 이다.** [`guides/verification.md`](../../guides/verification.md) §Required sections 가 *"The index's 판정 column and this first line must say the same thing"* 이라고 못 박은 자리이고, **디스크 310건 전수 대조에서 이 불일치는 이 기록 하나뿐이다**(내가 직접 센 수치 — 아래 §5). 바로 앞 커밋 `2e025dc` 는 같은 상황에서 선행 기록 넷의 판정 줄을 **전부** 고쳤다(4/4 선례). 한 줄로 닫힌다.

그 밖에는 **승격이 정당하다.** 대상이 보고한 변이 **열한 종을 diff 원문 그대로 재적용해 건수·기명 셀까지 전건 일치**했고(§2), 대상이 재지 않은 점 다섯을 더 찍어 **경계를 좁혔다**(§3). C1 이 요구한 두 갈래는 실제로 기명 셀을 얻었고 세 갈래가 분리 소유된다. **HP-1 을 비차단으로 분류한 것도 타당하다 — 다만 대상이 댄 근거는 약하고, 옳은 근거는 따로 있다**(§6). **범위 밖 변경 0.**

## Subject metadata

- **검증일**: 2026-09-12 · **검증자**: 독립 세션. 구현(`7979ff2`·`68aedf3`) · 발행 검증(세션 72 검증) · 조건 폐쇄(`70efc23`·`d6e381e`) · **승격 재검(`432f790`, 세션 74)** 어느 것도 이 세션이 아니다. 이 슬라이스의 코드·테스트·기록을 한 줄도 쓰지 않았다.
- **대상**: 커밋 **`432f790`**(HEAD) — 승격 재검 기록 [`activity_replay_c1_promotion.md`](activity_replay_c1_promotion.md) 신설 + 인덱스·기준선·CHANGELOG·HANDOFF·work_log 갱신.
- **정규 스펙(계약 스코프)**:
  - [`docs/guides/verification.md`](../../guides/verification.md) — §Required sections(판정 어휘·인덱스 일치) · §"boundary matrix has no empty cells" · §Mutation testing(원복 규칙 · `grep FAILED` 맹점 · 변이가 안 물 때).
  - [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.8.64·v1.8.65** 행 · [`HANDOFF.md`](../../../HANDOFF.md) **§지금의 계약 "활동 로그"**(60행) · §회귀 기준선(67행).
  - 선행 기록 [`activity_replay_and_dormant_docs.md`](activity_replay_and_dormant_docs.md) §Issues **C1 처방** · §경계 행렬 B1~B9.
- **검증 트리**: 본 트리 HEAD `432f790`. **시작·종료 모두 `git status --short` 가 비어 있었다.** 변이는 전부 탈치 워크트리 `/tmp/verify_s75`(`432f790` detached)에서 돌린 뒤 `worktree remove --force` 했고, **본 트리에 `git checkout`·`restore`·`stash`·`reset` 을 한 번도 쓰지 않았다.** 대조용으로 `/tmp/verify_s75_prev`(`2e025dc`) · `/tmp/verify_s75_pub`(`68aedf3`) 를 추가로 띄웠다 셋 다 제거했다.
- **환경**: WSL2 · 호스트 `python3 -m pytest`(user-site 의존성) · 초점 실행 내 skip 0 · 전수 미실행(지시). 대조는 `--collect-only`.
- **원복 규약**: 변이마다 「앵커 `count == 1` 단정 → `shutil.copy2` 백업 → `pathlib.write_text` 치환 → 초점 실행 → 백업 복원 → **바이트 동일성 단정** → `git status --short` 빈 것 확인」. `sed -i`·`perl -i` 는 쓰지 않았다(저장소 규칙).

## Scope

1. 대상이 보고한 변이 **MP-1 ~ MP-11b 열한 종**의 재현(건수 + 기명 셀).
2. 대상이 재지 않은 경계점(H3 앵커 두 낱말의 **각각**, 절 제목 앵커의 **정확한 경계**).
3. 승격의 자격 — C1 처방 이행 여부, 경계 행렬 B1~B9 의 현행 상태, **HP-1 비차단 분류의 타당성**.
4. 수치 주장 전건 재측정(기준선 넷 · 셀 수 셋 · 건수 · 판정 분포 · 회귀 기준선 유도).
5. 범위 밖 변경.

## Methodology

- 변이는 `python3` 헬퍼 하나로만 적용했다(위 §원복 규약의 여섯 단계가 스크립트에 단정으로 박혀 있다).
- 결과는 **요약 줄 + `FAILED|SUBFAILED`** 를 함께 읽었다 — `grep FAILED` 만 걸면 subtest 실패를 놓친다(가이드 §★).
- 수치는 대상 기록에서 베끼지 않고 **세 리비전(`68aedf3`·`2e025dc`·`432f790`)에서 각각 실행**해 양단으로 갈랐다.
- 건수·판정 분포는 산문을 읽지 않고 **인덱스 표를 파싱해 세고**, 디스크 `ls docs/verifications/*/*.md` 와 대조했다. 판정 열 ↔ 기록 본문 판정 줄은 **310건 전수를 접두 일치로** 기계 대조했다.

## Findings

### 1. 기준선 — 대상의 다섯 수치가 전부 재현된다

| 대상 | 대상이 적은 값(`2e025dc`) | 내 실측 | 리비전 |
|---|---|---|---|
| `test_activity_api` + `test_writing_accept` | 77 passed / 19 subtests | **77 / 19** | `432f790` |
| `test_docs_indexes` | 20 / 322 | **20 / 323**(`432f790`) · **20 / 322**(`2e025dc`) | 양쪽 |
| 넓은 셋(활동 3 + accept + application) | 238 / 694 | **238 / 694** | `432f790` |
| 발행 검증 시점 값 — `test_docs_indexes` 19/317 · 넓은 셋 **236**/694 | 표의 오른쪽 열 | **19 / 317** · **236 / 694** | `68aedf3` |
| `test_docs_indexes` + `test_repo_hygiene` | 948(변경 전) → 950(변경 후) | **948**(`2e025dc`) → **950**(`432f790`) | 양단 |
| `pytest --collect-only -q` | 3064 | **3064** | `432f790` |

**236 → 238 도 양단 실측으로 확인된다.** MB-8·MB-9 가 *전건 초록* 을 냈던 바로 그 236 셀에 특성 셀 둘이 더해졌다.

### 2. ★ 변이 재적용 — 열한 종 전건 일치

> 전부 `/tmp/verify_s75`(`432f790` detached). 각 행의 "diff" 는 대상 기록의 원문을 그대로 옮겨 적용한 것이다.

| # | 방향 | 파일 / 조작 | 대상 보고 | **내 실측** | 일치 |
|---|---|---|---|---|---|
| **MP-1**(=MB-8) | under | `writing.py` `if result.saved is not None:` → `… and not result.idempotent_replay:` | 1 failed · `test_writing_accept.py::WritingAcceptApiTest::test_resending_the_same_accept_key_still_records_a_second_row` · 237 passed | **1 failed, 237 passed, 694 subtests** · 같은 기명 셀 | ✅ |
| **MP-2**(=MB-9) | under | `drafts.py` 수동 저장 `activity.record(` 를 `if not result.idempotent_replay:` 로 감쌈 | 1 failed · `test_activity_api.py::ActivityRecordingTest::test_resending_the_same_save_key_still_records_a_second_row` | **1 failed, 237 passed, 694 subtests** · 같은 기명 셀 | ✅ |
| **MP-3**(=MV-1) | under | `drafts.py` finalize `if not finalized.idempotent_replay:` → `if True:`(앵커는 바로 위 주석줄을 붙여 유일화 — 맨 문자열은 **706·741 두 곳**) | 1 failed · `::test_resending_the_same_final_save_key_leaves_no_second_row` · 76 passed | **1 failed, 76 passed, 19 subtests** · 같은 셀 | ✅ |
| **MP-4**(=MV-2) | over | 같은 줄 → `if False:` | 1 failed · `::test_the_first_final_save_is_recorded` · 76 passed | **1 failed, 76 passed, 19 subtests** · 같은 셀 | ✅ |
| **MP-5** | under | `docs/README.md` 휴면 절에서 지시받은 문장 통째 삭제 | 1 failed · `DocsReadmeIndexTest::test_the_dormant_section_says_what_the_old_name_was` | **1 failed, 19 passed, 323 subtests** · 같은 셀 | ✅ |
| **MP-6** | 범위 | 같은 삭제 + **절 밖**(파일 끝) 미끼 `` `verifications/` 의 전신 `` | 1 failed — 같은 셀 | **1 failed, 19 passed** · 같은 셀 | ✅ |
| **MP-7** | over | 두 낱말을 지키며 문장을 정상적으로 다듬음 | 전건 초록 | **20 passed / 323 subtests** | ✅ |
| **MP-8** | 인접 | `quota/dedupe.py` `KEY_REPLAY_ACTIONS["writing_accept"]` `"handler"`→`"consume"` · 초점 셋 | 77 전건 초록 | **77 passed / 19 subtests** | ✅ |
| **MP-8b** | 층 확인 | 같은 변이 · `test_quota_enforcement.py` | 2 failed(`KeyConsumptionTest::test_every_body_key_action_has_one_of_the_three_dispositions` · `::test_handler_replay_actions_are_exempt_at_admission`) | **2 failed, 52 passed** · 같은 두 셀 | ✅ |
| **MP-9** | 사각 탐침 | `drafts.py` **replay 일 때만** `action` 을 `"draft_created"` 로 | 238 전건 초록 | **238 passed / 694 subtests** | ✅ |
| **MP-9b** | 대조 | 같은 자리를 **무조건** `"draft_created"` 로 | 2 failed(`::test_saving_a_draft_version_records_who_and_when` + **SUBFAILED** `test_activity_actions.py::ActivityActionClassificationTest::test_the_recorded_action_literal_matches_the_table`) | **2 failed, 237 passed, 693 subtests** · 같은 셀 + 같은 `operation=` 서브 | ✅ |
| **MP-10** | 비대칭 | `writing.py` 에서 replay 일 때만 다른 action(앵커는 `target_id` 줄을 붙여야 유일 — 맨 문자열은 **2곳**) | 1 failed · accept 특성 셀 · 76 passed | **1 failed, 76 passed** · 같은 셀 · 맨 앵커 `count = 2` **재현** | ✅ |
| **MP-11** | 덤 | `## 휴면 디렉터리 (한 번 쓰고 멈춘 것)` → `## 보존된 휴면 목록` | 1 failed — 같은 H3 셀(`docs/README.md 에 휴면 디렉터리 절이 없다`) | **1 failed, 19 passed** · 같은 셀 | ✅ |
| **MP-11b** | 경계 | `## 휴면 디렉터리 (보존)` | 전건 초록 | **20 passed / 323 subtests** | ✅ |

**열한 종(부호 포함 열세 회) 전부 건수·기명 셀까지 일치한다.** 한 넓은 셀이 둘을 흡수한 자리는 없다. **MP-3·MP-4 가 신규 특성 셀 둘을 건드리지 않는 것**도 실측으로 재현됐다 — 세 갈래(B1·B4·B5)가 각자 자기 셀을 갖는다.

### 3. ★ 내가 더 찍은 다섯 점 — 경계가 대상의 서술보다 좁다

| # | 조작 | 실측 | 뜻 |
|---|---|---|---|
| **MA-1** | H3 앵커 중 **`전신` 만** 지운다(`의 전신이고` → `의 앞선 형태이고`, `verifications/` 는 그대로) | **1 failed** — H3 셀 | `전신` 쪽 반쪽은 실제 잠금이다 |
| **MA-2** | H3 앵커 중 **`` `verifications/` `` 만** 지운다(`**옛 검증 브리프 관행의 전신이고 …**`, `전신` 은 그대로) | **20 passed / 323 subtests — 전건 초록** | **★ 사각(신규 HA-1).** `assertIn("verifications/", section)` 은 **무가드다** — 절 *본문 안* 43·45·47행이 `verifications/` 를 세 번 인용하므로 지시받은 문장에서 그 이름이 사라져도 셀이 만족된다 |
| **MA-3** | 절 제목의 **꼬리를 통째로 제거**(`## 휴면 디렉터리`) | **전건 초록** | 표 17행의 앵커 `#휴면-디렉터리-한-번-쓰고-멈춘-것` 이 **조용히 끊긴다** |
| **MA-4** | 접두 뒤에 글자 추가(`## 휴면 디렉터리들 (한 번 쓰고 멈춘 것)`) | **전건 초록** | 헬퍼가 `text.find("\n## 휴면 디렉터리")` **부분문자열**이라, 접두를 **포함하기만 하면** 통과한다 |
| **MA-5** | 접두 *내부* 공백 하나 추가(`## 휴면  디렉터리 …`) | **1 failed** — H3 셀 | 경계는 정확히 **문자열 `\n## 휴면 디렉터리` 의 보존 여부** 하나다 |

**→ MP-11/11b 에 대한 대상의 결론(*"접두가 사라지는 쪽만 닫혔다 · 꼬리만 바꾸면 조용하다"*)은 참이고, MA-3·MA-4·MA-5 가 그 경계를 **정확히** 고정한다.** H1(앵커 링크 무가드)은 여전히 열려 있다.

**그러나 MP-6 에 대한 대상의 결론(*"② 참 — 절 밖 우연 일치로는 못 속인다"*)은 미끼를 엉뚱한 곳에 놓았다.** 진짜 미끼는 **절 안**에 이미 있고(45·47행), MA-2 가 그것으로 가드를 통과시킨다. 즉 `_dormant_section` 헬퍼가 좁힌 범위는 **`전신` 에는 충분하지만 `verifications/` 에는 불충분하다.** H3 자체가 비차단 하드닝이었으므로 이것도 비차단이지만, **폐쇄 보고·대상 기록이 둘 다 "두 낱말"이라 적은 서술은 실효 한 낱말이다.**

### 4. C1 처방의 이행 — 처방 문면과 셀을 한 줄씩 대조

선행 기록 §Issues C1 의 처방은 셋을 요구했다.

| 처방 항목 | 현행 셀 | 이행 |
|---|---|---|
| ① accept: 같은 키 2회 POST → `len(repo.events) == 2` + 둘째 응답 `idempotent_replay is True` | `tests/test_writing_accept.py:382`(`assertEqual(len(repo.events), 2)` `:411` · `assertTrue(again.json()["idempotent_replay"])` `:410`) | **이행**(+ `{event.action …} == {"draft_version_accepted"}` `:412-414` 로 처방 **초과**) |
| ② 수동 저장: 같은 키 2회 POST(재전송에 `X-Confirm-Duplicate`) → 같은 단정 | `tests/test_activity_api.py:177`(`assertEqual(len(self.repo.events), before + 1)` `:206` · `assertTrue(again.json()["idempotent_replay"])` `:205` · 헤더 `:201`) | **이행**(행 *수* 축까지 · 정체 축은 없음 → HP-1) |
| ③ 두 docstring 에 *"이 동작을 승인하지 않는다 · D2=ⓑ 면 셀과 SoT·HANDOFF 문장이 함께 뒤집힌다"* | `test_writing_accept.py:383·396-398` · `test_activity_api.py:178·186-188` — **양쪽 다 그 문장이 실제로 있다**(v1.8.61 `WithdrawalCancelAfterPurgeClaimTest` 선례 인용까지) | **이행** |

**처방 세 항목이 전부 문면대로 이행됐다.** 대상이 "처방 그대로"라 적은 것은 참이다.

### 5. ★ 경계 행렬 재수립 — 빈 칸과, 이 커밋이 만든 새 빈 칸 하나

| # | 계약 분기(출처) | 기명 셀 | 상태(내 실측) |
|---|---|---|---|
| B1 | finalize replay 무행(SoT v1.8.64 · HANDOFF:60) | `test_resending_the_same_final_save_key_leaves_no_second_row` | **잠김**(MP-3) |
| B2 | finalize 첫 요청은 기록(같은 결정 over 방향) | `test_the_first_final_save_is_recorded` | **잠김**(MP-4) |
| B3 | replay 셀은 `idempotent_replay: true` 를 함께 단정(HANDOFF:60 명문) | 세 replay 셀 전부 + `KeyConsumptionTest` 2셀(입장 처분 층) | **잠김**(MP-8b — 2층 방어이고 층마다 셀이 있다) |
| B4 | **accept 는 replay 에 행을 남긴다** | `test_resending_the_same_accept_key_still_records_a_second_row` | **잠김**(MP-1) — **C1 폐쇄** |
| B5 | **수동 저장은 replay 에 행을 남긴다** | `test_resending_the_same_save_key_still_records_a_second_row` | **잠김**(MP-2) — **C1 폐쇄** |
| B6 | 휴면 셋 `.md` 도달(문서 D1=ⓐ) | `test_every_dormant_document_is_reachable_from_the_index` | 잠김 |
| B7 | 인덱스 `.md` 링크 해석 | `test_every_index_link_resolves` | 잠김 |
| B8 | 파일을 옮기지 않는다 | 셀 없음 | 비차단 **H4**(선행 판단 유지) |
| B9 | 브리프 지시 문장이 인덱스 줄에 있다 | `test_the_dormant_section_says_what_the_old_name_was` | 잠김 — 단 **실효 앵커는 `전신` 한 낱말**(MA-2) |
| **B10** | **검증 기록의 인덱스 판정 열과 그 기록 본문의 판정 첫 줄이 같은 말을 한다**([`guides/verification.md`](../../guides/verification.md) §Required sections) | 셀 없음(기계 대조로 잰다) | **★ 위반 — 차단 AC1**(아래) |

**B4·B5 의 빈 칸이 실제로 채워졌다 — 승격의 실체는 성립한다.** 대신 **이 커밋이 B10 에 빈 칸을 하나 만들었다.**

**실측(디스크 310건 전수 기계 대조)**: 인덱스 310행의 판정 열과 각 기록 본문 머리의 판정 토큰을 접두 일치로 맞대면 **불일치는 정확히 1건**이고, 그것이 [`activity_replay_and_dormant_docs.md`](activity_replay_and_dormant_docs.md) 다 — 인덱스 `**합격**`, 본문 3행 `**조건부 합격** — 조건 **C1**: …`. 대상 커밋 `432f790` 의 `--stat` 에 **그 파일이 없다**(건드리지 않았다).

**선례는 4/4 로 반대다.** 바로 앞 커밋 `2e025dc` 는 승격 넷을 실으면서 선행 기록 넷의 판정 줄을 전부 고쳤다 — `landing_l3_gate_and_landing.md` · `account_withdrawal_slice5_promotion.md` · `admin_residual_purge_slice4b.md` · `2026-09-06/final_save_n1_promotion.md` 가 모두 *"**최종 판정은 합격이다** — 조건 …은 폐쇄 커밋 …이 닫았고, 승격 재검(…)이 판정을 올렸다. 아래 본문은 발행 시점 그대로다."* 로 시작한다. 대상 기록 자신이 첫 줄에 *"(발행 시점 판정은 **그 기록 안에 인용으로 보존된다**)"* 라 적었는데, **그 상태가 성립하지 않는다** — 발행 시점 판정은 인용이 아니라 **여전히 그 기록의 판정 줄**이다.

### 6. ★ HP-1 비차단 분류 — 결론은 맞고, 대상이 댄 근거는 틀렸다

대상은 HP-1(수동 저장 특성 셀이 replay 행의 *정체* 를 안 본다)을 비차단으로 두며 이렇게 적었다: *"발행 검증의 처방은 두 셀에 **같은 단정** 을 요구했고 accept 쪽이 그것을 넘어섰으므로 C1 의 의무는 이행됐다."*

**그 논증은 성립하지 않는다.** 형제 셀이 처방을 *초과* 했다는 사실은 이쪽 셀의 의무를 정의하지 않는다 — 가이드 §"boundary matrix has no empty cells" 는 *계약이 요구한 분기* 가 기명 셀에 대응하는지만 묻고, 처방 문서가 아니라 **계약**이 기준이다. 이 논증대로라면 "형제가 더 했으니 됐다"가 무셀을 정당화하는 일반 논거가 되는데, 그것이 바로 그 절이 금지하는 모양이다.

**그럼에도 결론은 옳다. 옳은 근거는 계약 원문이다.**

- **HANDOFF:60**(§지금의 계약 · 코드 만지기 전 필독 자리): *"`drafts/{id}/finalize` 만 `idempotent_replay` 면 **기록하지 않고**, `writing/accept` 와 수동 저장은 **남긴다**(D2 유예). … **분기를 만들면 행위 셀이 따로** 필요하다 … 그리고 replay 셀은 응답의 `idempotent_replay: true` 를 함께 단정해야 한다."*
- **SoT v1.8.64**: *"ⓑ 는 … **셋으로 가른다**(finalize 무행 · accept 유행 · 수동 저장 유행)."*

계약이 적은 분기는 **"행을 남기는가"** 이고, 계약이 셀에 **명문으로 추가 요구한 것**은 `idempotent_replay: true` 단정 하나다. 수동 저장 셀은 **둘 다 갖는다**(`test_activity_api.py:205-206`). **replay 행의 *action 리터럴* 은 계약 어느 줄도 말하지 않는다** — 분류표 [`activity/actions.py`](../../../services/application/app/activity/actions.py) 는 *route → action* 의 배선 존재를 잠그지 분기별 리터럴을 잠그지 않고(MP-9b 의 SUBFAILED 가 그 층이다), 첫 저장 축은 이미 두 겹으로 잠겨 있다(MP-9b). 남은 것은 **계약이 침묵하는 자유도 하나**다. 따라서 **하드닝이 맞다**(가이드 §41 의 "spec-silent-but-code-enforced" 와도 다르다 — 코드가 무엇을 *거부* 하는 자리가 아니라 아무도 안 재는 자유도다).

처방도 대상이 적은 한 줄 그대로가 맞다: 수동 저장 셀에 `self.assertEqual(self.repo.events[-1].action, "draft_version_saved")`.

### 7. 수치 주장 대조 — 전건 재측정

| 주장 | 출처 | 내 실측 | 판정 |
|---|---|---|---|
| `test_activity_api` 20 → **21** | 폐쇄 보고 · SoT v1.8.65 · 대상 | `git show 70efc23~1:` **20** → `70efc23:` **21** | ✅ |
| `test_writing_accept` 55 → **56** | 동상 | **55 → 56** | ✅ |
| `DocsReadmeIndexTest` 2 → **3** | 동상 | `d6e381e~1` **2** → `d6e381e` **3**(클래스 블록 파싱) | ✅ |
| 신규 셀 셋이 **`subTest` 미사용**(= passed +3 · subtest +0) | 대상 | 셋을 개별 실행 — 셋 다 요약에 `subtests` 가 없다 | ✅ |
| `--collect-only` **3064** = 3063 passed + 1 skipped | 대상 | **3064 collected** | ✅ |
| 문서 가드 둘 **948 → 950**(양단 실측) | 대상 | `2e025dc` **29/948** → `432f790` **29/950** | ✅ |
| 유도 조건(**백엔드 소스 무변**)이 선다 | 대상 | `git show --stat 432f790` 에 `services/`·`tests/`·`scripts/` **0파일** — 문서 7개뿐 | ✅ |
| **4225 → 4227 은 +2** | 대상 · HANDOFF | 문서 1개 = `test_repo_hygiene` +1 + `test_docs_indexes`(검증 인덱스 행) +1 = **+2**, 948→950 과 **산술 일치** | ✅ |
| HANDOFF 기준선 **3063/1/4227** ↔ 루트 README ②행 **3,063 / 4,227** | HANDOFF:67 · README:104 | **같은 수**(`test_the_readme_repeats_the_regression_baseline` 초록) | ✅ |
| 검증 기록 **310건 · 72일치** | 네 자리 | 디스크 `ls docs/verifications/*/*.md` **310** · 날짜 디렉터리 **72** · 인덱스 표 행 **310** · `README.md:105` `**310건 / 72일치**` · `README.md:329` `(310건)` · `docs/README.md:12` `310건` · `docs/verifications/README.md:4` `310건` — **네 자리 전부 일치** | ✅ |
| 판정 분포 **합격 211 · 조건부 94 · 불합격 5** · **30%** | 대상 · 두 README | 인덱스 표 파싱 **211 / 94 / 5**(합 310) · 94/310 = **30.3% → 30%** | ✅ |

**대상이 적은 수치 중 틀린 것은 하나도 없다.** 다만 인덱스 요약 셀(70행)이 *"문서 가드 948 subtests"* 라 적은 것은 **변경 전 값**이라 발행된 트리에서는 이미 950 이다(낮음 — §Hardening HA-3).

### 8. 범위 밖 변경 — 없다

`git show --stat 432f790` = 7파일: `CHANGELOG.md`(+1) · `HANDOFF.md`(+5-3: 기준선 4225→4227 · 미수리 표에 HP-1 한 줄 · Next Tasks 백로그 문장 종결) · `README.md`(+4-4: 건수 2곳 · 기준선 · 분포·비율) · `docs/README.md`(+1-1: 건수) · `docs/daily_logs/2026-09-12/work_log.md`(+32) · 신규 기록(+142) · `docs/verifications/README.md`(+7-6). **서비스 소스·테스트 0줄**, 남의 기록 0파일. 훅 단위까지 슬라이스 안이다. **HP-1 을 스스로 고치지 않고 HANDOFF 미수리 표에 올린 것은 가이드 §Relation 대로다.**

## Issues / Risks

### Blocking (계약 의무)

**AC1 — 인덱스 판정 열과 선행 기록 본문의 판정 줄이 서로 다른 말을 한다.**

- **무엇이 계약인가**: [`guides/verification.md`](../../guides/verification.md) §Required sections — *"The index's 판정 column and this first line must say the same thing, so both must have one vocabulary."* 이 문장에는 **측정된 비용**이 붙어 있다(222건이 111가지 판정 표현을 냈고, 정규식 분류가 5건·4건을 오독했으며, **불합격 하나가 "—" 로 등재돼 일주일간 안 세어졌고, 루트 README 가 틀린 판정 분포를 발행했다**).
- **실측**: 디스크 310건 전수 기계 대조에서 **불일치 1건** — 인덱스 71행 `**합격**` ↔ `activity_replay_and_dormant_docs.md:3` `**조건부 합격** — 조건 **C1**: …`. `432f790` 은 그 파일을 열지 않았다.
- **왜 차단인가**: ① 계약이 *같은 말을 하라* 고 명문으로 요구한 두 자리가 서로를 반박한다. ② 지금 이 저장소에서 **유일한** 그런 자리다 — 통칙 위반이 한 건이면 그것이 다음 분류의 오독 지점이 된다. ③ **바로 앞 커밋이 같은 상황을 4/4 로 다르게 처리했다** — 선례가 흔들리면 다음 승격 세션이 어느 쪽을 따를지 고르게 된다. ④ 대상 기록 첫 줄의 주장(*"발행 시점 판정은 그 기록 안에 인용으로 보존된다"*)이 **현재 트리에서 거짓**이다.
- **처방**(닫으면 판정이 올라간다): `activity_replay_and_dormant_docs.md` 3행을 선례 모양으로 고친다 — 예: `**합격** — 조건 C1 은 폐쇄 커밋 `70efc23`·`d6e381e`(SoT v1.8.65)가 닫았고, 승격 재검([`activity_replay_c1_promotion.md`](activity_replay_c1_promotion.md) — 변이 재적용 열세 회 전건 일치)이 판정을 올렸다. **아래 본문은 발행 시점 그대로다**(발행 시점 판정: 조건부 합격 — 조건 C1).` **★ 선례 넷이 쓴 `**최종 판정은 합격이다**` 대신 `**합격**` 으로 시작하는 편이 낫다** — 같은 가이드 절이 판정 줄을 세 토큰 중 하나로 *시작* 하라고 규정하기 때문이다(아래 HA-2).

### Hardening (비차단)

- **★ HA-1(신규) — H3 가드의 두 앵커 중 `` `verifications/` `` 쪽이 무가드다.** `_dormant_section` 이 범위를 좁혔지만 **미끼가 절 *안*에 이미 있다** — `docs/README.md` 43·45·47행이 `verifications/` 를 세 번 인용하므로, 지시받은 문장에서 그 이름을 빼도 셀이 만족된다(MA-2 실측 전건 초록). 실효 앵커는 `전신` 한 낱말이다. 폐쇄 보고와 대상 기록이 둘 다 *"앵커를 두 낱말로 잡았다"* 라 적었으므로 **서술이 실제보다 한 낱말 강하다.** 처방: 헬퍼가 떼는 범위를 **그 한 줄**(`verification_briefs/2026-06-24` 항목 줄)로 더 좁히거나, 두 낱말이 **같은 줄**에 있는지를 재는 쪽으로 바꾼다. H3 자체가 하드닝이었으므로 차단이 아니다.
- **HA-2(신규, 낮음) — 승격된 선행 기록 넷의 판정 첫 줄이 세 토큰으로 시작하지 않는다.** `**최종 판정은 합격이다**` 는 가이드가 금지한 *"네 번째 어휘"* 의 문턱에 있다(§Required sections 은 `**합격**` / `**조건부 합격** — …` / `**불합격** — …` 셋뿐이라고 못 박는다). **이 커밋이 만든 것은 아니고**(선례 넷은 `2e025dc`·그 이전) 인덱스와 뜻이 어긋나지도 않으므로 비차단이다. 다만 AC1 을 닫을 때 같은 모양을 복제하지 말고 `**합격**` 으로 시작하는 편이 낫다.
- **HA-3(신규, 낮음) — 인덱스 요약 셀의 수치가 발행 즉시 낡았다.** `docs/verifications/README.md` 70행이 *"문서 가드 948 subtests"* 라 적는데, 그 인덱스가 실린 트리의 실측은 **950** 이다(자기 기록 파일이 +2 를 냈다). 기록 본문의 기준선 표는 `2e025dc` 시점 값이라 옳지만, **인덱스 요약은 발행 트리에서 읽힌다.**
- **HP-1(대상이 연 것) — 유지.** 수동 저장 특성 셀이 replay 행의 정체를 안 본다(MP-9 재현). **분류(비차단)는 옳고, 근거는 §6 으로 교체해야 한다.** HANDOFF 미수리 표에 이미 올라가 있다.
- **H1(선행) — 좁혀졌으나 열려 있다.** MA-3·MA-4 가 경계를 확정했다: 절 제목이 접두 `## 휴면 디렉터리` 를 **포함하기만 하면** 표 17행의 앵커가 끊겨도 전건 초록이다. 비-`.md` 링크(벤치마크 `.json` 둘) 축도 그대로다.
- **H2·H4(선행) — 그대로 열려 있다.** 발행 검증·폐쇄 보고·대상 재검·이 재감사 넷이 같은 판단이다.
- **HP-2(대상이 연 것) — 동의.** 두 특성 셀의 docstring 경고가 무가드지만, **오너 결정 D2 가 대기 중**이라 지금 가드를 세우는 것은 이르다.


> ## 폐쇄 보고 (2026-09-12, 세션 74 — 승격 재검 세션)
>
> **조건 AC1 을 닫았고 지적받은 정정 셋을 반영했다. 판정 승격은 이 보고가 하지 않는다** — 조건을 닫은 세션이 자기 판정을 올리면 독립성이 사라진다(v1.8.52·v1.8.57·v1.8.63·v1.8.65 선례).
>
> - **AC1 → 선행 기록 본문의 판정 두 자리를 승격했다.** 선례를 먼저 재현해 모양을 확인했다 — `2e025dc` 는 승격 대상 기록 넷에서 **머리 요약 줄**(`**최종 판정은 합격이다** — … 아래 본문은 발행 시점 그대로다`)과 **§Verdict 줄**(`**합격**(승격 — …). 발행 시점 판정 원문:`) **둘 다** 고쳤다. [`activity_replay_and_dormant_docs.md`](activity_replay_and_dormant_docs.md) 3행·220행을 같은 모양으로 올리고, **발행 시점 판정 원문은 두 자리 모두 인용(`>`)으로 보존**했다 — 인용으로 내린 것은 머리에 `**조건부 합격**` 으로 시작하는 줄이 남으면 나중 분류가 다시 흔들리기 때문이다(가이드 §Required sections 가 첫 줄을 규정하는 이유).
> - **HA-1 → 재현 확인 후 승격 기록에 반영.** 감사 주장을 그대로 받지 않고 **양방향으로 다시 쟀다**: `전신` 만 걷으면 **1 failed**(H3 셀) · `verifications/` 만 걷으면 **20 passed 전건 초록** · 절 안 `verifications/` 출현 **6회**. **감사가 옳다 — 실효 앵커는 한 낱말이다.** 승격 기록의 MP-6 결론 칸을 *"② 절반만 참"* 으로 정정하고 H1 하드닝 항목에 처방과 함께 이었다. **가드 자체는 고치지 않았다**(검증자는 결함을 조용히 고치지 않는다) — H2 와 한 슬라이스로 묶는 편이 싸다는 감사 판단에 동의해 HANDOFF 미수리 표에 올렸다.
> - **HP-1 근거 → 교체.** 감사 §6 의 지적이 옳다 — *"형제 셀이 처방을 넘어섰으므로 의무 이행"* 은 **"옆에서 더 했으니 됐다"** 로 무셀을 정당화하는 모양이고, 그것이 가이드 §"boundary matrix has no empty cells" 가 금지하는 바로 그 논증이다. 근거를 **계약 원문**으로 갈았다(계약이 요구한 것은 *행을 남기는가* 와 *`idempotent_replay` 를 단정하는가* 둘뿐이고 수동 저장 셀은 둘 다 갖는다 · **action 리터럴은 계약 침묵**). **분류(비차단)는 유지**된다.
> - **HA-3 → 측정 시점을 수치에 붙였다.** 인덱스 요약 셀의 *"문서 가드 948"* 을 *"변이 전 트리 `2e025dc` 기준 948"* 로 고쳤다 — 가이드 §"Recording a measurement" 가 요구하는 모양이다(수가 틀린 것이 아니라 **라벨이 불완전**했다).
> - **★ 패턴 스윕이 감사의 주장 하나를 정정했다.** 감사는 이 불일치를 *"디스크 310건 전수 기계 대조에서 유일한 1건"* 이라 적었다. AC1 을 닫은 뒤 같은 병을 저장소 전체로 다시 훑었더니(인용 아닌 줄의 판정 토큰 집합 ↔ 인덱스 판정 열) **선재 5건이 더 있다** — `2026-09-11/landing_l2_terms_privacy.md:70` · `2026-08-20/mypy_guard_slice.md:99` · `2026-08-20/embedding_adapter_slice.md` · `2026-08-20/reranker_slice.md` · `2026-08-23/llm_key_fallback_slice.md` 가 **인덱스 합격 · 본문 조건부 합격**이다. 즉 실측은 **여섯**(내가 닫은 1 + 선재 5)이고, AC1 은 *새로 생긴 병* 이 아니라 **반복되는 병의 최신 사례**다. **다섯 건은 내가 승격한 축이 아니라 손대지 않았고**(검증하지 않은 판정을 내가 올릴 수 없다) HANDOFF 미수리 표에 처방 둘과 함께 부채로 세웠다. **★ 여기서 드러난 더 큰 사실**: 이 축에는 가드가 없다 — `VerificationCountClaimsTest` 는 판정 열이 *비어 있지 않은가* 만 재고 **본문은 안 읽는다**. 본문↔인덱스 대조 셀이 처방인데, 217건이 판정 토큰을 줄머리에 두지 않아 **형식을 먼저 정해야** 세울 수 있다.
> - **안 닫은 것**: **HA-1 의 가드 보강**(위 — 다음 문서 슬라이스, H2 와 함께) · **HP-1**(수동 저장 셀의 action 단정 — 오너 결정 D2 와 같은 자리) · **HP-2·H1 남은 절반·H2·H4**. 전부 비차단이고 HANDOFF 미수리 표·승격 기록 §Hardening 이 담는다.
> - 회귀: 문서만 바뀌었다(백엔드 소스·테스트 0줄). `test_docs_indexes`+`test_repo_hygiene` **29 passed / 952 subtests**.

## Verdict

**조건부 합격** — **AC1**: 인덱스 판정 열(`**합격**`)과 선행 기록 [`activity_replay_and_dormant_docs.md`](activity_replay_and_dormant_docs.md) 본문 3행(`**조건부 합격** — 조건 C1: …`)이 서로 다른 말을 한다. 가이드 §Required sections 이 *"같은 말을 해야 한다"* 로 못 박은 자리이고, **디스크 310건 중 유일한 불일치**이며, 바로 앞 커밋이 같은 상황을 **4/4 로 반대로** 처리했다. 한 줄로 닫힌다(§Issues AC1).

승격의 **실체는 정당하다**:

1. **변이 표가 전건 재현된다** — MP-1 ~ MP-11b 열한 종을 diff 원문으로 재적용해 **건수·기명 셀까지 100% 일치**했다. 과장도 누락도 없다.
2. **C1 처방 세 항목이 문면대로 이행됐다** — 행 수 단정 · `idempotent_replay` 단정 · 지시받은 docstring 문장(두 셀 모두 실재, `file:line` 확인).
3. **세 갈래가 분리 소유된다** — finalize 변이(MP-3·MP-4)가 신규 셀 둘을 건드리지 않는다. C1 의 차단 사유(*"오너가 유예로 명시한 D2 를 다음 슬라이스가 코드 두 줄로 조용히 풀 수 있다"*)가 실제로 해소됐다.
4. **깨려는 시도가 실패했다** — 인접 계약(처분표)은 다른 층이 잠그고 있었고(MP-8b), H3 가드의 세 성질 중 둘은 참이며(MP-5·MP-7), 남은 사각들은 계약이 침묵하는 자유도다.
5. **수치 주장이 전건 실측과 일치한다** — 기준선 여섯, 셀 수 셋, 건수 네 자리, 판정 분포, 유도 조건(백엔드 소스 무변)까지 하나도 틀리지 않았다.
6. **범위 밖 변경 0** — 서비스 소스 무변, 남의 기록 무변, 훅 단위까지 슬라이스 안.

**대상이 틀린 것 둘**(둘 다 비차단): **HP-1 비차단 분류의 *근거***(§6 — 결론은 맞고 논증이 틀렸다) · **MP-6 의 결론 서술**(§3 HA-1 — 미끼를 절 밖에 놓아 실효 앵커가 한 낱말임을 놓쳤다).

## Outstanding items

1. **AC1 은 이 감사가 고치지 않았다** — 검증자는 결함을 조용히 고치지 않는다(가이드 §Relation). 한 줄짜리이며 처방이 §Issues AC1 에 그대로 있다. **B10 은 셀이 없는 축이라 기계 대조로만 잡힌다** — 닫을 때 `VerificationsIndexTest` 에 *인덱스 판정 열 ↔ 기록 판정 줄 일치* 셀을 하나 세우는 것을 함께 고려할 만하다(310건 전수 subtest — 지금 트리에서 위반 1건이므로 **셀을 먼저 세우면 빨갛게 뜬다**, 순서는 문서 먼저).
2. **HA-1 은 다음 문서 슬라이스 몫** — H2 와 같은 자리에서 한 번에 닫는 편이 싸다.
3. **HP-1·HP-2·H1·H2·H4 는 그대로** — 대상 기록과 HANDOFF 미수리 표가 이미 담고 있다.
4. **오너 결정 대기 두 건 그대로** — 활동 로그 D2 · 파기 청구 뒤 탈퇴 취소.
5. **이 기록 파일 자신이 기준선을 +2 한다**(문서 1 = `test_repo_hygiene` +1 · 검증 인덱스 행 1 = `test_docs_indexes` +1). HANDOFF 회귀 기준선 줄과 루트 README ②행을 **4,227 → 4,229** 로 같이 올렸다(양단 실측: 문서 가드 둘 950 → 952 · passed 무변 · 백엔드 소스 무변).
6. **커밋하지 않았다** — 변경은 작업 트리에 남겨 두었다(오너 지시).

## Reproduction

```bash
# 0) 본 트리를 건드리지 않는다 — 탈치 워크트리에서만 변이한다
cd /mnt/f/devel/ai_writte_system
git status --short                      # 비어 있어야 한다(첫 변이 전 게이트)
git worktree add --detach /tmp/verify_s75 432f790

# 1) 기준선 (세 리비전 양단)
cd /tmp/verify_s75
PYTHONPATH=$PWD python3 -m pytest tests/test_activity_api.py tests/test_writing_accept.py -q            # 77 / 19
PYTHONPATH=$PWD python3 -m pytest tests/test_docs_indexes.py -q                                        # 20 / 323
PYTHONPATH=$PWD python3 -m pytest tests/test_activity_api.py tests/test_activity_actions.py \
    tests/test_activity_log.py tests/test_writing_accept.py tests/test_application_api.py -q           # 238 / 694
PYTHONPATH=$PWD python3 -m pytest tests/test_docs_indexes.py tests/test_repo_hygiene.py -q             # 29 / 950
PYTHONPATH=$PWD python3 -m pytest --collect-only -q | tail -1                                          # 3064 collected
# 발행 시점·직전 리비전 대조: 같은 명령을 `68aedf3`(19/317 · 236/694) · `2e025dc`(20/322 · 29/948) 워크트리에서

# 2) 변이 — 매번 「앵커 count==1 단정 → copy2 백업 → write_text 치환 → 초점 재실행 → 백업 복원 → 바이트 대조」
#    diff 원문은 §2·§3 표에 있다. 결과는 요약 줄과 FAILED|SUBFAILED 를 함께 읽는다.
#    ★ 같은 파일에 두 군데를 칠 때는 백업을 **파일당 한 번** 잡는다(§Outstanding 아님 — 아래 주의).
PYTHONPATH=$PWD python3 -m pytest <초점> -q 2>&1 | grep -E "^(FAILED|SUBFAILED)|passed|failed"

# 3) 인덱스 대조 — 산문을 읽지 말고 표를 파싱해 센다
cd /mnt/f/devel/ai_writte_system
ls docs/verifications/*/*.md | wc -l                                   # 310(이 기록 전)
grep -c '^| \[' docs/verifications/README.md                           # 310
#   판정 열 ↔ 기록 본문 판정 줄 전수 대조: 인덱스 각 행의 링크를 열어 머리 8줄에서
#   `**합격**` / `**조건부 합격**` / `**불합격**` 접두를 찾아 맞댄다 → 불일치 1건(AC1)

# 4) 정리
git worktree remove --force /tmp/verify_s75
git status --short                      # 다시 비어 있어야 한다
```

**★ 재현 시 주의(이 감사가 실제로 겪은 것).** 첫 MP-6 실행에서 헬퍼가 **같은 파일에 두 편집**을 하며 백업을 두 번 잡아, 복원이 *한 번 변이된 상태* 를 원본으로 되돌려 놓았다. `git status --short` 가 `M docs/README.md` 로 그것을 즉시 드러냈고(헬퍼가 매 실행 끝에 찍는다), **그 오염된 트리 위에서 돈 MA-3·MA-4·MA-5 의 첫 실행은 전부 무효**였다 — 셋 다 "1 failed" 를 냈지만 그것은 제목 변경이 아니라 *앞서 지워진 문장* 때문이었다. 탈치 워크트리였으므로 `git checkout -- docs/README.md` 로 안전하게 되돌린 뒤(본 트리에는 쓰지 않았다) 헬퍼를 고쳐 넷을 다시 돌렸고, 그제야 MA-3·MA-4 가 **초록**으로 갈렸다. **이것이 가이드 §"When a mutation does not bite" 의 거울상이다 — *물었다* 쪽도 똑같이 의심해야 하고, 그 의심을 실제로 켜 주는 것은 매 실행 뒤의 `git status --short` 한 줄이다.**
