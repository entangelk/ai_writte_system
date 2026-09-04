# 00. 공통 기반

상태: **이행됨 — 설계 근거로 보존**. 여기 정한 전 Phase 공통 원칙은 시행 중이고 현재 계약 정본은 [`../system-contract-sot.md`](../system-contract-sot.md) 다. **다만 §"전역 착수 전 결정사항" 체크박스는 미갱신**이다 — 에러 envelope(H3)·삭제 정책·monorepo 경계는 이미 확정됐다(HANDOFF 열린 것).  
적용 범위: 모든 Phase

## 제품 목표

사용자의 글과 설정을 장기 기억으로 축적하고, 매 글쓰기 요청마다 필요한 기억만 근거와 함께 제공하는 개인 창작 메모리 시스템을 만든다.

핵심 루프는 다음과 같다.

```text
작성/저장 → 원문 snapshot → 구조화 기억 후보 추출 → 검색 인덱스 갱신
→ 필요한 기억 검색 및 정본 재조회 → 글 후보 생성 → 검증 → 사용자 채택
```

## 구성요소의 책임

| 구성요소 | 책임 | 하지 않는 일 |
|---|---|---|
| MongoDB | 원문, 버전, 근거, 구조화 기억, 상태의 정본 | 벡터 유사도 검색을 정본 판정에 사용 |
| ChromaDB | 의미적으로 유사한 후보와 Mongo pointer 검색 | 검색용 text를 최종 사실로 제공 |
| Elasticsearch | 이름·별칭·본문·metadata의 lexical 검색 | 정본 상태를 독립적으로 결정 |
| Analysis AI | 저장된 원문을 구조화 기억 후보로 변환 | 새 canon을 확정 |
| Agentic Search | 검색 계획, 후보 병합, SOT 재조회, ContextPackage 구성 | 검색 hit를 검증 없이 전달 |
| LLM Gateway | 모델 로드, inference, structured output, 사용량/성능 metadata | 프로젝트 memory 조회, 업무 규칙 판정 |
| Writing AI | 제공된 컨텍스트와 요청으로 글 후보 생성 | DB 직접 접근, canon 변경 |
| Gate | 후보의 근거·격리·연속성·POV·품질 검사 | 사용자 의도를 대신 확정 |
| Product Shell | 프로젝트·원고 관리, 작업 상태, 내보내기 | 기억의 정본이나 AI 판정을 별도로 소유 |
| Editor/Review UI | 사용자 작성, 채택, 승인, 거절 | AI 후보를 자동 canon으로 취급 |

## 불변 원칙

### MongoDB가 Source of Truth다

- 원문 snapshot은 primary SOT다.
- 사용자가 승인한 설정은 canonical SOT다.
- 분석 결과는 MongoDB에 저장되더라도 derived SOT이며 상태와 근거가 필요하다.
- ChromaDB와 Elasticsearch는 언제든 MongoDB로부터 재생성 가능한 파생 인덱스다.

### 모든 AI 출력은 candidate다

- Writing AI 출력은 `draft_candidate`다.
- Analysis AI 출력은 `analysis_candidate`다.
- 검색으로 고른 컨텍스트도 Gate 전에는 `context_candidate`다.
- candidate는 Gate 또는 사용자 승인 없이 canonical 상태가 되지 않는다.

### 모든 기억은 추적 가능해야 한다

- 구조화 기억에는 `project_id`, 상태, 버전, `source_ref`가 필요하다.
- `source_ref`는 snapshot/block/span/quote/hash로 원문을 다시 찾을 수 있어야 한다.
- 검색 결과는 MongoDB pointer로 정본을 다시 읽고 version/hash를 확인한다.

### AI와 데이터 계층을 분리한다

- Writing AI와 Analysis AI는 MongoDB, ChromaDB, Elasticsearch에 직접 접근하지 않는다.
- AI 입력은 명시적 계약을 가진 loader 또는 ContextPackage를 통해 전달한다.
- 검색·저장·검증 trace를 남겨 결과가 만들어진 이유를 설명할 수 있어야 한다.

### 프로젝트 격리는 필수다

- 모든 프로젝트 데이터와 검색 문서에 `project_id`를 둔다.
- 모든 query와 SOT 재조회에서 `project_id`를 강제한다.
- Context Gate는 다른 프로젝트의 항목을 제거하고 오류로 기록한다.

### ~~MVP는 단일 사용자 제품이다~~ (2026-07-26 오너 결정으로 만료 — 아래 정정)

> **★ 정정(2026-08-02).** 이 절은 **더 이상 성립하지 않는다.** 2026-07-26 오너 결정으로 단일 사용자
> 유예가 만료돼 제품이 **다중 사용자로 확장**됐다(정본 **`SoT v1.7.49`** — "단계 전환 — MVP 단일
> 사용자 유예 해제, 다중 사용자로 확장(오너 결정 D0=A)"). 계정(Argon2id)·서버
> 세션·프론트 로그인·**프로젝트 소유권 격리(403)**·관리자 tier·영구 파기가 이미 구현돼 있다.
> 아래 원문은 **당시의 경계를 남기기 위해** 지우지 않는다(왜 그렇게 계획했는지가 사라진다).
> 현재 그림은 [`../product-overview.md`](../product-overview.md) §5, 결정 근거는
> [`multi-user-auth-cms-decisions.md`](multi-user-auth-cms-decisions.md).
>
> **여전히 유효한 부분**: `project_id`는 소유권으로 **대체되지 않았다.** 데이터·검색 범위를 나누는
> 필수 경계로 그대로 강제되며, 소유권은 그 위에 얹힌 별개 축이다.

- ~~계정, 로그인, 사용자 초대, 권한 관리는 MVP에서 구현하지 않는다.~~
- `project_id`는 단일 사용자 환경에서도 데이터와 검색 범위를 나누는 필수 경계다. **(유효)**
- ~~향후 다중 사용자 가능성을 위해 현재 계획에 `user_id`를 억지로 넣지 않는다. 필요해지는 시점에 별도 migration/보안 계획을 세운다.~~ — 그 시점이 왔고, `Project.owner_id` 한 필드로 들어갔다(D3=A).

## 기본 상태 모델

초안이 제안하는 기억 상태는 다음과 같다.

```text
candidate → confirmed → canonical
          ↘ needs_review
          ↘ rejected
confirmed/canonical → deprecated
```

정확한 전이 권한, 자동 승격 허용 여부, `confirmed`와 `canonical`의 차이는 Phase 2와 Phase 6 착수 전에 확정한다.

## 주요 위험과 공통 대응

| 위험 | 공통 대응 |
|---|---|
| 분석 AI의 과잉 추론 | source anchor, confidence, candidate 기본값, 사용자 승인 |
| stale vector/lexical index | Mongo version 저장, SOT 재조회, mismatch 폐기/재색인 |
| Writing AI의 컨텍스트 오해 | 상태 구분, constraints, `do_not_use`, Writing Gate |
| 프로젝트 간 기억 오염 | 전 계층 `project_id` 강제 및 Context Gate 차단 |
| 과도한 컨텍스트 | 목적별 최소 정보, macro/micro 분리, token budget |

## 전체 런타임 경계

### 저장 후 분석

```text
Draft Save → draft_version/snapshot → block/ref 생성 → Analysis Job
→ 후보 추출 → Analysis Gate → 기억 저장 → Index Sync
```

### 글쓰기 요청

```text
Writing Request → Agentic Search → ES/Chroma 후보
→ Mongo SOT 재조회 → Context Gate → Writing AI
→ Writing Gate → editor 제안 → 사용자 채택 → 저장
```

### 사용자 제품 흐름

```text
프로젝트 생성/선택 → 원고 작성·버전 저장 → 분석/검색/검토 상태 확인
→ 결과 채택 또는 기억 검토 → 원하는 시점의 원고 내보내기
```

## 전역 착수 전 결정사항

- [ ] 첫 구현이 소설 전용인지, 일반 글쓰기까지 포함하는지 결정
- [ ] `confirmed`와 `canonical`의 의미 및 승격 주체 확정
- [ ] [`llm-gateway.md`](llm-gateway.md)의 monorepo/독립 서비스 경계 승인
- [x] 첫 model/runtime 기준: `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0` + llama.cpp CUDA
- [ ] 실제 실행 장비와 Gemma model terms/download 권한 확인
- [ ] API 오류 envelope, ID 형식, timestamp 규칙을 공통 계약으로 확정
- [ ] 프로젝트/원고 삭제와 snapshot 보존 정책의 최소 범위 결정

## 참고 아이디에이션

- [`../abstract.md`](../abstract.md) §0~4, §16, §18
- [`../contracts.md`](../contracts.md) §1~2, §12~14
