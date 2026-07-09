# Work Log — 2026-07-10

## Goals

- HANDOFF와 2026-07-09 work log를 읽고 다음 작업을 진행한다.
- 오너 지시: **튜닝(b-4)은 최후순위로 미루고, 오너 결정 브리프 없이 처리 가능한 작은 작업부터** 진행.
- 반복 추적되던 소부채 **`ConnectElasticsearchTest` skip guard**(b-5 후속)를 닫아 sandbox의 3 환경-의존 failed를 제거한다.

## Completed work

### `ConnectElasticsearchTest` skip guard (b-5 후속, 테스트 전용)

- **선택 근거**: HANDOFF Next Tasks #1의 큰 후보((b-4) 튜닝·(c)~(e)·Phase 6)는 전부 오너 선택 + 착수 결정 브리프가 선행이라 임의 착수 불가. 반면 이 skip guard는 HANDOFF:89·2026-07-09 work_log:267·277에서 반복 추적된 자족적 소부채이고 오너 결정 불필요 — 오너의 "작은 작업부터" 지시에 정확히 부합.
- **문제**: `tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest`(b-5 도입)는 배포 `connect_elasticsearch_memory_index` boot 경로를 검증하려고 `from elasticsearch import Elasticsearch`(구 217행)와 `mock.patch("elasticsearch.Elasticsearch", …)`(구 225행)로 실 `elasticsearch` 패키지를 요구한다. sandbox에 패키지가 없어 3개가 `ModuleNotFoundError`로 **hard-fail** → green bar가 "704 passed + 3 failed"로 오독됨. (같은 파일 docstring 5–7행은 "unit-tested with a fake client — no elasticsearch package"라 주장하지만 이 클래스만은 예외적으로 패키지에 의존 — docstring이 서술하는 대상은 `ElasticsearchAdapterTest`[fake client 주입]이고 `ConnectElasticsearchTest`는 별개 관심사라 docstring은 무변으로 둠.)
- **수정**(외과적, 테스트 전용):
  - `tests/test_context_search_memory_lexical_retrieval.py`: 상단에 `import importlib.util` 추가.
  - `ConnectElasticsearchTest`에 `@unittest.skipUnless(importlib.util.find_spec("elasticsearch") is not None, …)` 클래스 데코레이터 추가. 패키지가 있으면 종전대로 3개 실행, 없으면 skip.
- **다른 테스트 무영향**: 같은 파일의 `ElasticsearchAdapterTest`·`LexicalDrainTest` 등은 fake adapter/client 객체를 직접 주입해 `elasticsearch` 패키지에 의존하지 않는다. 프로덕션 모듈(`indexing/memory_lexical_index.py:303`·`candidate_lexical_index.py:254`)은 함수 내부 lazy import(`# lazy: optional dependency`)라 collection 시점에 실패하지 않는다 → guard가 필요한 곳은 이 클래스 하나뿐.

## Pattern sweep (CLAUDE.md §4)

- `mock.patch("elasticsearch…"` / `from elasticsearch import` repo-wide grep → tests/ 내 유일 발생이 이 파일 217·225행(둘 다 이제 guard된 `ConnectElasticsearchTest` 내부). 다른 테스트엔 동일 패턴 없음.
- 프로덕션 2곳은 lazy import라 무해. 패턴이 한 클래스에 격리 확인 → 추가 조치 불필요.

## Issues found

- 없음.

## Decisions

- **SoT 버전 bump 안 함**: 이 변경은 **테스트 인프라 전용**(skip guard) — 계약 literal·public interface·프로덕션 코드 무변, 동작 변화 0. v1.6.53처럼 프로덕션 `connect_` 기본값을 건드린 slice와 성격이 다르고, 오너가 선택한 slice도 아니라 버전 로그에 항목을 만들지 않는다. HANDOFF의 테스트 카운트(3 failed 제거)만 갱신.
- 3 failed → 3 skipped로 전환(45→48 skipped). "환경 의존 failed"라는 상시 각주 자체를 제거해 green bar 오독 가능성을 없앤다.

## Verification

- `python3 -m pytest tests/test_context_search_memory_lexical_retrieval.py -q` → **13 passed / 3 skipped**(패키지 부재 시 guard 발동).
- `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **704 passed / 48 skipped**(종전 704 passed / 45 skipped + 3 failed → failed 0). `git diff --check` clean.
- 이 sandbox엔 `elasticsearch` 미설치라 guard가 skip 경로로 검증됨. 패키지 있는 환경(b-5/b-6 작업 환경, "703 passed" 기록)에선 종전대로 3개 실행되어 회귀 잠금 유지.

## 검증 후속 보강 (오너 독립 감사 PASS → outstanding 2건 closure)

오너 독립 검증(`docs/verifications/2026-07-10/connect_elasticsearch_skip_guard.md`)이 **합격(PASS)** — 모든 카운트 독립 재현, under-strict guard 실증(guard 제거 시 정확히 3 hard-fail 재현). 검증자가 남긴 비차단 outstanding 2건을 오너 지시로 닫았다.

- **outstanding #1 — over-strict 실행 경로 실증**(종전 논리-only): 이 sandbox에 `elasticsearch>=8,<9`(requirements.txt 핀, 설치 8.19.3)를 scratchpad 격리 디렉토리에 `pip install --target`으로 설치하고 **PYTHONPATH 주입으로만** 노출(시스템 Python 무오염, 가역적). 패키지 present 시 guard가 skip하지 않고 3개 실행·전부 PASS(파일 단독 16 passed/0 skipped, 전체 스위트 **707 passed/45 skipped**) → over-strict 방향(`find_spec is not None`→실행) 실증, b-5 회귀 잠금이 패키지 있는 환경에서 유지됨을 확인. PYTHONPATH 미주입 시 `find_spec`=None·파일 단독 13/3으로 원상복구 확인(격리 무오염). under/over 양방향 실증 완료.
- **outstanding #2 — HANDOFF:103 stale 정정**: 오너 승인 하에 `HANDOFF.md:103` Project Structure 주석 `(Approved, v1.6.57)`→`(Approved, v1.6.58)` 1행 정정(8행과 정합). 선재 stale 독립 정정.

## Next steps

- HANDOFF Next Tasks #1의 다음 slice는 여전히 **오너 선택 대기**((b-4) hybrid 튜닝[최후순위 지시]·(c)~(e)·Phase 6). 각 후보는 착수 결정 브리프 선행.
- sandbox 밖 후속(코드 완료, 여기서 막힘)은 무변: 2B.6 threshold 캘리브레이션·2B.5/b-2/b-6 live 관통·ES-lexical/vector live backfill.
