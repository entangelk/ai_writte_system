# 독립 검증 — Phase 8 Slice 8.2b 실수 중복 요청 DB 잠금

- **날짜**: 2026-08-03
- **요청자**: 오너("작업 AI가 작업한 거 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Codex(본 세션, 구현에 관여하지 않음)
- **대상**: Slice 8.2b — `request_locks` 도메인·in-memory 저장소·Mongo 어댑터와 계약 회귀 61 cells
- **정본 계약**: [`docs/plans/08-2b-duplicate-request-lock-decisions.md`](../../plans/08-2b-duplicate-request-lock-decisions.md)(G1=C·G2~G6=A) + [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.86** + [`docs/mongo_collections.md`](../../mongo_collections.md) §43E
- **검증 대상 소스**: 커밋 `d4336f7`(구현)·`5db3aac`(문서), HEAD `5db3aac`, 시작 작업 트리 clean
- **머신**: 베타, 전용 test-mongo(rs-test, `127.0.0.1:27020`)를 검증 중에만 기동

## Scope

1. G1~G5 저장 의미론 — 진행 중/냉각 두 구간, 차지 시각 기준 최소 창, 만료 재차지, 실패 이유와 남은 시간.
2. G2 키·저장 모양 — `(user_id, action, target_project_id)`, `project_id` 필드 부재, TTL 외 추가 인덱스 부재.
3. **가장 의심한 축 — G3 원자성**: `find_one_and_update` 충돌과 release/TTL이 교차해도 성공한 요청만 DB 잠금을 소유하는가.
4. G4 fencing — force claim 뒤 옛 holder의 release가 새 잠금을 건드리지 않는가.
5. 테스트 자체의 회귀력 — 각 계약 분기가 named test에 연결되고 under/over-strict 양쪽을 실제로 잠그는가.
6. 실제 Mongo 기본 경쟁·인덱스, 집중 61 cells, test-mongo ON 전체 backend 회귀.
7. 문서 자기일관성 — 브리프, SoT v1.7.86, §43E, 구현 docstring/HANDOFF가 같은 계약을 말하는가.

## Methodology

계약 범위를 먼저 G1~G5와 §0.1~0.4, 구현 체크리스트로 한정해 경계 매트릭스를 만들고, 코드와 테스트를 각각 감사했다. 작업자의 61-cell green과 뮤테이션 보고는 증거가 아니라 반증 대상 가설로 취급했다.

- 범위·diff: `git diff 6a557e6..5db3aac --check`, `git show --stat d4336f7`, `git show --stat 5db3aac`.
- 집중 회귀: `python3 -m pytest -q tests/test_quota_lock.py tests/test_quota_lock_mongo.py -p no:cacheprovider`.
- 전체 회귀: test-mongo 기동 후 `python3 -m pytest -q -p no:cacheprovider`.
- 실제 Mongo: 20개 thread를 `Barrier`로 동시에 풀어 같은 키를 claim하고 grant/block 수 및 `index_information()`을 재계산.
- 적대적 경쟁 재현: 테스트 fake의 `DuplicateKeyError` 뒤 `find_one` seam에 (a) 기존 요청 release, (b) release 뒤 TTL 삭제를 주입하고 연속 claim 결과와 DB 문서 존재를 직접 단정.
- 패턴 스윕·문맥: `rg -n "except DuplicateKeyError|find_one_and_update\\(" services/application/app`, `git blame -L 57,70 d4336f7 -- services/application/app/quota/lock_mongo.py`.

## Findings

### F1. 계약 매트릭스 — 대부분은 잘 잠겼지만 G3의 예외 후 경계가 비어 있다

| 계약 분기 | 기대 | 기존 회귀 | 관찰 |
|---|---|---|---|
| 같은 삼중 키의 살아 있는 잠금 | 차단 | `ExclusionTest.test_only_one_of_two_requests_at_the_same_instant_wins` | 통과. 다만 실제 호출은 순차 in-memory다([`test_quota_lock.py:84`](../../../tests/test_quota_lock.py#L84)). |
| 만료 문서가 물리적으로 남음 | 재차지 | `test_an_expired_lock_is_reclaimed_even_though_the_document_is_still_there` | 통과([`:102`](../../../tests/test_quota_lock.py#L102)); TTL 존재 판정을 막는다. |
| 진행 중 / 냉각 / 경계 직전·정각 | 차단 / 차단 / 통과 | `WindowTest` 5 cells | 전부 통과([`:124-167`](../../../tests/test_quota_lock.py#L124)). |
| user/action/project 축 격리 | 다른 축 통과 | `KeyAxisTest` 5 cells | 전부 통과([`:214-237`](../../../tests/test_quota_lock.py#L214)). |
| force claim 뒤 세 번째 클릭 | 다시 차단 | `ForceClaimTest` | 통과([`:240-267`](../../../tests/test_quota_lock.py#L240)). |
| 옛 holder release / 현 holder release | no-op / 정상 해제 | `FencingTest` | 전부 통과([`:269-307`](../../../tests/test_quota_lock.py#L269)). |
| 실패 이유·올림·하한 1초 | `in_flight` + 양의 남은 초 | `BlockedReasonTest` | 전부 통과([`:170-211`](../../../tests/test_quota_lock.py#L170)). |
| **upsert 충돌 뒤 잠금이 release/TTL과 교차** | **만료면 다시 차지하고, grant면 DB에 자기 holder가 있어야 함** | **없음** | **두 방향 모두 계약 위반 재현(B1)**. |

문서끼리의 literal 충돌은 찾지 못했다. 브리프 §0.1의 세 연산, G1~G5, SoT v1.7.86, §43E와 구현의 정상 경로 의미론은 일치한다.

### F2. Blocking B1 — `DuplicateKeyError` 뒤 읽기 경쟁으로 거짓 차단 또는 저장 없는 성공이 난다

Mongo 어댑터는 최초 `find_one_and_update`가 `_id` 충돌을 내면 [`lock_mongo.py:66-70`](../../../services/application/app/quota/lock_mongo.py#L66)에서 `find_one`을 한 뒤:

- 문서가 있으면 만료 여부를 다시 보지 않고 그 문서를 반환한다.
- 문서가 없으면 **차지 연산을 다시 하지 않고** 호출자가 만든 `lock`을 반환한다.

이 보조 읽기 사이에 기존 요청이 정상 release할 수 있다. release는 오래 실행된 요청이면 `expires_at=now`로 당긴다([`lock_mongo.py:75-92`](../../../services/application/app/quota/lock_mongo.py#L75)). 재현 결과:

```text
release-race: LockGranted LockBlocked 1 stored_expires_at<=now True
```

즉 `expires_at <= now`라 잠기지 않았는데도 두 번째 요청을 막는다. 이는 브리프 §0.1/§43E의 **"`expires_at > now`가 판정의 유일한 축"**과 직접 충돌한다.

그 release 직후 TTL monitor가 문서를 지우면 더 심각하다. 현재 코드는 `None`을 보고 새 잠금을 실제 쓰지 않은 채 grant한다. 이어진 요청은 빈 키를 삽입해 또 grant된다:

```text
vanish-race: LockGranted persisted_after_second False LockGranted holders h2 h3
```

서로 다른 holder `h2`와 `h3`가 연속으로 둘 다 통과한다. 이것은 G3의 목적("동시 두 요청 중 하나만 차지") 자체를 깨며 과금 중복을 다시 연다. [`test_quota_lock_mongo.py:199-205`](../../../tests/test_quota_lock_mongo.py#L199)는 이 분기를 grant로 기대하지만, **grant 뒤 DB가 `h2`를 보유하는지 단정하지 않아 결함을 정상 동작으로 고정한다.**

해소 조건은 구현 방식을 미리 지정하지 않는다. 다만 다음 회귀가 먼저 필요하다.

1. 충돌 뒤 읽은 문서가 이미 `expires_at <= now`이면 재시도해 실제 차지를 얻거나 새 owner에게 져야 하며, 거짓 1초 차단이면 안 된다.
2. 충돌 뒤 문서가 사라지면 성공을 날조하지 말고 실제 원자적 차지를 다시 수행해야 한다.
3. 모든 `LockGranted(holder=X)` 뒤 저장소의 같은 키가 `holder=X`인 것을 단정해야 한다.
4. 위 재시도도 무한 spin이 되지 않는 종료 정책을 함께 잠가야 한다.

### F3. 정상 Mongo 기본 경쟁과 인덱스는 계약대로다

실제 Mongo에서 `Barrier(20)`으로 같은 키에 20 claim을 동시에 보냈다. 결과는 **1 granted / 19 blocked**였고, 인덱스는 Mongo 기본 `_id_`와 `request_locks_ttl(expireAfterSeconds=0)`뿐이었다. 기본 경쟁에서 [`lock_mongo.py:57-65`](../../../services/application/app/quota/lock_mongo.py#L57)의 단일 연산은 의도대로 작동한다.

이 실측은 B1을 상쇄하지 않는다. B1은 최초 충돌과 후속 read 사이에 release/TTL이 끼는 별도 interleaving이며, 기존 fake와 실제 Mongo 기본 경쟁 모두 그 seam을 강제하지 않는다.

### F4. 나머지 구현 결과 주장은 재현됐다

- 집중 회귀: **61 passed / 4 subtests**. 작업자 보고의 도메인 40 + 어댑터 21과 합계가 일치한다.
- 전체 backend(test-mongo ON): **2046 passed / 4 skipped / 1723 subtests**, 3 warnings, 118.13초. 보고와 정확히 일치한다.
- `git diff 6a557e6..5db3aac --check`: clean.
- 저장 문서 다섯 필드, `released_at` 재차지 초기화, 남은 시간 올림+하한 1, holder release 필터, TTL 옵션은 코드·테스트에서 확인됐다.

Green suite와 보고 수치는 참이다. 다만 테스트가 B1 interleaving을 포함하지 않아 **회귀 0건이라는 사실과 잠금 계약 충족은 동치가 아니다.**

## Issues / Risks

### Blocking (계약 의무)

- **B1 — 충돌 후 race에서 배타성/판정 계약 위반.** [`lock_mongo.py:66-70`](../../../services/application/app/quota/lock_mongo.py#L66)의 보조 read가 만료 문서를 차단으로 반환하고, 사라진 문서를 실제 차지 없이 성공으로 반환한다. 후자는 서로 다른 두 요청을 모두 grant한다. G3와 §43E의 load-bearing 의무 위반이므로 8.3 조립 전에 구현과 양방향 회귀가 닫혀야 한다.
- **B2 — 경계 매트릭스 빈 셀.** 구현 체크리스트의 "동시 두 요청 중 하나만 차지"는 순차 in-memory 셀과 단일 호출 shape 셀로만 연결돼 있다. 예외 후 release/TTL 교차 및 "grant ⇒ DB holder 소유" 회귀가 없고, 기존 vanish 셀은 반대로 저장 없는 grant를 승인한다. B1 수정과 함께 폐쇄해야 한다.

### Hardening recommendations (비차단)

- **H1 — holder factory의 fresh-token 전제를 API에 명시하거나 기본 UUID 생산을 소유할 것.** 브리프는 매 차지/강제 재차지가 "새 토큰"이라고 요구하지만([`08-2b…:50-55`](../../plans/08-2b-duplicate-request-lock-decisions.md#L50)), 서비스는 외부 `holder_factory`를 그대로 신뢰한다([`lock.py:180-205`](../../../services/application/app/quota/lock.py#L180)). 같은 토큰을 돌려주는 factory면 옛 요청이 새 잠금을 release해 fencing이 무너진다. 8.3 배선 전 production factory와 회귀를 명시적으로 잠그는 것이 안전하다.
- **H2 — env 값의 유효 범위를 명문화할 것.** 생성자는 `lease <= window`만 거부한다([`lock.py:189-202`](../../../services/application/app/quota/lock.py#L189)). 따라서 음수 window 또는 `6초 lease`도 구성 가능하지만 정본은 lease가 gateway timeout 120초보다 길어야 한다고 설명한다. 현재 확정 기본값 5/180은 올바르므로 비차단이나, env 오설정이 핵심 보호를 조용히 끌 수 있다.
- **H3 — 실제 Mongo 회귀를 추가할 것.** 본 검증의 20-way smoke는 기본 원자성을 확인했지만 저장소에는 fake 테스트만 남는다. 이 기능은 이름 그대로 DB 잠금이므로 실제 Mongo의 동시 claim 1승/나머지 차단과 TTL 인덱스를 지속 검증하면 driver/server 의미론 드리프트를 잡을 수 있다.

## Verdict

**불합격(FAIL).**

정상 경로 구현과 61-cell/전체 suite는 대체로 치밀하지만, 가장 중요한 G3 배타성이 `DuplicateKeyError` 뒤 release/TTL 교차에서 깨진다. 특히 문서 소실 분기는 잠금을 저장하지 않은 grant 뒤 다음 요청도 grant해 실수 중복 과금을 다시 허용한다. B1/B2를 회귀 우선으로 닫고 독립 재검증하기 전에는 Slice 8.2b를 완료로 보거나 8.3에 조립하면 안 된다.

## Outstanding items

- 다음 작업은 **B1/B2 closure → 8.2b 독립 재검증**이다. 8.3 시행은 그 뒤다.
- 구현 커밋 `d4336f7`·문서 커밋 `5db3aac`는 push되지 않았다.
- 본 검증은 구현을 수정하지 않았다. 검증 기록·인덱스·HANDOFF의 즉시 작업 순서만 갱신한다.
- test-mongo는 검증 종료 후 다시 내린다. worker·generation_worker의 기존 재시작 루프는 본 검증 범위 밖이며 건드리지 않는다.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system
docker compose -f docker-compose.test.yml up -d

# 집중 및 전체 회귀
python3 -m pytest -q tests/test_quota_lock.py tests/test_quota_lock_mongo.py -p no:cacheprovider
python3 -m pytest -q -p no:cacheprovider

# 결함 위치·기존 잘못된 기대
nl -ba services/application/app/quota/lock_mongo.py | sed -n '57,70p'
nl -ba tests/test_quota_lock_mongo.py | sed -n '180,206p'

# 적대적 재현 절차
# 1) live lock을 만든다.
# 2) 다음 claim의 find_one_and_update가 DuplicateKeyError를 낸 직후,
#    fake find_one seam에서 기존 문서를 expires_at=now/released_at=now로 바꾼다.
#    결과가 LockBlocked(1)임을 확인한다(만료인데 거짓 차단).
# 3) 같은 seam에서 기존 문서를 삭제하고 None을 반환한다.
#    두 번째 claim이 LockGranted지만 DB 문서가 없고, 세 번째 claim도 다른 holder로
#    LockGranted임을 확인한다.
# 이 검증 기록의 F2 출력:
# release-race: LockGranted LockBlocked 1 stored_expires_at<=now True
# vanish-race: LockGranted persisted_after_second False LockGranted holders h2 h3

docker compose -f docker-compose.test.yml down
```
