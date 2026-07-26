# HANDOFF

> **다음 작업자가 지금 일을 시작하는 데 필요한 것만.** 이력이 아니다.
> 완료 서술은 여기 쓰지 않는다 — `docs/daily_logs/`(상세) · `docs/system-contract-sot.md` 변경이력 · `CHANGELOG.md`(마일스톤) · `docs/verifications/`(독립 검증)에 이미 있다.
> 편집 규칙은 `CLAUDE.md`·`AGENTS.md`의 "HANDOFF.md" 절에 있다. **길이 상한은 없다** — 대신 **~200줄을 넘으면 자가 검수**하고(그 뒤로는 ~100줄마다) 결과를 아래 한 줄로 남긴다. 길어야 할 이유가 있으면 길어도 된다. 안 보는 것이 문제다.
>
> 마지막 자가 검수: 2026-07-23 · 111줄

## 지금 상태

- 정본은 `docs/system-contract-sot.md` **v1.7.47**(Approved). 미확정 항목은 추측 구현하지 않는다.
- **진행 중 페이즈 — LLM 파이프라인 관측(KPI)**(브리프 `plans/observability-kpi-decisions.md` 승인 D1=B·D2=C·D3=A). **계측 seam은 provider 데코레이터로 확정**(오너 결정 2026-07-25, 브리프 `plans/observability-instrumentation-seam-decisions.md` C안) — `ObservedProvider`가 `generate()` 1회를 레코드 1건으로 만들고, 워크플로 귀속은 `llm_call_scope` contextvar가 나른다. **계측 완료: LLM을 부르는 전 호출부 8종**(`analysis_extractor`·`writing_gate`·`compare_judge`·`query_planner`·`writing_retrieval_planner`·`writing_generation`·`writing_revision`·`writing_report`, 전부 seam C). 남은 것은 read-out(집계 API)뿐이다. 운영기획 포트폴리오는 `docs/observability-kpi-rationale.md`. QUAL-1(제품 품질·수기·dogfood)과 별개 트랙.
- **새 호출부를 계측하는 법**(Phase 7 등): ① `main.py` 조립 지점에서 provider를 `ObservedProvider(inner, call_site=…)`로 감싼다(도메인 코드는 건드리지 않는다). ② 그 호출이 일어나는 요청 경로에서 `llm_call_scope(...)`를 연다 — **감싸기와 scope 개방은 항상 함께 간다. 빠뜨리면 레코드가 조용히 0건인데 스위트는 green이다**(scope 유닛 테스트로는 안 물리므로 배선 회귀를 함께 넣는다). ③ **조립 가드도 함께 넣는다** — 하네스는 `ObservedProvider`를 직접 만들기 때문에 `_default_*`가 감싸기를 빠뜨려도 green이고 **배포에서만** 계측이 사라진다(실측: gate 조립에서 wrapper를 벗겨도 56 passed). 가드는 **리터럴까지 단정한다** — 잘못된 site로 감싸는 것은 안 감싸는 것과 똑같이 틀렸다. ④ 도메인만 아는 판정(gate decision·파생점수)은 `scope.annotate_last(...)`, 최종 도메인 거부는 **`scope.reclassify_last_as_parse_error(...)`**(마지막 레코드가 `success`일 때만 동작 — `provider_error` taxonomy를 덮지 않기 위한 가드)로 flush 전에 얹는다. `ContextSearchFailed` 계열은 같은 모듈의 `reclassify_planner_parse_error(scope, exc)`가 `llm_error` 계보만 걸러 준다 — **endpoint와 worker가 같은 정의를 쓴다**(복제하면 두 정책이 조용히 갈라진다).
- **계측에서 지켜야 하는 계약**(SoT §"LLM 파이프라인 관측(KPI)"): ① 레코드는 **provider가 실제로 호출된 경우에만** — seam C에서는 구조적으로 참이다. ② **실패한 호출도 센다**(성공만 세면 성공률이 영구히 100%). ③ **scope 밖 호출(worker·script)은 기록하지 않는다** — 추측 `project_id`는 오염이다. ④ 격리(`_flush`)를 **좁히지 않는다** — 좁히면 감사 저장소의 pymongo 예외가 전역 handler(v1.7.38)에 도달해 **정상 200이 503으로 뒤집히고**, flush가 `finally`에 있어 요청의 원래 예외까지 덮어쓴다.
- **`parse_error` 재분류는 호출부가 명시할 때만 일어난다**(데코레이터는 도메인 거부를 모른다). v1.7.47부터 **`analysis_extractor`만 재분류하지 않고 나머지 7 site는 재분류한다** — 재분류가 마지막 호출 1건만 건드리므로 repair로 회수된 첫 호출은 `success`로 남고 repair 빈도 신호가 손상되지 않기 때문이다. 따라서 **extractor의 `parse_error`=0은 구조적 사실이지 데이터 부족이 아니다**(`outcome`이 `success`·`provider_error` 둘뿐). **같은 repair 구조인데 정책이 갈리는 상태**이며, 정렬 여부는 아래 오너 결정 대기 항목이다.
- **집계할 때 `correlation_id`는 `call_site`와 함께 읽는다**(v1.7.47): 한 요청이 이제 여러 site를 지난다(revise-and-gate 1요청 = planner+revision+report+gate). site를 고정하지 않고 `correlation_id`당 레코드를 세면 다른 site의 정상 호출이 repair로 집계된다.
- **loop 내부 gate 레코드에는 `decision`·`gate_quality_score`가 없다**(v1.7.47 알려진 공백): 파생점수는 endpoint가 `annotate_last`로 얹는데 revise loop이 round별 판정을 결과에 노출하지 않는다(`WritingLoopStage`는 stage/ordinal/status만). 그 필드는 **독립 `POST …/writing/gate` 호출에만** 채워지므로 집계가 전수 커버리지를 가정하면 안 된다.
- 공개 API 계약(H3)은 닫혀 있다: **`/health`를 제외한 60개 operation 전부**가 realistic 에러 상태를 OpenAPI에 선언하고 **미매핑 500 부채는 0건**이다. 새 endpoint를 추가하면 **`responses=`도 함께** 붙여야 하며, 트랙별 전수 선언 가드 테스트가 빠뜨림을 잡는다. 저장소 장애 503 face는 이제 **예외 없이 전 endpoint 균일**하다 — v1.7.40이 마지막 두 잔여(광의 catch가 pymongo를 삼켜 502로 내던 곳)를 닫았다: `POST …/analysis/jobs/{id}/run`과 `POST …/context-search`의 `persist_rejection`. 둘 다 광의 catch 앞에 `except _STORAGE_ERRORS`를 두어 저장소 예외를 503으로 보낸다. **주의**: 앞으로 endpoint body를 광의 `except Exception`으로 감싸면 그 순간 저장소 예외가 다시 502/도메인 에러로 새므로, 그런 catch를 둘 때는 반드시 그 앞에 `except _STORAGE_ERRORS`를 둔다.
- 회귀 기준선: backend **1531 passed / 601 subtests**(test-mongo 기동), frontend **194 passed / 13 files**, build JS 399.03 kB. **skip 수는 머신마다 다르다** — live Chroma 1건은 항상 skip이고, `elasticsearch` 파이썬 패키지가 없는 머신에서는 lexical retrieval 3건이 추가로 skip된다(2026-07-25 이 머신 = 4 skipped). 숫자가 안 맞으면 회귀를 의심하기 전에 skip 사유부터 `-rs`로 확인할 것.
- **이 머신, 2026-07-24 기준 스택은 사실상 내려가 있다**: `application`·`gateway`·`mongo`·`elasticsearch`·`embedding`·`chroma`·`test-mongo`가 `Exited`, `frontend`와 두 worker만 떠 있다(worker는 의존 서비스가 없어 무의미하게 도는 중). 기동은 오너 몫.
- **현존 컨테이너는 전부 구 정의로 만들어졌다** — 옛 포트(`27019`/`8000`/`9200`…)와 `ulimits` 없는 상태다. `docker compose up`이 새 정의로 재생성하므로 별도 조치는 필요 없다.

## 기동 · 실행법

**포트는 전용 대역으로 repo에 고정돼 있다.** env 없이 `docker compose up`만으로 어느 머신에서든 같은 포트로 뜬다. 값과 근거는 [`.env.example`](.env.example)에 있고, 머신별로 바꿔야 하면 `.env`로 복사한다(커밋 금지).

| 서비스 | 포트 | 서비스 | 포트 |
|---|---|---|---|
| application | 8520 | chroma | 8523 |
| gateway | 8521 | elasticsearch | 9520 |
| embedding | 8522 | frontend | 5520 |
| mongo | 27520 | test-mongo | 27020 |

표준 포트(27017·8000~8003·9200·5173)를 쓰지 않는 이유는 `.env.example` 상단에 있다 — 여러 머신을 옮겨 다니는 프로젝트라 충돌하고, 임시 env 회피는 repo에 안 남아 문서에 머신-로컬 관측치가 사실처럼 적히게 된다.

**백엔드 테스트** — `docker compose -f docker-compose.test.yml up -d` 후 `python3 -m pytest -q`. env 불필요(기본 URI가 27020 replica set `rs-test`). 미기동이면 Mongo 테스트가 **skip**(실패 아님). 끝나면 `... down`.

**live Chroma 테스트**(호스트 `pytest`에서는 항상 skip되는 1건) — 호스트를 오염시키지 않고 이미 `chromadb`가 있는 application 이미지에서 돌린다:

```bash
docker compose up -d --no-deps chroma
docker compose run --rm --no-deps -v "$PWD/tests:/app/tests" \
  -e CHROMA_TEST_URL=chroma:8000 \
  application python -m unittest tests.test_chroma_adapter.ChromaAdapterLiveTest -v
```

**프론트** — `cd frontend && npm run gen:api && npx tsc --noEmit && npm run build && npx vitest run`.

## 함정 (모르면 시간을 잃는 것들)

- **출시된 프롬프트 본문은 immutable이다.** `tests/test_prompt_templates.py`가 `analysis_extract` v1/v2/v3 본문 sha256을 핀한다. 본문을 고치면 테스트가 깨지는데 **해시를 갱신하면 안 되고 새 버전을 만들어야 한다.** 어긴 결과: 기존 Mongo를 가진 배포가 `PromptTemplateConflict`로 전부 죽어 스택이 3일간 안 떴다. Mongo에 영속되는 프롬프트는 `analysis_extract` 하나뿐이라, 다른 프롬프트를 영속으로 옮기면 sha256 핀도 함께 확장해야 한다.
- **compose의 `ulimits.nofile`은 튜닝이 아니라 필수다.** Docker 기본 1024면 WiredTiger가 `Too many open files`로 mongod를 죽이는데, **test-mongo에서는 증상이 skip이 아니라 failure라 코드 회귀처럼 보인다.** 배포 `mongo`(64000)·`elasticsearch`(65535)에도 같은 이유로 들어가 있다 — 값이 다른 것은 각 데몬이 요구하는 최소치를 그대로 쓴 것이다.
- **백엔드는 `pytest`가 아니라 `python -m pytest`로 실행한다.**
- live 작업 시 외부 llama(`192.168.1.22:9080`)가 죽어 있으면 in-stack llama로 돌린다. `-hf`는 재다운로드 정체가 잦아 캐시 blob을 `-m`으로 직접 지정해야 뜬 전례가 있다.

## Active Decisions (앞으로의 작업을 구속하는 것)

완료 이력이 아니라 **표준 제약**만. 근거는 각 `docs/plans/*-decisions.md`.

- **개발 단계(2026-07-20 오너)**: "Gate 우선" 단계는 끝났다. 지금은 **Gate ↔ UI/UX 왕복**이 주축이다.
- 아이디에이션·계획이 충돌하면 임의 구현 없이 오너 결정을 받는다. 나중 요청이 기록된 결정과 충돌하면 어느 쪽이 canonical인지 먼저 묻는다.
- monorepo + 독립 LLM Gateway/Worker, Application = FastAPI. MVP는 계정/인증 없는 단일 사용자이며 경계는 `project_id`.
- frontend = React + TS + Vite, 서빙은 별도 compose 서비스(nginx). OpenAPI→TS 타입 생성 + 얇은 `fetch` 래퍼.
- **Core SOT**: offset = raw Unicode code point, `content_hash` = raw UTF-8 SHA-256. `source_ref` span은 단일 `source_block` 안에 든다. persistence는 Mongo transaction 기본이고 non-transaction fallback은 **single-writer local/test 전용**. project/draft는 archive(soft delete)하고 snapshot/version/source_ref는 보존한다(archive = 읽기 허용, 본문 쓰기·rename 409).
- **memory는 append-only**. AI가 직접 덮어쓰지 않고 검색·대조·Gate·검토·versioned upsert를 거친다. canonical만 `memory_vectors`에 색인하며 트리거는 async outbox→worker다. semantic 매칭은 **off 기본**.
- **재색인 enqueue는 무조건 choke point다**(v1.7.37): canonical을 만드는 모든 경로가 `MemoryService._enqueue_reindex`를 지나고 **idempotent replay도 재enqueue한다**. outbox가 PENDING/RUNNING 항목에만 dedup하므로 pending 중 replay는 no-op이고, drain된 뒤의 replay만 재색인을 한 번 더 돌린다(upsert라 오염 아님). **`promoted[]` 보고 의미론은 불변** — replay는 여전히 제외되며 바뀐 것은 색인 side-effect뿐이다.
- taxonomy 3종(`character_observation`/`event_observation`/`open_question_observation`), provenance `source_observed`/`ai_inferred`.
- **agent loop 계약층은 더 진행하지 않는다**(tool-call parsing·wire format 미계약). sub-agent spawn 없이 bounded flat loop만.
- **에러 계약(H3)**: 본문은 균일 `{"detail": <string>}`. 상태코드=기계용, `detail`=사람용이라 **`detail` 문자열로 분기하면 안 된다**. 503은 **세 얼굴** — 협력자 **미구성**(배포 구성) · 데이터 **무결성**(`scripts/migrate_ordered_units.py`) · **정본 저장소 장애**(v1.7.35, 복구 후 재시도가 유효한 유일한 얼굴). **상류가 없는 게 아니라 있는데 실패한 것은 502**이고, **정본 저장소는 상류가 아니라 503**이다. 저장소 face는 `create_app`의 **전역 exception handler**가 매핑하므로 새 endpoint가 자동 상속한다 — 다만 **`responses=`에 503을 붙이는 것은 여전히 수동**이고 전수 가드가 빠뜨림을 잡는다(`/health`만 제외).
- **균일 본문의 유일한 예외 = partial envelope**, 허용 지점 **정확히 6곳**(revise-and-gate 4 · accept 1 · auto-promote 1). 되돌릴 수 없는 성공 부분이 이미 영속된 실패 경로만 해당하며, 새 Union은 정본 목록을 함께 넓히는 명시 결정으로만 들어온다(트랙별 over-strict 가드가 drift를 막는다).

## 추적 부채

- **[누수 아님, 의존성 주의] `context_search/service.py:199`·`:406`의 `embed()`**: 자체적으로 `EmbeddingProviderError`를 안 잡지만 호출자(step runner `:752`·`:835`)의 광의 `except Exception` → `BACKEND_ERROR` → 502가 이미 보호한다. **그 catch를 좁히면 그 순간 500 누수가 된다.**

## Owner Decisions Needed

- **★ dogfood 착수(GATE-1)** — 가장 큰 갈림길. 실 12B 풀스택 관통은 끝났고 기술적 선행 조건은 없다. 착수하면 `OPS-1` Ready 승격.
- **`analysis_extractor`를 D4로 정렬할지**(v1.7.47): 지금 이 site만 최종 도메인 거부를 `parse_error`로 재분류하지 않아 같은 repair 구조인 `compare_judge`와 정책이 갈린다. 정렬하면 두 site가 같은 규칙을 따르고, 두면 v1.7.46 결정이 유지된다. 어느 쪽이든 이행 무손실 증명이 필요한 별도 증분.
- **loop의 round별 gate decision 노출 여부**(v1.7.47 공백): 노출하면 loop 내부 gate 레코드에도 파생점수를 얹을 수 있다. 도메인 계약(`WritingLoopStage`) 변경이라 D2-B(파생점수 정교화)와 함께 볼 사안.

## Next Tasks

1. **관측 KPI 증분 5** = `GET …/observability/kpi` 집계 API + H3 에러 선언. 계측은 끝났고 남은 것은 read-out이다. 집계 규칙 3개가 계약에 고정돼 있다 — 토큰은 `success`+`parse_error`만 · repair 빈도는 **site를 고정한** `correlation_id`당 레코드 수 · `gate_quality_score`는 커버리지가 전수가 아니다(loop 공백).
2. **dogfood 첫 세션에서 UI 레벨 확인**(백엔드는 라이브 확증됐고 화면만 미검증): 비동기 패드 렌더 · 이어쓰기 탭 완료 배지 · 5초 폴링 · "다시 시도" 버튼 · 탭 전환 후 폴링 생존.
3. **dogfood 관찰 항목**: `report field must be an array` 실패율(12B 간헐 비-배열, repair가 흡수 — 잦으면 repair 횟수/프롬프트 축 판단) · `analysis_extract_v4`의 `aspect` 오분류 빈도 · scratch per-draft 상한(기본 20) 밀어냄.
4. **Deferred(오너 결정 선행)**: 중첩 chapter→scene tree · ProjectBrief→Draft provenance · 관계 graph/완전 timeline · saved publication manifest · Phase 7 대화형 수정(`plans/07-conversational-authoring.md`).

## Project Structure

```text
docker-compose.yml            # 배포 스택: application·mongo(rs0)·gateway·embedding·chroma·elasticsearch(nori)·worker·generation_worker·frontend(nginx)
docker-compose.test.yml       # 테스트 전용 단일노드 RS mongo(27020) — 명시 -f 로만 뜬다
docker-compose.llama.yml      # opt-in: in-stack llama.cpp GPU 서버(9080)
.env.example                  # 호스트 게시 포트 전용 대역 + 근거
CLAUDE.md / AGENTS.md         # 작업 규칙(동일 내용). HANDOFF 편집 규칙·자가 검수 트리거 포함
docs/
├── system-contract-sot.md    # ★ 정본 계약 + 변경이력(버전별)
├── plans/                    # 계획 + 착수 결정 브리프(*-decisions.md)
├── daily_logs/YYYY-MM-DD/    # 작업 상세 이력
├── verifications/YYYY-MM-DD/ # 독립 검증 기록
├── runbooks/                 # 로컬 llama 등 운영 절차
└── abstract.md 등            # 보존된 아이디에이션 원본
schemas/                      # W0 등 계약 schema
scripts/                      # 마이그레이션·live smoke·worker 엔트리포인트
services/
├── application/app/          # FastAPI 본체
│   ├── main.py               # 전 endpoint + 에러 선언 상수(_ERRORS_*)
│   ├── core_sot/             # 정본 저장(project/draft/version/snapshot/source_ref)
│   ├── analysis/ memory/     # 추출·후보·비교·승격
│   ├── context_search/       # ContextPackage 구성 + Gate
│   ├── writing/              # 생성·Gate·revise·accept·scratch·생성 job
│   ├── indexing/             # vector/lexical 색인, embedding provider
│   └── observability/        # per-LLM-call 감사 + ObservedProvider/llm_call_scope(seam C)
├── llm_gateway/              # LLM 경계(ProviderError taxonomy)
└── embedding/                # 임베딩 서비스(BGE-m3-ko, 1024-dim)
frontend/                     # React+TS+Vite SPA
├── nginx.conf                # /api 리버스 프록시(변수 upstream + resolver)
└── src/api/schema.d.ts       # gen:api 생성물 — 손으로 고치지 않는다
tests/                        # 백엔드 회귀(python -m pytest)
```
