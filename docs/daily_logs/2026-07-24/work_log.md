# 2026-07-24 작업 로그

## Task — 배포 스택 fd 한도 폐쇄: `mongo` + `elasticsearch` `ulimits.nofile`

### Goals

- 오너 지시: "dogfood 외에 진행할 수 있는 것 중 **작은 것부터**". 남은 후보 중 가장 작은 것이 2026-07-23이 추적 부채로 등록한 배포 `mongo`의 `ulimits` 누락(4줄)이다.
- 목표는 배포 스택이 test-mongo와 **구조적으로 공유하던 fatal 크래시 조건**을 닫는 것. 런타임 코드 무변, compose 설정만.

### Issues found

- **착수를 막던 이유가 이미 사라져 있었다.** 07-23이 이 건을 오너 판단으로 넘긴 근거는 "**실행 중** 스택의 컨테이너 재생성이 필요"였다. 그러나 착수 시점에 `ai_writte_system-mongo-1`은 25시간 전 `Exited (255)`였고, 더 결정적으로 **옛 포트 매핑(`27019->27017`)으로 생성돼 있었다** — 07-23의 전용 대역 고정(`MONGO_PORT` 기본 27520) 때문에 **다음 기동 때 어차피 재생성된다.** 재생성 비용이 0인 시점이라 오너 판단을 다시 받을 실익이 없다고 보고 진행했다.
- **[패턴 스윕 → 인라인 수정] `elasticsearch`도 같은 상태였다.** 실측으로 확인: 빌드된 `ai_writte_system-elasticsearch:latest`가 Docker 기본 `nofile soft=1024`를 받는다. Elasticsearch 자신의 요구 최소치는 **65535**이고 평소에는 bootstrap check가 그 미만이면 기동을 거부하는데, 이 서비스는 `discovery.type=single-node`(개발 모드)라 **체크가 경고로 격하돼 그냥 뜬다**. 즉 "요구치 미달인 채로 조용히 운영되다가 segment/index 회전이 쌓이면 나중에 터지는" 형태로, mongo와 정확히 같은 근본 원인이다. 4줄 동일 패턴이라 §4의 "scope-trivial이면 인라인 수정"에 따라 함께 닫았다.
- **`chroma`는 제외했다.** 상태 볼륨(`chroma_data`)은 갖지만 SQLite+HNSW 단일 저장소라 WiredTiger 같은 fd 회전이 없고 벤더 요구치도 없다. 스윕은 30초 예산의 sanity check이지 리팩터가 아니라는 §4 기준으로 판단했고, 근거를 여기 남겨 다음 사람이 같은 지점을 다시 조사하지 않게 한다.

### Completed work

- **[`docker-compose.yml`](../../../docker-compose.yml) `mongo`**: `ulimits.nofile {soft: 64000, hard: 64000}`. 값은 mongod 자신이 기동 시 권고하는 `recommendedMinimum 64000`이고 `docker-compose.test.yml`과 동일하다. 주석에 실패 형태(`WT_PANIC: __posix_directory_sync … Too many open files` → fassert → 프로세스 사망)와 "배포 노드는 장수 DB 하나뿐이라 아직 도달하지 않았을 뿐"을 기록했다.
- **[`docker-compose.yml`](../../../docker-compose.yml) `elasticsearch`**: `ulimits.nofile {soft: 65535, hard: 65535}`. 값은 mongo와 다른데, 각각 **벤더가 명시한 최소치**를 그대로 쓴 것이다(mongod 64000 / ES 65535). 주석에 single-node 개발 모드가 bootstrap check를 경고로 격하한다는 점을 적었다 — 이게 "왜 지금까지 안 터졌나"의 답이다.
- **`memlock`은 건드리지 않았다**: `bootstrap.memory_lock`이 켜져 있지 않고, 이미지 기본 memlock은 65536으로 나온다. 증상이 관측된 축(fd)만 수정한다(§3 수술적).

### Verification

- **파싱**: `docker compose config --quiet` 통과. `docker compose config mongo`가 `ulimits.nofile {soft,hard}=64000`을 해석함을 직접 확인.
- **A/B 실측(핵심)** — 서비스 정의가 실제로 한도를 바꾸는지를 컨테이너 안에서 확인:
  - `docker run --rm --entrypoint bash mongo:7 -c 'ulimit -Sn'` → **`soft=1024 hard=1048576`** (수정 전 상태)
  - `docker compose run --rm --no-deps --entrypoint bash mongo -c 'ulimit -Sn'` → **`soft=64000 hard=64000`**
  - 같은 방식으로 elasticsearch → **`soft=65535 hard=65535`** (수정 전 `1024`)
- **장수 컨테이너·데이터 볼륨 무접촉**: 검증은 `--rm` 일회용 `compose run` 컨테이너로만 했고 `--entrypoint bash`로 덮어써 **mongod/ES 프로세스는 기동하지 않았다.** 검증 후 `ai_writte_system-mongo-1`이 여전히 `Exited (255)` 그대로임을 확인. 스택 기동은 오너 몫이라는 07-23 경계를 유지했다.
- **회귀 대상 없음**: compose는 배포 설정이고 테스트 코드 경로가 아니다. `docker-compose.test.yml`은 무변이라 백엔드 스위트 조건도 그대로다.

### Decisions (구현자 판단)

- **오너 판단을 다시 받지 않고 진행했다.** 07-23이 이 건을 오너 몫으로 넘긴 유일한 근거가 "실행 중 스택 재생성 비용"이었는데 그 전제가 사라졌고(위 Issues), 결정 자체는 "벤더 권고 최소치를 따르는가"라 실질적 갈림길이 아니다. 오너 지시가 "작은 것부터 진행"이었던 것도 함께 고려했다.
- **두 서비스에 다른 숫자를 쓴 것**은 일관성 부족이 아니라 의도다. 각 데몬이 자기 문서/기동 경고에서 요구하는 값이 다르고, 임의로 하나로 맞추면 "이 숫자가 어디서 왔는가"의 추적성이 사라진다. 주석에 각각의 출처를 적었다.

### Next steps

- 스택 재기동 시 두 컨테이너는 새 포트 대역 + 새 `ulimits`로 재생성된다. 기동 후 확인하려면 `docker compose exec mongo bash -c 'ulimit -Sn'`.

---

## Task — `auto_promote_job` 부분 실패 의미론 결정 브리프

### Goals

- 남은 추적 부채 2건 중 마지막(다른 1건은 07-23에 "누수 아님"으로 성격 정정 완료). H3 페이즈가 60개 endpoint의 에러를 선언하며 닫혔으나 이 건만 **코드 매핑으로 닫히지 않아** 남았다.
- 목표는 **구현이 아니라 브리프**다. 07-23이 이 건을 "코드 매핑보다 계약 질문"으로 분류했고, 임의로 고르면 오너가 선택하지 않은 봉투 형태를 굳히게 된다.

### Issues found

- **계약 공백을 새로 발견했다 — 이게 브리프를 2결정으로 만들었다.** 루프에서 실제로 터지는 주 경로는 Mongo 쓰기 실패인데([`memory/mongo_repository.py:88-94`](../../../services/application/app/memory/mongo_repository.py#L88-L94)가 `DuplicateKeyError`만 감싸고 나머지 pymongo 예외는 그대로 통과), **SoT 상태코드 의미론 표에 "정본 저장소가 있는데 실패했다"에 해당하는 행이 없다.** 502는 "**상류**(LLM·gateway·검색·임베딩)", 503은 "협력자 **미구성** / 데이터 **마이그레이션** 필요"다. 어느 쪽도 Mongo 장애가 아니다.
  - 즉 D1(부분 실패 응답 형태)을 무엇으로 정하든 **찍을 코드가 정본에 없다.** 코드가 임의로 고를 문제가 아니라 계약 증보 대상이라(CLAUDE.md: spec-silent-but-code-enforced), 별도 결정 항목 D2로 분리했다.
- **복구 경로는 이미 계약에 있었다.** SoT v1.6.40 조항이 승격 idempotency를 `(project_id, source_candidate_id)` unique index로 못박고 재호출은 replay라 재보고하지 않는다 — **부분 실패 후 "그냥 다시 호출"이 안전한 복구**다. 이 사실이 "전체 실패로 응답한다"(A안)의 비용을 크게 낮추므로, 추천안과 나란히 A안의 반론으로 명시했다.
- **프론트 소비자가 0건**이다(`grep -rn "auto-promote" frontend/src` → 생성물 `schema.d.ts` 외 없음). 봉투를 넓히는 비용이 지금 가장 싸다는 근거이자, dogfood에서 리뷰 인박스가 이 endpoint를 부르기 시작하면 비싸진다는 시한 근거.
- **전역 exception handler가 없음**을 확인했다(`main.py`에 `exception_handler` 0건). 따라서 루프 안의 모든 미포착 예외는 예외 없이 500이다 — "혹시 어딘가에서 잡히고 있지 않나"를 배제했다.

### Completed work

- **[`docs/plans/auto-promote-partial-failure-decisions.md`](../../plans/auto-promote-partial-failure-decisions.md)** 신설. `03-index-sync-outbox-decisions.md` 구조를 따랐다.
  - **D1 부분 실패 응답 형태** 4안(A 전체 실패 / B 부분 성공 봉투 / C 200+실패 항목 / D 트랜잭션) → **추천 B**. 근거 3개: memory append-only + mint 불가역이라 A/D는 응답과 실제 상태가 어긋난다 · writing accept의 502 partial([`main.py:4110-4121`](../../../services/application/app/main.py#L4110-L4121))이 동일 구조의 **기존 선례**라 새 패턴이 아니다 · 프론트 소비자 0이라 지금이 가장 싸다.
  - **D2 저장소 장애 상태코드** 4안(A 503 세 번째 얼굴 / B 502 확장 / C 계약된 500 / D 저장소 taxonomy 선행) → **추천 A**. 503 정의문("지금 수행할 수 없다 / 요청을 고쳐서는 해결되지 않는다")에 의미가 정확히 맞고 재시도가 유효한 복구라는 관용적 의미와도 일치. B의 단점(운영상 "AI가 이상하다"와 "DB가 죽었다"가 구분 불가)과 C의 단점(H3가 500을 누수로 규정해 제거해 온 판정력이 약해짐)을 명시했다.
  - **D3 `MemoryNotFound` 매핑**: 404. 형제인 수동 promote([`main.py:2484`](../../../services/application/app/main.py#L2484))와 동일하고 선언 집합이 이미 `{404}`라 OpenAPI 무변 — 논쟁 없는 부수 항목으로 분리했다.
  - **Follow-up considerations**: 후속 저장소 taxonomy가 이 슬라이스에 막히지 않도록 잡는 예외를 한 곳에 모을 것 · outbox enqueue는 `put_memory` **이후**라 D1=B의 봉투가 "memory는 mint됐고 재색인만 유실"이라는 세 번째 상태를 갖게 됨.
  - **Deferred**: 전 저장소 pymongo wrapping · 루프 트랜잭션화 · threshold 캘리브레이션 · 프론트 에러 UX · 다른 배치성 endpoint의 같은 질문(결정 확정 후 스윕).

### Verification

- 문서 전용 변경이라 §4 "Documentation-only" 기준으로 검증했다.
- **인용 라인 직독 확인**: `main.py:2572-2600`(루프가 `try` 밖) · `main.py:2484`(수동 promote의 `except (AnalysisNotFound, MemoryNotFound, NotFound)`) · `main.py:4110-4121`(writing accept 502 partial) · `mongo_repository.py:88-94`(`DuplicateKeyError`만 wrapping) · `memory/service.py:194,324-332`(enqueue가 put 이후) · `tests/test_application_api.py:2244`(선언 lock `{"404"}`) · `system-contract-sot.md:314-318`(상태코드 표).
- **상대 링크 5개 전부 해석 확인**(`docs/plans/` 기준 `../` · `../../`).
- 코드·계약·산출물 무변이므로 pytest/vitest/`gen:api` 재실행 대상 없음.

### Decisions (구현자 판단)

- **구현하지 않고 브리프에서 멈췄다.** D1은 공개 봉투 형태를, D2는 정본 상태코드 표를 바꾼다 — 둘 다 오너가 선택하지 않은 경로로 프로젝트를 묶는 항목이라 CLAUDE.md의 결정 브리프 요건에 정면으로 해당한다.
- **추천안을 명시했다(메뉴만 내밀지 않음).** 다만 A안(전체 실패)에도 실재하는 반론 — idempotent 재호출이 복구를 "다시 누른다"로 끝내므로 부분 상태 노출의 실익이 적다 — 을 같은 무게로 적었다. A를 택하면 슬라이스가 절반이 된다는 점도 함께.
- **D2에 "결정하지 않음"(저장소 taxonomy 선행)을 선택지로 남겼다.** 방향은 옳지만 범위가 이 endpoint를 훨씬 넘어(모든 `*_mongo.py`가 같은 상태) 슬라이스 성격이 달라지므로, 그 판단 자체를 오너에게 넘기는 편이 맞다고 봤다.

### Next steps

- **오너 결정 접수 → 아래 구현 task로 이어짐**(D1=B · D2=A · D3=404).

---

## Task — `auto_promote_job` 503 partial envelope 구현 (SoT v1.7.35)

### Goals

- 위 브리프에 대한 오너 결정 **"1 B, 2 A로 가자"** 를 구현한다. D3(404)는 논쟁 없어 함께 처리.
- 순서는 브리프 말미 절차대로: 브리프에 결정 기록 → **정본 증보 선행**(D2가 상태코드 표를 바꾸므로) → 구현 → 양방향 회귀 → 선언/OpenAPI/프론트 타입.

### User Decisions and Rationale

- **D1 = B (부분 성공 봉투)**. 실패 시에도 이번 호출이 새로 mint한 `promoted[]`를 실패 상태코드와 함께 반환한다. 근거는 브리프 추천 사유 그대로 — canonical mint가 append-only·불가역이라 숨기면 응답이 저장 상태와 어긋나고, writing accept의 502 partial이 동형 선례이며, 프론트 소비자가 아직 0이라 봉투 확장이 지금 가장 싸다.
- **D2 = A (503의 세 번째 얼굴)**. 정본 저장소 장애를 503 의미론에 편입한다. 502(상류 실패)에 넣으면 "AI/검색이 이상하다"와 "DB가 죽었다"가 운영상 구분 불가가 되고, 계약된 500 신설은 H3가 500을 "선언되지 않은 누수"로 규정해 온 가드를 약화시킨다.
- **채택하지 않은 A안의 실익도 기록해 둔다**: 승격 idempotency 덕에 "그냥 다시 호출"이 이미 안전한 복구라 전체 실패 응답도 성립했고 슬라이스가 절반이 됐을 것이다. 오너는 응답-상태 정합을 우선했다.

### Issues found

- **계약 정합성 문제를 하나 먼저 처리해야 했다.** v1.7.33이 "partial 봉투와 균일 `detail`의 Union 허용 지점을 **정확히 5곳**으로 고정"하는 회귀를 이미 세워 뒀다(`WritingErrorContractDeclarationTest.UNION_BODIES`). D1=B는 6번째 Union을 만드므로, 그냥 추가하면 **정본이 자기 자신과 불일치**한다. 그래서 정본의 D1=A 조항에 "허용 지점 = 정확히 6곳"을 명시하고 목록에 auto-promote를 넣었다 — drift가 아니라 명시 결정으로만 늘어난다는 성질을 유지했다.
  - 다만 writing 트랙의 over-strict 가드는 **writing 경로만** 순회하므로 analysis 트랙에 Union이 생겨도 잡지 못했다. analysis 트랙에 같은 성격의 `UNION_BODIES` + over-strict 테스트를 **신설**했다(아래 회귀).
- **`main.py`는 pymongo를 의도적으로 지연 임포트한다**(in-memory 경로가 드라이버 설치 없이 떠야 한다 — `_default_core_sot_service` 등 3곳 주석). 따라서 최상단 `from pymongo.errors import PyMongoError`가 불가능하다. 브리프 Follow-up이 요구한 **단일 seam**과 이 제약을 동시에 만족해야 했다.
  - 해결: 지연 해석 튜플 `_STORAGE_ERRORS`(`_resolve_storage_error_types()`)를 한 곳에 두고 드라이버 부재 시 **빈 튜플**로 축약한다. `except ()`는 아무것도 잡지 않는데, 이는 버그가 아니라 정확한 동작이다 — Mongo가 없는 배포에는 분류할 Mongo 장애도 없다.
- **outbox enqueue 실패도 같은 seam으로 덮인다.** `_enqueue_reindex`는 `put_memory` **이후** 별도 Mongo write라(`memory/service.py:194,324-332`), 저장소 계층만 감쌌다면 이 경로는 여전히 500으로 샜을 것이다. 예외 타입 기준(pymongo 계열) seam이라 저장소·outbox 양쪽을 한 지점에서 덮는다.
- **첫 회귀 작성 시 fake가 복구를 모델링하지 않아 스스로 걸렸다.** "두 번째 put부터 계속 실패"로 만들었더니 재시도 테스트가 200을 못 받고 503을 받았다. 이건 테스트 버그였지만 **의미 있는 실패**였다 — 503 description이 약속하는 복구 경로를 검증하려면 fake가 *일시적* 장애여야 한다. `puts == 2`에서만 실패하도록 고쳐 "장애 → 복구 → 재호출" 전체를 잠갔다.

### Completed work

- **정본 증보** [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.34 → v1.7.35**:
  - 상태코드 표 503 행: "아래 **세** 얼굴" + 대표 원인에 **정본 저장소(Mongo) 장애** 추가.
  - **"503의 두 얼굴" → "세 얼굴"**, 3번 항목 신설: 502가 아닌 이유(상류 vs 저장 계층) · 계약된 500을 만들지 않는 이유(H3 가드 약화) · **현재 매핑 지점은 이 endpoint 1곳이고 나머지는 여전히 500으로 샌다는 범위 명시**. 공통 규칙 문장도 "저장소 face는 조치 **후** 재시도가 유효하다"로 정밀화(앞 두 얼굴은 재시도가 무의미하다는 대비).
  - D1=A 균일 본문 조항에 **partial envelope 예외**를 명문화: 허용 지점 정확히 6곳(revise-and-gate 4 · accept 1 · auto-promote 1), 에러 arm이 단일 `ErrorDetailResponse`라 위반 아님.
  - v1.6.40의 `promoted[]` 조항에 **부분 실패 시에도 같은 의미**임과 재호출 복구를 추가.
- **구현** [`services/application/app/main.py`](../../../services/application/app/main.py):
  - `_resolve_storage_error_types()` / `_STORAGE_ERRORS` — 단일 seam(위 Issues).
  - `AutoPromotePartialResponse` 모델 + `_STORAGE_503`(Union 선언 + 복구 절차를 description에 명시) + `_ERRORS_404_STORAGE`.
  - 승격 루프에 `except MemoryNotFound → 404`(D3)와 `except _STORAGE_ERRORS → 503 partial JSONResponse`(D1=B/D2=A) 추가. 선언 `{404}` → `{404,503}`.
  - `promoted[]`는 실패 시점까지 누적된 것을 그대로 싣는다 — 성공 경로와 같은 빌더·같은 의미.
- **회귀 신규 6**:
  - `tests/test_memory_api.py::AutoPromoteStorageFailureTest` **5** — ① 루프 중간 저장소 실패 → 503 + **partial 봉투 exact-key** + 앞선 mint가 `GET /memory`에 **실제로 남아 있음**(응답 ≠ 주장, 저장 상태와 일치) ② **복구 후 재호출이 남은 것만 승격**(idempotency 실증) ③ 정상 200 유지 + 성공 봉투 키 집합 유지 ④ **절 폭 over-strict**(무관한 `RuntimeError`는 503으로 재분류되지 않고 그대로 전파) ⑤ D3 404.
  - `tests/test_application_api.py::AnalysisErrorContractDeclarationTest` **1 신설 + 2 갱신** — `UNION_BODIES` 도입, 균일-본문 테스트가 그 지점만 Union을 허용(양 arm 모두 확인), 신규 `test_union_bodies_appear_only_where_the_contract_allows`가 analysis 트랙 전체에서 Union drift를 막는다.
- 테스트 헬퍼 `_build`에 `memory_repository`/`memory` 주입 인자 추가(기존 호출부 무변).

### Verification

- **mutation 5종 실증** — 각각 해당 회귀만 물었다:

  | 변이 | 물린 테스트 |
  |---|---|
  | `except _STORAGE_ERRORS` 절 제거(`except ()`) | 저장소 503 회귀 2건 |
  | 절을 `except Exception`으로 확대 | `test_unrelated_failure_is_not_relabelled_as_a_store_outage` |
  | `except MemoryNotFound` 절 제거 | `test_memory_not_found_mid_loop_is_404` |
  | 503 → 502 | 저장소 503 회귀 2건 |
  | 선언 `_ERRORS_404_STORAGE` → `_ERRORS_404` | analysis 선언/Union 가드 |

- **회귀 전량**: backend **1459 passed / 1 skipped / 526 subtests**(test-mongo 기동). 기준선 1453/1/525 대비 **+6 passed / +1 subtest**이고, 신규 6건과 auto-promote 선언 코드가 1→2개가 되며 늘어난 subtest 1건으로 **정확히 설명된다**(설명되지 않는 증감 0).
- **프론트**: `gen:api` **+20행 / -0행 순수 additive**(`AutoPromotePartialResponse` 컴포넌트 + 503 anyOf arm), `tsc` clean, build JS **399.03 kB**(무변), vitest **194 passed / 13 files**(무변).
- **OpenAPI 실물 확인**: 덤프된 spec에서 auto-promote 503이 `anyOf: [AutoPromotePartialResponse, ErrorDetailResponse]`, 404가 단일 `$ref`임을 직접 읽었다(코드가 emit할 의도가 아니라 실제 노출을 확인).

### Decisions (구현자 판단)

- **`AutoPromotePartialResponse.promoted`를 `list[dict[str, object]]`로 뒀다.** 이 endpoint의 **성공 arm이 오늘 무타입 dict**라, partial에만 좁은 memory 모델을 붙이면 endpoint가 실제로 약속하지 않는 wire 형태를 문서화하게 된다. memory payload 타입화는 별도 슬라이스다.
- **모델을 `writing/http_models.py`가 아니라 `main.py`에 뒀다.** 선례(`WritingAcceptAnalysisPartial`)는 그 파일에 있지만 그건 writing 트랙 모듈이고, 이건 analysis 트랙 봉투다. `main.py`는 이미 다수의 응답 모델을 정의하고 있어 파일 역할과도 맞는다.
- **저장소 예외를 repository 계층에서 감싸지 않았다.** 그 방향(브리프 D2 선택지 D)이 근본적으로는 옳지만 범위가 전 `*_mongo.py`이고, 무엇보다 **outbox enqueue 경로를 놓친다**(위 Issues). 예외 타입 seam이 이 슬라이스에서 두 경로를 다 덮으면서 후속 taxonomy의 교체 지점도 한 곳으로 남긴다.
- **다른 endpoint의 저장소 장애는 손대지 않았다**(§3 수술적). 대신 그 사실을 정본 503 절에 **명시적 범위 문장으로 적었다** — "아직 매핑돼 있지 않고 500으로 샌다"를 계약이 말하지 않으면 다음 검증자가 이걸 결손인지 의도인지 추측하게 된다.

### Next steps

- **H3가 남긴 미매핑 500 부채는 이로써 0건**이다. 남은 갈림길은 dogfood 착수(GATE-1) 하나.
- 후속 후보(오너 결정 선행): 전 `*_mongo.py` 저장소 예외 taxonomy — 정본이 의미론을 이미 고정해 뒀으므로 착수 시 결정할 것은 "어디까지 한 번에" 뿐이다.

---

## Task — 독립 검증 지적 반영: 부분 봉투의 enqueue-모드 결손 폐쇄 (SoT v1.7.36)

### Goals

- 오너 요청 독립 검증(`docs/verifications/2026-07-24/auto-promote-503-partial-envelope.md`, **조건부 합격**)이 차단 사유 3건(F3·F4·F5)을 재현으로 확정했다. 오너 지시는 **"보강할 부분만 보강"**.
- 목표는 **계약을 약화시키지 않고 계약이 참이 되게 만드는 것**. 오너는 이미 D1=B("응답이 저장 상태와 일치")를 결정했고, F3/F5는 그 결정을 구현이 못 지킨 것이므로 코드로 닫는다. 검증자가 제시한 경로 A(계약을 현실에 맞춰 약화)는 오너 결정을 되돌리는 방향이라 택하지 않았다.

### Issues found — 지적 3건 모두 사실이며, 근인은 하나다

- **먼저 1차 소스로 재도출했다**(검증자 주장을 그대로 수용하지 않음): `memory/service.py`에서 `put_memory`(:187) → `_enqueue_reindex`(:194)는 **두 번의 Mongo write이고 한 transaction이 아니다.** 그리고 replay early-return(:158-163)은 `_enqueue_reindex`보다 **앞**이다. 코드 직독만으로 F3·F4가 성립한다.
- **검증자가 남긴 재현 스크립트 2종을 직접 실행**해 경험적으로도 확인했다(`docs/verifications/2026-07-24/repro_outbox_*.py`).
  - F3: `promoted=['c1']`인데 `STORED=['c1','c2']` → **내가 쓴 정본 단정이 거짓**.
  - F4: 재시도 후에도 `enqueued=['memory-1']` 그대로 → c2의 memory가 **영구 비색인**.
- **근인은 하나**: v1.7.35가 "실패는 항상 mint **이전**에 온다"고 전제했다. seam을 예외 타입(pymongo 계열)으로 잡아 저장소·outbox를 함께 덮은 것이 **상태코드 관점에서는 맞았지만**, 두 write의 **경계를 지운 것**이 문제였다. 내가 v1.7.35 로그에 "seam이 양쪽을 한 지점에서 덮는다"를 장점으로 적었는데, 정확히 그 지점이 결손의 근인이다.
- **슬라이스 내 계약 모순도 사실이었다**: 브리프 D2 도달성 표는 이 경로를 "memory는 있는데 재색인 유실"로 **이미 인지**하고 있었는데, 내가 SoT에는 "어긋나지 않는다"로 **무조건 단정**을 썼다. 두 문서가 서로 달랐다.
- **F4는 성격이 다르다**: replay가 enqueue를 건너뛰는 것은 **v1.6.46이 잠근 기존 계약**이고 이 슬라이스가 만든 결함이 아니다. 다만 이 슬라이스가 "재시도=복구"를 **새로 계약으로 세웠으므로** 그 계약의 정확한 범위를 밝힐 의무는 이 슬라이스에 있다.

### Completed work

- **F3 폐쇄(코드)** — [`memory/service.py`](../../../services/application/app/memory/service.py):
  - 신규 `MemoryReindexEnqueueFailed(RuntimeError)`가 **완료된 `PromoteMemoryResult`를 실어** raise한다. `promote_candidate`가 `_enqueue_reindex`를 try로 감싸 mint 성공 사실을 잃지 않는다.
  - **`MemoryError`(=`ValueError`) 계열로 두지 않은 것은 의도다**: `ValueError`를 400으로 매핑하는 endpoint가 인프라 장애를 "클라이언트 잘못"으로 재분류하기 때문. `DuplicatePromotionRequest(RuntimeError)` 선례를 따랐다.
  - 그 catch는 광의(`except Exception`)인데, **매핑이나 삼킴이 아니라 컨텍스트를 붙여 re-raise**하는 용도라 폭이 정당하다(주석에 명시). enqueue 실패는 타입과 무관하게 남기는 상태가 동일하다.
- **F3 폐쇄(endpoint)** — [`main.py`](../../../services/application/app/main.py): `except MemoryReindexEnqueueFailed` 절이 그 mint를 `promoted[]`에 **넣은 뒤** 503을 반환한다.
- **F5 폐쇄(브리프 Follow-up #2)**: `promotion_error`가 **실패 단계를 명시**한다 — mint 이전이면 `"canonical store write failed before this candidate was minted: …"`, mint 이후면 `"canonical memory <id> was minted, but its reindex enqueue failed: …"`. 운영자가 봉투만 보고 `promoted[]`의 완전성을 판단할 수 있다.
- **F4 처리(계약 정밀화)**: 정본 조항·OpenAPI 503 description·HANDOFF 추적 부채에 **"mint 이후 유실된 재색인은 재호출로 회복되지 않으며 회복 수단은 backfill `scripts/phase2b5_reindex_memory.py`"**를 명시했다. replay 재enqueue 전환은 v1.6.46 변경이라 **오너 결정**으로 등록(enqueue는 memory_id dedup이라 그 자체는 안전하다는 사실도 함께 — 결정 입력값).
- **정본** [`system-contract-sot.md`](../../system-contract-sot.md) **v1.7.35 → v1.7.36**: `promoted[]` 조항의 무조건 단정을 **두 실패 모드 서술**로 교체하고(모드 2는 반드시 `promoted[]`에 포함), 재호출 복구의 정확한 범위를 분리해 적었다.
- **회귀 신규 3(총 13)** — `tests/test_memory_api.py::AutoPromoteStorageFailureTest`: enqueue-모드가 mint를 보고하는지(`reported == stored`) · `promotion_error` 단계 명시(두 모드 문구가 서로 다름) · **F4 잔여 lock**(재호출이 유실 재색인을 회복하지 못함 — docstring에 "문서화된 잔여이지 승인이 아니며 replay 전환 시 의도적으로 갱신하라"를 명시).
  - 기존 하네스가 `reindex_outbox`를 **주입하지 않아** 이 모드가 테스트에서 보이지 않았던 것이 빈 칸의 직접 원인이라, 실패하는 outbox를 주입하는 헬퍼를 추가했다.

### Verification

- **검증자의 재현 스크립트를 수정 후 재실행**(같은 스크립트, 같은 명령):
  - F3: `response.promoted == stored state?: True` → **`=> SoT claim HOLDS`**(수정 전 `False`).
  - F4: 여전히 `NO` — 의도된 잔여이며 이제 회귀와 문서가 그것을 명시적으로 붙잡는다.
- **mutation 3종 실증** — 각각 해당 회귀만 물었다. 특히 **`promoted.append(...)` 제거는 v1.7.35가 출하한 결함 그대로를 재현**하고 `test_enqueue_failure_after_the_mint_still_reports_that_mint` 하나만 문다. 서비스가 enqueue 실패를 삼키도록 바꾸면 3건이 동시에 문다.
- **회귀 전량**: backend **1462 passed / 1 skipped / 526 subtests**. 직전 1459/1/526 대비 **+3 passed**로 신규 회귀 3건과 정확히 일치하며 subtest는 무변이다(신규 테스트가 `subTest`를 쓰지 않음) — 설명되지 않는 증감 0.
- 프론트: `gen:api` **+20/-0**(v1.7.35와 동일 — description 문구는 타입에 영향 없음), `tsc` clean, build JS **399.03 kB**(무변), vitest **194 passed / 13 files**(무변).
- **검증자의 "전체 스위트 카운트 미검증"에 대해**: 그 timeout은 **LLM 서버와 무관**하다. 스위트는 `192.168.1.22:9080`에 접속하지 않으며 LLM 관련 테스트는 전부 `llama.test` 가짜 호스트를 쓴다(`tests/test_llm_benchmark_script.py`·`test_httpx_transport.py`). 실측 소요는 이 머신에서 **656초**로, 검증자의 540초 상한을 넘긴 것이 원인이다.

### Decisions (구현자 판단)

- **검증자의 경로 A(계약 약화)를 택하지 않았다.** "응답이 저장 상태와 일치"는 오너가 D1=B로 고른 것의 핵심이다. 구현이 못 지켰다고 계약을 낮추면 오너 결정을 구현 편의로 되돌리는 것이 된다. F3/F5는 코드로 닫고, **정말로 계약 수정이 필요한 F4만** 정밀화했다.
- **F4를 코드로 닫지 않았다.** 닫으려면 replay가 재enqueue해야 하는데 그건 v1.6.46이 잠근 조항 변경이라 오너 결정 사항이다. 대신 (1) 회복 수단이 있는 상태로 만들고(F3+F5 덕에 어떤 memory가 색인 유실인지 봉투에 보인다) (2) 회귀로 잔여를 lock해 조용히 바뀌지 않게 했다.
- **검증 기록은 수정하지 않았다.** 독립 감사 산출물이고 검증자가 결함을 직접 고치지 않는 것과 대칭으로, 피검증자도 그 기록을 고쳐 쓰지 않는다. 해소 경위는 이 로그와 SoT v1.7.36에 남긴다.

### Next steps

- **오너 결정 1건 추가**: replay 재enqueue 전환 여부(v1.6.46 조항 변경). 하면 F4가 코드로 닫히고, 안 하면 backfill이 공식 회복 절차로 남는다.
- 커밋은 오너 승인 후. 검증 기록의 "B1-B3 해소 전 커밋 보류 권장"은 F3/F5 폐쇄로 해소됐고, F4는 문서화된 잔여로 전환됐다.

---

## Task — F4 폐쇄: 재색인 enqueue를 무조건 choke point로 개정 (SoT v1.7.37)

### Goals

- 오너 결정: **"안전하다면 뭐 그렇게 하고 커밋까지"** — v1.7.36이 "문서화된 잔여"로 남긴 F4(mint 이후 유실된 재색인이 재호출로 회복되지 않음)를 코드로 닫는다.

### User Decisions and Rationale

- **replay도 재enqueue한다**(v1.6.46의 replay 면제 개정). 오너가 "안전하다면"을 조건으로 달았고, 내가 직전 답변에서 "enqueue는 memory_id dedup이라 안전"이라고 말한 것이 근거였다.
- **그래서 착수 전에 그 근거부터 1차 소스로 검증했다**(아래 Issues). 내 주장에 기대어 동작을 바꾸는 상황이라, 주장이 정확한지 먼저 확인하는 것이 순서다.

### Issues found

- **"dedup이라 안전"은 절반만 맞았다.** `get_outbox_entry_by_dedup_key`([`indexing/mongo_repository.py:95-108`](../../../services/application/app/indexing/mongo_repository.py#L95-L108))는 **`PENDING`/`RUNNING` 상태 항목에만** collapse한다. 즉:
  - 항목이 아직 pending인 동안의 replay enqueue = **완전한 no-op**(내가 말한 그대로).
  - **이미 drain된 뒤의 replay = 새 항목 생성 → 재색인 한 번 더 실행**. 이건 내가 언급하지 않은 비용이다.
  - 결론은 **정합성은 안전**(재색인은 upsert라 중복 실행이 오염을 만들지 않음), **비용은 공짜가 아님**(replay마다 임베딩 1회 + upsert 1회가 추가될 수 있음). 오너에게 "안전하다"고만 말한 것은 불완전했으므로 여기 정확한 형태로 기록한다.
- **그 성질 덕에 기존 회귀가 깨지지 않는다**: `test_manual_promote_replay_does_not_double_enqueue`(`tests/test_memory_vector_index.py`)는 항목이 pending인 상태에서 replay하므로 dedup이 흡수해 **항목 수 1 그대로**다. 실제로 통과했다. 그 테스트의 단정(1건)은 여전히 참이고 의미만 "replay는 enqueue 안 함" → "replay의 enqueue는 pending 항목에 collapse함"으로 바뀐다.
- **[패턴 스윕] 같은 replay 분기가 `_versioned_upsert`에도 있었다**(`memory/service.py`). 같은 근본 원인·같은 3줄이고, 오너가 정한 것은 "모든 승격 경로가 색인 요청을 남긴다"는 **불변식**이라 한쪽만 적용하면 불변식이 반만 참이 된다 — 어느 극단보다 나쁘다. 양쪽에 적용했다.
- **테스트 fake가 또 영구 장애를 모델링해 스스로 걸렸다**(v1.7.36 때와 같은 부류). "enqueued가 1건일 때 실패"는 재시도 시점에도 조건이 성립해 재시도까지 503을 냈다. 실 outbox 서비스(`IndexSyncOutboxService` + `InMemoryIndexSyncRepository`)를 쓰고 **딱 한 번만** 실패하도록 고쳤다 — 부수 효과로 **실 dedup 경로까지 테스트가 타게 됐다**(stub이었다면 dedup을 모델링하지 못해 거짓 중복을 보고했을 것이다).

### Completed work

- [`memory/service.py`](../../../services/application/app/memory/service.py): `promote_candidate`·`_versioned_upsert`의 replay 분기 **양쪽**이 `_enqueue_reindex`를 호출한다. `promote_candidate` 쪽에 근거·비용·적용 범위를 주석으로 남기고 `_versioned_upsert`는 역참조.
  - **replay 분기의 enqueue 실패는 `MemoryReindexEnqueueFailed`로 감싸지 않는다**(주석에 명시). 감싸면 endpoint가 그 memory를 `promoted[]`에 싣는데, replay는 "이번 호출이 mint한 것"이 아니라 v1.6.40 조항을 깬다. 원시 저장소 예외가 그대로 전파돼 평범한 503 arm으로 간다.
- **정본** v1.7.36 → **v1.7.37**: 본문에 "재색인 enqueue는 무조건 choke point" 조항 신설(비용 유계 근거 포함), `promoted[]` 조항의 "재호출 복구 범위"를 **승격과 색인 양쪽 회복**으로 갱신. **과거 changelog 행(v1.6.46)은 소급 수정하지 않았다** — 이력이고, 07-23에 세운 원칙이다. 새 행이 개정을 기록한다.
- OpenAPI 503 description·`CHANGELOG.md`·HANDOFF(추적 부채 삭제 + Active Decisions에 불변식 추가)를 같은 내용으로 갱신.
- 회귀: v1.7.36이 잔여를 잠갔던 테스트를 **회복 단정으로 뒤집었다**(`test_retry_recovers_a_reindex_enqueue_lost_after_a_mint`). over-strict로 **재시도가 재승격은 하지 않음**(`promoted` 빈 배열 · memory 수 불변)을 함께 잠갔다.

### Verification

- **mutation**: replay 분기를 v1.7.36 형태로 되돌리면 `test_retry_recovers_a_reindex_enqueue_lost_after_a_mint` **하나만** 문다.
- 인접 스위트 무손상: `test_memory_vector_index.py`·`test_analysis_apply_api.py` 포함 실행에서 실패 0.

### Decisions (구현자 판단)

- **오너의 "안전하다면"을 조건으로 취급했다.** 검증 결과 정합성은 안전이고 비용만 존재하므로 조건 충족으로 보고 진행했으나, 내가 앞서 생략한 비용을 이 로그와 정본에 명시해 오너가 나중에 다른 판단을 할 근거를 남겼다.
- **backfill 스크립트는 그대로 둔다.** 필수 복구 절차에서 선택 도구로 내려갔을 뿐, 대량 재색인 용도는 유효하다.

### Next steps

- 커밋 후 다음 작업. 남은 갈림길은 dogfood 착수(GATE-1)와 저장소 예외 taxonomy 착수 여부.
