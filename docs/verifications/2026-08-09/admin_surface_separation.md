# Slice 2 — 관리자 표면 주소 분리(A1=ⓑ) 독립 검증

- **날짜**: 2026-08-09
- **요청자**: 오너("작업 AI가 작업한 거 검증하고 의심하고 또 의심해 줘")
- **검증자**: Claude Code 세션(구현자와 다름 — 구현 커밋 `5bdaf15`·`878f24d`·`bb26d6e`를 건드리지 않은 채 HEAD `bb26d6e`에서 감사)
- **대상 슬라이스**: 라우터 정리 Slice 2 — `/admin` 8 operation 을 제품 앱에서 들어내 **같은 이미지·다른 command 의 네 번째 compose 서비스**로. H-2(shim drift 가드) 폐쇄 포함.
- **정규 스펙**: [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.91** §"제품과 프로젝트 경계" — "관리자 표면은 제품과 다른 주소에 있다" 하위 4조항(배포 앱 둘·계약 하나·`/health` 양쪽·세션 Mongo 공유).
- **오너 결정 근거**: A1=ⓑ(2026-08-05, [`plans/router-split-and-admin-separation-decisions.md`](../../plans/router-split-and-admin-separation-decisions.md)); D8-7 G1=C(제품 포트 의도적 LAN 게시); 선행 H-2([`verifications/2026-08-05/router_split_slice1_auth_admin.md`](../2026-08-05/router_split_slice1_auth_admin.md)).
- **검증 원천**: 커밋 `bb26d6e`(HEAD, working tree clean).

## Scope

이 검증이 잰 표면 — 계약 스코프는 SoT v1.7.91 의 4조항 + H-2 이다.

1. **★ 표면 분할 수학** — 합집합 76 = 제품 68 ∪ 관리자 9, 교집합 `{/health}`. 구현자 보고 숫자를 믿지 않고 라우트를 직접 뽑아 재계산.
2. **★ 공개 표면 무변** — `create_app()`(합집합)이 Slice 2 직전과 바이트 동일. `repro_router_split.py` worktree 비교.
3. **★ H-2 구조적 폐쇄** — 세 factory 가 한 함수 본문인가; "배포 앱만 따로 조립하는 코드"가 정말 없는가; drift 형 결함을 넣으면 가드가 무는가.
4. **소켓 라이브 토포로지** — 관리자/제품 두 앱을 호스트 uvicorn 으로 띄워 상태코드. 핵심은 **LAN 게시 포트에서 `/admin` 이 404** 인가.
5. **뮤테이션 7종** — under 6 · over 1, 각각 자기 조항을 물고 있는지 페어링까지 재현.
6. **배선 파일** — compose `admin` 서비스(포트 미게시·command·env Mongo 셋), nginx `location /api/admin/` 순서·rewrite.
7. **전수 회귀 + nginx -t + compose config**.
8. **컨테이너 관통** — 작업자가 못 닫은 "nginx → admin 한 홉" 을 트리 마운트로 최대한.

## Methodology

트리는 clean(`git status --short` empty)이므로 뮤테이션 원복은 `git checkout -- <path>` 안전 분기를 썼고 매 회 복원을 바이트로 확인했다.

```bash
# 표면 분할 — 세 앱을 직접 만들어 (path,method) 집합 추출
PYTHONPATH=$PWD python3 - <<'PY'
from services.application.app.main import create_app, create_product_app, create_admin_app
# union=76 product=68 admin=9, P|A==U, P&A=={/health}
PY

# 공개 표면 무변 — Slice 2 직전(4644232=5bdaf15^) vs HEAD worktree
git worktree add -q /tmp/pre-split 4644232
PYTHONPATH=/tmp/pre-split python3 docs/verifications/2026-08-05/repro_router_split.py >/tmp/pre.json
PYTHONPATH=$PWD        python3 docs/verifications/2026-08-05/repro_router_split.py >/tmp/post.json
diff /tmp/pre.json /tmp/post.json   # IDENTICAL

# 소켓 라이브 — 호스트 uvicorn 2개(in-memory)
python3 -m uvicorn services.application.app.admin_asgi:app --port 8531 &
python3 -m uvicorn services.application.app.main:app        --port 8532 &
curl … /admin/users  /projects  /health   # 각 표면에서 상태코드

# 뮤테이션 7종 — cp 없이 clean-tree 분기: mutate → pytest 초점 → git checkout -- → status+byte 확인
#  초점 = tests/test_admin_surface_separation.py + tests/test_compose_exposure.py

# 회귀 — test-mongo ON(docker-compose.test.yml up -d, healthy 대기) 후 python3 -m pytest -q

# 컨테이너 관통 — 낡은 이미지(2026-08-02)에 admin_asgi.py 가 없으므로 services/ 마운트
docker run --rm -d -p 8541:8000 -v "$PWD/services:/app/services" \
  -e PYTHONPATH=/app -e CORE_SOT_MONGO_URI= \
  ai_writte_system-application:latest \
  uvicorn services.application.app.admin_asgi:app --host 0.0.0.0 --port 8000
```

## Findings

### 1. 표면 분할 수학 — 구현자 보고와 한 치 없이 일치

직접 추출: union **76** · product **68** · admin **9**, `P|A == U` 참, `P&A == {("/health","get")}` 정확히. admin-only 8 operation 은 `/admin/audit-events`·`/admin/observability/kpi`·`/admin/projects`·`/admin/projects/{id}/access-grants`·`/admin/projects/{id}/purge`·`/admin/users`(get·post)·`/admin/users/{id}/deactivate`. `main:app`(이미지 기본 CMD)에 `/admin` **0건**, `admin_asgi:app` 에 `/admin` 8 + `/health` = 9.

**의심 해소**: `register_observability` 가 제품 블록(`if not include_product: return app` 뒤)에 있어 "전역 KPI `/admin/observability/kpi` 가 관리자 앱에 없는 것 아니냐" 를 걸었는데 — 그 route 는 `register_admin` 이 더한다(실측). per-project `/projects/{id}/observability/kpi` 만 제품 블록. 관리자 앱 표면 = admin tier 8 + health 가 정확히 성립.

### 2. 공개 표면 무변 — worktree diff IDENTICAL

`4644232`(Slice 2 직전, 코드 무변 docs 커밋 = `5bdaf15`^) vs HEAD `bb26d6e` 에서 `repro_router_split.py` 지문 `diff` 출력 **없음**. route **76** · order-sensitive pairs **0** · openapi sha `f8b42ef191d95a2341debb0c879805b31ebc5c351dac1ca3c4ee51b2f809cfa1` · stdout 지문 sha `c3dfb3910e30f752a21f0c4c6fef591497182b5589a7e8f3d5f029f4b75693fe`. 구현자·HANDOFF·CHANGELOG·SoT v1.7.91 가 인용한 값과 전부 동일. 즉 프론트 `schema.d.ts` 입력이 변하지 않았고, Slice 2 는 76 operation 합집합을 건드리지 않았다.

### 3. H-2 구조적 폐쇄 — 한 본문 확인, drift 가드 작동

`create_product_app()` = `create_app(include_admin=False, **kwargs)`, `create_admin_app()` = `create_app(include_product=False, **kwargs)`. 세 factory 의 차이는 `include_product`·`include_admin` 두 인자뿐, 본문은 `create_app` 하나. 서비스 조립(core_sot·quota·sessions·…)은 표면과 무관하게 무조건 실행 — "배포 앱만 따로 조립하는 두 번째 배선" 은 코드에 존재하지 않는다(구현자가 의도적으로 안 잘랐다고 한 것과 일치).

**★ drift 뮤테이션(M6)** — 관리자 분기에만 `register_observability(...)` 를 넣어 "합집합 앱이 모르는 표면이 배포 관리자 앱에 생기는" H-2 형 결함을 시위했더니 3 셀이 물었다(`test_the_admin_surface_serves_exactly_the_admin_tier_and_health`·`test_the_two_surfaces_partition_the_union_app`·`test_the_admin_container_entrypoint_serves_the_admin_app`). 구현자 보고와 동일.

### 4. 소켓 라이브 — 분리의 핵심 보안 속성 입증

| 표면 | `/health` | `/admin/users` | `/projects` | `/auth/login` |
|---|---|---|---|---|
| 관리자(8531) | 200 | **401**(route+`require_admin_user`) | **404**(route 없음) | 404 |
| 제품(8532) | 200 | **404**(route 없음) | **401**(route+인증) | 405(GET)/422(POST) |

핵심: **LAN 게시되는 제품 포트에서 `/admin/users` 를 치면 404** 다. 분리 전에는 `require_admin_user` 가 401/403 을 냈을 것이고, 그것이 "방어 한 겹" 이었는데 이제 **라우터가 route 자체를 모른다**. `require_admin_user` 는 사라지지 않고 관리자 앱(nginx 뒤)에서 두 번째 겹으로 산다. 구현자 보고·SoT v1.7.91 서술과 정확히 일치.

### 5. 뮤테이션 7종 — 전부 재실패, 페어링까지 일치

| # | 방향 | 변이 | 실패 셀(독립 실측) |
|---|---|---|---|
| M1 | under | `if include_admin:`→`if True:` | product-no-admin · partition · image-default (3) |
| M2 | under | `create_admin_app` 가 `include_product=False` 망각 | admin-exactly · partition · admin-entrypoint (3) |
| M3 | under | `app=create_product_app()`→`create_app()` | image-default (1) |
| M4 | under | admin 서비스에 `ports: ["8524:8000"]` | admin-no-port · compose-classified (2) |
| M5 | over | nginx rewrite `^/api/admin/(.*)$`(세그먼트 소실) | nginx-admin-prefix (1) |
| **M6** | **under(drift)** | **배포 관리자 앱에만 observability 추가** | admin-exactly · partition · admin-entrypoint (3) |
| M7 | over | `register_health`→`if include_product:` | admin-exactly · partition · admin-entrypoint (3) |

매 변이 후 `git status --short` empty + 파일 바이트 복원 확인. 구현자 보고 셀 이름·개수와 전부 일치. M1 의 "test_every_operation_keeps_its_guards 는 안 문다" 도 재현(관리자 route 가 양쪽에 다 실리면 `{**product,**admin}` 이 합집합 계약을 여전히 덮으므로).

**★ 추가 — A6 셀 생존 입증(M8)**: 구현자의 7종은 `test_every_operation_keeps_its_guards_on_the_split_apps`(operation 별 가드·상태코드·에러·**route 클래스** 동일)을 물 변이를 빠뜨렸다. route_class(`QuotaSettledRoute`)를 `if include_product:` 로 감싸 관리자 앱의 route 클래스를 `APIRoute` 로 만드는 변이를 넣었더니 **9 subTest 실패**(`/admin/users` 가 union=`QuotaSettledRoute` vs admin=`APIRoute`). 즉 그 셀은 dead cell 이 아니라 route_class 단정까지 살아 있다. (검증자 추출 도구가 `SUBFAILED` 접두사를 안 잡아 처음에 "재실패 없음" 으로 오독했으나, 단독 실행으로 정정 — 가드는 정상 작동.)

### 6. 배선 파일 — 모두 일치

`docker compose config` 해석: admin command=`uvicorn services.application.app.admin_asgi:app` · **ports=없음** · env=Mongo 셋(`CORE_SOT_MONGO_URI`·`_DB`·`_TRANSACTIONS`) · depends_on=mongo · healthcheck=python urllib `/health` · frontend depends_on 에 `admin` 추가. nginx `location /api/admin/`(line 21)이 `/api/`(line 39)보다 **위·더 구체적**(longest-prefix 매칭), `rewrite ^/api/(.*)$ /$1 break;` 로 `/api` 만 벗겨 `/admin` 세그먼트 보존, `set $admin_upstream admin` + 런타임 resolver. `worker`·`generation_worker` 와 동일 패턴(같은 Dockerfile 재사용·command 만). **★ admin env Mongo 셋의 근거 독립 확인**: `purge_project`(91줄)·`register_admin` 협력자 전부에서 gateway/chroma/embedding 직접 참조 **0건** — purge 의 벡터·lexical 파기는 `sync_outbox` 로 넘겨 worker 가 드레인.

`nginx -t`(nginx:1.27-alpine, conf.d/default.conf 마운트): `syntax is ok` / `test is successful`.

### 7. 회귀 — 구현자 기준선 재현

`2208 passed / 4 skipped / 2247 subtests in 172s`(test-mongo ON). skip 4 = live Chroma 1(호스트 구조적) + ES 패키지 부재 3(알파 정상값). ES 3건을 passed 로 보정하면 **2211 / 1 / 2247** — HANDOFF 기준선·README ②·구현자 보고와 정확히 일치. cell +11(분리 가드 10 + 진입점 로드 1)·subtest +78(operation 76 전수 계약 대조 + 2), operation 76 무변.

### 8. 컨테이너 관통 — 진입점 기동 입증, nginx 한 홉은 오너 판단

작업자가 남긴 "nginx → admin 한 홉" 의 전제(이미지 부채)를 독립 확인: application 이미지는 **2026-08-02 빌드**(HANDOFF ★★ 가 "2026-07-22" 라 한 것보다는 새로우나 Slice 2=08-09 이전)이고 `admin_asgi.py` 가 이미지에 **없다**(`ls` 로 확인). 재빌드 없이는 관통 불가.

대신 **트리 마운트 관통**으로 한 단계 더 갔다: application 이미지에 `services/` 를 마운트해 `admin_asgi:app` 을 띄웠더니(`/admin/users` 401 · `/projects` 404 · `/health` 200, 시작 에러 없음) — 호스트 파이썬이 아닌 **실제 배포 이미지 환경**에서 새 진입점 모듈이 호환되게 기동함을 입증. 남은 nginx 경유 `:5520` 한 홉은 admin 컨테이너가 compose 네트워크에 있어야 하므로 재빌드 필수이고, 그것은 작업자가 명시적으로 오너 판단 사안으로 넘긴 것이다. nginx 설정(location·rewrite·upstream)은 이미 3축(문법·compose 해석·가드)에서 검증됐다.

## Issues / Risks

### Blocking (계약 의무 위반)

**없음.** SoT v1.7.91 의 4조항이 전부 충족됐고, boundary matrix 의 모든 셀이 채워져 있으며, 뮤테이션 7종 + 추가 A6 입증으로 양방향 가드가 실제로 문다.

### Hardening (비차단)

- **작업자 뮤테이션 매트릭스에 A6(route_class) 축이 빠졌다.** `test_every_operation_keeps_its_guards_on_the_split_apps` 가 route 클래스 단정까지 살아 있음을 입증했지만(M8), 작업자의 7종은 이 셀을 물 변이를 포함하지 않았다. 셀 자체는 계약-required 분기(named test)에 매핑되어 empty-cell 규칙을 충족하므로 blocking 이 아니다. 다음 비슷한 분리 슬라이스에서 뮤테이션 축에 route_class(또는 가드 튜플의 한 요소) 차이를 포함하면 매트릭스가 더 완전해진다.
- **작업자가 M1 재측정 때 §6 게이트를 온전히 안 지켰다(사실대로 기록됨).** 재측정 시 작업 트리에 미커밋 문서 3건이 있었고 `git checkout --` 가 `main.py` path 지정이었다. 손실은 없었으나 "첫 뮤테이션 전 clean" 게이트 위반이다. 본 검증은 트리 clean 전제로 게이트를 지켰고 매 회 바이트 복원을 확인했다.
- **nginx → admin 컨테이너 한 홉 미실측** — 재빌드 후 `curl :5520/api/admin/users` 가 **401**(404 가 아니라) 인지로 닫는다. 작업자가 남긴 것이 타당(이미지 부채 독립 확인). 설정 3축은 통과했고 진입점 기동도 입증했으므로 위험은 낮다.

## Verdict

**합격** — SoT v1.7.91 의 관리자 표면 주소 분리 4조항(배포 앱 둘·계약 하나·`/health` 양쪽·세션 Mongo 공유)과 H-2 폐쇄가 전부 충족됐다. 공개 표면 무변(worktree diff IDENTICAL, openapi sha `f8b42ef1…`), 표면 분할 수학(76=68∪9, 교집합 `/health`) 독립 재현, 소켓 라이브로 "LAN 포트에서 `/admin` 은 라우터 404" 핵심 보안 속성 입증, 뮤테이션 7종 전부 재실패 + A6 셀 생존 추가 입증, 회귀 2208/4/2247(보정 2211/1) 재현. Blocking 0. 남은 nginx→admin 컨테이너 한 홉은 재빌드 후 오너가 닫는 것(작업자가 이미 그렇게 위임).

## Outstanding items

- **오너 판단**: application·admin·frontend 이미지 재빌드 후 `curl :5520/api/admin/users` = 401 확인으로 관통 한 홉 폐쇄. 404 면 nginx location/rewrite 를 본다.
- 본 검증 기록 추가로 `docs/verifications/` 건수 227→228·일수 45→46. 인덱스·README 카운트 동반 갱신했고 `VerificationCountClaimsTest`·`VerificationsIndexTest` 로 확인.

## Reproduction

```bash
git status --short   # clean 전제
# 표면 분할·지문·소켓·뮤테이션·정적(2~6 절) — Mongo 무관, 수 초
PYTHONPATH=$PWD python3 -c "from services.application.app.main import create_app,create_product_app,create_admin_app; ..."
git worktree add -q /tmp/pre-split 4644232 && (cd /tmp/pre-split && PYTHONPATH=$PWD python3 docs/verifications/2026-08-05/repro_router_split.py >/tmp/pre.json); PYTHONPATH=$PWD python3 docs/verifications/2026-08-05/repro_router_split.py >/tmp/post.json; diff /tmp/pre.json /tmp/post.json
python3 -m pytest tests/test_admin_surface_separation.py tests/test_compose_exposure.py -q   # baseline 16/85
# (M1~M7 변이 → pytest → git checkout -- → status+byte)  / 추가 M8: route_class 를 if include_product: 로
# 회귀 — Mongo 필요
docker compose -f docker-compose.test.yml up -d && until […healthy]; do sleep 2; done && python3 -m pytest -q   # 2208/4/2247
# 컨테이너 관통 — 트리 마운트
docker run --rm -d -p 8541:8000 -v "$PWD/services:/app/services" -e PYTHONPATH=/app -e CORE_SOT_MONGO_URI= ai_writte_system-application:latest uvicorn services.application.app.admin_asgi:app --host 0.0.0.0 --port 8000 && curl :8541/admin/users  # 401
```
