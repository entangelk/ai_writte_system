# 독립 재검증 — Phase 8 Slice 8.2b 실수 중복 요청 DB 잠금 (B1·B2 폐쇄 확인)

- **날짜**: 2026-08-04
- **요청자**: 오너("작업 AI가 작업한 거 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude(본 세션, 구현에 관여하지 않음). 깊은 독립 감사는 구현에 관여하지 않은
  서브에이전트 둘(B1/B2/H1~H3 코드+뮤테이션+실 Mongo / 브리프 사실 전수)에게 맡기고, 본
  세션은 교차 문서 정합성·뮤테이션 원복 무결성·최종 의심을 직접 담당했다.
- **대상**: Slice 8.2b — `2969a09`(B1/B2/H1~H3 코드 보강) + `8d4575b`(SoT v1.7.87·§43E 정정).
  **검증 시점 HEAD `bfcfdbc`**. 현재 HEAD `0c6f57b`까지 잠금 코드·테스트는 한 줄도 바뀌지
  않았다(`git diff --stat bfcfdbc..0c6f57b -- services/application/app/quota/ tests/test_quota_lock*.py` 공백 확인).
- **정본 계약**: [`docs/plans/08-2b-duplicate-request-lock-decisions.md`](../../plans/08-2b-duplicate-request-lock-decisions.md)
  (G1=C·G2~G6=A) + [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.87** +
  [`docs/mongo_collections.md`](../../mongo_collections.md) §43E
- **선행 FAIL 기록**: [`2026-08-03/slice_8_2b_duplicate_request_lock.md`](../2026-08-03/slice_8_2b_duplicate_request_lock.md)
  (커밋 `c0e9ba9`, 불합격). 본 기록은 그 B1·B2가 폐쇄됐는지를 확인하고 판정을 뒤집는다.
- **머신**: 베타, 전용 test-mongo(rs-test, `127.0.0.1:27020`)를 검증 중에만 기동

## Scope

1. **B1(차단)** — `DuplicateKeyError` 뒤 읽기 경쟁: 충돌과 확인 읽기 사이에 release/TTL이 끼어
   ① 만료 잠금으로 거짓 차단, ② 저장 없는 성공(= 중복 실행)이 나는가. 4조건(만료 재차지 /
   소실 시 실제 차지 / `LockGranted(holder=X)`⇒DB 보유 / 유한 종료)이 닫혔는가.
2. **B2(차단)** — 예외 후 release/TTL 교차 및 "grant ⇒ DB holder" 회귀가 named test에
   연결됐는가. 종전 vanish 셀(저장 없는 성공을 정상으로 고정)이 교체됐는가.
3. **★ 뮤테이션** — 보강 코드를 수정 전으로 되돌렸을 때 신규 회귀가 **재실패**하는가(under-strict).
   정상 경로를 과잉으로 깨는 셀은 없는가(over-strict).
4. **H1~H3** — holder factory 기본 uuid4 소유 / env 검증(lease>120·window≥1, 생성자 인자는 자유) /
   실 Mongo 회귀(20-way 1승 + DB 승자 보유·TTL 인덱스·만료 재차지·fencing).
5. 계약 자기일관성 — 브리프·SoT v1.7.87·§43E·docstring·코드가 같은 계약을 말하는가.
6. 집중·전체 회귀 수치와 작업자 보고의 일치.

## Methodology

계약 범위를 G1~G6·§0.1~0.4로 한정해 경계 매트릭스를 세운 뒤, 작업자의 "74 cells(+13)·뮤테이션
재실패" 보고를 반증 대상 가설로 취급했다.

- 코드 추적: [`lock_mongo.py:69-94`](../../../services/application/app/quota/lock_mongo.py#L69)(`claim`
  유한 재시도)·[`lock.py:202-296`](../../../services/application/app/quota/lock.py#L202)(서비스·factory·env).
- **뮤테이션(under-strict)**: `git show 2969a09~1:…/lock_mongo.py > …/lock_mongo.py` 로 보강 전
  `claim()`으로 되돌리고(`CLAIM_ATTEMPTS=3` import shim만 추가, **재시도 루프는 복원하지 않음**)
  집중 회귀 실행 → 신규 셀이 재실패하는지 → `git checkout` 원복 → `git diff HEAD` 공백 단정.
  H1/H2 도 같은 방식(고정 토큰 factory / env 검증 제거).
- **실 Mongo(H3)**: `docker compose -f docker-compose.test.yml up -d`(rs-test `myState=1` 확인) 후
  `test_quota_lock_live_mongo.py` 실행 → `down` 으로 회수.
- 집중·전체 회귀: `PYTHONPATH=. python3 -m pytest -q … -p no:cacheprovider`.
- 교차 검증: `billable_actions.py`(9경로·extract replay 주석), 91초 출처(`docs/benchmarks/2026-07-15`,
  4096tok÷45tok/s), §43E↔코드, `analysis_compare` 선언 코드, 프론트 `describeWritingError`.

## Findings

### F1. B1 — 닫혀 있다. 네 조건 모두.

[`lock_mongo.py:69-94`](../../../services/application/app/quota/lock_mongo.py#L69)의 유한 재시도가 종전
`DuplicateKeyError` ⇒ `find_one` ⇒ 무조건 반환(`2969a09~1`)을 대체한다.

1. **충돌 → 만료 문서**: 재확인 읽기 `blocking is not None and _aware(blocking["expires_at"]) > now`
   ([`:88-90`](../../../services/application/app/quota/lock_mongo.py#L88))가 `False` → 루프 계속 → 다음
   `find_one_and_update({expires_at:{$lte:now}}, upsert=True)`([`:73-78`](../../../services/application/app/quota/lock_mongo.py#L73))가
   **실제 재차지**. 거짓 1초 차단 제거.
2. **충돌 → 문서 소실**: `blocking is None` → 루프 → upsert가 **실제 삽입**. 저장 없는 성공 날조 제거.
3. **`LockGranted(holder=X)`⇒DB 보유**: 서비스단 [`lock.py:248-256`](../../../services/application/app/quota/lock.py#L248)에서
   `current.holder == attempt.holder`일 때만 grant. `current`는 `find_one_and_update(AFTER)`가 돌려준
   실제 문서이고, 충돌 경로 재읽기는 **옛 holder**를 줘 `LockBlocked`가 된다. 소진 시 `raise
   conflict`([`:94`](../../../services/application/app/quota/lock_mongo.py#L94))라 위조 grant 없음. 실 Mongo에서
   [`test_quota_lock_live_mongo.py:131-133`](../../../tests/test_quota_lock_live_mongo.py#L131)이 단정.
4. **유한 종료**: `for _attempt in range(CLAIM_ATTEMPTS)`(`CLAIM_ATTEMPTS=3`, [``:43``](../../../services/application/app/quota/lock_mongo.py#L43)).
   매 시도가 충돌하고 매 읽기가 "없거나 만료"면 `raise conflict` — fail-closed.

**재시도 루프가 새로 만드는 race도 적대적으로 찾았다** — TOCTOU(자기수정적)·stale `now`(안전
방향으로만 편향)·동일 holder(재차지 순간 반환라 무해)·비-`DuplicateKeyError` 일시장애(전파→실패).
어느 쪽도 중복 허용으로 이어지지 않는다.

### F2. B2 — 닫혀 있다. 뮤테이션으로 양방향 확인.

신규 4셀([`test_quota_lock_mongo.py:215-273`](../../../tests/test_quota_lock_mongo.py#L215)):

| 셀 | 잠근 계약 |
|---|---|
| `test_a_lock_released_between_the_conflict_and_the_read_is_not_a_false_block` | B1 조건1 — 반환 holder **및** DB holder 단정 |
| `test_a_lock_removed_between_the_conflict_and_the_read_is_actually_stored` | B1 조건2+3 — 소실 시 실제 저장, 다음 요청 차단 |
| `test_every_granted_claim_is_persisted` | B1 조건3 — free-key/만료 재차지/force 세 정상 경로 |
| `test_a_conflict_that_never_resolves_fails_closed` | B1 조건4 — `find_one_and_update` 횟수 == `CLAIM_ATTEMPTS`, 경쟁자 무결 |

**under-strict(뮤테이션)**: `lock_mongo.py`를 보강 전으로 되돌리자 **정확히 B1 관련 3셀이 재실패**
(3 failed / 67 passed). `test_every_granted_claim_is_persisted`(정상 경로)는 녹색 유지 — 올바른
분담. `git checkout` 원복, `git diff HEAD` 공백 확인(본 세션이 직접).

### F3. H1~H3 — 모두 존재·정확.

- **H1**: [`lock.py:239`](../../../services/application/app/quota/lock.py#L239) `holder_factory or (lambda:
  uuid.uuid4().hex)`. 고정 토큰 factory 뮤테이션 → `test_the_default_factory_never_repeats_a_token`
  재실패(50 → 1로 붕괴).
- **H2**: `LONGEST_SYNCHRONOUS_SECONDS=120`([`:63`](../../../services/application/app/quota/lock.py#L63)) =
  `main.py:713 LLM_GATEWAY_TIMEOUT_SECONDS` 기본 120.0. `configured_lease_seconds` ≤120 거부,
  `configured_minimum_window_seconds` <1 거부. 생성자 kwargs는 자유(테스트용). 검증 제거 뮤테이션 →
  lease 셀 + window 셀(2 subtest) 재실패.
- **H3**: [`test_quota_lock_live_mongo.py`](../../../tests/test_quota_lock_live_mongo.py) 4셀, 실 Mongo.
  20-way `Barrier` 동시 차지 → **1 grant + `stored["holder"]==granted[0].holder`** 단정 통과. TTL
  인덱스(`{_id_, request_locks_ttl}`, expireAfterSeconds=0)·만료 재차지·fencing 실증.

### F4. 회귀 수치 — 보고와 일치.

- 집중: **70 passed / 6 subtests**(도메인+어댑터). 종전 FAIL 기록의 61에서 +9(보강 셀).
- 전체(test-mongo ON): **2062 passed / 1 skipped / 1725 subtests**. 종전 FAIL(`5db3aac`)
  2046/4/1723 대비 +13 신규 셀 + 3 skip 해소 = +16 passed로 정합. (858s — §"알려진 한계" 참조)

### F5. 계약 자기일관성 — 일치(한 줄 보강 후보).

SoT v1.7.87 changelog·`mongo_collections.md` §43E·`lock_mongo.py` docstring은 모두 "`_id` 충돌은
잠겨 있음의 **증거가 아니라 신호**다"로 일치한다. 다만 **브리프 본문 G3 행**([`08-2b…:257`](../../plans/08-2b-duplicate-request-lock-decisions.md#L257))이
아직 종전 문언("실패가 곧 '잠겨 있음'이라 분기가 명확")을 남기고 있다 — B1이 드러낸 오개념
그 자체다. SoT v1.7.87·§43E·브리프 상태줄(`:3`, "SoT v1.7.87 … 재검증 대기")이 정정하므로
정식 계약 모순은 아니다(저장소 우선순위: SoT가 구현 상태 정본, 브리프는 시점 결정 기록).
미래 독자가 브리프만 읽고 B1을 재도출할 수 있어 한 줄 각주를 권한다(비차단).

## Issues / Risks

### Blocking (계약 의무)

없다. B1·B2의 네 조건이 코드로 닫혔고, 뮤테이션(되돌려 재실패)과 실 Mongo 20-way가 이를
독립으로 확인했다.

### Hardening recommendations (비차단)

- **H-recheck-1 — 브리프 G3 행 문언 정정(한 줄 각주)**. [`08-2b…:257`](../../plans/08-2b-duplicate-request-lock-decisions.md#L257)의
  "충돌 = 잠김" 서술을 §43E를 가리키는 각주로 보강. SoT가 정본이라 당장은 무해하나, 브리프 단독
  독자를 위한 정돈.
- **H-recheck-2 — B1 교차 interleaving은 fake 주입셀로만 검증**. 실 Mongo 20-way는 충돌→재확인
  경로까지는 실증하지만, "충돌과 읽기 사이에 release/TTL이 끼는" 정확한 교차는 fake `find_one`
  seam 셀로만 잠갔다. fake의 `DuplicateKeyError`가 실 pymongo(E11000) 의미론과 같으므로 잔류
  위험은 낮다. 낮지만 "완벽 증명"이라고 못박지는 않는다.
- **H-recheck-3 — over-strict는 읽기 점검**. B2 셀의 over-strict를 뮤테이션이 아닌 inspection으로
  닫았다. 긍정 불변(grant⇒DB 보유)을 고정하는 형태라 의미 있는 over-strict 뮤테이션 구성이
  어려워 받아들였으나, 엄밀히는 inspection-only다.
- **H-recheck-4 — 전체 suite 118s→858s**. 모두 통과라 정확성엔 무관하나 WSL2 부하로 추정.
  동시성 테스트가 느린 머신에서 직렬화됐을 가능성은 있으나, 보장이 Mongo 문서수준 잠금에
  있으므로 원칙적 영향은 없다.

## Verdict

**합격(PASS).**

c0e9ba9 FAIL을 낸 B1·B2가 코드 수준에서 닫혔고, 양방향 회귀가 진짜로 살아 있다(보강을
되돌리면 B1 관련 3셀이 정확히 재실패). H1~H3는 존재·정확하며 뮤테이션/실 Mongo로 확인됐다.
전체 suite 녹색. Slice 8.2b는 완료로 볼 수 있고, 8.3 조립은 더 이상 8.2b 때문에 막혀 있지 않다.
차단 결함은 없다 — 위 Hardening 4건은 모두 비차단 정리/잔류 위험 기록이다.

## Outstanding items

- 본 검증은 코드·문서를 수정하지 않았다(인덱스·카운트 갱신은 이 기록 등재의 필수 동반
  작업으로, 가드가 요구하는 분). 뮤테이션 원복 후 `git diff HEAD` 공백·`docker ps` test-mongo
  없음을 본 세션이 직접 확인했다.
- 오너는 이미 [`15ef2a2`](../../../HANDOFF.md)에서 본 세션의 verbal 판정으로 8.2b 상태를 "재검증 PASS"로
  갱신하고 "조립 금지"를 풀었으되, **"PASS의 검증 기록은 아직 `docs/verifications/`에 없다"**고
  명시했다. 본 기록이 그 자리를 채운다.
- Slice 8.3은 이제 오너의 Q1~Q9 확정만 남은 상태로 `0a21eef`에서 "구현 대기"로 못박혀 있다.
- `15ef2a2`는 본 검증이 올린 브리프 지적(B-1 `analysis_compare` 400 누락·N-2 Q5 H3 전제 약화)도
  같이 반영했다 — 그것들은 8.3 브리프 정확도 정정이며 8.2b 잠금 계약과는 별개다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git rev-parse --short HEAD          # 0c6f57b (잠금 코드는 bfcfdbc과 동일)

# 집중 회귀
PYTHONPATH=. python3 -m pytest -q tests/test_quota_lock.py tests/test_quota_lock_mongo.py -p no:cacheprovider
# → 70 passed, 6 subtests

# B1/B2 under-strict 뮤테이션(핵심)
git show 2969a09~1:services/application/app/quota/lock_mongo.py > services/application/app/quota/lock_mongo.py
# (CLAIM_ATTEMPTS=3 import shim 추가 — 재시도 루프는 복원하지 않는다)
PYTHONPATH=. python3 -m pytest tests/test_quota_lock.py tests/test_quota_lock_mongo.py -p no:cacheprovider
# → 3 failed(B1 관련 셀), 67 passed, 6 subtests
git checkout services/application/app/quota/lock_mongo.py   # 원복
git diff HEAD -- services/application/app/quota/lock_mongo.py   # 공백이어야 한다

# H1/H2 뮤테이션(고정 토큰 factory / env 검증 제거) → 각 셀 재실패 후 git checkout lock.py

# H3 실 Mongo
docker compose -f docker-compose.test.yml up -d
PYTHONPATH=. python3 -m pytest -q tests/test_quota_lock_live_mongo.py -p no:cacheprovider -v
# → 4 passed (20-way 1승 + DB 승자 보유 · TTL 인덱스 · 만료 재차지 · fencing)
docker compose -f docker-compose.test.yml down

# 전체(test-mongo ON)
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider
# → 2062 passed, 1 skipped, 1725 subtests
```
