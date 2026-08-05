# Slice 8.2c 구현 — 파기가 프로젝트 이름 한 값을 남긴다 — 독립 검증

- **날짜**: 2026-08-05
- **의뢰자**: 오너("작업 AI가 작업한 거 확인 검증하고 의심하고 또 의심해줄래 … 8.2c 구현 완료, 커밋 4개(507be95 → d1f736c), 트리 clean")
- **검증자**: Claude Code (독립 세션 — 구현에 관여하지 않음)
- **검증 대상**: 구현 커밋 4개 `507be95..d1f736c`(feat 본체 + reconciler 셀 보강 + over-strict HTTP 보강 + 기록). HEAD `d1f736c`, 작업 트리 clean. 본 슬라이스의 **결정 브리프** 검증은 [`slice_8_2c_brief_and_phase9.md`](slice_8_2c_brief_and_phase9.md)(커밋 `c884151`)가 이미 닫았다 — 본 기록은 그 결정을 **코드로 옮긴 구현**만 다룬다.
- **정본 참조**: `docs/system-contract-sot.md` v1.7.90 · `docs/plans/08-2c-project-name-history-decisions.md`(N1~N6=A) · `docs/plans/08-2-usage-ledger-decisions.md` L6 · `docs/mongo_collections.md` §43B(예외 포인터)·§43F
- **작업 출처**: 커밋 `507be95` → `d1f736c`(committed; working tree 미사용). 실측 HEAD `d1f736c`.

---

## Scope

계약(N1~N6=A)을 코드·테스트·문서가 일관되게 이행했는지를 잡는다. 뮤테이션은 이 슬라이스의 핵심 방어(N1=A)에 대해 **두 방향**으로 직접 돌렸다.

1. **계약 자기일관 + 코드 부합** — SoT v1.7.90 · §43B 예외 포인터 · §43F 문서 예시 · 08-2 L6 해결 표기가 코드와 충돌 없이 들어갔는가.
2. **저장 계약(N1/N2)** — `_id`=project id, 필드 셋(`_id`·`name`·`purged_at`)만, `project_id` 불가, 최신 한 값.
3. **쓰기 위치·순서·실패 방향(N3)** — 감사 `requested` 행 뒤·파괴 앞·fail-closed. rename/생성 경로는 건드리지 않는다.
4. **회귀 가드 양 방향** — under-strict(쓰기 제거/지연/try-except)와 over-strict(rename에 쓰기)가 각각 셀에 매핑됐는가.
5. **뮤테이션 재현** — N1=A의 2중 방어(fake key-set 셀 + 실 Mongo reconciler 셀)와 over-strict HTTP 셀이 실제로 무는가.
6. **전체 suite** — 8.2c 변경에 다른 테스트가 부서지지 않았는가, 보고된 숫자가 재현되는가.
7. **실 Mongo 셀 실구동** — test-mongo가 살아 있어 reconciler 실 Mongo 셀이 skip 없이 도는가.

## Methodology

검증자는 구현에 관여하지 않았고, 작업자 주장을 1차 소스(코드·SoT·테스트·실 실행)에서 재도출했다. 트리는 검증 시작 시 clean이었으므로 뮤테이션 복원은 clean-tree 분기(`git checkout --`)를 썼고, 매 뮤테이션 전후로 `git status --short` 공백과 마커 grep으로 원복을 확인했다([`docs/guides/verification.md`](../../guides/verification.md) §"The restore rule").

```bash
git rev-parse HEAD                      # d1f736c
git status --short                      # (비어있음 — 뮤테이션 전후 매번)
git log --oneline 507be95^..d1f736c     # 4개 커밋
git diff --stat 507be95^..d1f736c       # 16 파일 +645/-12

# in-scope 3파일(실 Mongo 셀 skip 여부 관찰)
python3 -m pytest tests/test_project_name_history.py tests/test_purge_reconciler.py \
                  tests/test_auth_api.py -v
# → 117 passed, 781 subtests, **0 skip**(test-mongo 살아 있어 PurgeReconcilerTest 실구동)

# 전체 suite
python3 -m pytest tests/ -q
# → 2189 passed, 1 skipped, 1931 subtests, 0 failed (943.8s)

# 뮤테이션 #3(N1=A 핵심): _doc() 에 project_id 주입 → 두 방어 셀이 모두 재실패하는지
#   (Edit 로 project_name_history_mongo.py:_doc 에 "project_id": snapshot.project_id 추가)
python3 -m pytest \
  tests/test_project_name_history.py::MongoProjectNameHistoryRepositoryTest::test_the_document_key_set_is_fixed_and_has_no_project_id_field \
  tests/test_purge_reconciler.py::PurgeReconcilerTest::test_the_project_name_history_is_not_swept -v
# → 2 failed(양쪽 다 물림) → git checkout -- 로 원복 → status 비어있음 확인

# 뮤테이션 #4(over-strict): rename_project 핸들러에 record_purged 주입
#   (Edit 로 main.py:rename_project 에 project_name_history.record_purged(...) 추가)
python3 -m pytest \
  tests/test_auth_api.py::AdminProjectPurgeTest::test_a_live_project_has_no_history_row -v
# → 1 failed(HTTP over-strict 셀이 물림) → git checkout -- 로 원복 → status 비어있음 확인
```

## Findings

### 1. 계약 자기일관 + 코드 부합 — 일치

- **SoT v1.7.90**([`system-contract-sot.md:36`](../../system-contract-sot.md))이 N1~N6=A·쓰기 순서/실패 방향·TTL 없음·N4 조회 미개방·N5 UI 문구를 코드와 충돌 없이 기술. "reconciler가 수습한 경로는 이름을 못 남기며 그때 화면은 '삭제된 프로젝트' 폴백"이라고 **한계를 정직하게 명시** — 이것이 아래 Hardening-2의 소스.
- **§43B 예외 포인터**([`mongo_collections.md:2487-2494`](../../mongo_collections.md)): "이 컬렉션은 이름을 안 저장한다"는 여전히 참이되, purge 전체로는 이름이 §43F로 나간다고 포인트. 다음 검증자가 같은 §43B 문장을 근거로 이 구현을 결함으로 판정하는 함정을 닫는다.
- **§43F 문서 예시**([`mongo_collections.md:2849-2855`](../../mongo_collections.md))가 코드 `_doc()`와 **정확히 같은 3키**(`_id`·`name`·`purged_at`). L6 선택지 A 행의 `created_at`은 결정 전 재료라 08-2:254-256 각주가 N3=A로 정밀화(덮어쓰기)했고 §43F가 그 최종 형태 — 모순 아님.
- **08-2 L6**([`08-2-usage-ledger-decisions.md:3,251-256`](../../plans/08-2-usage-ledger-decisions.md))이 "8.2c에서 Resolved(N1~N6=A, SoT v1.7.90)"로 표기.

### 2. 저장 계약(N1/N2) — 정확

- [`project_name_history_mongo.py:44-51`](../../services/application/app/deletion/project_name_history_mongo.py) `_doc()`가 **정확히 3키**. `replace_one(..., upsert=True)`(`:34-37`)로 project 당 1행 보장. `_aware()`(`:19-23`)가 pymongo naive-BSON 함정을 경계에서 UTC 재부착 — HANDOFF가 반복해 밟은 함정을 선제 처리.
- [`project_name_history.py:30-77`](../../services/application/app/deletion/project_name_history.py) `ProjectNameSnapshot`(frozen/slots) + 서비스. 이름은 정규화·거부 없이 **있는 그대로** 스냅샷("이름은 사용자 텍스트지 검증 대상이 아니다").

### 3. 쓰기 위치·순서·실패 방향(N3) — 계약 일치

[`main.py:3544-3637`](../../services/application/app/main.py) purge 핸들러에서 쓰기 위치가 세 성질을 동시에 만족한다:

- `:3579` 감사 `record_purge_requested` → `:3596-3598` `project_name_history.record_purged(project_id=, name=project.name)`(try 블록 첫 줄, `name=project.name`는 `:3569` get_project 스냅에서 읽은 **파괴 전 이름**) → `:3599` `core_sot.purge_project`(파괴).
- **fail-closed**: 이름 쓰기 예외가 `:3612 except Exception`로 전파 → failed 감사 outcome(`:3614-3623`) + `:3630 raise`(전역 handler → 503). try/except로 "안정화"하면 이 전파가 막혀 조용히 진행 — 뮤테이션 #4와 함께 이 방향을 `test_a_failed_name_snapshot_stops_the_purge_before_it_destroys_anything`가 잠근다.
- rename 핸들러 `:3440-3454`는 `core_sot.rename_project`만 부르고 **`record_purged`를 부르지 않는다**(grep 상 `record_purged`는 `:3596` 유일). N3=A(파기 시점에만) 부합.

### 4. 회귀 가드 양 방향 — 매핑 확인

- **under-strict / 순서**: [`test_auth_api.py:837-877`](../../tests/test_auth_api.py) `FailingRepository.put`가 raise → 503 + `list_projects()==[id]`(파기 미시작) + `memory_spy.purged==[]`. docstring(`:846-848`)이 "쓰기를 파괴 뒤로 옮기면 `list_projects()` 단정이 무너진다"를 못박아 순서 뮤테이션도 같은 셀이 잠근다.
- **over-strict(rename)**: [`test_auth_api.py:879-898`](../../tests/test_auth_api.py) `POST /projects` → `PATCH`(rename) → `DELETE`(archive)를 **HTTP로** 돌리고 `count()==0` 단정. 서비스 직접 호출이 아니라 HTTP라 endpoint 과잉 구현을 잡는다(작업자 보고: 첫 판엔 서비스 호출이라 통과 → HTTP로 고침).
- **저장 계약(N1)**: fake 셀 [`test_project_name_history.py:85-104`](../../tests/test_project_name_history.py)(`set(doc)=={_id,name,purged_at}` + `project_id not in doc`)과 실 Mongo reconciler 셀 [`test_purge_reconciler.py:140-174`](../../tests/test_purge_reconciler.py)가 **독립된 두 층**으로 같은 결함을 잠근다.

### 5. 뮤테이션 재현 — 두 방향 모두 물림(직접 실측)

- **#3 `_doc()`에 `project_id` 주입** → fake key-set 셀 **FAILED**(`set`이 4키) **및** 실 Mongo reconciler 셀 **FAILED**(`project_name_history`가 sweep 대상으로 발견). N1=A의 2중 방어가 실재하고 서로 독립적임을 확인. `git checkout --` 원복 후 status 비어있음·마커 grep 공백 확인.
- **#4 rename 핸들러에 `record_purged` 주입** → HTTP over-strict 셀 **FAILED**(`ProjectNameSnapshot(name='바뀐 이름') is not None`). 작업자가 "첫 판 통과 → HTTP로 고침"이라 고백한 셀의 고침이 **지금 실제로 물리는 것**을 확인. 마찬가지로 원복·clean 확인.
- (뮤테이션 #1 순서·#2 try/except·#5 UI 문구는 #1/#2를 잠그는 `test_a_failed_name_snapshot`의 단정과 docstring을 정독해 추적했고, #5는 UI 문구 되돌림 시 프론트 purge 셀의 단정이 깨지는 구조라 직관적이라 별도 실측은 생략. 핵심인 #3·#4는 직접 돌렸다.)

### 6. 전체 suite — 재현, 0 실패

- **2189 passed / 1 skipped / 1931 subtests / 0 failed**(943.8s). 작업자 보고 숫자와 **정확히 일치**.
- 작업자는 "2189가 마지막 두 보강 커밋 전에 잰 값, 백그라운드 재실행 중"이라고 했으나, 본 독립 실행(보강 커밋 2개 포함 전부)이 같은 **2189/1**을 확인 → 두 보강 커밋은 기존 셀을 제자리 수정해 **순 셀 수를 바꾸지 않았음**. 기록 정정 불필요.
- skip 1은 8.2c 무관(8.2c in-scope 3파일은 **0 skip**). 환경 의존 lexical 셀로 추정되며 본 검증 대상 아님.

### 7. 실 Mongo 셀 실구동 — 확인

`docker ps`: `ai_writte_system-test-mongo-1` Up(healthy, `127.0.0.1:27020`). 이 덕에 `PurgeReconcilerTest`·`PurgeReconcilerCommandTest` 계열이 skip 없이 실 Mongo 위에서 돌았다(in-scope 실행 0 skip로 확인). 가짜 collection으로는 `list_collection_names`·`find_one` 판정을 재현할 수 없어, 이 셀들이 **실제로 돌았다**는 것이 N1=A 방어의 실효성 조건이다.

## Issues / Risks

### Blocking — 없음

계약 요구 분기(N1~N6, 쓰기 순서/실패 방향, over-strict rename 금지, reconciler 비발견)가 전부 명명된 회귀 셀에 매핑되고, 핵심 두 셀은 뮤테이션으로 물리는 것을 직접 확인했다. 경계 행렬에 빈 칸 없음.

### Hardening recommendations (비차단)

- **NIT-1 — 브리프 상태 헤더 낡음.** [`08-2c-project-name-history-decisions.md:3`](../../plans/08-2c-project-name-history-decisions.md)이 "상태: … 구현 대기"로 남아 있다. 구현 완료 후 "구현 완료(SoT v1.7.90)"로 고치는 것이 일관적(08-2:3은 이미 "8.2c에서 Resolved"로 맞춤). 다음 독자가 "결정만 나고 구현이 안 됐나?" 오독할 수 있다.
- **HARDEN-1 — 생산 Mongo 배선의 종단 셀 부재.** `test_auth_api`의 purge 셀은 InMemory 저장소로 돌고, reconciler 셀은 어댑터를 직접 부른다. "endpoint → `_default_project_name_history_service()`(Mongo) → persist → 생존" 한 묶음 경로를 실 Mongo로 관통하는 셀은 없다. 계약 표면은 단위·어댑터·HTTP 셀로 덮였으므로 스펙 요구는 아니지만, 생산 배선의 오타(예: `db_name` 누락)를 잡을 셀로 가치가 있다.
- **HARDEN-2 — derived-실패-후-core_sot-파괴 시 이름 생존은 순서로만 보장.** 이름 쓰기가 파괴 **앞**이라 core_sot 파괴 뒤 derived 단계가 실패해도 이름은 이미 영속화돼 있다. 이 부분 경로는 `test_the_project_name_survives...`(happy path)와 `test_a_failed_name_snapshot`(이름 쓰기 자체 실패) 사이의 빈 칸으로, 직접 단정하는 셀이 없다. 단 SoT v1.7.90이 이 한계를 정직하게 명시(reconciler 수습 경로는 이름 미저장 → "삭제된 프로젝트" 폴백)하므로 **문서화된 수용 한계**이지 숨겨진 빈 칸은 아니다. 전자(이미 쓴 이름이 derived 실패에도 생존)를 한 셀로 못박으면 순서 불변식이 표면에 든다.

## Verdict — **합격(PASS)**

- 계약(N1~N6=A)이 코드·테스트·정본에 충돌 없이 반영됐고, 정본은 스스로 일관된다.
- N1=A의 2중 방어(fake key-set + 실 Mongo reconciler)가 뮤테이션 #3으로 **양쪽 다 물리는 것**을 직접 확인했고, over-strict rename 가드가 뮤테이션 #4로 **현재 물리는 것**을 확인했다.
- 전체 suite 2189/1/1931, **0 실패**로 재현. 실 Mongo 셀이 skip 없이 실구동.
- 비차단 3건(NIT-1, HARDEN-1/2)은 스펙 요구를 넘는 보강 후보라 판정을 바꾸지 않는다([`docs/guides/verification.md`](../../guides/verification.md) §"boundary matrix has no empty cells").

## Outstanding items (결함 아님)

- **test-mongo 가동 상태로 둠**(본 머신, 지금). 다음 독립 검증·실 Mongo 셀이 쓴다. 불필요 시 `docker compose -f docker-compose.test.yml down`.
- **뮤테이션 복원 상태**: 검증 종료 시 `git status --short` 공백, HEAD `d1f736c` 유지. 작업자 트리에 잔류 없음.
- 다음은 작업자 handoff에 따라 **main.py 라우터 정리**(별건).

## Reproduction

```bash
git -C /mnt/d/devel/에베베/ai_writte_system rev-parse HEAD   # d1f736c
git -C /mnt/d/devel/에베베/ai_writte_system status --short   # (비어있어야)
docker ps --format '{{.Names}}\t{{.Ports}}' | grep test-mongo # Up, 27020

python3 -m pytest tests/test_project_name_history.py \
                  tests/test_purge_reconciler.py tests/test_auth_api.py -v   # 117 passed, 0 skip
python3 -m pytest tests/ -q                                                   # 2189/1/1931, 0 fail

# 뮤테이션 #3: project_name_history_mongo.py 의 _doc() 에 "project_id": snapshot.project_id 행 추가 후
python3 -m pytest \
  tests/test_project_name_history.py::MongoProjectNameHistoryRepositoryTest::test_the_document_key_set_is_fixed_and_has_no_project_id_field \
  tests/test_purge_reconciler.py::PurgeReconcilerTest::test_the_project_name_history_is_not_swept
# → 2 failed  →  git checkout -- services/application/app/deletion/project_name_history_mongo.py

# 뮤테이션 #4: main.py rename_project() 에 project_name_history.record_purged(...) 추가 후
python3 -m pytest tests/test_auth_api.py::AdminProjectPurgeTest::test_a_live_project_has_no_history_row
# → 1 failed  →  git checkout -- services/application/app/main.py
```
