# 검증 기록 — 인증 D8-2 (Project.owner_id) 슬라이스 2a·2b 2026-07-27

## Subject metadata
- **날짜**: 2026-07-27
- **요청자**: 오너 ("다음작업 검증해줘. D8-2를 두 개의 작은 슬라이스로 ... 7ffd615(2a), b7a1873(2b)")
- **검증자**: Claude(독립 검증, max effort) — 직접 실측(전체 스위트 재실행·mutation·코드 정주행)
- **대상 작업**: D8-2를 2a(필드+저장, `7ffd615`)·2b(세션에서 owner 채우기, `b7a1873`)로 분할. 사이에 `c982ecd`(직전 검증 조건 B-1 해소)가 선행 — 본 검증에서 함께 확인.
- **정본 계약 참조**: `docs/plans/multi-user-auth-cms-decisions.md` — D3=A(`Project.owner_id` 격리) · D4(마이그레이션 불요, 개발 데이터 폐기 허용) · **D8 step2("owner_id + 마이그레이션 — 필드만, 검사는 아직 없음")** · D8 step1 비-목표 연속("표면 무변", 인가는 D8-3).
- **작업 출처**: 커밋 `7ffd615`, `b7a1873`(HEAD 전), 보조 `c982ecd`. 본 검증은 커밋된 코드 기준.

## Scope
boundary matrix를 D8 step2("필드만, 검사 없음") + 비-목표("표면 무변, 인가 없음")에서 세웠다. 점검 표면: `models.py`(Project) · `mongo_repository.py`(`_project_doc`/`_to_project`) · `service.py`(`create_project`) · `main.py`(POST /projects) · `test_core_sot_mongo.py`(2a, `_MongoContractMixin`) · `test_auth_api.py`(2b, `ProjectOwnershipRecordingTest`) · 공개 API 무변(ProjectPayload·schema.d.ts) · `c982ecd`(직전 조건 해소) · HANDOFF 인계 메모.

## Methodology
독립 재도출. (1) 커밋 diff 전수 정독 (2) `_current_user`·`_project_payload`·ProjectPayload 정의 직접 확인 (3) `_MongoContractMixin` 서브클래스 수로 +9 분해 검증 (4) **mutation**: main.py owner 배선을 `None` 상시로 되돌려 2b 회귀 실행 → 1건 실패 확인 → `cp` 복원 (5) 전체 스위트 재실행(test-mongo, 520s) (6) 병렬 디코더 부재 sweep(`Project(` 생성처·디코더 전수) (7) `test_no_non_auth_operation_is_protected_yet`(c982ecd)가 D8-3에서 자가-역전하는지 논리 검증.

## Findings

### 1. 기준선 — 실측 정확 일치
- 백엔드 전체: **1627 passed / 1 skipped / 623 subtests**(520.77s). skip 1 = live Chroma(상시). 직전 1614(post-c982ecd) 대비 **+13**, 분해 = 2a 신규 3건 × `_MongoContractMixin` 서브클래스 **3개**(Fallback·Transaction·WritingIntent) = 9 + 2b 4 = 13. **정확 일치, 설명되지 않는 증감 0.**

### 2. 2a — 필드 + 저장 (`7ffd615`)
- `models.py:31` `owner_id: str | None = None`. nullable이 의도(D8 step2 "검사 없음", D3=A 비고). ✓
- `mongo_repository.py`: `_project_doc`가 owner_id 쓰기, `_to_project`는 `.get("owner_id")`로 읽기 — **legacy 문서(키 부재)가 KeyError가 아니라 None**이 되도록. ✓ 배포 DB 현상과 정합.
- `service.py:351` `create_project(*, name, owner_id=None)` — optional이라 worker·script·테스트 기존 호출자 무변. ✓
- 회귀 3건(`_MongoContractMixin`): 소유자 왕복(get·list **두 디코더**) · 미지정 시 None 유지(over-strict — 자리표시자 owner가 D8-3에서 실제 user id로 오인되는 것 방지) · **owner_id 키가 아예 없는 legacy 문서 → unowned**(실제 심어 확인).
- **병렬 디코더 sweep(직접)**: services/에서 `Project(` 생성처는 정확히 2곳(`mongo_repository.py:531` `_to_project`, `service.py:354` `create_project`)만이며 둘 다 owner_id 처리. owner_id를 조용히 떨구는 평행 디코더 **부재** → 2a 저장 왕복 보장이 우회경로로 무력화되지 않음. ✓

### 3. 2b — 세션에서 owner 채우기 (`b7a1873`)
- `main.py:2266-2273` POST /projects: `http_request: Request` 추가 → `_current_user(http_request)` → `owner_id=current.id if current is not None else None`. ✓
- **핵심 "401 아님" 검증(직접)**: `_current_user`(main.py:2080-2095)은 세션/사용자가 없으면 **None을 반환(raise 아님)**. 따라서 미인증 생성은 `owner_id=None`로 200. "여기서 401로 만들면 시행 슬라이스가 된다"는 주장이 코드와 일치. ✓
- 회귀 4건(`ProjectOwnershipRecordingTest`, in-memory): 로그인 후 생성 → owner 기록 · **익명 생성 → 200 + unowned**(over-strict 슬라이스 경계) · **owner_id 공개 payload 미노출**(`set(response.json()) == {"id","name","archived"}`) · 로그아웃 후 생성 → unowned(살아 있는 세션에서만).
- **mutation(직접)**: owner 배선을 `owner_id=None` 상시로 되돌리면 → **1 failed, 3 passed**. 실패 = `test_logged_in_create_records_the_creator_as_owner`(`None != user:350c…`). 작업자 주장("해당 회귀 1건 정확히 실패")과 일치. 복원 확인.

### 4. 공개 API 무변 (직접)
- `ProjectPayload`(main.py:1295-1298) = `id/name/archived`만, owner_id 없음. `_project_payload`(2128)도 동일. ✓
- `schema.d.ts`에 `owner_id` **0회**(grep). gen:api no-diff 주장과 일치. 노출은 공개 계약 변경이라 2c(선택)로 연기 — `test_owner_is_not_exposed_on_the_public_payload_yet`가 그 결정을 잠근다(누락 아님).

### 5. c982ecd — 직전 검증 조건 해소 (루프 클로즈)
직전 검증(`auth_d8_slice1.md`, 조건부 합격)의 조건 3을 전부 닫았다:
- **B-1(차단→해소)**: `EnumerationHardeningTest` 3건이 `users.py:101` timing 열거 방지를 잠근다. `_FakeHasher`가 `verify_calls`를 기록하게 해 "오답·미존재·비활성의 verify 횟수 동일"을 단언 — `assertIsNone` 계열로는 원리적으로 안 잡히던 성질을 "verify 수행 여부"로 잠근 설계가 정확. 프로덕션 코드 무변(이미 있던 동작 잠금). ✓
- **H-1(해소)**: `DefaultTokenEntropyTest.test_default_tokens_are_unique_and_full_length`가 기본 token_factory 엔트로피 잠금. ✓
- **H-2(해소)**: `test_no_non_auth_operation_is_protected_yet`가 비-목표를 **전수**(표본 3개가 아닌 OpenAPI 순회)로 잠근다. **자가-역전 논리 검증(직접)**: 두 신호(`security` 키 **또는** `401` 응답 선언)를 잡는데, H3가 모든 현실 상태 선언을 강제하므로 D8-3이 bare `Depends()`로 인가를 넣어도 401 응답 선언이 의무적으로 붙어 이 테스트가 발화한다. 즉 D8-3에서 "실패하는 것이 정상"이라는 HANDOFF 메모의 주장이 **코드적으로 성립**. ✓
- c982ecd는 **tests-only**(services/ 변경 0건). ✓

### 6. HANDOFF 인계 메모 (직접 확인)
- 슬라이스 진행표(1a~2b 완료·2c 선택·3 다음) · 자가 검수 줄(`2026-07-27 · 171줄`, 다음 트리거 200) — 형식·내용 모두 정합. ✓
- **D8-3 착수자 메모** 3점: (a) 재료 위치(`_current_user`+`project.owner_id`) 정확 (b) legacy `owner_id=None` 처리가 첫 결정 — "소유자 불일치면 거부"만 쓰면 주인 없는 데이터가 전부 닫히거나 전부 열린다는 경고 정확 (c) `test_no_non_auth_operation_is_protected_yet`가 D8-3에서 실패 → 삭제 말고 역명제로 재작성 — 위 5에서 논리 검증완료.

## Issues / Risks

### Blocking (계약 의무)
- **없음.**

### Hardening recommendations (비차단, 정본 밖)
- H-1: legacy 문서 회귀(`test_legacy_project_document_without_owner_field_reads_as_unowned`)가 `self.repo._projects.insert_one`로 private 컬렉션에 직접 심는다. repo 내부 컬렉션명이 바뀌면 불투명하게 깨짐 — 허용되는 테스트 패턴이나 메모.
- H-2 (D8-3 전향 주의): `test_no_non_auth_operation_is_protected_yet`는 `401` 선언에 키를 둔다. D8-3이 인가를 설계할 때 미인증=**401**(표준)을 쓰면 자가-역전이 발화하지만, 만약 403만 쓰는 변형을 하면 발화 안 함 — D8-3은 401(미인증)+403(비소유자) 표준 설계로 가야 이 비-목표 잠금이 정상 종료된다.

## Verdict — **합격(Pass)**
구현은 D8 step2("필드만, 검사 없음")·비-목표("표면 무변, 인가 없음") 계약에 정확히 부합. owner_id는 기록만 되고 시행은 없으며, nullable·legacy-safe(`.get`)·공개 API 무변이 모두 확인. 회귀는 양방향으로 잠겨 있고 **mutation으로 확인**. 기준선 1627/1/623 실측 정확 일치. 직전 검증의 조건 B-1(+보강 2)이 c982ecd로 전부 해소됐다. 차단 사항 0.

## Outstanding items
- D8-3 착수 전 **owner 결정 필요**: legacy `owner_id=None` 프로젝트를 인가가 어떻게 다룰지. 이 결정이 implementation을 블록하므로 CLAUDE.md "Owner decision brief" 절에 따라 브리프(옵션 표+권고안) 선행이 맞다. D4("개발 데이터 폐기 허용")가 한 옵션(폐기 후 clean slate)을 준다.
- test-mongo(27020) 가동 중(검증자 기동). `liveprobe` 사용자(직전 검증 잔류) 여전히 dev DB에 — 차기 폐기 시 소거.

## Reproduction
```bash
cd "/mnt/d/devel/에베베/ai_writte_system"
docker compose -f docker-compose.test.yml up -d
PYTHONPATH=. python3 -m pytest tests/ -q -rs | tail -2   # 1627 passed, 1 skipped, 623 subtests
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py::ProjectOwnershipRecordingTest -q   # 4 passed
# mutation(2b owner 배선)
cp services/application/app/main.py /tmp/bak
sed -i 's/owner_id=current.id if current is not None else None,/owner_id=None,/' services/application/app/main.py
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py::ProjectOwnershipRecordingTest -q --tb=line  # 1 failed
cp /tmp/bak services/application/app/main.py
# 공개 API 무변
grep -c owner_id frontend/src/api/schema.d.ts   # 0
```
