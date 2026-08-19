# 2026-08-19 작업 로그 (감마)

> **머신은 감마다** — GPU 가 없어 임베딩 서비스도 LLM 도 못 띄운다. 오늘도 **코드 0줄 · 문서만**이며,
> 그것이 브리프 확정을 여기서 하는 이유다(구현·실측은 외부 키 또는 알파/베타에서).

## Goals

- 오너가 [`plans/embedding-adapter-slice-decisions.md`](../../plans/embedding-adapter-slice-decisions.md)
  의 **결정 1~4 를 추천안 그대로 확정**했다(*"다 괜찮네. 추천안 대로 브리프 확정해줘."*). 그것을
  브리프에 반영한다.
- 오너가 **조건을 하나 더 붙였다** — *"재색인 같은 경우는 리드미에 자세히 설명을 해놔야 햇갈리지
  않겠네. 내부 구조를 아는 사람들이면 당연히 임베딩 모델이 변경될때마다 재색인은 당연한 수순이겠지만
  모르는 사람들은 모를꺼아냐."* → README 에 재색인 절을 쓴다.
- HANDOFF 의 "다음 작업 = 브리프 확정" 을 **다음 작업 = 임베딩 어댑터 구현 슬라이스**로 넘긴다.

## Completed work

### Task 1 — 임베딩 어댑터 브리프 확정 (결정 1~4 = 전부 A)

- 파일: [`docs/plans/embedding-adapter-slice-decisions.md`](../../plans/embedding-adapter-slice-decisions.md)
- 바꾼 것: 헤더 `오너 결정 대기` → **`Resolved 2026-08-19`** + 확정값 요약 · 각 결정 절 끝에
  **`★ 확정`** 항목 넷 · `## 권고 요약` → **`## 확정 요약 (2026-08-19)`** + **산출물 넷** ·
  `## 승인 전 보류` → **`## 착수 조건 (승인 완료)`** + 착수 순서 · 유예 절 두 항목 갱신.
- 효과: **"승인 전 보류" 가 해제**됐다. 이제 이 슬라이스는 코드를 쓸 수 있고, 착수 순서가 문서로
  고정됐다 — **① 조립 헬퍼+가드 → ② `OpenAIEmbeddingProvider` → ③ README 재색인 절 → ④
  `docker-compose.external.yml` 주석 수정.**
- **헬퍼를 provider 보다 먼저 두는 이유를 브리프에 명시했다**: 새 provider 가 붙을 자리를 하나로
  만들어 놓지 않으면 **조립 6곳에 "어느 provider 인가" 분기가 여섯 벌 생긴다.**

### Task 2 — README 재색인 절 (오너 조건)

- 파일: [`README.md`](../../../README.md) — `서비스` 축, `### 구성` 과 `### 어디까지 노출하는가`
  사이에 **`### 임베딩 모델을 바꾸면 색인을 다시 만들어야 한다`** 신설(44줄).
- **독자를 "내부 구조를 모르는 사람" 으로 잡았다**(오너 문언). 그래서 절차가 아니라 **왜**부터
  적는다 — 저장된 벡터와 질의 벡터는 같은 모델이 만든 것이어야 거리 비교가 성립한다(다른 지도의
  좌표끼리 거리를 재는 셈).
- **실패 모드 둘을 표로 갈랐다**: 차원이 다르면 **fail-fast 로 멈춘다**(시끄럽다) · 차원이 같은 다른
  모델이면 **아무 일도 안 일어나고 품질만 조용히 떨어진다**(위험한 쪽). 규칙이 *"차원"* 이 아니라
  *"모델"* 기준인 이유가 그 두 번째 칸이다.
- 절차 3단계(env → 재기동 → **프로젝트마다** 스크립트 둘)와 명령을 그대로 적었다.
- **함정 하나를 함께 적었다** — `CHROMA_HOST`·`ELASTICSEARCH_URL` 없이 돌리면 두 스크립트는
  in-memory 가짜에 쓰고 **요약까지 정상 출력한 뒤 사라지는 dry run** 이다(스크립트 docstring 실측).
  실패하지 않으므로 모르면 "재색인했다" 고 믿게 된다.
- **없는 절차를 있는 것처럼 적지 않았다** — 차원까지 바뀔 때의 컬렉션 재생성은 스크립트가 없다.

### Task 3 — 인덱스·HANDOFF 갱신

- [`docs/plans/README.md`](../../plans/README.md) 행을 `오너 결정 대기` → `Resolved(2026-08-19)` 로.
- [`HANDOFF.md`](../../../HANDOFF.md): `Owner Decisions Needed` 에서 임베딩 브리프 항목을 내리고,
  `Next Tasks` 를 **구현 슬라이스**로 교체.

## Issues found

**I-1. 차원까지 바뀌는 경로는 이 저장소에서 검증된 적이 없다 (문서화로 닫음, 코드는 안 건드림).**

- *문제*: 결정 3=A 는 *"차원이 바뀌면 `EMBEDDING_DIMENSIONS` 를 함께 바꾸고 재색인"* 이라고 적지만,
  `phase2b5_reindex_*` 둘은 **기존 컬렉션에 upsert 만** 한다. 컬렉션을 비우거나 다시 만드는 경로가
  없다.
- *실측*: 벡터 삭제 경로 전수 확인 결과 **프로젝트 단위 purge 하나뿐**이다
  ([`chroma.py:372`](../../../services/application/app/indexing/chroma.py#L372) ·
  [`:524`](../../../services/application/app/indexing/chroma.py#L524)).
- *처리*: **이 슬라이스에서 만들지 않는다**(CLAUDE.md §2 — 지금 없는 문제). 대신 README 와 브리프
  유예 절이 **"이 경로는 아직 검증되지 않았다"** 고 명시한다. 트리거 = 실제로 차원이 다른 모델을
  조달할 때.
- *왜 침묵하지 않았나*: 오너 조건이 *"헷갈리지 않게"* 였는데, 절차가 반쪽이라는 사실을 빼면
  README 가 바로 그 헷갈림을 만든다.

### Task 4 — 오너 질문에서 나온 전수 스윕: *"에러인데 어떻게 그린이 떴지? 다른 것도 있나?"*

- **왜 green 이었나 (구조적 원인 셋)**: ① **테스트가 `scripts/` 를 실행하지 않는다** — 스크립트 33개 중 테스트에서 이름조차 참조되지 않는 것이 **10개**, 그중 **9개는 `*_live_smoke.py`(설계상 sandbox-external)** 라 정상이고 **남는 하나가 `calibrate_character_identity_threshold.py`** 다. ② **CI 가 없다**(`.github/` 없음). ③ **타입체커·린터 설정이 없다**(mypy·ruff·pyright·pyproject·setup.cfg 전부 없음). → 시그니처 불일치를 잡을 층이 **하나도 없다.** "green" 은 *"있는 테스트가 전부 통과한다"* 는 뜻이고, 그 테스트 집합에 이 파일이 들어간 적이 없다.
- **같은 형태가 더 있는가 (AST 전수, 353파일 · 정의 4726종)**:
  - **위치 인자 arity 불일치 — 진짜 적중 1건**(그 파일 그 줄). 나머지 6건은 이름 충돌 오탐(`re.match` · `list.index` · 테스트 스텁 `send`).
  - **존재하지 않는 키워드 인자 — 진짜 적중 0건**(17건 전부 테스트 스텁과의 이름 충돌: pymongo `update_one(session=…)` 등).
  - **`from services…import X` 의 X 가 사라진 경우 — 0건.**
- **★ 스윕이 새로 찾은 것: 그 파일은 `:20` 이전에 이미 죽는다.** `sys.path` 부트스트랩이 없어 `python3 scripts/calibrate_character_identity_threshold.py --help` 가 **`ModuleNotFoundError: No module named 'services'`** 로 끝난다(실행 확인). 다른 스크립트(`phase2b5_reindex_memory.py`)는 같은 명령으로 `--help` 가 정상 출력된다 — 부트스트랩 유무가 갈랐다. `PYTHONPATH=/app` 을 주면 그때 `:20` 의 `TypeError` 를 만난다.
- **그래서 결정 4=A 의 이관 범위가 늘었다** — 헬퍼로 옮기는 것만으로는 *"돌아간다"* 가 되지 않는다. **부트스트랩도 함께 넣어야 한다.** 부트스트랩이 없는 스크립트는 6개지만 나머지 5개(`create_user` · `purge_reconciler` · `migrate_ordered_units` · `smoke_llm_provider` · `phase4_lexical_memory_live_smoke`)는 **컨테이너 exec / live smoke 용**이고 `PYTHONPATH=/app` 관례가 이미 문서화돼 있다(2026-07-12 이후 여러 work_log).
- **기록**: HANDOFF `추적 부채` 최상단에 등재했다. 코드는 안 건드렸다 — CLAUDE.md §3(남의 결함은 알리되 손대지 않는다) + 이 결함의 처방이 이미 결정 4=A 로 잡혀 있다.
- **미확인으로 남긴 인접 축 하나**: 위 오탐 17건은 **테스트 스텁이 실제 드라이버 API 를 그대로 흉내 내지 않는다**는 것을 보여 준다(예: 스텁 `update_one` 에 `session` 파라미터가 없다). 스텁이 실물과 갈라지면 그것도 조용한 축인데, **지금 사고가 난 적은 없어 판정하지 않았다.**

## Decisions

**D-2026-08-19-a. 임베딩 어댑터 슬라이스 브리프 결정 1~4 확정.**

| 결정 | 확정값 | 근거 (한 줄) |
|---|---|---|
| 1. 어댑터 자리 | **A** — 앱 안 두 번째 Provider(`OpenAIEmbeddingProvider`) | 저장소가 이미 쓰는 형태 · 리랭커 결정 2=A 와 같은 규율 · 새 컨테이너 0 |
| 2. 배치 | **A** — 단건 유지, Protocol 세 곳 무변 | 병목이 측정된 적 없다 · A→B 는 additive |
| 3. 차원 전환 | **A** — fail-fast 가드 + 수동 재색인 | 가드도 스크립트도 이미 있다 (코드 0줄) |
| 4. 조립 누락 | **A** — 조립 헬퍼 하나 + 전수 가드 | 조립 6곳 중 하나가 **한 달 넘게 깨진 채 green** 이었다 |

- 오너 문언은 **한 줄**이었다: *"다 괜찮네. 추천안 대로 브리프 확정해줘."* — 즉 선택지별 재논의가
  아니라 **브리프의 권고 근거를 그대로 채택**한 것이다.
- *결정 1 의 C(gateway 범용 프록시)는 기각이 아니라 유예*: 리랭커까지 외부로 나가면 앱이 키 둘을
  들게 되고, 그때 다시 볼 값이 생긴다.
- *결정 4 확정의 부수 효과*:
  [`calibrate_character_identity_threshold.py:20`](../../../scripts/calibrate_character_identity_threshold.py#L20)
  의 `TypeError`(2026-07-12 이후 방치)가 헬퍼 이관에 **포함되어 닫힌다.** 별도 부채 항목으로
  남기지 않는다. **다만 그 스크립트를 부르는 테스트는 여전히 0건**이므로 닫혔다는 증거는
  **가드 셀**이지 *"돌려 봤다"* 가 아니다.

**D-2026-08-19-b. 결정 3 의 문서 의무는 runbook 한 줄이 아니라 README 절이다 (오너 지시).**

- 브리프 초안은 *"A 의 약점은 문서로 닫는 종류 — runbook 한 줄"* 로 적었다. 오너가 **자리와 독자를
  바꿨다**: 자리는 **README**, 독자는 **내부 구조를 모르는 사람**.
- *왜 그 변경이 옳은가*: runbook 은 **이미 절차를 아는 사람이 찾아보는 곳**이다. 그런데 이 결함의
  피해자는 *"모델을 바꿔도 되는 줄 아는 사람"* 이라 **runbook 을 찾을 이유 자체가 없다.** 진입점에
  있어야 읽힌다.
- *범위 경계*: README 는 **개념과 절차**까지다. 외부 API 어댑터가 붙은 뒤의 env 서술(`OpenAI 형식
  주소를 어디에 넣는가`)은 **어댑터가 존재한 다음**에 적는다 — 지금 적으면 없는 기능을 문서가
  약속한다.

## Verification

- `python3 -m pytest tests/test_docs_indexes.py -q` → **13 passed**. 이 셀이 잠그는 것은 ① 브리프가
  인덱스에 등재돼 있는가 ② 인덱스·README 의 `.md` 링크가 실제 파일을 가리키는가 두 방향이다.
- **README 의 `.py` 링크는 그 가드의 범위 밖**이다(정규식이 `.md` 만 본다). 그래서 넷을 `ls` 로 직접
  확인했다 — `indexing/embedding.py` · `indexing/chroma.py` · `phase2b5_reindex_memory.py` ·
  `phase2b5_reindex_candidate.py`.
- README 에 쓴 사실 넷의 출처: `EMBEDDING_MODEL_NAME` 기본값 `dragonkue/BGE-m3-ko`
  ([`docker-compose.yml:236`](../../../docker-compose.yml#L236)) · `EMBEDDING_DIMENSIONS` 기본 `1024`
  (같은 파일 107·356·418) · 차원 가드 fail-fast
  ([`embedding.py:79-84`](../../../services/application/app/indexing/embedding.py#L79)) ·
  env 없으면 dry run (두 재색인 스크립트 docstring).
- **코드 0줄** — `git diff --stat` 이 `README.md` · 브리프 · `docs/plans/README.md` · 이 로그뿐임을
  확인했다.

## Next steps

- **다음은 구현이다** — 임베딩 어댑터 슬라이스. 순서는 브리프 §착수 조건: ① 조립 헬퍼 + 전수 가드
  → ② `OpenAIEmbeddingProvider` → ③ README(이미 절이 있으니 **어댑터 env 서술만 추가**) → ④
  `docker-compose.external.yml` §"아직 안 되는 것" 의 임베딩 문단 수정.
- **감마에서 할 수 있는 것은 ①②의 코드·단위 테스트까지다.** 외부 키로 실제 호출을 보내는 것과
  **재색인 지연·호출 수 실측(결정 2 의 트리거)** 은 외부 키 또는 알파/베타가 필요하다.
- 그 뒤가 리랭커 슬라이스([`reranker-slice-decisions.md`](../../plans/reranker-slice-decisions.md)
  Resolved).
