# 독립 검증 — D8-7 G1=C 저장소 노출면 축소(loopback 바인드) (commit 6380b4c + 663d533)

## Subject metadata

- **날짜**: 2026-08-02
- **요청자**: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? D8-7 G1=C를 시행까지 끝냈습니다.")
- **검증자**: Claude(독립 세션, max 노력) — 시행자 세션이 아님.
- **대상 슬라이스**: D8-7 G1=C — `docker-compose.yml`의 `mongo`·`chroma`·`elasticsearch`·`gateway`·`embedding`, `docker-compose.test.yml`의 `test-mongo` 호스트 게시를 `127.0.0.1:` 바인드로 축소; `application`·`frontend`·`llama`는 의도적 공개 유지; 전수 가드 `tests/test_compose_exposure.py`. 애플리케이션 코드 0줄.
- **정규 스펙**: `docs/system-contract-sot.md` **v1.7.75**(§"제품과 프로젝트 경계" line 279-284, "외부 노출 금지" 해제 조건 개정) · `docs/plans/auth-d8-7-infra-auth-decisions.md`(G1=C 확정, Partially resolved) · v1.6.53 G3=A(저장소 무인증의 원래 근거, 개정이 못박은 회귀 위험).
- **검증 대상 출처**: `6380b4c`(코드 — compose 3파일 + 가드) · `663d533`(문서 — SoT v1.7.75 + 브리프 + HANDOFF + work_log + .env.example). HEAD = `663d533`. push 안 됨.

## Scope

1. **★ 노출 축소의 완전성** — 6개 서비스가 정말 loopback인지, **다른 노출 경로**(`network_mode: host`·`expose:`)가 남아 있지 않은지. compose 파일 리터럴과 docker 자신의 렌더링(`compose config`)을 독립 비교.
2. **전수 가드 `test_compose_exposure.py`의 강도** — 파서가 게시 서비스 집합을 파일에서 읽어 분류 리터럴과 대조한다는 주장을 **반증 시도**(작은따옴표·인라인 포트로 우회)로 검증. "목록을 믿지 않는다"가 진짜인지.
3. **양방향 뮤테이션 3종 재현** — under-strict(mongo 접두 제거)·over-strict(application loopback)·분류 강제(worker 포트 추가)가 정확히 예상 테스트만 re-fail 시키는지.
4. **SoT v1.7.75 계약 일관성** — §279-284(노출 없음) ↔ §284(저장소 여전히 무인증) 자체 모순 여부; changelog entry와 본문 합치.
5. **회귀 전량 재실행** — 작업자 보고 1836 passed/4 skipped/1556 subtests 독립 재현 + 회귀 0건.
6. **"호스트 툴링 무영향" 직접 증거** — test-mongo를 새 바인드로 띄워 호스트 pytest가 붙는지; `migrate_ordered_units.py`·runbook curl의 기본 URI가 loopback인지.
7. **★ 런타임 상태 vs 파일 시행의 괴리** — `docker ps` 실측으로 compose 파일 수정이 **이미 존재하는 컨테이너에 적용되었는지** 여부.

## Methodology

- compose 리터럴: `grep -nE "ports:|127.0.0.1|0.0.0.0"` 직접 추출 + `git show 6380b4c -- docker-compose*.yml` diff 전수 독해.
- docker 자신의 답: `docker compose -f docker-compose.yml config` 렌더링에서 `host_ip` 유무로 loopback/공개 판정.
- 다른 노출 경로: `grep -rnE "network_mode|expose:" docker-compose*.yml`(exit 1 = 전무).
- 양방향 뮤테이션(작업 트리 일시 변이 → re-fail → `git checkout` 원복, CLAUDE.md §6): `sed -i`/Edit로 변이 → `git diff`로 의도 확인 → `python3 -m pytest tests/test_compose_exposure.py -v` → `git checkout --` 복구 → `git status --short` clean 확인. 각 변이마다.
- 가드 파서 공격(반증 시도): worker에 (a) 작은따옴표 포트 `- '8599:8000'` (b) 인라인 포트 `ports: ["8599:8000"]` 각각 추가 → docker 수용 여부(`compose config` + yaml)와 가드 포착 여부(`pytest`)를 분리 측정.
- SoT 계약: `docs/system-contract-sot.md` line 274-285 + changelog v1.7.75/v1.7.74 엔트리 교차 독해; operation 카운트는 `tests/test_auth_api.py:854`(권위 소스)로 실측.
- 회귀: `docker compose -f docker-compose.test.yml up -d test-mongo` → healthy 대기 → `docker port`로 127.0.0.1:27020 확인 → `python3 -m pytest -q`(test-mongo ON).
- 런타임: `docker ps -a --format`으로 각 컨테이너의 STATUS·PORTS 원본 관찰.
- boundary matrix(G1=C 계약 요구 분기): [should fire] 저장소·내부 5종 + test-mongo가 `127.0.0.1:` 바인드 · [should fire] 게시 서비스 집합 = `_LOOPBACK_ONLY ∪ _PUBLIC_ON_PURPOSE` · [should NOT fire] `application`·`frontend`가 loopback으로 묶임 · [should NOT fire] `llama`가 loopback으로 묶임.

## Findings

### 1. 노출 축소 시행 — 완전하다 (compose 리터럴 = docker 렌더링)

`docker-compose.yml`의 게시 매핑(직접 grep):

| 서비스 | 매핑 | 분류 |
|---|---|---|
| mongo (`docker-compose.yml:16`) | `127.0.0.1:${MONGO_PORT:-27520}:27017` | loopback |
| gateway (`:144`) | `127.0.0.1:${GATEWAY_PORT:-8521}:8001` | loopback |
| embedding (`:175`) | `127.0.0.1:${EMBEDDING_PORT:-8522}:8002` | loopback |
| chroma (`:204`) | `127.0.0.1:${CHROMA_PORT:-8523}:8000` | loopback |
| elasticsearch (`:240`) | `127.0.0.1:${ELASTICSEARCH_PORT:-9520}:9200` | loopback |
| application (`:103`) | `${APPLICATION_PORT:-8520}:8000` | **공개**(접두 없음) |
| frontend (`:381`) | `${FRONTEND_PORT:-5520}:80` | **공개** |
| test-mongo (`docker-compose.test.yml:41`) | `127.0.0.1:${TEST_MONGO_PORT:-27020}:…` | loopback |
| llama (`docker-compose.llama.yml:42`) | `${LLAMA_PORT:-9080}:9080` | **공개** |

`docker compose config` 렌더링(docker 자신의 답): `host_ip: 127.0.0.1` 5건(chroma·ES·embedding·gateway·mongo), `application` 8520·`frontend` 5520은 host_ip 없음(=0.0.0.0). 작업자 보고와 정확히 일치.

**다른 노출 경로**: `grep -rnE "network_mode|expose:" docker-compose*.yml` exit 1 — 전무. `network_mode: host`나 `expose:`로 빠져나가는 우회 없음.

### 2. 전수 가드 — "목록을 믿지 않는다"는 진짜다 (반증 1건 실패, 1건 성공)

`tests/test_compose_exposure.py`의 파서는 `_PORTS_RE`(`^    ports:\s*$`)가 `ports:` 섹션을 만나면 `published.setdefault(service, [])`로 **서비스를 집합에 넣는다**. 이 설계가 핵심이다.

**반증 시도 (a) — 작은따옴표 포트** `- '8599:8000'`를 worker에 추가: docker는 유효 게시로 수용(`published: '8599'`)하지만, 가드가 `test_every_publishing_service_is_classified`로 **잡아낸다**. 파서가 매핑 *문자열*(`_PORT_ITEM_RE`는 큰따옴표만)은 못 읽어도, `setdefault`가 ports 섹션 존재만으로 worker를 집합에 넣기 때문. 작업자의 "분류 강제"는 내가 우회하려 한 따옴표 방식보다 **강하다**.

**반증 시도 (b) — 인라인 포트** `ports: ["8599:8000"]`를 worker에 추가: docker는 수용하지만 **가드가 못 잡는다**(5 passed). `_PORTS_RE`의 `\s*$`가 `ports:` 뒤에 내용이 있으면 매칭 실패하여 worker의 ports 섹션을 아예 인식 못 함 → worker가 published 집합에서 누락 → classification 통과 → **blind spot**. 현재 compose 3파일은 전부 멀티라인 `ports:` + `      - "…"` 형식이라 당장 결함은 아니나, "분류 강제"는 **멀티라인 형식에만 성립**한다 (→ Hardening #1).

### 3. 양방향 뮤테이션 3종 — 전부 예상대로 정확히 re-fail (독립 재현)

각 변이는 `git diff`로 의도 확인 후 pytest, `git checkout`으로 복구, `git status --short` clean(exit 0) 확인.

| 변이 | re-fail한 테스트 | 다른 테스트 | 결과 |
|---|---|---|---|
| mongo `127.0.0.1:` 접두 제거 | `test_data_stores_are_published_to_loopback_only` SUBFAILED(service='mongo') | classification·over-strict 통과 | under-strict ✓ |
| application → `127.0.0.1:` 묶음 | `test_the_product_surface_stays_published_to_every_interface` SUBFAILED(service='application') | classification·under-strict 통과 | over-strict ✓ |
| worker에 포트 추가(멀티라인 큰따옴표) | `test_every_publishing_service_is_classified` FAILED('worker') | 나머지 통과 | 분류 강제 ✓ |

세 변이 모두 정확히 하나의 테스트만(그리고 정확한 subTest 서비스만) 깨뜨린다 — 가드가 경계를 서로 겹치지 않게 분리해 잠갔다는 증거. 작업자 보고의 뮤테이션 표와 정확히 일치.

### 4. SoT v1.7.75 계약 — 내부 모순 없음

`docs/system-contract-sot.md` line 279-284:
- §279: 저장소 조건 "인증했다" → "노출이 없다" 개정. 근거 3종(위험의 형태·단계·되돌림 가능).
- §284: "저장소는 여전히 무인증이며 그 사실은 바뀌지 않았다 — 바뀐 것은 그것이 위험이 되는 조건이다. 저장소 포트를 다시 0.0.0.0으로 게시하는 순간 v1.6.53의 원래 위험이 그대로 돌아온다."

§279(노출 없음) ↔ §284(무인증 유지)는 모순이 아니다 — 위험은 "무인증 + 도달 가능"의 결합이었고, 도달성을 없애면 위험이 사라진다. changelog v1.7.75 엔트리도 동일. 헤더 버전 1.7.74→1.7.75, 갱신일 08-01→08-02 합치. 본문 2곳 + changelog 1행. 작업자가 "가장 오독하기 쉬운 자리(저장소 무인증)를 함께 못박았다"고 한 것은 사실이다.

changelog의 "operation 카운트 무변(71)"도 G1=C 범위에서 정확 — G1=C는 operation을 건드리지 않는다(compose만).

### 5. 회귀 — 작업자 보고 정확 재현

`python3 -m pytest -q`(test-mongo 127.0.0.1:27020 healthy): **1836 passed, 4 skipped, 1556 subtests passed in 103.30s**, exit 0. 작업자 보고(1836/4/1556, ~105s)와 정확히 일치, 회귀 0건. `tests/test_compose_exposure.py` 5 passed/7 subtests 포함(loopback 5 + 공개 2).

### 6. "호스트 툴링 무영향" — 직접 증명

- test-mongo를 새 바인드로 기동 후 `docker port ai_writte_system-test-mongo-1` → `27020/tcp -> 127.0.0.1:27020`. 호스트 pytest가 거기에 붙어 1836 passed가 돌았다 = "loopback 바인드가 호스트 툴링을 깨지 않는다"의 직접 증거.
- `scripts/migrate_ordered_units.py:20` 기본 `mongodb://localhost:27520` — loopback이라 무영향.
- `docs/runbooks/local-llama-server.md:48` `curl localhost:8521` — gateway 8521 loopback이라 무영향.
- Mongo 테스트 5종 기본 `mongodb://localhost:27020/?replicaSet=rs-test`(`test_*_mongo.py`) — loopback.

### 7. ★ 런타임 상태 — 파일 시행과 괴리 (Outstanding으로 이동, 아래 참조)

`docker ps -a` 실측: `mongo-1`·`gateway-1`·`elasticsearch-1`·`chroma-1`·`embedding-1`이 `Exited (255) 25 hours ago` 이면서 **여전히 `0.0.0.0:27520->27017` 등 옛 매핑을 보유**. 컨테이너 포트 매핑은 생성 시점에 고정되므로, compose 파일의 127.0.0.1 바인드는 이 컨테이너들에 **아직 적용되지 않았다**. 현재 Exited이므로 실제 노출은 아니나, 옛 설정으로 재기동하면 LAN 노출이 복귀한다.

## Issues / Risks

### Blocking (계약 의무 위반)

**없다.** G1=C 계약이 요구하는 모든 boundary cell — [should fire] 5종 loopback·test-mongo loopback·게시 집합=분류 합집합, [should NOT fire] application·frontend·llama 공개 유지 — 이 가드에 매핑되어 있고, 뮤테이션으로 양방향이 실증됐으며, 회귀 0건이다. boundary matrix에 빈 칸이 없다.

### Hardening recommendations (비차단, 현재 스펙 범위 밖)

1. **가드 파서의 인라인 `ports:` blind spot** (`tests/test_compose_exposure.py:42` `_PORTS_RE`). `ports: ["8599:8000"]` 한 줄 형식을 파서가 인식 못 해 새 게시 서비스를 조용히 누락시킨다(Findings §2-(b)에서 실증). 현재 compose는 전부 멀티라인이라 결함이 아니나, 작업자의 "못 읽으면 리터럴 대조에서 실패하므로 조용한 skip이 되지 않는다"(`work_log.md:78-79`)는 주장은 **멀티라인 형식에만** 성립한다. 보강 후보: `_published_ports`를 YAML 파싱으로 전환하거나(작업자가 `yaml` 의존 추가를 피한 이유와 상충), 최소한 인라인 형식도 잡는 정규로 넓히기. 현 컨벤션 고정 전제하에 우선순위 낮음.
2. **SoT §276 operation 카운트 낡음** (`docs/system-contract-sot.md:277`). "현재는 69개가 네 티어(public 4 · 인증 전용 2 · 관리자 4 · project-scoped 59)"라고 하나, 권위 소스 `tests/test_auth_api.py:854`는 `assertEqual(len(tiers), 71)`. changelog v1.7.74("70→71")·v1.7.75("무변 71")와 코드는 71로 일관. **G1=C 슬라이스와 무관**(G1=C는 operation 카운트에 무관) — v1.7.58~v1.7.74 사이 증가분이 본문에 반영 안 된 문서 부채. `HANDOFF.md:52`의 "69개 tier 분할" 표기도 동일하게 낡음. 별도 1줄 수정 권장.

## Verdict

**합격.** G1=C 시행은 완전하고(compose 리터럴 = docker 렌더링, 다른 노출 경로 전무), 가드는 양방향으로 boundary를 잠갔으며(뮤테이션 3종 + 파서 반증 1건), 회귀는 1836/4/1556/103.30s로 작업자 보고 그대로 재현됐고 회귀 0건이다. SoT v1.7.75 계약 변경은 내부 모순 없이 "저장소 무인증 유지 + 포트 재개장 시 위험 복귀"까지 못박았다. Hardening #1(인라인 ports blind spot)·#2(§276 카운트)는 둘 다 비차단이며 #2는 이 슬라이스 범위 밖이다.

유일한 주의 — "G1=C 시행 완료"는 **compose 파일 수준에서는 참**이되 **운영 중인 컨테이너 수준에서는 미적용**이다(Outstanding §1). 오너가 옛 컨테이너를 재생성(`docker compose down && up -d`)하기 전까지는 런타임 노출면이 바뀌지 않는다.

## Outstanding items

1. **옛 컨테이너 5종이 여전히 0.0.0.0 바인드** (`mongo-1`·`gateway-1`·`elasticsearch-1`·`chroma-1`·`embedding-1`, Exited 255 / 25h). compose 수정을 런타임에 반영하려면 재생성이 필요. 작업자가 보고한 크래시 루프(`frontend`·`worker`·`generation_worker`, restart: unless-stopped)도 같은 맥락의 고아 상태. **오너 결정(2026-08-02): 지금은 그대로 둠** — 현재 Exited 상태라 실제 노출은 아니고 compose 파일이 이미 고쳐졌으므로, 다음 정상 기동 시 새 `127.0.0.1` 바인드가 자연 적용된다.
2. **G2~G6(자격증명)은 원격/다중 호스트 배포 시점까지 유예** — 브리프에 실행 계획으로 남아 있음(Partially resolved). G6의 ES `ELASTIC_PASSWORD` 실측 항목은 그때 선행 필요.
3. **이 슬라이스 밖의 오너 결정 대기 페이즈는 D8-5 하나**(C-1~C-6).
4. push는 안 됨(커밋 2개 로컬 main).

## Reproduction

```bash
# 1. 노출면 실측 (compose 자체 답)
docker compose -f docker-compose.yml config | grep -B1 host_ip
grep -rnE "network_mode|expose:" docker-compose*.yml   # exit 1 = 전무

# 2. 가드 베이스라인
python3 -m pytest tests/test_compose_exposure.py -v      # 5 passed / 7 subtests

# 3. 양방향 뮤테이션 (각각 변이 → pytest → git checkout -- docker-compose.yml)
#    mongo 접두 제거 / application loopback / worker 포트 추가

# 4. 회귀 (test-mongo 새 바인드)
docker compose -f docker-compose.test.yml up -d test-mongo
docker port ai_writte_system-test-mongo-1               # 127.0.0.1:27020
python3 -m pytest -q                                     # 1836 passed / 4 skipped / 1556 subtests
```
