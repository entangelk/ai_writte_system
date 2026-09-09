# 계정 탈퇴 Slice 3 — 파기 데몬이 계정 축 데이터를 어떻게 찾는가

상태: `Resolved — ⓑ 두 규칙 스윕 · ⓔ 데몬+스크립트(오너 2026-09-09)`
작성: 2026-09-09
선행: [`account-withdrawal-implementation-phases.md`](account-withdrawal-implementation-phases.md) Slice 0~2 완료(SoT v1.8.45·v1.8.46·v1.8.48) · D3=ⓐ(실패하면 멈춘다) · D4=ⓐ(원장 `target_user_id` 개명)

## 결정 필요

**파기 데몬이 "이 계정의 데이터"를 무엇으로 식별하는가 — 그리고 그 규칙이 남겨야 할 것(원장·감사·사용자명 묘비)을 어떻게 비껴가는가.**

계획서 Slice 3 은 *"프로젝트 밖 사용자 축 데이터 파기(세션·가입 기록 등 — 목록은 **DB 에서 유도**하고 손으로 들지 않는다)"* 라고만 적었다. 그 문장은 프로젝트 축 선례([`scripts/purge_reconciler.py`](../../scripts/purge_reconciler.py))를 그대로 옮긴 것인데, **사용자 축에서는 그 규칙이 성립하지 않는다.** 실측이 두 가지를 드러냈다.

### 실측 1 — 필드 이름 스윕이 컬렉션 하나를 조용히 놓친다

프로젝트 축의 규칙은 *"`project_id` 필드를 가진 컬렉션을 DB 에서 발견한다"* 이고, 그래서 **필드 이름이 파기의 opt-in/opt-out 스위치**다(D4 가 원장을 `target_project_id`·`target_user_id` 로 개명해 쓸이를 피한 근거). 사용자 축에 같은 규칙을 적용하면:

| 컬렉션 | 사용자 축 키 | `user_id` 필드 스윕이 보는가 | 파기 대상인가 |
|---|---|---|---|
| `users` | `_id` | ✗ | 계정 행 — **마지막에** |
| `sessions` | `user_id` 필드 | ✓ | ✓ |
| `writing_generation_jobs` | `user_id` 필드 (+`project_id`) | ✓ | ✓ (프로젝트 파기가 이미 가져간다) |
| `index_sync_outbox` · `index_sync_logs` | `user_id` 필드지만 **값이 항상 `None`** ([`indexing/service.py:439`](../../services/application/app/indexing/service.py)) | 컬렉션은 발견되나 일치 0건 | ✗ (프로젝트 축) |
| **`request_quota_policies`** | **`_id` = user_id** ([`quota/policy_mongo.py:46`](../../services/application/app/quota/policy_mongo.py)) | **✗ — 못 본다** | ✓ (회원 한도·정지 상태) |
| `request_usage_ledger` | `target_user_id` | ✗ | **남긴다**(D4·오너 결정) |
| `admin_audit_events` | `admin_user_id` / `target_user_id` | ✗ | 남긴다(감사 원장) |
| `login_failures` | **`_id` = username** ([`auth/login_guard_mongo.py:39`](../../services/application/app/auth/login_guard_mongo.py)) | ✗ | 사용자명 축 — 아래 "후속 고려" |
| `access_grants` · `access_grant_uses` · `activity_events` | `admin_user_id`/`actor_user_id` + `project_id` | ✗ | 프로젝트 파기가 가져간다 |

정확히 **한 컬렉션(`request_quota_policies`)만** 의도 없이 살아남는다. 크지 않은 누락처럼 보이지만 성격이 나쁘다 — *약속한 삭제가 조용히 안 된 것*이라 D5(부분 삭제 = 조용한 고아) 금지와 약관 제8조가 걸린다.

**★ 계획서와 코드가 어긋난다 — 어느 쪽도 조용히 고르지 않는다.** D4 절의 *"세션·색인·생성 job·**회원 한도 정책**도 `user_id` 를 쓰지만 탈퇴 시 지워져야 하는 계정 데이터라 쓸이 대상인 것이 맞다"* 는 문장이 **회원 한도 정책에 대해 사실이 아니다.** 그 컬렉션은 `user_id` 필드를 쓰지 않는다(회원당 한 행이라는 P1 계약을 `_id` 로 강제한 것이 그 설계의 의도이고, 그 자체는 옳다). 이 브리프의 결정이 그 문장을 무엇으로 정정할지도 함께 정한다.

### 실측 2 — 규칙을 `_id` 로 넓히면 이번엔 사용자명 묘비를 지운다

계획서 Slice 3 은 *"사용자명 한 값 보존(08-2c `project_name_history` 와 같은 모양)"* 을 요구한다. 그런데 그 선례의 모양은 **`_id` = 파기 대상 id** 이고, 그것이 우연이 아니라 **명시된 설계**다 — [`deletion/project_name_history_mongo.py`](../../services/application/app/deletion/project_name_history_mongo.py) 머리말이 *"``_id`` is the project id **on purpose**: the document then carries no ``project_id`` field, and ``scripts/purge_reconciler.py`` — which discovers sweep targets by that field — cannot mistake this collection for orphaned project data"* 라고 적었다. 즉 **이 저장소에서 "파기를 살아남는다"의 기존 표식이 곧 `_id` 키잉**이다.

따라서 사용자 축 스윕에 *"`_id` 가 user_id 인 문서도 지운다"* 를 더하면, 데몬이 **방금 자기가 쓴 사용자명 묘비를 지운다**. 선례를 그대로 따를 수 없고, 어느 쪽이든 **한 축은 선례와 다른 모양**이 된다.

## 선택지

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **ⓐ 필드 스윕 + 손으로 든 `_id` 예외 목록** | `user_id` 필드 발견은 그대로 두고, `_id` 축 컬렉션(`request_quota_policies`)만 코드에 목록으로 적는다 | 변경이 가장 작다. 보존 축은 손대지 않으므로 사용자명 묘비가 `project_name_history` **선례를 그대로** 따른다 | **목록이 낡는다** — 이 저장소가 값을 두 번 치른 실패 모양이다(`purge_reconciler` 머리말: *"목록을 믿지 말고 디렉터리/DB 를 읽어라"*). 새 `_id`-키 계정 컬렉션이 생기면 아무도 모르게 빠진다 |
| **ⓑ 두 규칙 스윕 + 보존 표식을 `target_user_id` 로 통일** | 발견 규칙 = *"`user_id` 필드를 가졌거나 `_id` 가 이 user_id 인 컬렉션"*. 남길 것은 전부 **`target_user_id`** 로 가리키게 한다(원장·감사가 이미 그렇다). 사용자명 묘비도 `_id` 가 아니라 `target_user_id` 필드로 짓는다 | **손으로 든 목록이 없다.** 규칙이 한 문장이 된다 — *"`user_id`·`_id` 로 사용자를 가리키면 지운다, `target_user_id` 로 가리키면 남긴다."* D4 가 이미 그 표식을 원장에 심어 뒀으므로 **새 관례가 아니라 완성**이다. 새 계정 컬렉션이 생겨도 자동으로 덮인다 | **사용자명 묘비가 `project_name_history` 선례와 키 모양이 다르다** — 두 묘비를 나란히 읽는 사람이 왜 다른지 물을 자리가 생긴다(주석 부담). `_id` 스윕이 전 컬렉션에 `find_one({"_id": uid})` 를 도므로 발견 비용이 컬렉션 수만큼 는다(현재 20여 개, 무시 가능) |
| **ⓒ 발견 대신 계약 — 서비스마다 `purge_user()`** | 프로젝트 파기가 `purge_project` 를 각 서비스에 두는 것과 **같은 모양**으로, 계정 축 서비스에 `purge_user` 를 더하고 데몬이 그 목록을 부른다 | 파기 본체와 읽는 모양이 같다. 각 저장소가 자기 키 모양을 스스로 알므로 `_id`/필드 구분이 사라진다. 타입 체커가 미구현 서비스를 잡는다 | **결국 목록이 코드에 박힌다** — 프로젝트 축이 정확히 이 모양이었고, 그래서 `purge_reconciler` 라는 안전망을 따로 만들어야 했다. 계정 축에서 같은 값을 두 번 치른다 |
| **ⓓ 데몬은 프로젝트 + 계정 행만, 나머지는 사용자 축 reconciler** | 데몬은 `execute_project_purge` 반복 + `users` 행 삭제까지만. 잔류는 별도 스크립트가 주기적으로 쓸어 간다 | 데몬이 짧아지고 실패 지점이 준다 | **파기 직후 잔류가 정상 상태가 된다.** 30일을 기다린 삭제 약속이 "언젠가 스크립트를 돌리면"이 되고, D3 의 *부분 파기 표시*가 정상과 구별되지 않는다 |

## 추천 — ⓑ (두 규칙 스윕 + `target_user_id` 보존 표식)

**이유 셋.**

1. **이 저장소는 손으로 든 목록에 이미 두 번 데었다.** `purge_reconciler` 가 존재하는 이유가 그것이고(프로젝트 축 ⓒ 의 사후 수습), 스크립트 로그인 슬라이스(2026-08-01)도 같은 교훈을 남겼다. 계정 축은 **지금 처음 여는 축**이라 같은 값을 두 번 치를 이유가 없다.
2. **보존 표식이 이미 절반 서 있다.** D4 가 원장을 `target_user_id` 로 개명했고 `admin_audit_events` 도 같은 이름을 쓴다. 남은 것은 사용자명 묘비 하나뿐이라, **통일 비용이 신규 컬렉션 한 개의 필드 이름**이다. 반대로 ⓐ 는 그 절반 선 관례를 남겨 둔 채 예외 목록이라는 두 번째 규칙을 더한다.
3. **선례 이탈이 실제로 싼 쪽이다.** ⓑ 가 어기는 것은 `project_name_history` 의 **키 모양**뿐이고 그 컬렉션은 손대지 않는다. ⓐ 가 어기는 것은 *"목록을 손으로 들지 않는다"* 라는 **이 저장소가 명시적으로 적어 둔 규칙**이다. 전자는 주석 한 줄로 설명되고 후자는 시간이 지나면 결함이 된다.

**다만 ⓐ 를 고를 이유도 진짜다** — 계정 축 컬렉션이 앞으로도 늘지 않을 거라면(로컬 1인 서비스이고 계정 축은 3년간 셋뿐이었다) 예외 목록 한 줄이 두 규칙 스윕보다 읽기 쉽다. **오너가 "계정 축은 더 안 늘어난다"고 보면 ⓐ 가 맞다.**

## 함께 결정할 것 — Slice 3 의 범위

D3 에 오너가 *"관리자 화면에 잔여 정리 실행을 둔다"* 를 더했는데, **화면은 Slice 4 의 범위**로 이미 적혀 있어 두 슬라이스가 한 편집을 자기 것이라고 말한다(Slice 0 과 Slice 5 가 §6 승격을 놓고 겪은 것과 같은 모양).

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **ⓔ Slice 3 = 데몬 + 사용자 축 reconciler 스크립트. 관리자 endpoint·화면은 Slice 4** | 수습 경로는 `purge_reconciler.py` 선례대로 **스크립트**로 먼저 선다 | D3 의 요구(*실패하면 표시하고 멈춘다*)는 **표시 + 수습 경로**만 있으면 성립한다. 슬라이스가 백엔드 한 덩어리로 끝나 검증이 단순하다 | 오너가 화면을 원한 시점보다 한 슬라이스 늦다 |
| ⓕ Slice 3 에 관리자 endpoint·화면까지 | D3 문언 그대로 | 오너 요구가 한 번에 닫힌다 | 백엔드 데몬 + 새 저장소 + 관리자 route + 프런트가 한 슬라이스 — Slice 0~2 각각보다 3~4배 크고, 실패 시 되돌릴 단위가 없다 |

**추천 ⓔ.** 이 축의 슬라이스 넷이 전부 "한 화면 또는 한 계약"이었고 그 크기가 검증을 성립시켰다.

## 후속 고려 (어느 쪽을 골라도 열어 둘 것)

- **`login_failures` 는 제3의 축(`_id` = username)이다.** 어떤 규칙도 이것을 사용자 id 로 못 찾는다. 탈퇴 계정의 사용자명이 재사용되면(재가입 차단은 범위 밖) **새 계정이 옛 계정의 잠금을 물려받는다.** 정리 대상으로 볼지, TTL 에 맡길지는 이 브리프 밖이지만 **Slice 3 이 알고 지나가야** 한다.
- **파기 본체 재호출 경계.** [`routers/admin.py::execute_project_purge`](../../services/application/app/routers/admin.py) 는 `HTTPException` 을 던진다. 데몬은 그것을 번역하는 얇은 경계 하나를 두고 **본체는 손대지 않는다**(세 벌째를 만들지 않는다는 계획서 실측 1). 서비스 18개 조립은 `main.py` 의 `_build_*` 를 그대로 부른다 — `admin` 컨테이너가 이미 "Mongo only" 로 같은 집합을 세운다.
- **묘비의 자리는 `deletion/` 패키지다** — `project_name_history` 가 거기 산다. 사용자명 묘비를 어느 키 모양으로 짓든 같은 패키지에 두어 두 묘비가 나란히 읽히게 한다.
- **부분 파기 표시는 `users` 행에 둔다.** 실패하면 계정 행을 지우기 전에 멈추므로 그 행이 표식의 자리로 살아 있다. 새 컬렉션을 만들면 그것 자신이 파기 축의 새 항목이 된다.
- **`is_purge_due`·`purge_due_at` 를 데몬이 그대로 쓴다.** 유예 산술은 한 곳이다(Slice 0 계약 ⓑ).
- **프로젝트 파기 순서**: `archive → execute_project_purge` 를 그 함수가 강제한다(409). 데몬은 archive 를 먼저 부른다.

## 유예 · 범위 밖

- **관리자 대행 탈퇴 · 데이터 내보내기 · 탈퇴 사유 수집 · 재가입 차단 · 유예 만료 알림** — 계획서 Deferred 그대로.
- **정책 문서 §8 → §6 승격** — Slice 5.
- **화면(요청·취소·남은 일수)** — Slice 4.
- **`login_failures` 의 사용자명 축 정리 규칙** — 위 후속 고려에 드러냈을 뿐 이 슬라이스에서 정하지 않는다.

---

## ✅ 오너 결정 (2026-09-09)

| # | 결정 | 뜻 |
|---|---|---|
| **식별 규칙** | **ⓑ — 두 규칙 스윕 + 보존 표식 `target_user_id` 통일** | 발견은 *"`user_id` 필드를 가졌거나 `_id` 가 이 user_id 인 컬렉션"*. **남길 것은 전부 `target_user_id` 로 가리킨다** — 원장·감사가 이미 그렇고, 사용자명 묘비도 `_id` 가 아니라 그 필드로 짓는다. 규칙이 한 문장이 된다: **`user_id`·`_id` 로 사용자를 가리키면 지운다, `target_user_id` 로 가리키면 남긴다** |
| **범위** | **ⓔ — Slice 3 = 데몬 + 사용자 축 reconciler 스크립트** | 관리자 endpoint·화면은 **Slice 4**. D3 의 요구(*실패하면 표시하고 멈춘다*)는 **표시 + 수습 경로**로 성립한다 |

### 이 결정이 만드는 것 — 착수 시 지켜야 할 계약

1. **사용자명 묘비는 `project_name_history` 의 키 모양을 따르지 않는다.** `_id` 가 아니라 **`target_user_id` 필드**를 쓴다 — 선례를 그대로 따르면 데몬이 방금 자기가 쓴 묘비를 지운다. 두 묘비가 `deletion/` 에 나란히 살되 키 모양이 다른 이유를 **묘비 파일 머리말이 적는다**(안 적으면 다음 사람이 선례 위반으로 읽는다).
2. **`request_quota_policies` 가 이 결정으로 처음 쓸이에 들어온다**(`_id` = user_id). 계획서 D4 절의 *"필드 이름이 파기의 opt-in/opt-out 스위치"* 는 **사용자 축에서 "필드 이름 `target_user_id` 가 opt-out 스위치"** 로 정정된다.
3. **`_id` 스윕은 컬렉션 전건에 `find_one({"_id": uid})` 를 돈다.** user id 가 `user:<hex>` 라 다른 축의 `_id`(project id·username·client_ip·lock key)와 겹치지 않는 것이 이 규칙의 안전 근거다 — **id 접두가 바뀌면 그 근거가 사라진다**(셀이 그 사실을 잠근다).
4. **`login_failures`(`_id` = username)는 여전히 어느 규칙도 못 찾는다.** 이 슬라이스에서 정하지 않는다(위 후속 고려).
