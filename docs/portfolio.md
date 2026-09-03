# 포트폴리오 설명문 — 에-라잇

> **이 문서는 이 저장소를 평가하러 온 사람을 위한 안내다.** 프로젝트가 무엇이고, 어떤 공학적
> 판단이 들어갔으며, 그 증거를 어디에서 직접 확인할 수 있는지를 한 자리에 정리한다. 저장소의
> 정문은 [`../README.md`](../README.md)(기획 · 개발 · 서비스 세 축), 제품 요약은
> [`product-overview.md`](product-overview.md)다 — 여기는 그 위의 **읽기 안내와 해설**이다.
>
> 아래 숫자는 특별한 표기가 없는 한 **2026-08-25 디스크 실측**이다(이 저장소 규칙상 숫자 주장에는
> 기준 시점을 붙인다). 살아 있는 최신 숫자의 정본은 [`../README.md`](../README.md)와
> [`system-contract-sot.md`](system-contract-sot.md)다.

## 1. 무엇을 만들었나

**에-라잇**은 장편 창작의 일관성 문제를 푸는 개인용 AI 글쓰기 시스템이다. 장편에서 무너지는
것은 문장력이 아니라 **일관성**이다 — 인물의 말투가 3장과 17장에서 다르고, 죽은 인물이
되살아나고, 작가 자신도 "그때 그 설정이 뭐였더라"를 못 찾는다. 범용 챗봇은 대화창을 벗어나면
아무것도 기억하지 못하므로 이 문제를 구조적으로 풀 수 없다.

그래서 이 시스템의 중심은 생성 모델이 아니라 **기억과 그 기억의 검증**이다. 사용자의 원고·설정·
세계관·문체를 장기 기억으로 축적하고, 글을 쓰는 시점마다 필요한 기억만 근거와 함께 검색해
모델에 제공한다. 핵심 루프는 한 줄이다:

```text
작성·저장 → 원문 snapshot → 구조화 기억 후보 추출 → 파생 색인 갱신
→ 기억 검색 + 정본 재조회 → 글 후보 생성 → Gate 검증 → 사용자 채택
```

**AI 출력은 정본이 아니다.** 생성·분석 결과는 전부 `candidate`로 남고 Gate 판정과 사람의 검토를
거쳐야 기억이 된다. 기억은 append-only로 버전을 쌓고, 모든 주장에는 원문 위치까지 되짚는 근거
포인터(`source_ref`)가 붙는다. 이 원칙들은 기획 단계에서 못박았다
([`plans/00-foundations.md`](plans/00-foundations.md)).

## 2. 어떻게 만들었나 — 1인 오너 + AI 작업 세션

이 저장소의 특징 대부분은 **작업 방식에서 나온다.** 진행은 오너 1인과 AI 작업 세션의 협업다:

- **오너** — 제품 방향과 모든 소프트 결정. "조용히 고르면 나중에 되돌릴 수 없는" 선택은 코드를
  쓰기 전에 **결정 브리프**(선택지 표 + 권고 + 유예 항목)로 올리고, 오너가 고른다. 오너 발언은
  원문과 함께 [`daily_logs/`](daily_logs/)에 남는다.
- **AI 세션** — 구현·테스트·문서. 단 **구현한 세션과 다른 세션이 검증한다** — 구현자의 맥락을
  물려받지 않은 상태에서 반증을 시도한다.

왜 이렇게까지 하는가. **AI가 쓴 코드는 "테스트가 green이다"만으로 신뢰할 수 없다.** green은
"지금 있는 셀이 통과한다"일 뿐 "그 셀이 무엇을 잡는지"와 "계약이 지켜지는지"를 말하지 않는다.
그래서 이 저장소는 테스트에 **양방향**(결함 재현·과잉 교정 방지)을 요구하고, 검증에 **뮤테이션**
(고친 것을 일부러 되돌려 대상 셀이 다시 실패하는지 확인)을 요구한다. 이 문서의 나머지는 그
작업 방식이 남긴 것들을 안내한다. 규칙 자체는 [`../CLAUDE.md`](../CLAUDE.md)와
[`guides/verification.md`](guides/verification.md)에 있다.

## 3. 규모 한눈에 (2026-08-25 기준)

| 축 | 값 |
|---|---|
| 개발 기간 | 2026-06-24 첫 커밋 → 진행 중(약 2개월, 개인 프로젝트) |
| 커밋 | 794 |
| 공개 API | **87 operation** (FastAPI — 공개 5 · 관리자 16 포함, tier 전수 가드) |
| 배포 단위 | docker compose 서비스 10개(앱·관리자·워커 2·LLM 게이트웨이·Mongo·ES·Chroma·임베딩·프론트) |
| 서버 코드 | Python 35,818줄 (`services/`) |
| 프론트 코드 | TS/TSX 16,585줄 (`frontend/src`, 테스트 제외) |
| 회귀 테스트 | backend **2,506 passed**(+subtest 2,812) · frontend **338 passed** — 152개 테스트 파일 |
| 결정 브리프 | **93개** ([`plans/`](plans/README.md)) |
| 독립 검증 | **256건 / 56일치** — 합격 183 · 조건부 합격 71 · 불합격 2 ([`verifications/`](verifications/README.md)) |
| 계약 정본 | SoT **v1.8.4** (변경이력 전량 보존, [`system-contract-sot.md`](system-contract-sot.md)) |

재현 — 이 표의 숫자는 전부 이 저장소에서 다시 잴 수 있다: `git rev-list --count HEAD` ·
`ls docs/plans/*-decisions.md | wc -l` · `find docs/verifications -mindepth 2 -name '*.md' | wc -l`.
검증 판정 분포의 정본은 [`verifications/README.md`](verifications/README.md) 표이고, 그 일관성은
테스트(`tests/test_docs_indexes.py`)가 디스크 실측과 대조해 잠근다.

## 4. 시간 예산별 읽기 경로

**5분 — 무엇인지만**
1. [`../README.md`](../README.md) 상단의 세 축 표.
2. [`product-overview.md`](product-overview.md) §1~4(문제·원칙·MVP 도달점).
3. 이 문서 §1~3.

**30분 — 작업 방식까지 (권장)**
1. 최상위 [`README.md`](../README.md)의 **"개발 — 어떻게 만들어졌는가"** 축 전체(절차 표 +
   "평가자를 위한 짧은 경로").
2. 그 짧은 경로의 링크 둘 — 결정 브리프
   [`plans/auth-d8-7-infra-auth-decisions.md`](plans/auth-d8-7-infra-auth-decisions.md)(저장소
   무인증 노출을 자격증명으로 막을지, 노출면을 없앨지를 놓은 4지선다)와 검증 기록
   [`verifications/2026-08-02/d8_7_g1c_loopback_exposure.md`](verifications/2026-08-02/d8_7_g1c_loopback_exposure.md)
   ("시행 완료"가 파일 수준에서만 참이고 런타임에서는 거짓이었음을 잡아낸 기록).
3. 이 문서 §5~6(하이라이트와 스토리).

**2시간 — 코드·계약까지**
1. [`system-contract-sot.md`](system-contract-sot.md) 헤더·문서 우선순위 + 변경이력 최근 20행
   (이 저장소는 "왜 바뀌었는가"를 버전 단위로 보존한다).
2. [`plans/README.md`](plans/README.md)에서 관심 트랙 하나를 골라 브리프 한 건을 전문으로.
3. [`../HANDOFF.md`](../HANDOFF.md)의 "함정" 절 — 테스트로는 안 보이는 것들의 축적.
4. 검증 기록 한 건 전문 — 추천은 가장 최근 관례가 다 담긴
   [`verifications/2026-08-24/phase_8_5_quota_console.md`](verifications/2026-08-24/phase_8_5_quota_console.md).
5. 경계 테스트 코드 — [`../tests/test_auth_api.py`](../tests/test_auth_api.py)의 tier 전수 가드·
   결합 행렬(`CombinedBoundaryMatrixTest`).
6. (선택) 전수 회귀 직접 실행 — 최상위 README의 절차표. 그 자체가 이 저장소 주장의 재현이다.

## 5. 이 저장소가 보여주는 것 여섯

1. **추측으로 구현하지 않는다 — 결정 브리프 93개.** 아키텍처·계약 리터럴·정책은 선택지 표
   (`선택지·설명·장점·단점`)와 권고를 먼저 올리고 결정을 받는다. 유예 항목에는 "무엇을 보면
   여는가"의 **트리거**가 붙는다 — 트리거 없는 유예는 망각이라는 판단에서다.
2. **검증은 통과 확인이 아니라 반증 시도다 — 256건.** 구현 세션과 다른 세션이 뮤테이션으로
   "이 셀은 무엇을 잡는가"를 증명한다. **조건부 합격 71건(28%)** — 형식적 통과가 아니라는 증거를
   분포로 남긴다. 절차는 [`guides/verification.md`](guides/verification.md).
3. **회귀 가드는 양방향이다.** under-strict(원래 결함을 재현하면 실패)와 over-strict(과잉 교정이
   정상 경로를 깨도 실패)를 함께 단정한다. 과잉 교정을 잡는 방향은 일반적 관행에서 잘 안 지키는
   쪽이다.
4. **계약이 문서에서 끝나지 않는다.** 공개 API의 OpenAPI에서 프론트 TS 타입을 자동 생성하고,
   재생성이 **바이트 멱등**인지(손편집이 없는지) 검증이 확인한다. 컬렉션 키 집합·에러 상태코드
   선언·문서 인덱스·숫자 주장까지 테스트가 잠근다.
5. **운영 관측을 설계했다.** LLM을 부르는 호출부 9곳이 표준 감사 레코드를 남기고 KPI로 집계된다.
   **실패한 호출도 센다**(성공만 세면 성공률이 영구히 100%가 되므로), 지표의 한계는 문서로
   명시한다 — [`observability-kpi-rationale.md`](observability-kpi-rationale.md).
6. **보안을 전수로 시행한다.** 87 operation 전부가 인증 tier·소유권·에러 선언 전수 가드 아래
   있고, 관리자 표면은 별도 주소로 분리돼 제품 앱에는 관리 라우트 자체가 없다(LAN에서 치면
   가드가 아니라 **라우터가 404**). 저장소는 `127.0.0.1` 바인드로 노출면을 축소하는 방향을
   골랐다(자격증명이 아니라 노출이 없게).

## 6. 스토리 셋 — 판단이 갈렸던 자리

### 6-1. 회귀 테스트가 결함을 "정상"으로 고정하고 있었다

유료 API에 중복 제출을 막는 분산 잠금(Mongo)을 만들던 초판은 `_id` 충돌을 "잠겨 있음"의
**증거**로 해석했다. 결함은 정상 경로에서만 참이었다 — 충돌과 그 뒤의 확인 읽기 사이에 원래
요청이 해제되거나 TTL이 문서를 치우면, ① 이미 만료된 잠금으로 **거짓 차단**을 내고, ② 문서가
사라지면 **저장되지 않은 성공**을 돌려줘 **다음 요청까지 통과**시킨다. 둘이 동시에 실행되는
것은 이 잠금이 막으려던 중복 그 자체였다.

흥미로운 것은 발견 경로다. 이 결함은 **독립 검증의 FAIL 판정**으로 나왔고
([`verifications/2026-08-03/slice_8_2b_duplicate_request_lock.md`](verifications/2026-08-03/slice_8_2b_duplicate_request_lock.md)),
수정은 코드보다 **테스트 기대치를 먼저 고치는 일**에서 시작했다 — 기존 회귀가 "성공 수만
세는" 단정으로 그 결함을 정상으로 고정하고 있었기 때문이다. 개정된 계약은 "충돌은 신호다 —
살아 있음을 다시 확인하고 없으면 원자적으로 재차지하며, 재시도는 유한하고 소진되면
fail-closed"다(SoT v1.7.87). 교훈: **green은 셀이 통과한다는 뜻이지, 셀이 올바른 것을 잡는다는
뜻이 아니다.** 재검: [`verifications/2026-08-04/slice_8_2b_duplicate_request_lock_recheck.md`](verifications/2026-08-04/slice_8_2b_duplicate_request_lock_recheck.md).

### 6-2. 한 겹을 지워도 아무 테스트가 실패하지 않는다면

모든 project 경로는 **인증 dependency와 소유권 dependency 두 겹**으로 서 있다(소유권 겹은 인증을
하위로 포함한다). 뮤테이션 실측(2026-07-28) 결과, **어느 한 겹을 지워도 관측되는 상태코드가
전혀 변하지 않는다** — 둘 다 지워야 401이 403으로 샌다. 즉 요청을 보내 응답만 보는 테스트는
원리적으로 이 결함을 못 본다.

처방은 "두 겹을 다 없앤 일회용 앱에 소유권 겹만 마운트해 격리 구동하는 셀"이다
(`tests/test_auth_api.py`의
`test_the_ownership_dependency_cannot_run_without_authentication`). 인증을 유지한 리팩터링은 이
셀을 깨지 않지만, **인증을 실제로 잃는 리팩터링은 여기서만 보인다.** 일반화하면 — 방어가 두 겹
이상인 곳의 한 겹 제거는 관측 불가능하므로, 격리 구동 셀만이 그것을 본다.

### 6-3. 프롬프트를 73% 줄인 방식 — 실측으로 찾고, 계약을 좁혀서 줄였다

실 12B 모델에서 긴 보고서 생성이 4/4 실패(400)했다. 추측으로 프롬프트를 줄이지 않고 **어디서
토큰이 나가는지부터 쟀다** — 지배 항은 문맥 항목마다 붙는 **근거 포인터 JSON**이었다
([`verifications/2026-07-29/beta_long_report_pointer_root_cause.md`](verifications/2026-07-29/beta_long_report_pointer_root_cause.md)).

처방은 흥미롭게도 **모델에게 덜 주는 것**이 아니라 **모델이 덜 쓰게 하는 것**이다: 모델은 포인터
대신 항목 **번호**(`related_context_pointers: [1, 3]`)를 쓰고, 번호→포인터 매핑은 서버에서 한다.
결과 — 프롬프트 **11,841 → 3,216 tok(−72.8%)**, 헤드룸 **−1,665 → +7,024**(부호 반전),
실 모델 관통 3/3 strict parse·repair 0회. **공개 계약은 무변**(`schema.d.ts` 재생성 diff 0),
바뀐 것은 모델이 쓰는 wire 하나뿐이라 오히려 도메인 계약이 강해졌다 — 이제 모델이 만들 수 있는
것은 범위 안의 정수뿐이다. 그래도 여전히 창을 넘는 요청은 **모델을 부르기 전에** 400으로
거부한다(왕복 0회). SoT v1.7.61 · 재검
[`verifications/2026-07-30/r_e_citation_numbers_audit.md`](verifications/2026-07-30/r_e_citation_numbers_audit.md).

## 7. 기술 스택

| 축 | 선택 |
|---|---|
| 언어·런타임 | Python(FastAPI) · TypeScript(React + Vite) |
| 정본 저장소 | MongoDB(트랜잭션 기본, append-only 버전 관리) |
| 파생 색인 | ChromaDB(벡터, BGE-m3-ko) · Elasticsearch(nori lexical) — RRF 하이브리드 융합 |
| LLM | llama.cpp 로컬 서버 또는 OpenAI 호환 외부 API(구글 등) — **게이트웨이 뒤에서 교체 가능**(키 회전·모델 폴백·실패 taxonomy) |
| 배포 | docker compose(서비스 10개, 전용 포트 대역 고정) · 제품·관리자 표면 분리(nginx) |
| 계약 | OpenAPI → TS 타입 자동 생성 · SoT 문서가 버전 관리(v1.8.4) |

## 8. 정직한 한계

이 저장소는 강점만큼 한계를 명시하는 데 익숙하다 — 그래야 평가자도 정확할 수 있다.

- **제품 품질 데이터는 아직 없다.** 지금 있는 숫자는 전부 *시스템* 지표이지 *작품* 지표가
  아니다. 실사용 관찰(dogfood)은 2026-08-23 착수 선언 단계다.
- **운영 규모는 로컬 1인**이다. 세 대의 머신을 옮겨 다니는 개인 환경이며, 원격 다중 호스트
  배포는 계기가 오면 여는 유예 목록으로 관리된다.
- **미구현 화면이 있다.** 인물 카드·타임라인·관계 그래프는 의도적으로 뒤로 미뤘고 승인 UI만
  서 있다([`product-overview.md`](product-overview.md) §4·§6).
- **리랭커 품질 평가는 미실시**다(외부 API 어댑터는 있으나 기본은 꺼짐이다).
- **라이선스는 CC BY-NC-SA 4.0.** 개인·연구·평가는 자유고, 상업 이용은 금지다. 평가를 위한
  코드 검토·로컬 실행은 환영한다([`../LICENSE`](../LICENSE)).

## 9. 증거 지도 — 무엇을 어디서 확인하는가

| 궁금한 것 | 어디 |
|---|---|
| 검증이 정말 반증 시도인가 | [`verifications/README.md`](verifications/README.md)(절차 설명 + 256건 판정 분포) · [`guides/verification.md`](guides/verification.md) |
| 결정이 어떻게 내려지나 | [`plans/README.md`](plans/README.md)(트랙별 브리프 인덱스) · [`daily_logs/`](daily_logs/)(오너 결정 원문) |
| 하루 작업의 실제 모습 | [`daily_logs/`](daily_logs/) — 착수 전 실측·결정·뮤테션·회귀 수치까지 |
| 계약의 현재 정본 | [`system-contract-sot.md`](system-contract-sot.md) |
| 테스트로 안 보이는 함정들 | [`../HANDOFF.md`](../HANDOFF.md) "함정" 절 |
| 회귀가 실제로 green인가 | 직접 실행 — 최상위 [`README.md`](../README.md)의 절차표(`docker-compose.test.yml` + pytest) |
| 성능 실측 근거 | [`benchmarks/`](benchmarks/2026-07-15/writing_loop_per_stage_ceiling_q4.md) — 실 12B 모델로 단계별 비용을 재서 loop 예산을 정했다 |
| 직접 띄워 보기 | 최상위 [`README.md`](../README.md) "서비스" 축 · [`../.env.example`](../.env.example) |
