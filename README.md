# AI Writing System

개인 창작자를 위한 **글쓰기 운영체제** — 사용자의 원고·설정·세계관·문체·분석 결과를 장기 기억으로
축적하고, 글쓰기 시점마다 필요한 기억만 검색해 제공하는 시스템이다. 단순 "AI 글쓰기 챗봇"이 아니라,
**MongoDB 정본(SOT) + Narrative Memory + Agentic Search**를 결합해 일관성 있는 장편 창작을 돕는 것을
목표로 한다.

모든 AI 출력(생성·분석)은 곧바로 정본이 되지 않고 **candidate**로 남아, Gate와 검토·결정적 승격을
거쳐 기억으로 반영된다.

## 문서

- **정본 계약(먼저 읽기)**: [`docs/system-contract-sot.md`](docs/system-contract-sot.md)
- **개발 계획 · 결정 브리프 인덱스**: [`docs/plans/README.md`](docs/plans/README.md)
- **독립 검증 기록**: [`docs/verifications/README.md`](docs/verifications/README.md)
- **현재 상태 스냅샷**: [`HANDOFF.md`](HANDOFF.md) · **마일스톤 이력**: [`CHANGELOG.md`](CHANGELOG.md)
- **문서 안내**: [`docs/README.md`](docs/README.md) · **아이디에이션 원본**: [`docs/abstract.md`](docs/abstract.md)

## 어떻게 만들어졌는가 (설계 결정과 검증)

이 저장소에서 **문서는 코드의 부산물이 아니라 선행 조건**이다. 아키텍처·계약 리터럴·정책처럼
"조용히 고르면 나중에 되돌릴 수 없는" 선택은 코드를 쓰기 전에 **결정 브리프**로 올리고,
구현 뒤에는 **다른 세션의 검증자가 반증을 시도**한다. 규칙 자체는 [`CLAUDE.md`](CLAUDE.md)에 있다.

```
결정 브리프 → 오너 결정 → 구현 + 양방향 회귀 가드 → 독립 검증(반증 시도) → 정본(SoT) 개정
```

| 단계 | 산출물 | 규모 |
|---|---|---|
| **① 결정 브리프** — 선택지 표(`선택지·설명·장점·단점`) + 구현자 추천 + 유예 항목을 적고 **멈춘다**. 추측 구현 금지 | [`docs/plans/`](docs/plans/README.md) | **73개** |
| **② 구현 + 회귀 가드** — 가드는 **양방향**이어야 한다: 원래 결함을 재현하면 실패(under-strict), 과잉 교정으로 정상 경로를 깨도 실패(over-strict) | `tests/` | **1,839 passed / 1,556 subtests** |
| **③ 독립 검증** — 구현자가 아닌 세션이 **뮤테이션**(고친 것을 되돌려 회귀가 다시 실패하는지)으로 반증을 시도한다 | [`docs/verifications/`](docs/verifications/README.md) | **202건 / 39일치** |
| **④ 정본 개정** — 계약이 바뀌면 SoT 버전을 올리고 **변경 이유와 근거 링크**를 남긴다 | [`docs/system-contract-sot.md`](docs/system-contract-sot.md) | **v1.7.75**, 변경이력 전량 보존 |
| **⑤ 인수인계** — 다음 작업자가 시간을 잃지 않도록 **함정**을 기록한다 | [`HANDOFF.md`](HANDOFF.md) · [`docs/daily_logs/`](docs/daily_logs/) | 일자별 |

**검증 판정 분포는 합격 134 · 조건부 합격 54 · 서술형 14**다. **조건부 합격이 27%**라는 것이
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

## 구성 (요약)

- **LLM Gateway** — llama.cpp 호환 provider 앞단(외부 Gemma Q4 endpoint 호출)
- **Core SOT** — MongoDB 정본: project/draft/version/snapshot/source reference
- **Analysis / Memory** — 구조화 기억 후보 추출 → 대조 → append-only canonical memory
- **Indexing** — ChromaDB(vector) · Elasticsearch(nori lexical) 파생 인덱스
- **Context Search** — 검증된 ContextPackage(정본 재조회 기반)
- **Agent loop / Gate** — bounded flat loop, 출력 품질 통제

외부 의존(MongoDB · Chroma · Elasticsearch · 임베딩 서비스 · 외부 llama.cpp[Gemma Q4])은
`docker-compose.yml`로 기동한다. 자세한 경계는 정본 계약 문서를 참고.

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
