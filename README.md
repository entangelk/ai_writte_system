# AI Writing System

개인 창작자를 위한 **글쓰기 운영체제** — 사용자의 원고·설정·세계관·문체·분석 결과를 장기 기억으로
축적하고, 글쓰기 시점마다 필요한 기억만 검색해 제공하는 시스템이다. 단순 "AI 글쓰기 챗봇"이 아니라,
**MongoDB 정본(SOT) + Narrative Memory + Agentic Search**를 결합해 일관성 있는 장편 창작을 돕는 것을
목표로 한다.

모든 AI 출력(생성·분석)은 곧바로 정본이 되지 않고 **candidate**로 남아, Gate와 검토·결정적 승격을
거쳐 기억으로 반영된다.

## 이 저장소를 읽는 세 축

같은 시스템을 **기획 · 개발 · 서비스** 세 관점에서 문서로 남겼다. 어느 쪽이 궁금한지에 따라
들어가는 문이 다르다.

| 축 | 답하는 질문 | 시작점 |
|---|---|---|
| **[기획](#기획--무엇을-왜-만드는가)** | 무엇을 왜 만드는가. 어디까지가 MVP인가 | [`docs/product-overview.md`](docs/product-overview.md) · [`docs/observability-kpi-rationale.md`](docs/observability-kpi-rationale.md) |
| **[개발](#개발--어떻게-만들어졌는가-설계-결정과-검증)** | 결정을 어떻게 내리고 어떻게 검증하는가 | [`docs/system-contract-sot.md`](docs/system-contract-sot.md) · [`docs/plans/README.md`](docs/plans/README.md) |
| **[서비스](#서비스--어떻게-돌리고-지켜보는가)** | 어떻게 띄우고, 무엇을 보고, 어떻게 고치는가 | [`HANDOFF.md`](HANDOFF.md) · [`docs/runbooks/local-llama-server.md`](docs/runbooks/local-llama-server.md) |

---

## 기획 — 무엇을, 왜 만드는가

### 풀려는 문제

장편 창작에서 무너지는 것은 문장력이 아니라 **일관성**이다. 인물의 말투가 3장과 17장에서 다르고,
20장 전에 죽은 인물이 되살아나고, 작가 자신도 "그때 그 설정이 뭐였더라"를 못 찾는다. 범용 챗봇은
대화창을 벗어나면 아무것도 기억하지 못하므로 이 문제를 구조적으로 풀 수 없다.

그래서 이 시스템의 중심은 생성 모델이 아니라 **기억**이다. 원고·설정·세계관·문체를 장기 기억으로
축적하고, 글을 쓰는 시점마다 **필요한 조각만 검색해** 모델에 준다.

### 제품 원칙 (기획 단계에서 못박은 것)

- **AI 출력은 정본이 아니다.** 생성·분석 결과는 전부 **candidate**로 남고, Gate 판정과 사람의
  검토를 거쳐야 기억이 된다. "AI가 쓴 것이 곧 사실"이 되는 순간 기억이 오염되기 때문이다.
- **기억은 append-only.** 덮어쓰지 않고 버전을 쌓는다. 잘못된 갱신이 과거를 지우지 못한다.
- **모든 주장에는 근거 포인터가 붙는다**(`source_ref`). "어디서 나온 설정인가"를 원문 위치까지
  되짚을 수 있어야 작가가 AI의 판단을 검증할 수 있다.

**제품 컨셉·MVP 범위·핵심 위험을 한 자리에서 보려면
[`docs/product-overview.md`](docs/product-overview.md)** — *무엇을, 누구를 위해, 어디까지*를
**현재 상태 기준**으로 정리한 한 장 요약이다. 원안에서 달라진 지점(단일 사용자 → 다중 사용자,
추출 5종 → 3종 등)을 따로 모아 뒀다.

전체 구상과 대안 검토는 [`docs/abstract.md`](docs/abstract.md)에 있다 —
**§1 핵심 제품 컨셉** · **§2 핵심 설계 원칙** · **§15 MVP 범위 제안** · **§16 핵심 위험과 대응**.
다만 이것은 **2026-06 초안**이라 현재 상태와 다른 곳이 있다(위 한 장 요약 §5).
확정된 제품 경계·불변 원칙은 [`docs/plans/00-foundations.md`](docs/plans/00-foundations.md)로 내려왔다.

### 무엇을 먼저 만드는가 (Phase ↔ MVP)

기술 의존성 순서(Phase)와 사용자에게 전달되는 가치 묶음(MVP)은 **1:1이 아니다.** 그 매핑을
[`docs/plans/README.md`](docs/plans/README.md#phase와-mvp의-관계)에 표로 유지한다. 제품화에 필요하지만
당장 급하지 않은 것들은 **트리거가 왔을 때 하나씩 여는 백로그**로 분리했다 —
[`docs/plans/product-readiness-backlog.md`](docs/plans/product-readiness-backlog.md).

### 운영 KPI 기획

> **"지금 이 AI가 제대로 일하고 있는가?"** — LLM 파이프라인은 블랙박스라, 계측이 없으면 운영자는
> **감으로** 프롬프트를 바꾸고 모델을 교체한다.

[`docs/observability-kpi-rationale.md`](docs/observability-kpi-rationale.md)는 **어떤 운영 질문에
답하기 위해 이 지표를 잡았고, 이 숫자로 어떤 의사결정을 내리는가**를 정리한 문서다. 코드 구조가
아니라 기획 관점이며, 이 저장소에서 **제품/운영 기획 사고를 가장 직접적으로 보여주는 문서**다.

- 지표를 새로 만들지 않고 **이미 있는 판단 AI(Gate)의 결정을 정량 점수로 재활용**했다.
- 그 점수의 **한계를 함께 적었다** — Gate는 가장 심각한 지적 하나로 결정하므로 지적의 개수·조합은
  버려진다. 의도된 단순화임을 명시하고 정밀화 경로를 로드맵으로 남겼다.

---

## 개발 — 어떻게 만들어졌는가 (설계 결정과 검증)

이 저장소에서 **문서는 코드의 부산물이 아니라 선행 조건**이다. 아키텍처·계약 리터럴·정책처럼
"조용히 고르면 나중에 되돌릴 수 없는" 선택은 코드를 쓰기 전에 **결정 브리프**로 올리고,
구현 뒤에는 **다른 세션의 검증자가 반증을 시도**한다. 규칙 자체는 [`CLAUDE.md`](CLAUDE.md)에 있다.

```
결정 브리프 → 오너 결정 → 구현 + 양방향 회귀 가드 → 독립 검증(반증 시도) → 정본(SoT) 개정
```

| 단계 | 산출물 | 규모 |
|---|---|---|
| **① 결정 브리프** — 선택지 표(`선택지·설명·장점·단점`) + 구현자 추천 + 유예 항목을 적고 **멈춘다**. 추측 구현 금지 | [`docs/plans/`](docs/plans/README.md) | **82개** |
| **② 구현 + 회귀 가드** — 가드는 **양방향**이어야 한다: 원래 결함을 재현하면 실패(under-strict), 과잉 교정으로 정상 경로를 깨도 실패(over-strict) | `tests/` | **2,170 passed / 1,931 subtests** |
| **③ 독립 검증** — 구현자가 아닌 세션이 **뮤테이션**(고친 것을 되돌려 회귀가 다시 실패하는지)으로 반증을 시도한다 | [`docs/verifications/`](docs/verifications/README.md) | **218건 / 42일치** |
| **④ 정본 개정** — 계약이 바뀌면 SoT 버전을 올리고 **변경 이유와 근거 링크**를 남긴다 | [`docs/system-contract-sot.md`](docs/system-contract-sot.md) | **v1.7.89**, 변경이력 전량 보존 |
| **⑤ 인수인계** — 다음 작업자가 시간을 잃지 않도록 **함정**을 기록한다 | [`HANDOFF.md`](HANDOFF.md) · [`docs/daily_logs/`](docs/daily_logs/) | 일자별 |

**검증 판정 분포는 합격 146 · 조건부 합격 57 · 불합격 1 · 서술형 14**다. **조건부 합격이 26%**라는 것이
이 절차가 형식적 통과가 아니라는 증거이며, 각 지적은 후속 커밋에서 닫힌다.

### 평가자를 위한 짧은 경로

전부 읽을 필요는 없다. 이 셋이면 작업 방식이 드러난다.

1. **결정이 어떻게 내려지는가** — [`docs/plans/auth-d8-7-infra-auth-decisions.md`](docs/plans/auth-d8-7-infra-auth-decisions.md)
   저장소 무인증 노출을 **자격증명으로 막을지, 노출면을 없앨지**를 4지선다로 올린 브리프.
   `mongod --auth --replSet`이 keyfile을 강제한다는 **직접 실측**이 추천을 바꿨다.
2. **검증이 무엇을 잡는가** — [`docs/verifications/2026-08-02/d8_7_g1c_loopback_exposure.md`](docs/verifications/2026-08-02/d8_7_g1c_loopback_exposure.md)
   위 결정의 구현을 검증한 기록. **"시행 완료"가 compose 파일 수준에서만 참이고 런타임에서는
   거짓**이었음을 `docker ps`로 잡아냈다.
3. **함정이 어떻게 축적되는가** — [`HANDOFF.md`](HANDOFF.md)의 "함정" 절.
   `pymongo`가 naive datetime을 돌려줘 **유닛 46건이 전부 통과하는데 배포만 깨진** 사례처럼,
   테스트로는 안 보이는 것들이 재발 방지 형태로 적혀 있다.

---

## 서비스 — 어떻게 돌리고, 지켜보는가

**현재 단계는 로컬 1인 운영(dogfood 직전)이다.** 아래는 그 단계에서 실제로 하고 있는 것이며,
"나중에 하겠다"는 계획이 아니라 돌아가는 절차다.

### 구성

| 서비스 | 역할 |
|---|---|
| **LLM Gateway** | llama.cpp 호환 provider 앞단. 실패 taxonomy·창 가드를 여기서 통제 |
| **Core SOT** | MongoDB 정본 — project/draft/version/snapshot/source reference |
| **Analysis / Memory** | 구조화 기억 후보 추출 → 대조 → append-only canonical memory |
| **Indexing** | ChromaDB(vector) · Elasticsearch(nori lexical) 파생 인덱스 + async outbox 워커 |
| **Context Search** | 정본 재조회 기반의 검증된 ContextPackage |
| **Agent loop / Gate** | bounded flat loop, 출력 품질 통제 |
| **Frontend** | React + TS SPA(nginx). 원고 작업공간 · Review Inbox · 관측 대시보드 |

전 구성요소가 `docker compose up` 하나로 뜬다. **포트는 전용 대역으로 repo에 고정**돼 있어
어느 머신에서든 같은 번호로 뜬다([`.env.example`](.env.example)에 값과 근거).

### 어디까지 노출하는가

저장소(MongoDB · Elasticsearch · Chroma)와 내부 서비스는 **`127.0.0.1`에만 바인드**한다.
LAN에 열리는 것은 **인증 뒤에 있는 제품 표면 둘**(application · frontend)과, GPU 없는 머신에
모델을 주는 llama 서버뿐이다. 이것은 취향이 아니라 **오너 결정으로 정본에 박힌 계약**이며
(`SoT v1.7.75`), compose 파일을 읽어 강제하는 회귀가 있다(`tests/test_compose_exposure.py`).

### 무엇을 보고 있는가

LLM을 부르는 **호출부 8곳 전부**가 표준 감사 레코드를 남기고, 그것을 집계한 KPI를 화면으로 본다
(프로젝트별 + 전역 관리자). **"8"은 `LlmCallSite` enum 리터럴 수 = LLM 어댑터 수**이고,
**"전부"는 호출부 단위이지 "모든 LLM 호출"이 아니다** — 요청 경로와 생성 워커는 기록하지만
script·diagnostic 등 감사 scope 밖 경로는 **계약상** 기록하지 않는다(추측한 `project_id`는 오염이다).
지표 선정 이유는 위 [운영 KPI 기획](#운영-kpi-기획), 계약 정의는 정본의
"LLM 파이프라인 관측(KPI)" 절에 있다. **실패한 호출도 센다** — 성공만 세면 성공률이 영구히
100%가 되기 때문이다.

### 실사용에서 나온 것을 어떻게 되먹이는가

- **실검수 브리프** [`docs/live_review_briefs/`](docs/live_review_briefs/2026-07-18/writing_workspace_ux_restructure.md) —
  브라우저로 직접 써 보다 발견한 결함이 **기존 승인 계약과 충돌할 때** 재현 증거·충돌 지점·오너
  결정·재검수 기준을 남긴다. 코드 이슈가 아니라 **계약 재협상 기록**이다.
- **성능 실측** [`docs/benchmarks/`](docs/benchmarks/2026-07-15/writing_loop_per_stage_ceiling_q4.md) —
  실 12B 모델로 단계별 비용을 재서 loop 예산 기본값을 정했다. 기본값은 추정이 아니라 측정에서 왔다.
- **운영 절차** [`docs/runbooks/local-llama-server.md`](docs/runbooks/local-llama-server.md) —
  로컬 GPU 모델 서버 기동 절차.
- **함정 축적** [`HANDOFF.md`](HANDOFF.md) — 세 대의 머신(배포용·개발용·노트북)을 옮겨 다니며
  겪은 것들이 재발 방지 형태로 쌓여 있다. *"테스트는 전부 통과하는데 배포만 깨지는"* 종류가
  여기 모인다.

### 작업 절차 문서

[`docs/guides/records-and-handoff.md`](docs/guides/records-and-handoff.md) — 작업 로그·인수인계·
CHANGELOG 작성 규칙 · [`docs/guides/verification.md`](docs/guides/verification.md) — 남의 슬라이스를
독립 검증하는 절차. 규칙을 사람 기억이 아니라 문서로 둔다.

---

## 문서 지도

| | 어디 |
|---|---|
| 제품 한 장 요약 (기획 진입점) | [`docs/product-overview.md`](docs/product-overview.md) |
| 정본 계약(먼저 읽기) | [`docs/system-contract-sot.md`](docs/system-contract-sot.md) |
| 계획 · 결정 브리프 인덱스 (100개) | [`docs/plans/README.md`](docs/plans/README.md) |
| 독립 검증 기록 (218건) | [`docs/verifications/README.md`](docs/verifications/README.md) |
| 현재 상태 스냅샷 | [`HANDOFF.md`](HANDOFF.md) |
| 마일스톤 이력 | [`CHANGELOG.md`](CHANGELOG.md) |
| 일자별 작업 이력 | [`docs/daily_logs/`](docs/daily_logs/) |
| 문서 안내 (전체 지도) | [`docs/README.md`](docs/README.md) |
| 아이디에이션 원본 | [`docs/abstract.md`](docs/abstract.md) |
| 작업 규칙 | [`CLAUDE.md`](CLAUDE.md) |

## License

본 프로젝트의 **자체 소스 코드와 문서**는 **[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.ko)
(저작자표시–비영리–동일조건변경허락)** 라이선스를 따릅니다. 전체 조건은 [`LICENSE`](LICENSE)를 참고하세요.

- **개인 · 연구 · 학습 (자유)**: 저작자 표시를 유지하는 한 자유롭게 열람·수정·재배포할 수 있습니다.
  2차 저작물은 동일한 CC BY-NC-SA 4.0으로 공개해야 합니다(ShareAlike).
- **채용 · 평가 (환영)**: 기업 채용 담당자·면접관의 코드 검토 및 로컬 실행·테스트는 언제나
  환영합니다(비영리 평가로 간주).
- **상업적 이용 (금지)**: 사전 서면 허가 없이 영리 목적으로 이용하거나 상용 제품·서비스에 포함할 수
  없습니다. 상업적 이용은 저작권자에게 문의해 주세요.

> ⚠️ **적용 범위**: 위 라이선스는 이 저장소의 **자체 코드·문서에만** 적용됩니다. MongoDB ·
> Elasticsearch · ChromaDB · Google Gemma 모델 · Python 패키지 등 **외부 의존 요소는 각자의
> 라이선스/약관**을 따릅니다. 특히 **Gemma는 Google의 *Gemma 이용약관*을 별도로 준수**해야 하며,
> 모델 가중치는 본 저장소에 포함되지 않습니다(외부 endpoint 호출). 위 요약은 이해를 돕기 위한
> 것이며, 법적 효력은 [`LICENSE`](LICENSE)와
> [CC BY-NC-SA 4.0 전문](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode)이 우선합니다.
