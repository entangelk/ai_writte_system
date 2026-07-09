# AI Writing System

개인 창작자를 위한 **글쓰기 운영체제** — 사용자의 원고·설정·세계관·문체·분석 결과를 장기 기억으로
축적하고, 글쓰기 시점마다 필요한 기억만 검색해 제공하는 시스템이다. 단순 "AI 글쓰기 챗봇"이 아니라,
**MongoDB 정본(SOT) + Narrative Memory + Agentic Search**를 결합해 일관성 있는 장편 창작을 돕는 것을
목표로 한다.

모든 AI 출력(생성·분석)은 곧바로 정본이 되지 않고 **candidate**로 남아, Gate와 검토·결정적 승격을
거쳐 기억으로 반영된다.

## 문서

- **정본 계약(먼저 읽기)**: [`docs/system-contract-sot.md`](docs/system-contract-sot.md)
- **개발 계획(Phase 인덱스)**: [`docs/plans/README.md`](docs/plans/README.md)
- **현재 상태 스냅샷**: [`HANDOFF.md`](HANDOFF.md)
- **문서 안내**: [`docs/README.md`](docs/README.md) · **아이디에이션 원본**: [`docs/abstract.md`](docs/abstract.md)

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
