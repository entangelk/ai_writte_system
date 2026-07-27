# 2026-07-27 작업 로그

## Task — 베타 머신 스택 기동 + HANDOFF 머신 구분 절 + 검증 지적 반영

### Goals

- HANDOFF Next Tasks #1(스택을 올리면 바로 할 것 — 관측 화면 육안 확인)의 선행: 이 **베타 테스트
  머신**(외부 LLM `192.168.1.22`)에서 배포 스택을 실제로 기동한다.
- 오너 요청: HANDOFF 상단에 머신 구분(알파·베타·감마) 기록을 남겨 "환경과 안 맞는다"는 오해를 없앤다.
- 오너의 독립 검증(조건부 합격)이 지적한 차단 1건·보강 3건을 반영하고 커밋한다.

### Completed work

- **HANDOFF 머신 구분 절 신설** [`HANDOFF.md`](../../../HANDOFF.md): 상단에 알파(배포·in-stack GPU
  llama)·베타(지금 이 머신·외부 LLM `192.168.1.22:9080`)·감마(노트북·LLM 불가, CPU 컨테이너/DB만) 표와,
  "무엇을 띄울 수 있는지(항구적 성질) vs 지금 무엇이 떠 있는지(머신-로컬 관측치)"를 구분하라는 규칙.
- **베타 머신 `.env` 생성**(커밋 금지 — gitignore 확인): `LLAMA_BASE_URL=http://192.168.1.22:9080`.
  gateway 기본값 `host.docker.internal:9080`(= 호스트 로컬)을 외부 12B 서버로 덮는다.
- **전체 스택 기동**: `docker compose up -d --build`(3~4일 전 이미지가 관측 코드 이전이라 재빌드).
  기동 중 발생한 `PromptTemplateConflict`를 해소(아래 Issues) 후 재기동.
- **frontend healthcheck 결함 수정** [`docker-compose.yml`](../../../docker-compose.yml) `:360-364`:
  probe URL `http://localhost/` → `http://127.0.0.1/`. 근거는 아래 Issues.

### Issues found — PromptTemplateConflict (기존에 문서화된 함정)

- 스택 기동 시 `application`·`generation_worker`가 `PromptTemplateConflict`로 죽었다. 원인은 dev
  `mongo_data` 볼륨에 굳은 **구 `analysis_extract_v3` 프롬프트 본문**이 현재 코드의 canonical v3와
  달라서다([`prompt_templates.py:118-121`](../../../services/application/app/analysis/prompt_templates.py#L118):
  같은 version인데 body가 다르면 충돌).
- **코드 회귀가 아님**을 확인: canonical v3 sha256을 재계산 → `4376310…`이고
  [`tests/test_prompt_templates.py:36-38`](../../../tests/test_prompt_templates.py#L36)의 pin과 정확히 일치.
  코드↔테스트는 자기일관적이고, 저장 볼륨만 stale했다. 이 실패 양상은 테스트가 "2026-07-22 boot
  failure"로 명시해 둔 기존 패턴(HANDOFF 함정 절).

### User Decisions and Rationale — 데이터 볼륨 초기화

- 해소 방식으로 오너에게 3안(구 v3 문서 1건만 삭제 / mongo 볼륨 전체 초기화 / 보류)을 물었고,
  **오너가 "mongo 볼륨 전체 초기화"를 선택**했다 — fresh 상태에서 관측 화면을 확인하려는 의도.
- 구현 판단으로 `down -v`(모든 볼륨) 대신 **데이터 볼륨(mongo·es·chroma)만 제거하고 embedding 모델
  캐시(`embedding_cache`)는 보존**했다. 오너 의도(fresh 데이터)는 그대로 충족하면서 BGE-m3-ko
  재다운로드 비용을 피한다.
- **소거된 것**: 이전 dev DB 전체(drafts·versions·source_refs·memory·llm_call_audits·gate_findings 등)와
  ES/chroma 색인. 보존: embedding 모델 캐시. 즉 관측 화면·모든 데이터는 **빈 상태부터** 시작한다.
- 재기동 후 9개 서비스가 뜨고 application이 healthy, `/health` 200 확인.

### Issues found — 검증이 잡은 차단 1건: HANDOFF에 거짓 관측치

- 오너 요청 독립 검증(`docs/verifications/2026-07-27/stack_bringup_handoff_machine_section.md`,
  **조건부 합격**)이 **B-1**을 지적: 내가 HANDOFF에 "9개 서비스 전부 Up·healthy"라고 적었으나 실측은
  **healthy 6 / unhealthy 1(frontend) / healthcheck 없음 2(worker·generation_worker)**. `up` 출력에서
  추론하고 `docker compose ps`로 확인하지 않은, CLAUDE.md가 정확히 금지하는 실패 양상. 내가 같은
  HANDOFF에 "머신-로컬 관측치를 믿지 말라"는 절을 쓰면서 저지른 것이라 특히 반영이 필요했다.
- **직접 재측정으로 확인**(검증자 진술도 회의적으로): `docker compose ps` → healthy 6
  (application·gateway·mongo·elasticsearch·embedding·chroma), frontend unhealthy(FailingStreak 65),
  worker·generation_worker는 Health 컬럼 공란(healthcheck 미정의, async 워커라 by design).

### Issues found — frontend healthcheck 근본 원인 (사전 존재 결함)

- **직접 재현**: frontend 컨테이너 안에서 `wget http://localhost/` → exit 1 "Connection refused",
  `wget http://127.0.0.1/` → exit 0. `/etc/hosts`가 `::1 localhost`를 함께 매핑해 busybox wget이
  IPv6를 먼저 시도하는데 nginx는 `listen 80;`(IPv4 `0.0.0.0`만) → refused. **기능은 정상**(host
  `curl localhost:5520` → 200), healthcheck만 거짓 보고.
- `nginx.conf`·frontend Dockerfile은 `46f6009`(frontend 첫 슬라이스) 이후 미변경 → 내 `--build`가
  유발한 것이 아니라 **사전 존재 결함**. 검증자도 같은 결론.
- **수정**: healthcheck probe를 `http://127.0.0.1/`로 변경(IPv4 강제, nginx `listen 80`과 일치).
  `listen [::]:80;` 추가 대신 이 최소 수정을 택한 이유는 nginx의 서빙 동작(IPv4 전용)을 바꾸지 않고
  healthcheck의 거짓 보고만 교정하기 때문(§3 surgical). 수정 후 frontend가 healthy로 전환됨을 확인.

### Verification

- **검증자 판정**: 조건부 합격. 진짜로 맞는 것(재확인 완료) — `/health` 200 · operation 62개 ·
  관측 route 등록 · gateway 컨테이너에서 `192.168.1.22:9080` TCP+/health 200 종단 도달 ·
  PromptTemplateConflict 진단이 코드 메커니즘·테스트 pin·알려진 패턴과 일치. 조건 = B-1 정정.
- **비검증 한계(검증자 명시)**: 저장돼 있던 구 v3 sha `fb4e272…`는 볼륨 초기화로 증거가 소거되어
  재확인 불가. 진단의 저장 측은 내 진술에 의존(정본 측 재확인 + 알려진 패턴 + 코드 일치로 개연성은 충분).
- **반영 후 재측정**: frontend healthcheck 수정 후 재생성 → healthy 전환 확인. 최종 상태 =
  **healthy 7**(application·gateway·mongo·elasticsearch·embedding·chroma·frontend) + **healthcheck
  없음 2**(worker·generation_worker, by design). "9개 전부 healthy"라고 쓰지 않는다 — 워커 2종은
  구조적으로 healthcheck가 없다.

### Decisions (구현자 판단)

- **볼륨 초기화 범위를 데이터 볼륨으로 국한**(embedding 캐시 보존): 오너 의도 충족하면서 재다운로드 회피.
- **frontend healthcheck는 URL 최소 수정**(nginx listen 미변경): 서빙 동작을 넓히지 않고 거짓 보고만 교정.
- **`.env`는 커밋하지 않는다**: 외부 LLM IP는 베타 머신-로컬 배선이라 repo 정본이 아니다. HANDOFF
  머신 표에는 성질("외부 LLM")로 적고 구체 IP는 머신-로컬로 마킹.

### Next steps

- **A/B 갈림길(오너 대기)**: (A) 실 12B로 파이프라인을 관통시켜 `llm_call_audits`를 적재 → 관측 화면
  육안 검증 가능화 / (B) 빈 상태로 오너가 UI에서 dogfood. 검증자·나 모두 A를 권하되, B-1 정정이 선행.
- 관측 화면 URL: `http://localhost:5520/projects/:id/observability`. DB가 fresh라 지금은 빈 상태만 보인다.

---

## Task — 외부 API 확장성 확인 + 인증/외부 API 브리프 결정 확정 (문서만)

### Goals

- 오너가 인증 착수 전에 "임베딩·리랭커·LLM을 외부 API로 붙일 수 있는 확장성"을 확인 요청.
- 확인 결과를 바탕으로 외부 API 확장 계획(결정 브리프)을 세우고, 인증 브리프의 D1~D8까지 함께 확정.

### 확장성 확인 결과 (코드 실측)

- **LLM**: gateway 경계·OpenAI 호환 wire는 있으나 **인증 헤더 주입 지점 없음**([`httpx_transport.py:37`](../../../services/llm_gateway/app/httpx_transport.py#L37))·provider 선택 config 없음(`LlamaCppProvider` 하드코딩) → keyless OpenAI 호환만 지금 됨(베타 12B가 그 경로).
- **임베딩**: `EmbeddingProvider` Protocol seam 있음, `RemoteEmbeddingProvider`는 인하우스 `/embed` 계약 전용·인증 없음 → 외부는 어댑터 1개 추가 필요.
- **리랭커**: **뉴럴 cross-encoder 리랭커는 없음.** 현재 리랭킹은 **RRF 융합만**([`context_search/service.py:279`](../../../services/application/app/context_search/service.py#L279)). 내가 처음 "리랭커 개념 자체가 없다"고 답한 것은 **틀렸고**(RRF 융합 리랭킹은 있음), 오너 지적으로 정정 — 정확히는 "뉴럴 cross-encoder 리랭커가 없다".
- **Elasticsearch/검색엔진**: 있음(lexical + nori). 벡터(Chroma)+lexical(ES)+RRF 융합이 실제 RAG 구성.

### User Decisions and Rationale — 외부 API 확장 브리프 (신규 `plans/external-api-expansion-decisions.md`)

- **D1 = 세 축 전부 확장, 슬라이스 분리**(LLM → 임베딩 → 리랭커 각각 독립). 오너: "모두 확장이 맞는데 LLM과 임베딩 슬라이스는 별도로." wire·실패모드·조달이 축마다 달라 묶으면 성격이 섞인다.
- **D2=A**(generic OpenAI 호환), **D3=A**(env 키, 인증 시크릿 재사용), **D4=A**(전역 기본 + site별 후속) — 추천안 수용.
- **D5 = 리랭커 포함(유예 해제)**. 로컬 self-host **`dragonkue/bge-reranker-v2-m3-ko`**(임베딩 서비스 패턴) + 외부 리랭커 API도 붙일 `RerankProvider` seam. 오너: "로컬엔 이거 쓰고, 외부꺼도 쓸 수 있게 뚫어놓기." **이 모델은 2026-07-05에 임베딩으로 잘못 지목됐다 유예됐던 바로 그 cross-encoder**가 제 역할로 복귀한 것. 리랭커 API는 공통 wire 표준이 없어(Cohere·Jina·Voyage 각자) provider별 어댑터로 붙는다.

### User Decisions and Rationale — 인증 브리프 D1~D8 (`plans/multi-user-auth-cms-decisions.md`)

- **D1=A**(Application 내부 모듈), **D2=A**(세션+HttpOnly 쿠키) **+ 보안 하드닝**(오너 "인증은 곧 보안"): Argon2id 해시·HttpOnly/Secure/SameSite=Lax·Mongo 서버측 세션(즉시 무효화)·CORS 계속 닫음.
- **D3=A**(`Project.owner_id` 격리). **공유·협업 글쓰기는 미래 확장으로 유예**(오너 "생각 안 해봤다, 나중에") — D3=A가 `members[]`/workspace 승격 문을 닫지 않음. HANDOFF에 미래확장 메모 남김.
- **D4 = 마이그레이션 불요, 개발 데이터 폐기 허용**. 오너: "개발단계라 기존 데이터 싹 날려도 됨, 굳이 하면 A." 정본 보존 정책은 *실 창작물* 보호이지 *개발 테스트 데이터*가 아니며 오늘 볼륨을 이미 초기화해 귀속 대상이 사실상 없다. **실 데이터가 쌓인 뒤면 A(부트스트랩 관리자 귀속)로 되돌린다**는 조건 명시.
- **D5=A**(2단계 archive→관리자 영구삭제) **+ 파기=all delete(전체 그래프)**. 오너: "영구보존은 *작업* 층위, CMS 삭제는 *관리* 층위(작업 상위)라 진짜 삭제, all delete가 맞다." 부분 삭제(고아 데이터) 금지가 이 결정으로 확정.
- **D6=A**(최소 관리자, additive).
- **D7=A**(dependency + 전수 가드) — **오너가 "보안 중점으로 구현자 선택" 위임**. 보안 근거: 실패 모드가 데이터 유출이라, 미들웨어(B)는 소유권(데이터 기반) 검사 불가·신규 경로 조용히 열림, 서비스층(C)은 시그니처 오염. A만이 authn+authz를 경계에서 강제하고 누락을 green으로 통과 못 하게 하는 fail-closed 전수 가드를 얹는다(H3·관측 조립 가드 선례).
- **D8 = 브리프 7단계 유지**(D4가 마이그레이션 불요라 2단계 축소). 오너 미명시 → 구현자 제안 유지, 이견 시 조정.

### Decisions (구현자 판단)

- **두 브리프 다 "결정됨/착수 대기"로 상태 전환**하되 코드·스키마·정본은 안 건드렸다 — 착수는 인증 슬라이스이고, 각 슬라이스가 자기 계약을 정본에 함께 적는 것이 이 repo 규칙이라 지금 정본을 미리 고치면 "문장뿐인 계약"과 "선 코드"가 섞인다.
- **D7·D4·Argon2id·D8은 구현자 판단이 들어간 지점**이라 브리프·work_log에 근거를 명시하고 오너가 veto할 수 있게 남겼다.

### Next steps

- 오너 확인 후: 인증 슬라이스 D8-1(사용자·세션 저장 + 로그인 API)부터 착수. 그 뒤 외부 API(LLM→임베딩→리랭커), 시크릿은 인증 산출물 재사용.
- dogfood(★)와 인증의 선후는 아직 열려 있음(오너 "인증 먼저"지만 dogfood를 앞에 끼울지 미결).
