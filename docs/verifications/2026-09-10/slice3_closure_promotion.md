# 승격 재검 — 세션 51 폐쇄분(검증 조건 셋 + 하드닝 둘) · 선행 기록 판정 승격

## Subject metadata

- **검증일**: 2026-09-10 · **요청자**: 오너("핸드오프 확인해서 다음작업 진행해줘" — HANDOFF Next Tasks 1번이 승격 재검을 가리킨다)
- **검증자**: 독립 세션(세션 52) — **구현(49)·검증(50)·폐쇄(51) 어느 세션도 아니다**
- **대상**: 세션 51 폐쇄 커밋 둘 — `b23f689`(법률 축: 부칙 시행 표기 + 결합 가드 조임 + 제5조 1항 6,000자 + 상징 참조 셀) · `7e07b37`(파기 축: B3·H1·H2 다섯 셀), SoT **v1.8.52**
- **정규 스펙(계약 범위)**: 선행 검증 기록 [`account_withdrawal_slice3_legal_effective.md`](account_withdrawal_slice3_legal_effective.md) §Blocking(B1·B2·B3)·§Hardening(H1·H2)·§Verdict 의 조건 문구 · SoT v1.8.51(파기 5단계 순서 · compose `stop_grace_period` 120s)·v1.8.52 변경이력 · [`guides/verification.md`](../../guides/verification.md) §"Mutation testing"
- **작업 소스**: 커밋 트리 `c1cb282`, 작업 트리 clean(측정 전 `git status --short` 무출력 실측)
- **환경**: 알파 · 호스트 `/usr/bin/python3` · test-mongo `rs-test` 단일노드 27020(PRIMARY 확인 후 측정) · 개발 스택 14컨테이너 중 `withdrawal_worker` **여전히 없음**(Slice 3 이전 컨테이너들 — 선행 기록 Outstanding 그대로)

**이 검증이 존재하는 이유.** 조건 셋을 닫은 것이 **세션 51 자신**이라 선행 기록의 판정이 `조건부 합격` 에 멈춰 있고, 폐쇄분이 미검증 구간으로 남았다. 승격 권한은 *"다음 독립 세션 또는 오너"* 이며(선행 기록 §Outstanding 3 · 오너 결정 2026-08-06 *"판정 열은 그 기록의 최종 판정이다"* · 선례 [`2026-08-10/accept_activity_cell_reinforcement.md`](../2026-08-10/accept_activity_cell_reinforcement.md)), 이 세션이 그 독립 세션이다.

## Scope

1. **조건 폐쇄가 처방대로인가** — B1·B2·B3 각각의 처방 문구 ↔ 실제 diff 대조
2. **★ 변이 재적용** — 선행 기록이 지정한 MU-7·8·12~16 + 세션 51 이 주장한 over 둘(MU-7b·8b). 새 셀 다섯이 **자기 조항을** 무는지, 세션 51 의 조항-셀 페어링이 재현되는지
3. **★ 반증 시도(신규 변이)** — 폐쇄가 *주장보다 약한/강한* 자리를 찾는다. 가드 조임의 필요성 반증(MU-15r) · 새 셀의 경계 폭(MU-17·18·19·22) · **폐쇄가 손대지 않은 형제 자리**(MU-20)
4. **회귀 기준선 재현** — 3023/1/4117(`f37fab0` 주장) 을 `c1cb282` 에서 재측정
5. **패턴 스윕** — B2 축(낡은 수치)이 다른 자리에도 남았는가

## Methodology

```bash
git status --short                                   # 무출력 = 프리플라이트 통과
docker ps                                            # test-mongo healthy · withdrawal_worker 부재 실측
python3 -c "…MongoClient(27020).admin.command('hello')"   # isWritablePrimary True
python3 -m pytest -q                                 # 전수(고정 트리, 문서 편집 전)
# 변이: 편집 → 초점 실행 → git checkout -- <path> → git status --short 무출력 확인
python3 -m pytest -q tests/test_account_purge.py tests/test_account_withdrawal_worker.py
python3 -m pytest -q tests/test_service_policy_contract.py
```

- 판독은 **요약 카운트 줄 + `FAILED|SUBFAILED` 양쪽**으로 했다(가이드 §"`grep FAILED` misses subtest failures"). 실제로 법률 축 변이 넷은 전부 `SUBFAILED` 로 나왔다 — `FAILED` 만 걸렀으면 *"안 물었다"* 로 오독했을 자리다.
- 변이는 **적용한 diff 를 그대로** 기록한다(패러프레이즈 금지 — 가이드 2026-08-09 실측).
- 전수는 **문서를 한 자도 고치기 전에** 고정 트리에서 돌렸다(세션 51 이 겹쳐 돌려 37분을 버린 선례 넷째를 피한다).

## Findings

### 1. 조건 폐쇄 ↔ 처방 — 셋 다 처방대로, 하나는 처방보다 넓다

| 조건 | 처방(선행 기록 §Verdict) | 실제 diff | 판단 |
|---|---|---|---|
| **B1** | 부칙 `draft-0 (미시행)` 정리 + *"결합 가드가 `draft-0` 토큰 잔류도 보게 조이는 것을 권장"* | 부칙 두 줄 → `1.0`([terms:102](../../legal/terms-of-service-draft.md)·[privacy:94](../../legal/privacy-policy-draft.md)) + 가드가 셋을 함께 본다([test_service_policy_contract.py:277-293](../../../tests/test_service_policy_contract.py)) | **처방보다 넓다** — 권고한 토큰 부재에 더해 **머리말 버전 줄 전체 대조**까지 넣었다. §3 의 MU-15r 이 그 추가분이 장식이 아님을 실증한다 |
| **B2** | 4,000자 → 6,000자 | 문장 정정 + **상징 참조 셀**([test_service_policy_contract.py:211-254](../../../tests/test_service_policy_contract.py)) | 처방대로 + 잠금. 값을 핀으로 박지 않고 `env.py::DRAFT_RAW_TEXT_MAX_CHARS`·`core_sot/service.py::SCENE_NOTE_MAX_CHARS` 를 읽는다 — MU-19 가 그 방향을 확인했다 |
| **B3** | *"스위퍼가 실패하는 픽스처에서 계정 행 생존 + `failed_at="account_axis_sweep"` 단정"* | 그대로 + **`purge_started_at` 표식**까지([test_account_purge.py:498-533](../../../tests/test_account_purge.py)) | 처방대로. 표식 단정이 더해진 것이 옳다 — B3 의 결함 서술이 *"reconciler 가 못 찾는다"* 이고 그 질의의 실제 조건이 `{"purge_started_at": {"$ne": None}}` 이다([account_purge_reconciler.py:56](../../../scripts/account_purge_reconciler.py)) |

- **픽스처가 허수아비가 아니다** — 새 셀 셋 다 실제 `InMemoryUserRepository`·`AccountPurgeService` 를 쓰고 대역은 실패시킬 한 축(`_FailingSweeper`)·정지 신호(`_StopAfter`)뿐이다.
- **셀 수 실측**: `test_account_purge.py` 29 + `test_account_withdrawal_worker.py` 14 = **43**(주장과 일치, 38→43) · `test_service_policy_contract.py` **8**(7→8).

### 2. 변이 재적용 — 지정 7종 + over 2종, **세션 51 의 페어링이 전건 재현**

프리플라이트 `git status --short` 무출력 · 매 변이 뒤 `git checkout --` → 무출력 확인(15회 전부). 초점 = `test_account_purge.py + test_account_withdrawal_worker.py`(43셀) 또는 `test_service_policy_contract.py`(8셀).

| # | 방향 | 적용한 diff | 실측 결과 | 세션 51 주장 |
|---|---|---|---|---|
| **MU-7** | under | `account_purge.py::purge_account` 의 `try: swept = self._sweeper.sweep(...)` 4줄과 `try: self._users.delete(...)` 4줄을 **통째로 교환** | **1 failed** `AccountPurgeFailureTest::test_a_failed_sweep_leaves_the_account_row_alive_and_stamped` | 일치 |
| **MU-7b** | over | 같은 자리를 `except Exception: swept = {}` 로(스윕 실패를 삼키고 계정 행은 그대로 삭제) | **1 failed** 같은 셀 | 일치 |
| **MU-8** | under | `run_once` 의 `if stop_check is not None and stop_check():` / `break` **두 줄 삭제** | **1 failed** `GracefulStopTest::test_a_stop_request_ends_the_pass_at_the_next_claim_boundary` | 일치 |
| **MU-8b** | over | 같은 자리를 `if stop_check is not None:`(값과 무관하게 끊음) | **2 failed** 위 셀 + `test_without_a_stop_request_the_pass_drains_everything` | 일치 |
| **MU-16** | under | `_summary_doc` 의 `for result in summary.results if not result.succeeded` → `for result in summary.results` | **2 failed** `ApplyModeTest` 두 셀 | 일치 |
| **MU-12** | under | 약관 부칙 `- 이 약관 버전: \`1.0\`` → `` `draft-0` (미시행) `` | **1 failed**(SUBFAILED `document='terms-of-service-draft.md'`) `test_both_documents_carry_the_enforced_version_and_date` | 일치 |
| **MU-13** | under | 방침 부칙에 같은 복원 | **1 failed**(SUBFAILED `document='privacy-policy-draft.md'`) 같은 셀 | 일치 |
| **MU-14** | under | 제5조 1항 `본문은 **6,000자**` → `**4,000자**` | **1 failed** `test_the_length_limits_in_the_terms_match_the_constants` | 일치 |
| **MU-15** | over | 머리말 `버전: \`1.0\`` → `\`2.0\``(부칙은 `1.0` 유지) | **1 failed**(SUBFAILED) `test_both_documents_carry_the_enforced_version_and_date` | 일치 |

**아홉 종 전부 세션 51 이 적은 셀 이름·개수와 같다.** 새 셀 다섯이 각자 자기 조항을 물고 있고, 한 셀이 여럿을 뭉뚱그려 흡수한 자리는 없다.

### 3. 반증 시도(신규 변이 여섯) — 다섯은 폐쇄를 더 굳혔고, **하나가 새 갭을 열었다**

| # | 방향 | 적용한 diff | 결과 |
|---|---|---|---|
| **MU-15r** | **반사실** | MU-15 를 적용한 채로 가드를 **폐쇄 이전 형태로 되돌린다**(`assertNotIn(_DRAFT_VERSION, …)`·부칙 줄 단정 제거, 머리말은 `assertIn(f"버전: \`{_ENFORCED_VERSION}\`", text)` 부분 문자열로) | **8 passed — 초록.** 세션 51 의 *"종전 가드로는 초록이던 자리"* 주장이 **실측으로 참**이다. 줄 전체 대조는 장식이 아니라 하중을 받는다 |
| **MU-17** | under | 약관 상태줄만 `시행 — 2026-09-08` → `2026-10-01`(부칙 시행일은 유지) | **1 failed**(SUBFAILED) 같은 결합 셀 — 날짜 축도 두 자리가 함께 잠긴다 |
| **MU-18** | over/순서 | `run_once` 의 정지 확인을 루프 **머리에서 꼬리로 이동**(청구 전 → 파기 후) | **1 failed** `test_a_stop_request_ends_the_pass_at_the_next_claim_boundary` — H1 셀은 정지 확인의 **존재만이 아니라 위치**를 잠근다(주장보다 강하다) |
| **MU-19** | over | `env.py::DRAFT_RAW_TEXT_MAX_CHARS = 6000` → `5000`(문서는 그대로) | **2 failed** — 정책 문서 축(SUBFAILED `axis='원고 유닛 본문 상한'`) + 새 약관 셀. 상징 참조가 **상수→문서** 방향으로도 문다 |
| **MU-22** | under | `purge_account` 의 `self._users.delete(user.id)` → `pass`(성공해도 계정 행을 안 지운다) | **4 failed**, 그중 `AccountPurgeOrderTest::test_a_due_account_is_purged_end_to_end` — 새 셀 docstring 이 *"반대편은 그 셀이 받는다"* 고 적은 주장이 참이다 |
| **★ MU-20** | under | `run_loop` 의 `service.run_once(limit=args.limit, stop_check=stop.is_requested)` → `service.run_once(limit=args.limit)`(**정지 플래그를 안 넘긴다**) | **43 passed — 초록. 아무것도 안 문다** → 아래 H1' |

**MU-20 이 왜 초록인가 — 어느 층이 흡수한 것이 아니라 층이 없다.** `LoopTest` 의 대역 `_FakeService.run_once` 가 `stop_check` 를 **받기만 하고 버린다**([test_account_withdrawal_worker.py:110](../../../tests/test_account_withdrawal_worker.py)), 그래서 `_FakeStop.checks` 는 `run_loop` 자신의 `while`/`if` 두 호출로만 오른다 — 배선을 끊어도 `calls=2 · slept=[7.0] · events` 가 전부 그대로다. 다른 셀도 없다(`grep -rn "run_loop\|stop_check" tests/` 실측).

### 4. 회귀 기준선 — 재현

**3023 passed / 1 skipped / 4117 subtests · EXIT=0**(알파·호스트, **1618초**, test-mongo ON, 커밋 `c1cb282`, 문서 편집 전 고정 트리). 세션 51 주장(3023/1/4117, `f37fab0`)과 **셀·skip·subtest 전부 일치**. `c1cb282` 는 `f37fab0` 대비 문서 5파일만 바꾼 커밋이고 subtest 가 안 움직였다 — 세션 51 의 *"subtest +3 은 `a3d6cf2` 몫"* 귀속과 모순되지 않는다. skip 1 = live Chroma(함정 절 규칙).

**소요 1618초는 머신-로컬 값이다** — 세션 51 의 2271초와 비교하지 말 것(같은 머신이라도 부하가 다르다). 값이 아니라 **셀·skip·subtest 세 수**가 재현의 기준이다.

### 5. 패턴 스윕 — B2 축의 잔류 없음

- `docs/legal/`·`docs/service-policy-contract.md` 전체에서 `4,000`·`4000` **0건**, 시행값 6,000 은 약관 제5조 1항과 정책 문서 표 두 자리에만 있다(실측).
- `draft-0` 토큰: 법률 문서 둘에 **0건**. 저장소 잔류는 [`plans/landing-page-scope-decisions.md`](../../plans/landing-page-scope-decisions.md) 의 **당시 상태 서술**(선행 조건·착수 순서 항목)뿐이고, 같은 문서가 87·91행에서 *"① 은 2026-09-09 에 닫혔다"* 로 스스로 갱신한다 — 브리프는 결정 시점의 기록이므로 **정정 대상이 아니다**.

## Issues / Risks

### Blocking (계약 의무 — 판정을 결정)

**없다.** 선행 기록의 차단 셋은 처방대로 닫혔고, 지정 변이 일곱과 over 둘이 전부 기명 셀을 물었으며, 신규 변이 여섯 중 다섯이 폐쇄를 더 굳혔다.

### Hardening (비차단)

- **★ H1' — `run_loop` → `run_once` 의 정지 배선이 무셀이다**(MU-20 초록). H1 폐쇄는 **피호출자**(`run_once` 가 `stop_check` 를 존중하는가)를 닫았고, **호출자가 그 플래그를 실제로 넘기는가**는 그대로 열려 있다. 그 배선이 끊기면 SIGTERM 은 `while` 경계에서만 서므로 **진행 중인 pass 가 최대 `limit`(기본 10) 계정을 끝까지 돈다** — compose `stop_grace_period: 120s` 를 넘기면 SIGKILL 이고 그 계정이 부분 파기로 남는다(H1 이 막으려던 바로 그 결과가 다른 문으로 들어온다).
  **처방은 한 줄이고 저장소에 선례가 있다** — 형제 워커가 정확히 이 축을 잠근다: `_FakeWorker.run_once` 가 `self.last_stop_check = stop_check` 로 받아 두고 셀이 `assertIsNotNone(worker.last_stop_check)` 를 단정한다([test_index_sync_worker_script.py:294·341](../../../tests/test_index_sync_worker_script.py), 주석 *"stop_check was threaded into run_once (G2 wiring, not just the loop guard)"*). `_FakeService` 에 같은 두 줄을 넣고 `test_run_loop_drains_then_idles_then_stops` 에 한 단정을 더하면 닫힌다.
  **왜 비차단인가** — 선행 기록이 이 축 전체를 **H1(비차단)** 으로 분류했고 이 발견은 그 축의 **이음매**다. 판정을 뒤집을 계약 의무가 아니라, 같은 하드닝의 남은 절반이다.
- **H2' — `test_the_effective_date_and_the_unenforced_marker_move_together` 가 시행 뒤 퇴화했다.** 재는 것이 `"\`[시행일]\`" in text == "Draft — 법률 검토 전 · 미시행" in text` 인데 시행 후 양변이 항상 `False` 라 **공허하게 참**이다. 셀 docstring 스스로 *"진짜 시행은 이 셀을 삭제하는 것이 아니라 그때의 사실로 고치는 것"* 이라 적는데 그 고침이 아직 안 됐다 — 지금 시행 축을 실제로 잠그는 것은 B1 이 조인 결합 셀뿐이다. 비차단(중복 잠금의 공백이지 계약 구멍이 아니다)이나, 남겨 두면 다음 사람이 이 셀을 시행 축의 가드로 오해한다.
- **H3'(승계) — 약관·방침의 나머지 수는 여전히 무잠금.** 세션 51 이 부채로 남긴 그대로다. 이 세션이 손 스윕으로 현재 일치를 다시 확인했다(§5). *조항 ↔ 상수* 표가 생기기 전까지는 사람이 읽는 축이다.

## Verdict

**합격** — 차단 없음.

근거: ① 선행 기록의 차단 셋이 **처방대로**(B1 은 처방보다 넓게) 닫혔고 ② 지정 변이 **MU-7·8·12~16 + over 둘이 전부 세션 51 이 적은 기명 셀·개수 그대로 재실패**했으며 ③ 반사실 변이(MU-15r)가 가드 조임이 하중을 받는다는 것을, 신규 변이 넷(MU-17·18·19·22)이 새 셀들이 주장보다 넓게 문다는 것을 실측했고 ④ 회귀 기준선 3023/1/4117 이 셀·skip·subtest 전건 재현됐다. 남은 셋은 전부 하드닝이며 그중 H1' 은 저장소 안에 복사할 선례가 있는 한 줄짜리다.

**→ 선행 기록 [`account_withdrawal_slice3_legal_effective.md`](account_withdrawal_slice3_legal_effective.md) 의 판정을 `조건부 합격` → `합격` 으로 승격한다.** 오너 결정 2026-08-06(*"판정 열은 그 기록의 **최종** 판정이다"*)에 따른다. 인덱스 분포가 합격 194 → **196**(승격 1 + 이 기록 1) · 조건부 96 → **95** 로 움직인다.

## Outstanding items

- **Slice 4(화면)를 열어도 된다.** 승격 전 금지(*"파기 축은 되돌릴 수 없다"*)의 조건이 해제됐다. 다음은 요청·취소·남은 일수 배너 + D3 의 관리자 잔여 정리다.
- **H1' 은 Slice 4 에 얹는 편이 싸다** — 같은 워커 축이고 셀 하나다. 독립 슬라이스를 열 크기가 아니다.
- **개발 스택(알파) 재생성은 그대로 남아 있다** — `withdrawal_worker` 컨테이너가 아직 없다(이 세션 `docker ps` 실측). 배포 대기도 그대로(HANDOFF 5번 절차 — `migrate_ledger_user_axis.py` 선행).
- **이 기록 자신**이 인덱스 건수를 295 → **296**(70일치 유지)으로 움직인다. 셀은 안 늘었으므로 **회귀 기준선 3023/1/4117 은 그대로**이고, 문서 파일 +1 이 위생 가드 subtest 회계에 들어갈 수 있다(가드는 파일 수를 조용히 세므로 다음 전수에서 subtest 가 움직이면 이 파일이 원인이다 — 예고이지 측정값이 아니다).

## Reproduction

```bash
git checkout c1cb282
docker compose -f docker-compose.test.yml up -d      # test-mongo healthy · PRIMARY 대기
git status --short                                   # 무출력이어야 변이 착수 가능

python3 -m pytest -q                                 # 3023 / 1 / 4117 · EXIT=0
python3 -m pytest -q tests/test_account_purge.py tests/test_account_withdrawal_worker.py   # 43
python3 -m pytest -q tests/test_service_policy_contract.py                                  # 8 / 44

# 변이 — 매번: 편집 → 위 초점 실행 → git checkout -- <path> → git status --short 무출력
# MU-7  : account_purge.py purge_account 의 sweep 4줄 ↔ delete 4줄 교환        → 1 failed
# MU-8  : run_once 의 "if stop_check is not None and stop_check(): break" 삭제 → 1 failed
# MU-12 : 약관 부칙 버전 줄을 `draft-0` (미시행) 로                              → 1 failed(SUBFAILED)
# MU-14 : 제5조 1항 6,000자 → 4,000자                                          → 1 failed
# MU-15 : 머리말 "버전: `1.0`" → "`2.0`" (부칙 유지)                            → 1 failed(SUBFAILED)
# MU-16 : _summary_doc 의 "if not result.succeeded" 제거                       → 2 failed
# MU-20 : run_loop 의 run_once(..., stop_check=stop.is_requested) 인자 삭제     → 43 passed(갭)
```

환경 민감 항목: 전수·초점 모두 **알파·호스트**(test-mongo 27020 `rs-test` PRIMARY)이고 `.env` 는 손대지 않았다. 소요(1618초)는 머신-로컬 값이라 다른 측정과 비교하지 않는다. 법률 축 변이는 **`SUBFAILED` 로 나온다** — `FAILED` 만 거르면 물지 않은 것으로 오독한다.
