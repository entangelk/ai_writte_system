# Slice 9.2 독립 검증 — 개인 허브 `/me` + 통합 활동 `GET /me/activity`

- **일자**: 2026-08-10
- **요청자**: 오너(*"작업 AI가 작업한거 검증하고 의심하고 또 의심해줄래?"*)
- **검증자**: Claude (독립 세션)
- **대상 슬라이스**: Phase 9 Slice 9.2 — P1~P8(개인 허브 `/me` · 통합 활동 조회 · IA 재배치)
- **정본 계약 참조**: `docs/system-contract-sot.md` **v1.7.96**(Approved) · 결정 브리프 `docs/plans/09-2-personal-hub-and-ia-decisions.md`(Resolved)
- **검증 대상 소스**: 커밋 `20be3c0`(feat me) · `8b5a30d`(feat ui) · `7a1fb5e`(test activity) · `6d7dd9a`(docs). HEAD `6d7dd9a`, 작업 트리 clean.
- **머신**: 베타(GTX 1060 3GB). `elasticsearch` 패키지 있음 → 원시 skip 수가 곧 보정값(skip 1 = live Chroma). test-mongo `27020` healthy.

## Scope

1. **계약 읽기** — SoT v1.7.96 changelog · 브리프 P1~P8·S-1~S-3 를 경계 행렬로 조립.
2. **구현 코드** — 저장 계층(`activity/log.py`·`log_mongo.py`) · endpoint(`routers/auth.py`) · 모델(`api/models.py`) · 프론트(`AuthGate.tsx`·`App.tsx`·`me/PersonalHubPage.tsx`).
3. **회귀 셀** — 신규 10 backend 셀 · 12 frontend 셀의 계약-대-테스트 대응.
4. **회귀 기준선 재측정** — backend 전수 · frontend 전수 · 빌드 번들.
5. **뮤테이션** — 빈 집합 방어(양방향) · P8 소유 기준 · `?next=` 딥링크(over).
6. **공개 표면/스키마** — operation 77→78 · tier 가드 등재 · `schema.d.ts` · `client.ts` 배선.

## Methodology

```bash
# 머신 상태 (memory: verify-machine-state-before-claiming-blocked)
docker compose ps                       # healthy 8 + healthcheck 없는 2
docker compose -f docker-compose.test.yml up -d   # test-mongo 27020
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done

# 회귀 기준선 (정확한 skip 수를 위해 elasticsearch 패키지가 있는 호스트에서)
python3 -m pytest -q                    # backend 전수
cd frontend && npx vitest run           # frontend 전수
npx tsc --noEmit && npm run build       # 타입 + 빌드

# 뮤테이션 (뮤테이션 전 git status --short 가 비어 있어야 안전 — 매번 확인)
git status --short                      # ← 게이트: 비어 있어야 함
# ...변이 적용(Edit) → 포커스 셀 실행 → git checkout -- <path> → git status --short 확인
```

뮤테이션은 clean 트리에서 했으므로 `git checkout -- <path>` 로 HEAD 원복(verification.md §"The restore rule" clean-tree 분기). 매 회 원복 후 `git status --short` 가 비어 있음을 확인했다. 결과는 `grep FAILED` 가 아닌 **요약 count 줄**을 읽었다(§"Reading the result").

## Findings

### 1. 회귀 기준선 — 작업자 주장과 정확히 일치 (측정 단위)

| 검사 | 작업자 주장 | 재측정(베타) | 판정 |
|---|---|---|---|
| backend 전수 | `2265 / 1 / 2364` | **`2265 passed, 1 skipped, 2364 subtests`**(972s) | 일치(수) |
| frontend 전수 | `285 / 20` | **`285 passed / 20 files`** | 일치 |
| 빌드 진입 | `420.08 kB` | **`420.08 kB`** | 일치 |
| 빌드 lazy(관측) | `386.70 kB`(무변) | **`386.70 kB`** | 일치(P3=ⓐ 유지) |
| 빌드 모듈 | `704 modules` | **`702 modules transformed`** | **2 차이(비부하)** |
| tsc | — | OK | — |

skip 1 = 호스트에서 구조적으로 항상 skip되는 live Chroma 셀. 수(2265/1/2364·285/20·420.08·386.70)는 부하를 받는 지표 전부 정확히 일치한다. **모듈 수 702 vs 704** 만 차이인데, 이는 부하를 안 받는 지표(의존 해석에 따라 흔들림)이고 부하 지표(진입 kB·lazy kB)가 정확히 일치하므로 결함이 아니다.

### 2. 빈 집합 이중 방어(★ 작업자가 뮤테이션으로 연 자리) — 방어 실재, 경로별 3층

소유 프로젝트가 없는 회원에게 빈 집합을 줄 때 "없음"이 아니라 "전부"로 뒤집히면 **남의 활동이 전부 보이는** 최악의 구멍이다. 방어는 경로별로 셋이다:

- **Mongo(배포) 경로**: 서비스 단락 `if not project_ids: return ()`([`log.py:179`](../../services/application/app/activity/log.py#L179)) + Mongo `$in: []`([`log_mongo.py:60`](../../services/application/app/activity/log_mongo.py#L60)).
- **인메모리(테스트) 경로**: 서비스 단락 + 인메모리 공집합 필터(`set(project_ids)` 가 공집합 → 무매칭, [`log.py:77-79`](../../services/application/app/activity/log.py#L77)).

**뮤테이션 3종 실측**(요약 count 줄 기준):

| 변이 | 적용 diff | 결과 | 해석 |
|---|---|---|---|
| A | 어댑터 `$in` → 무필터 `{}` | `test_an_empty_project_set_reads_nothing_at_the_store` + 병합 셀 **2 failed** | mongo 직접 셀이 문다 |
| B | 서비스 단락 제거(어댑터 정상) | 서비스/HTTP 빈 집합 셀 **2 passed** | 어댑터 `$in`이 가린다(단락은 방어가 아님 — 작업자 주장 확인) |
| B+A | 단락 제거 + 어댑터 무필터 | mongo 직접 셀 **1 failed**, 서비스/HTTP **2 passed** | 서비스/HTTP는 **인메모리**를 써서 mongo 변이에 안 닿는다 |

**핵심**: 작업자의 *"두 층이 서로를 가린다"* 는 본질이 맞다. 단, 서비스/HTTP 셀은 **인메모리 어댑터**를 쓰므로 **mongo `$in: []` 동작을 실제로 고정하는 것은 직접 셀 하나뿐**이다. 그 셀([`test_activity_log.py:330`](../../tests/test_activity_log.py#L330))이 없으면 mongo 경로의 빈 집합 성질은 어느 셀로도 재지 못한다 — 작업자가 셀을 추가한 판단이 정확히 맞았다(8.3 선례와 같은 형태). 서비스 주석의 과장 정정(단락은 왕복 절약이지 방어가 아니다)도 사실이다.

### 3. P8 소유 기준 경계 — SOUND, 셀이 문다

`GET /me/activity`([`auth.py:164-196`](../../services/application/app/routers/auth.py#L164))는 주체를 세션에서(`require_authenticated_user`) · 소유 집합을 `core_sot.list_projects_for_owner(owner_id=current.id)`([`auth.py:180`](../../services/application/app/routers/auth.py#L180) · mongo 쿼리 `{"owner_id": owner_id}` [`mongo_repository.py:175`](../../services/application/app/core_sot/mongo_repository.py#L175))에서 유도한다. 경로가 project id 를 안 받는 것이 S-3.

**뮤테이션 C**(소유 필터 제거: `list_projects_for_owner` → `list_projects` 전체): `test_it_never_shows_another_members_project` **failed**(alice 의 `/me/activity` 에 bob 의 `project-2` 가 샘). 경계 셀이 정확히 물린다.

> 참고: P8=ⓐ 는 다중 사용자가 되면 승격 관리자의 행위가 행위자 표시 없이 타임라인에 섞이지만, 오너 확정("소유 기준, 지속")이고 그때 바뀌는 것은 범위가 아니라 표시(F4)다 — 결함이 아니다(브리프·SoT 에 명시).

### 4. `?next=` 미도입 판단 — SOUND, 정본(SoT)에 기록됨

작업자가 결정 브리프 P5의 `?next=` 보존을 **도입하지 않았다**. 실증:

- **제자리 렌더링 확인**: `AuthGate` 는 `state==="anonymous"` 일 때 `<LoginScreen/>` 을 `{children}` 대신 그린다([`AuthGate.tsx:105-128`](../../frontend/src/auth/AuthGate.tsx#L105)) — URL 을 바꾸지 않는다. 로그인 후 상태가 `authenticated` 가 되면 그 URL 의 route 가 그대로 렌더링된다. 딥링크가 **이미** 보존된다.
- **`next` 흐름 부재**: 프론트 전수 grep — `next`(목적지)·`useSearchParams`·`window.location` 사용 0건. `navigate()` 호출 3곳(AuthGate `/admin`, DraftEditor·ReviewInboxDetail 의 하드코딩 내부 경로) 전부 외부 입력을 안 읽는다 → **open redirect 표면 0**.
- **뮤테이션 M3**(over: 관리자 리다이렉트 `location.pathname === "/"` 조건 제거 → 무조건 `/admin`): `does not swallow an administrator's deep link` **failed**(관리자가 `/projects/p1` 에서 로그인해 "겨울 이야기"를 못 받는다). 양방향 셀(루트 로그인→`/admin` under-strict + 딥링크 보존 over-strict)이 제자리 렌더링의 성질을 잠근다.

**정본 기록 확인**: SoT **v1.7.96** changelog 가 해소를 명시한다 — *"S-2 `?next=` 를 만들지 않았다 … (브리프는 `?next=` 보존을 적었으나 도입하지 않는 편이 더 안전하다 — 범위 축소, 근거 기록)"*. 결정 자체는 사운(S-2 목표인 open redirect 가 표면 자체가 없어 더 잘 충족)·정본에 연결돼 있다. (브리프 본문 P5/S-2 의 옛 문구는 그대로 남아 있으나 SoT 가 *"브리프는 … 적었으나"* 로 무효화하므로 발견 가능하다 — §Issues 참조.)

### 5. 상한 100 양쪽 일치 — 일치(비hardening 1건)

`list_for_project`·`list_for_projects` 모두 `limit: int = 100`([`log.py:155,160`](../../services/application/app/activity/log.py#L155))이고 두 endpoint(`/me/activity`·`/projects/{id}/activity`) 모두 limit 인자 없이 호출 → 기본 100. 다른 hardcode 값 없음. P2 역설(통합 < 단일) 조건 불발.

### 6. 공개 표면 — operation 78 · tier 4 · 스키마 배선 일치

`/me/activity` 가 AUTH_ONLY tier 4번째로 등재([`test_auth_api.py:1129`](../../tests/test_auth_api.py#L1129), 근거 명시)되고 `test_every_operation_lands_in_exactly_one_named_tier` 가 전수 단정. `client.ts` 의 `listMyActivity` → `/me/activity` 배선([`client.ts:253-256`](../../frontend/src/api/client.ts#L253))·`PersonalActivityEventPayload` 모델(`project_id` 추가 상속, [`models.py:215`](../../services/application/app/api/models.py#L215))·`schema.d.ts` 재생성이 tsc·빌드로 일치.

### 7. 변경 범위 — 범위 내

네 커밋의 변경 파일 전부가 P1~P8 에 대응(P7 DraftList 관측 링크 제거 등). 범위 외 변경·고아 import 없음.

## Issues / Risks

### Blocking (계약 의무)

없음. 계약이 요구하는 분기(빈 집합·소유 기준·인증 tier·딥링크 보존) 전부 명명된 회귀 셀에 대응하고, 양방향 뮤테이션에 물린다.

### Hardening recommendations (비차단)

1. **★ 허브 표시 상한 ↔ 서빙 상한 연결 가드 누락(9.1 선례 미연장).** 9.1 이 `ActivityCeilingClaimTest`([`test_activity_ui_labels.py:125`](../../tests/test_activity_ui_labels.py#L125))로 *프로젝트별 화면의 `ACTIVITY_PAGE_SIZE` ↔ `list_for_project` 기본* 을 양방향으로 묶었다(S2=ⓐ). 그러나 이 셀은 `list_for_project`(단일)만 본다. 9.2 허브는 **별도의** `ACTIVITY_PAGE_SIZE=100`([`PersonalHubPage.tsx:14`](../../frontend/src/me/PersonalHubPage.tsx#L14), 주석에 "per-project 와 같은 수 — P2 역전 방지" 라 연결을 인지)을 쓰고 `list_for_projects`(기본 100)로 서빙하는데, **이 짝을 잠그는 셀이 없다**. `list_for_projects` 기본이 바뀌면 허브가 "최근 100건까지" 라 말하며 50건만 주는 — 9.1 이 닫은 바로 그 거짓 상한 — 가 조용히 재현된다. 동일한 `inspect.signature` 연결 셀을 허브 짝으로 하나 더 두는 것을 권장(현재 둘 다 100 이라 결함은 아님).

2. **브리프 본문 P5/S-2 옛 문구 정리(저우선순위).** `09-2-…-decisions.md` 의 P5(line 211)·S-2(line 45)·구현 순서(line 320)가 여전히 `?next=` 보존·양방향 셀을 서술하지만, SoT v1.7.96 이 그것을 무효화했다. SoT 가 *"브리프는 … 적었으나"* 로 연결하므로 발견은 되나, 브리프만 읽는 다음 작업자 혼란을 줄이려 P5/S-2 에 SoT v1.7.96 해소를 한 줄로 비고하는 것이 깔끔하다.

## Hardening 폐쇄 (2026-08-10, 발행 뒤 추가)

오너 지시(*"검증기록 확인해서 보강할 부분 보강해줘"*)로 **①이 같은 날 닫혔다**. 아래는 발행 후
추가된 사실이며 원 지적 문언은 그대로 둔다. **판정은 원래 `합격` 이라 승격 문제가 없다.**

| 항목 | 처리 | 실측 |
|---|---|---|
| **① 허브 상한 연결 가드 누락** | `ActivityCeilingClaimTest` 를 **짝 전수**로 확장 — 등재된 (화면, 서빙 메서드) 쌍마다 subtest, 그리고 **`ACTIVITY_PAGE_SIZE` 를 선언한 `.tsx` 를 글롭해 등재를 강제** | **먼저 갭을 재현**했다(`list_for_projects` 100→50 에 42 cells 전부 green). 확장 뒤 **세 방향**이 문다 — 서빙 100→50 · 허브 상수 100→250 · **미등재 세 번째 상한**(임시 화면 추가) |
| **② 브리프 본문의 `?next=` 옛 문구** | 브리프 §P5 에 **구현 결과 주석**을 달았다(결정 자체는 안 고친다 — 오너 결정 기록이다) | SoT v1.7.96 이 이미 해소를 적고 있어 저우선이었다 |
| **모듈 수 704 vs 702** | **검증이 옳다 — 704 는 측정하지 않고 쓴 값**이다(빌드 출력의 모듈 줄이 잘렸는데 채워 넣었다). HANDOFF·work_log 를 **702** 로 정정 | 재측정 `702 modules`. 부하 지표(진입 420.08 kB · lazy 386.70 kB)는 정확히 일치 |

**★ ①은 내가 §4 "패턴 스윕"을 빠뜨린 자리다** — 9.1 이 상한 연결선을 만들었는데 9.2 가 **두 번째
상한을 만들면서 그 패턴을 따라가지 않았다**. 이제 세 번째 상한은 등재 없이는 못 생긴다.

## Verdict

**합격** — Blocking 0.

부하를 받는 회귀 수치(backend `2265/1/2364` · frontend `285/20` · 진입 `420.08 kB` · lazy `386.70 kB`)가 작업자 주장과 정확히 일치하고, 검증자가 묻는 축 전부(빈 집합 방어 양방향 · P8 소유 기준 · `?next=` 딥링크 over)에서 셀이 물렸다. 빈 집합 이중 방어는 작업자 서술이 본질에서 맞다(mongo 직접 셀이 유일한 고정점). `?next=` 미도입은 사운·정본(SoT v1.7.96)에 기록됐다. 모듈 수 702↔704 차이·허브 상한 연결 가드 누락은 비차단 hardening 이다.

## Outstanding items

- 작업 트리 clean. 뮤테이션 전부 원복 완료(`git status --short` 비어 있음 확인).
- **test-mongo 가 이 검증을 위해 기동돼 있다**(`docker-compose.test.yml`). 종전 상태(미기동)로 돌리려면 `docker compose -f docker-compose.test.yml down`.
- 허브 렌더 **육안 확인**은 검증 범위 밖(회귀로 잠갔고 스택은 떠 있다). 오너 재량: `http://localhost:5520/me`(계정 `timeline_demo` / `timeline-demo-0810`).
- Hardening 1(허브 상한 연결 셀)을 반영할지는 오너 결정 사안.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git status --short                          # 비어 있어야 함(HEAD 6d7dd9a)
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done

# 1) 기준선
python3 -m pytest -q                        # 2265 passed, 1 skipped, 2364 subtests
cd frontend && npx vitest run               # 285 passed / 20 files
npx tsc --noEmit && npm run build           # 진입 420.08 kB · 관측 lazy 386.70 kB
cd ..

# 2) 빈 집합 뮤테이션 A (어댑터 $in → 무필터)
#   log_mongo.py: {"project_id": {"$in": list(project_ids)}} → {"_MUTATION": True}
python3 -m pytest tests/test_activity_log.py::MongoActivityLogRepositoryTest -q   # 2 failed
git checkout -- services/application/app/activity/log_mongo.py

# 3) P8 뮤테이션 C (소유 필터 제거)
#   auth.py:180 list_projects_for_owner(owner_id=current.id) → list_projects()
python3 -m pytest "tests/test_activity_api.py::PersonalActivityQueryTest::test_it_never_shows_another_members_project" -q  # 1 failed
git checkout -- services/application/app/routers/auth.py

# 4) ?next= over 뮤테이션 M3 (위치 조건 제거)
#   AuthGate.tsx:123 if (nextUser.is_admin && location.pathname === "/") → if (nextUser.is_admin)
cd frontend && npx vitest run src/App.test.tsx -t "administrator"                # 1 failed
cd .. && git checkout -- frontend/src/auth/AuthGate.tsx

git status --short                          # 비어 있어야 함(원복 확인)
```
