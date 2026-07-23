# HANDOFF

> **다음 작업자가 지금 일을 시작하는 데 필요한 것만.** 이력이 아니다.
> 완료 서술은 여기 쓰지 않는다 — `docs/daily_logs/`(상세) · `docs/system-contract-sot.md` 변경이력 · `CHANGELOG.md`(마일스톤) · `docs/verifications/`(독립 검증)에 이미 있다.
> 편집 규칙은 `CLAUDE.md`·`AGENTS.md`의 "HANDOFF.md" 절에 있다. **길이 상한은 없다** — 대신 **~200줄을 넘으면 자가 검수**하고(그 뒤로는 ~100줄마다) 결과를 아래 한 줄로 남긴다. 길어야 할 이유가 있으면 길어도 된다. 안 보는 것이 문제다.
>
> 마지막 자가 검수: 2026-07-23 · 111줄

## 지금 상태

- 정본은 `docs/system-contract-sot.md` **v1.7.34**(Approved). 미확정 항목은 추측 구현하지 않는다.
- 공개 API 계약(H3)은 닫혀 있다: 60개 endpoint가 realistic 에러 상태를 OpenAPI에 선언한다. 새 endpoint를 추가하면 **`responses=`도 함께** 붙여야 하며, 트랙별 전수 선언 가드 테스트가 빠뜨림을 잡는다.
- 회귀 기준선: backend **1453 passed / 1 skipped / 525 subtests**(test-mongo 기동 시), frontend **194 passed / 13 files**, build JS 399.03 kB.
- **이 머신의 스택은 내려가 있다**: `application`·`gateway`·`mongo`·`elasticsearch`·`embedding`이 `Exited (255)`. `frontend`·`chroma`·`test-mongo`만 떠 있다. 기동은 오너 몫.

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
- **test-mongo의 `ulimits.nofile 64000`은 튜닝이 아니라 필수다.** Docker 기본 1024면 WiredTiger가 `Too many open files`로 mongod를 죽이는데, **증상이 skip이 아니라 failure라 코드 회귀처럼 보인다.**
- **배포 `mongo`에는 그 `ulimits`가 없다**([docker-compose.yml](docker-compose.yml)) — 같은 크래시 조건을 구조적으로 공유한다. 4줄로 닫히지만 컨테이너 재생성이 필요해 미적용. 오너 판단.
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
- taxonomy 3종(`character_observation`/`event_observation`/`open_question_observation`), provenance `source_observed`/`ai_inferred`.
- **agent loop 계약층은 더 진행하지 않는다**(tool-call parsing·wire format 미계약). sub-agent spawn 없이 bounded flat loop만.
- **에러 계약(H3)**: 본문은 균일 `{"detail": <string>}`. 상태코드=기계용, `detail`=사람용이라 **`detail` 문자열로 분기하면 안 된다**. 503은 두 얼굴 — 협력자 **미구성**(배포 구성) vs 데이터 **무결성**(`scripts/migrate_ordered_units.py`). **없는 게 아니라 있는데 실패한 것은 502다.**

## 추적 부채

- **[오너 판단 필요] `auto_promote_job` 미매핑 500**: 승격 루프가 `try` 밖이라 예외 시 500이 샌다([`main.py`](services/application/app/main.py)). **코드 매핑이 아니라 계약 질문**이라 임의로 고르지 않았다 — 일부 승격 뒤 실패하면 부분 성공 봉투인가 전체 실패인가? writing accept의 502 partial이 참고지만 그쪽은 "정본은 저장됐다"가 명확한 반면 여기는 승격 개수가 가변이다. 착수 시 결정 브리프 권장.
- **[누수 아님, 의존성 주의] `context_search/service.py:199`·`:406`의 `embed()`**: 자체적으로 `EmbeddingProviderError`를 안 잡지만 호출자(step runner `:752`·`:835`)의 광의 `except Exception` → `BACKEND_ERROR` → 502가 이미 보호한다. **그 catch를 좁히면 그 순간 500 누수가 된다.**

## Owner Decisions Needed

- **★ dogfood 착수(GATE-1)** — 가장 큰 갈림길. 실 12B 풀스택 관통은 끝났고 기술적 선행 조건은 없다. 착수하면 `OPS-1` Ready 승격.
- 배포 `mongo` `ulimits` 적용 여부(스택 재생성 필요).
- `auto_promote_job` 부분 성공 의미론(위 추적 부채).

## Next Tasks

1. **dogfood 첫 세션에서 UI 레벨 확인**(백엔드는 라이브 확증됐고 화면만 미검증): 비동기 패드 렌더 · 이어쓰기 탭 완료 배지 · 5초 폴링 · "다시 시도" 버튼 · 탭 전환 후 폴링 생존.
2. **dogfood 관찰 항목**: `report field must be an array` 실패율(12B 간헐 비-배열, repair가 흡수 — 잦으면 repair 횟수/프롬프트 축 판단) · `analysis_extract_v4`의 `aspect` 오분류 빈도 · scratch per-draft 상한(기본 20) 밀어냄.
3. 위 추적 부채 2건.
4. **Deferred(오너 결정 선행)**: 중첩 chapter→scene tree · ProjectBrief→Draft provenance · 관계 graph/완전 timeline · saved publication manifest · Phase 7 대화형 수정(`plans/07-conversational-authoring.md`).

## Project Structure

```text
docker-compose.yml            # 배포 스택: application·mongo(rs0)·gateway·embedding·chroma·elasticsearch(nori)·worker·generation_worker·frontend(nginx)
docker-compose.test.yml       # 테스트 전용 단일노드 RS mongo(27020) — 명시 -f 로만 뜬다
docker-compose.llama.yml      # opt-in: in-stack llama.cpp GPU 서버(9080)
.env.example                  # 호스트 게시 포트 전용 대역 + 근거
CLAUDE.md / AGENTS.md         # 작업 규칙(동일 내용). HANDOFF 편집 규칙·상한 포함
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
│   └── indexing/             # vector/lexical 색인, embedding provider
├── llm_gateway/              # LLM 경계(ProviderError taxonomy)
└── embedding/                # 임베딩 서비스(BGE-m3-ko, 1024-dim)
frontend/                     # React+TS+Vite SPA
├── nginx.conf                # /api 리버스 프록시(변수 upstream + resolver)
└── src/api/schema.d.ts       # gen:api 생성물 — 손으로 고치지 않는다
tests/                        # 백엔드 회귀(python -m pytest)
```
