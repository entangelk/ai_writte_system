# 승격 재검 2차 — 세션 52 레코드·기준선 커밋 독립 재검(변이 재표집 · 전수 재실행)

## Subject metadata

- **검증일**: 2026-09-10 · **요청자**: 오너("작업 Ai가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래")
- **검증자**: 독립 세션(세션 53) — **구현(49)·검증(50)·폐쇄(51)·승격 재검(52) 어느 세션도 아니다**
- **대상**: 세션 52 산출 셋 — `4f451c4`(승격 재검 기록·선행 기록 판정 승격) · `3644147`(기록화 — work_log 세션 52·HANDOFF·CHANGELOG·부채) · `7f30027`(기준선 4119 직접 실측 확정)
- **정규 스펙(계약 범위)**: [`slice3_closure_promotion.md`](slice3_closure_promotion.md) 본문(판정·변이 표·Outstanding) · [`guides/verification.md`](../../guides/verification.md)(§"Mutation testing"·§"Recording a measurement") · HANDOFF 회귀 기준선 줄의 자기 규정("*기준선을 갱신하는 슬라이스가 그 한 줄도 함께 고친다*")
- **작업 소스**: 커밋 트리 `7f30027`(HEAD), 작업 트리 clean(모든 측정 전 `git status --short` 무출력 실측)
- **환경**: 알파 · 호스트 `/usr/bin/python3` · test-mongo `rs-test` 27020(PRIMARY·healthy 실측) · 개발 스택 compose 정의 11 서비스 중 `withdrawal_worker` 제외 10 기동 + test-mongo(`docker ps -a` 에 withdrawal 컨테이너 자체가 없다). 세션 52 기록 환경 줄의 *"14컨테이너"* 는 머신 전체 `docker ps` 수(타 프로젝트 3 포함)로 읽는다 — 개발 스택 규모가 아니다

## Scope

1. **서류 일관성** — 승격이 본문·인덱스·분포표·세 README·HANDOFF·CHANGELOG·work_log 전체에서 같은 숫자를 말하는가
2. **변이 재표집** — 세션 52 의 표에서 부채를 낳은 축(MU-20)과 폐쇄의 실증축(MU-8)을 직접 재적용
3. **기준선 재도출** — 양단 산술(`c1cb282` 305/606 ↔ 현행 306/607)을 워크트리로 독립 재현 + HEAD 전수 재실행
4. **인용 정확성** — 선례 행 번호·대역 동작·production 배선을 1차 소스와 대조
5. **머신 상태** — `withdrawal_worker` 부재·test-mongo 상태를 직접 실측(stale note 여부)

## Methodology

```bash
git status --short                                   # 무출력 = 프리플라이트 통과(변이 전후 각 2회)
git log --oneline -6 · git show --stat <세 커밋>       # 문서 전용 확인(코드 무변)
docker ps · docker ps -a | grep -i withdrawal         # 머신 상태 실측
# 변이(프리플라이트 무출력 확인 뒤): 편집 → 초점 실행 → git checkout -- <path> → 무출력 확인
python3 -m pytest -q tests/test_account_purge.py tests/test_account_withdrawal_worker.py
python3 -m pytest -q tests/test_docs_indexes.py       # 파일별 subtest 수 판독
python3 -m pytest -q tests/test_repo_hygiene.py
git worktree add --detach /tmp/wt_c1cb282 c1cb282     # 양단 산술의 반대쪽 끝
python3 -m pytest -q                                  # 전수(고정 트리, 문서 편집 전)
```

- 판독은 요약 카운트 줄 + `FAILED|SUBFAILED` 양쪽(가이드 §"`grep FAILED` misses subtest failures").
- 전수는 이 세션의 문서 편집 **전에** 돌렸다(가이드·선례 준수).

## Findings

### 1. 서류 — 승격 축은 전건 일치

- **세 커밋 모두 문서 전용**(diff --stat 실측: README·docs·CHANGELOG·HANDOFF·work_log·검증 기록만, 코드 무변). 코드는 `7e07b37`(세션 51 폐쇄 커밋) 이후 한 줄도 안 바뀌었다 — 이것이 3번의 플레이크 판정의 전제다.
- **본문 ↔ 인덱스 판정 일치**: 선행 기록 [`account_withdrawal_slice3_legal_effective.md`](account_withdrawal_slice3_legal_effective.md) 의 Verdict 첫 줄 `**합격**`, 발행 시점 판정(`조건부 합격`)은 인용 블록으로 원문 보존. 인덱스 판정 열도 `**합격**`(가드 `test_every_record_row_states_a_verdict` 요구대로 분류값만).
- **분포 산술**: 194+96+5=295 → 196+95+5=296(승격 1 + 신규 1), 백분율 95/296=32%. 분포표(38~40행)·루트 README 문장·건수 셋(루트 ③행·문서 표·docs/README) 동반 갱신 실측.
- **"예고" 잔류 없음**: 세 기준선 자리(HANDOFF·레코드 Outstanding·work_log) 모두 실측 문구. 남은 `예고` hit 은 전부 다른 맥락(구현자가 예고한 약점 등).
- **등재 검증**: 미수리 표에 H1' 행(위치 `account_withdrawal_worker.py#L257`·대역 `:110`·선례 `test_index_sync_worker_script.py:294·341`) 실존, Next Tasks 1번 = Slice 4~5 + H1' 탑재.

### 2. 변이 재표집 — 둘 다 주장 그대로

| # | 방향 | 적용한 diff | 실측 | 세션 52 주장 |
|---|---|---|---|---|
| **MU-20** | under | `run_loop` 의 `service.run_once(limit=args.limit, stop_check=stop.is_requested)` → `service.run_once(limit=args.limit)`(정지 배선 인자 삭제) | **43 passed · EXIT=0 — 전건 초록** | 일치 |
| **MU-8** | under | `run_once` 의 `if stop_check is not None and stop_check():` / `break` 두 줄 삭제 | **1 failed** `GracefulStopTest::test_a_stop_request_ends_the_pass_at_the_next_claim_boundary`(나머지 42 통과) | 일치 |

프리플라이트 무출력 → 변이 → 초점 실행 → `git checkout --` → 무출력(각 2회). **MU-20 갭은 실재하고 MU-8 폐쇄 셀은 실제로 문다** — H1' 부채 등록의 사실적 기반이 이 재검에서도 성립한다.

### 3. 기준선 — 산술은 일치, EXIT=0 은 이 시도에서 재현 못함(★)

- **양단 산술 독립 재현**: `git worktree add --detach /tmp/wt_c1cb282 c1cb282` 에서 `test_docs_indexes` **305**·`test_repo_hygiene` **606**, 현행 트리에서 **306**·**607**(합산 25 passed / 913 subtests). +2 귀속 정확.
- **HEAD(`7f30027`) 전수**: **1 failed · 3022 passed · 1 skipped · 4119 subtests · EXIT=1**(1712초). 셀 총계(3022+1=3023)·skip 1(live Chroma)·subtest 4119 는 주장과 전부 일치하나 **EXIT=0 이 재현되지 않았다**.
- **실패 셀**: `tests/test_final_save_analysis.py::test_final_save_analysis_contract_s1_to_s13` — `S13 unknown draft status: expected=404 observed=503`.
- **단독 재실행**: `python3 -m pytest -q tests/test_final_save_analysis.py` → **2 passed · EXIT=0**(7.9초).
- **플레이크 판정 근거**: ① 코드는 세션 52 가 두 번(1618·1534초) 초록으로 측정한 트리와 동일(`7e07b37` 이후 문서 커밋만 — 1차 실측) ② 단독 초록 ③ 셋 수 전부 일치. **회귀가 아니라 전수 컨텍스트 한정 플레이크**다.
- **503 의 경로**: 그 앱은 저장 계층 오류를 전역에서 503 으로 뒤집는다(SoT v1.7.38 — `main.py` 의 `PyMongoError` 예외 핸들러, 엔드포인트마다 조항을 두는 대신 앱 전역 하나). 프로브는 InMemory core_sot·analysis 를 주입하지만 모든 의존성까지는 아니므로, 일시적 저장 계층 오류 하나가 S13 의 404 자리를 503 얼굴로 대신할 수 있다. **미수리 표에 백엔드 플레이크로 등재했다**(프런트 둘에 이어 셋째 — 이 표가 "전수 1실패를 만나면 알려진 플레이크부터" 지침의 근거가 되므로 등재 자체가 절차의 마무리다).

### 4. 인용 정확성 — 전부 1차 소스와 일치

- 선례: [`test_index_sync_worker_script.py:294`](../../../tests/test_index_sync_worker_script.py)(`self.last_stop_check = stop_check`)·`:341`(`assertIsNotNone(worker.last_stop_check)` + 주석 *"stop_check was threaded into run_once (G2 wiring, not just the loop guard)"*) — 실존.
- 대역: [`test_account_withdrawal_worker.py:110`](../../../tests/test_account_withdrawal_worker.py) `_FakeService.run_once` 가 `stop_check` 를 **받고 버린다**(본문 미사용 실측) — MU-20 프레임(production 은 배선돼 있으나 무잠금)의 전제 확인.
- production 배선: [`account_withdrawal_worker.py:257-259`](../../../scripts/account_withdrawal_worker.py) — 미수리 표 앵커 `#L257` 은 배선 문장의 시작 행으로 정확.
- `grep -rln "run_loop" tests/` → 위험 축 3파일. `test_generation_job_worker.py` 에 stop_check 계열 단정 없음(다른 워커의 run_loop 셀) — "다른 셀도 없다" 주장과 모순 없음.

### 5. 잔류 — 산문 숫자 둘(이 세션에서 수정)

- **루트 [`README.md:104`](../../../README.md) 절차 표 ②행이 `3,023 passed / 4,117 subtests`** — 기준선은 4119(이제 4121). HANDOFF 기준선 줄이 스스로 "*아무 가드도 안 잡는다 — 기준선을 갱신하는 슬라이스가 그 한 줄도 함께 고친다*"고 규정한 바로 그 줄인데 `7f30027` 이 세 곳(HANDOFF·레코드·work_log)만 고치고 놓쳤다. **→ 4,121 로 동기화했다.**
- **검증 인덱스 자신의 분포 문장이 `조건부 합격이 33%`**([`verifications/README.md:42`](../README.md)) — 승격 후 실측은 95/296=32%인데 `4f451c4` 가 루트 README 백분율만 고치고 분포표가 사는 바로 그 파일의 문장은 안 고쳤다(커밋 메시지는 *"백분율 32% 동반 갱신"* 이라 주장 — 절반만 참). **→ 32% 로 수정했다.**
- 둘 다 같은 부류다: **가드가 지키는 것(표 합·루트 README 반복) 바깥의 산문 숫자**는 아무도 안 잡는다. 등재·분포·기준선을 움직이는 슬라이스는 "표"만이 아니라 **같은 숫자를 말하는 산문**까지 센다.

## Issues / Risks

### Blocking (계약 의무 — 판정을 결정)

**없다.** 승격의 실질(조건 폐쇄 재현·변이 재표집·분포 이동)은 전건 확증됐고, 아래 셋은 문서 위생·환경 관찰이다.

### Hardening (비차단)

- **S13 플레이크 등재** — 이 세션에서 미수리 표에 넣었다(위 §3). 재발이 쌓이면 S13 의 404 기대가 저장-오류 얼굴과 구분되는지(404/503 재분류 또는 프로브의 저장 백엔드 완전 주입) 재검토한다.
- **산문 숫자 스윕** — 이 세션에서 고친 둘 외에 "아무 가드도 안 잡는 산문 숫자" 부류를 일괄 검사하는 셀은 없다(가능도 불가능도 아님 — 산문은 자유 서술이므로). 대안은 등재 절차에 "같은 숫자를 말하는 산문" 체크를 남기는 것뿐이다(이 기록 §5 가 선례가 된다).
- **세션 52 기록의 "14컨테이너" 표기** — 타 세션의 발행된 기록이므로 정정하지 않는다. 이 기록 환경 줄에 실측(compose 11 서비스·10 기동+test-mongo)을 남긴다.

## Verdict

**합격** — 차단 없음.

근거: ① 승격 서류가 본문·인덱스·분포·세 README·HANDOFF·CHANGELOG·work_log 전부에서 같은 숫자를 말하고 ② 변이 재표집(MU-20·MU-8)이 주장 그대로 재현됐으며 ③ 양단 산술(305/606↔306/607)이 독립 재현됐고 ④ 선례·대역·배선 인용이 전부 1차 소스와 일치한다. **EXIT=0 미재현은 플레이크로 판정한다**(코드 동일성·단독 초록·셋 수 일치 — §3) — 기준선의 세 수(3023·1·4119)는 이 세션 실측과 일치하므로 기준선 자체는 흔들리지 않는다. 잔류 둘(README 절차 표·분포 문장)은 이 세션에서 이미 고쳤다.

## Outstanding items

- **H1' 등급(하드닝 유지 vs Slice 4 게이트)은 오너 결정으로 열려 있다** — 세션 52 가 서피스했고 이 재검은 사실 관계만 확인했다: 갭 실재(MU-20 초록 재현)·production 배선 존재·선례 존재. 등급을 올리려면 HANDOFF Next Tasks 순서 한 줄이면 된다.
- **이 기록 자신**이 subtest 를 4119 → **4121** 로 움직인다(문서 가드 실측: `test_docs_indexes` 306→**307**·`test_repo_hygiene` 607→**608**). 셀·skip 은 그대로(3023·1). **직접 실측으로 확인했다** — 이 기록까지 실린 커밋 `8990fbc` 전수 **3023 passed / 1 skipped / 4121 subtests · EXIT=0**(2133초). 산술과 직접 측정이 일치하며 **S13 은 재발하지 않았다**(같은 날 2회 중 1회).
- **개발 스택 재생성·배포 대기** — 세션 52 와 동일하게 남아 있다(`withdrawal_worker` 컨테이너 부재 실측·`migrate_ledger_user_axis.py` 선행).

## Reproduction

```bash
git status --short                                   # 무출력이어야 한다
docker compose -f docker-compose.test.yml up -d      # test-mongo 27020 PRIMARY 대기

python3 -m pytest -q                                 # 3023/1/4119(±S13 플레이크) — 셋 수가 기준
python3 -m pytest -q tests/test_account_purge.py tests/test_account_withdrawal_worker.py   # 43

# 변이 — 매번: 편집 → 초점 실행 → git checkout -- <path> → git status --short 무출력
# MU-20: account_withdrawal_worker.py run_loop 의 run_once(..., stop_check=…) 인자 삭제 → 43 passed(갭)
# MU-8 : deletion/account_purge.py run_once 의 "if stop_check is not None and stop_check(): break" 삭제 → 1 failed

git worktree add --detach /tmp/wt_c1cb282 c1cb282
python3 -m pytest -q tests/test_docs_indexes.py      # 305 (현행 307)
python3 -m pytest -q tests/test_repo_hygiene.py      # 606 (현행 608)
git worktree remove /tmp/wt_c1cb282

python3 -m pytest -q tests/test_final_save_analysis.py   # 단독 — S13 초록(플레이크 가르기)
```

환경 민감 항목: 전부 **알파·호스트**(test-mongo 27020 `rs-test` PRIMARY). 소요(1712초)는 머신-로컬 값 — 같은 날 같은 머신이 1618·1534·1712초를 냈다. **전수 1실패는 먼저 미수리 표의 알려진 플레이크(S13 포함)와 대조하고 단독 재실행으로 가른다.**

## 폐쇄 보고 (2026-09-10, 세션 54 — 검증자와 다른 세션)

**이 기록은 차단이 없었으므로 판정은 처음부터 `합격` 이고, 승격 문제도 없다.** 닫은 것은 **하드닝 둘**이다 — 이 기록 §Hardening 의 "산문 숫자 스윕"과, 이 기록이 사실 관계를 확증해 준 **H1'**(세션 52 기록의 부채). 커밋 `85259d6`(배선 셀)·`9e2e5cf`(문서 가드) · SoT **v1.8.53** · 상세는 [`daily_logs/2026-09-10/work_log.md`](../../daily_logs/2026-09-10/work_log.md) 세션 54.

| 항목 | 무엇을 했는가 | 변이 확인 |
|---|---|---|
| **H1'** 정지 배선 무셀 | 대역이 `last_stop_check` 를 받아 두고, 셀이 **정지를 세운 뒤 넘겨받은 호출자에게 물어본다**. 형제 워커 선례를 따르되 **동일성이 아니라 동작**으로 재는 것이 차이다 | **MU-20(인자 삭제) 1실패** — 두 세션이 초록으로 재현했던 자리 · **MU-20b(다른 플래그) 1실패** · **MU-20c(등가 람다 재배선) 초록** — 과잉 아님 실증 |
| **산문 숫자** ① 백분율 | 백분율 셀이 루트 README 만 보던 것을 **분포표가 사는 파일까지** subTest 둘로 | **MU-24(인덱스만 33%) · MU-24b(루트만 33%)** 각자 자기 subTest 실패 — 두 자리가 독립으로 잠긴다 |
| **산문 숫자** ② 절차 표 기준선 | README 절차 표 ②행을 **HANDOFF 회귀 기준선 줄을 정본으로** 잠금(SoT 버전 칸 선례와 같은 모양) | **MU-23(README 만 낡음) 1실패 · MU-23b(HANDOFF 만 움직임) 1실패** — 어느 쪽이 맞는가가 아니라 *같은 수를 말하는가* 를 잰다 |

**닫지 않은 것과 그 이유**:
- **S13 플레이크** — 이 기록이 트리거를 달아 유예했다(*"재발이 쌓이면 404/503 재분류 또는 프로브의 저장 백엔드 완전 주입을 재검토"*). 현 시점 근거는 2회 중 1회이고, 트리거 없이 지금 손대면 **원인 없이 기대값을 바꾸는 일**이 된다. 미수리 표의 등재를 그대로 둔다.
- **"14컨테이너" 표기** — 발행된 타 세션 기록이라 이 기록의 판단(정정하지 않는다)을 그대로 따른다.

**H1' 등급 질문이 소멸했다.** 세션 52 가 서피스하고 이 기록이 Outstanding 으로 넘긴 *"하드닝 유지 vs Slice 4 게이트"* 는 **셀이 들어오면서 물음 자체가 사라졌다** — 게이트로 올릴 대상이 없다. Slice 4 는 이제 조건 없이 열려 있다.
