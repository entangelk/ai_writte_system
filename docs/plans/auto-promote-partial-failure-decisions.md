# Decision brief — `auto_promote_job` 부분 실패 의미론

상태: `Approved — 2026-07-24 (D1=B · D2=A · D3=404)`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md) §상태코드 의미론(v1.7.29 H3 S1), 승격 idempotency 조항(v1.6.40 기술 — "job auto-promote 응답의 `promoted[]`는 **이번 호출에서 신규 승격된 memory만** 담는다")
대상 코드: [`services/application/app/main.py:2572-2600`](../../services/application/app/main.py#L2572-L2600)
계기: H3 에러 응답 계약 페이즈(S1~S5)가 60개 endpoint의 realistic 에러를 선언하며 닫혔으나, 미매핑 500 누수 2건 중 **1건이 코드 매핑으로 닫히지 않아** 남았다. v1.7.34가 다른 1건(source-block rebuild 502)을 닫으면서 이 건을 "코드 매핑보다 계약 질문"으로 분류해 오너 판단으로 이월했다.

## Owner decisions — 2026-07-24

- **D1 = B (부분 성공 봉투)**. 실패 시에도 이번 호출에서 새로 mint된 `promoted[]`를 실패 상태코드와 함께 반환한다. 채택 근거는 아래 추천 사유 3개 그대로 — mint 불가역이라 숨기면 응답이 시스템 상태와 어긋나고, writing accept의 502 partial이 동형 선례이며, 프론트 소비자가 아직 0이라 지금이 가장 싸다.
- **D2 = A (503의 세 번째 얼굴)**. 정본 저장소 장애를 503 의미론에 명시적으로 편입한다. 정본 상태코드 표와 "503의 두 얼굴" 절을 함께 증보한다(→ 세 얼굴).
- **D3 = 404**(논쟁 없음). 형제인 수동 promote와 동일 매핑, 선언 집합 무변.

구현 시 확인된 제약 하나 — **잡을 예외 타입을 어디에 두는가**: `main.py`는 pymongo를 **의도적으로 지연 임포트**한다(in-memory 경로가 드라이버 설치 없이 떠야 한다, `_default_core_sot_service`). 따라서 모듈 최상단에 `from pymongo.errors import PyMongoError`를 둘 수 없고, "Follow-up considerations"가 요구한 **단일 seam**도 함께 만족해야 한다. 해결: 지연 해석 튜플 `_STORAGE_ERRORS`를 한 곳에 두고, 드라이버 부재 시 빈 튜플로 축약한다(`except ()`는 아무것도 잡지 않으므로 Mongo 없는 배포에서 분류할 Mongo 장애도 없다는 사실과 정합). 이 seam이 저장소·outbox 양쪽 실패를 **한 지점**에서 덮으므로 후속 taxonomy는 이 한 줄만 교체하면 된다.

## Decision needed

`POST /projects/{id}/analysis/jobs/{job_id}/auto-promote`는 job의 candidate를 **루프로 순회하며 하나씩** canonical memory로 승격한다. 그 루프가 `try` 밖이라 N번째에서 예외가 나면 **앞의 N-1건은 이미 영속된 채** opaque 500이 나간다. 무엇을 반환할지는 코드에서 유도되지 않는다 — **일부 승격 뒤 실패는 "성공한 요청"인가 "실패한 요청"인가**가 먼저 정해져야 매핑이 결정된다.

부수적으로, 그 매핑이 무엇이든 **찍을 상태코드가 정본에 없다**(§D2).

### 현재 코드가 하는 일 (1차 소스)

```python
# main.py:2588-2600 — 루프 전체가 try 밖
promoted = []
for candidate in candidates:
    if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:
        continue
    result = memory.auto_promote_candidate(project_id=project_id, candidate=candidate)
    if result is not None and not result.idempotent_replay:
        promoted.append(_memory_payload(result.memory))
return {"auto_promotion_threshold": ..., "promoted": promoted}
```

- 선언은 `responses=_ERRORS_404`뿐이고, 전수 선언 가드도 `{"404"}`로 잠겨 있다([`tests/test_application_api.py:2244`](../../tests/test_application_api.py#L2244)).
- 앱에 전역 exception handler가 **없다**(`main.py`에 `exception_handler` 0건) → 루프 안의 모든 미포착 예외 = **500**.

### 실제로 터질 수 있는 것 (경로별)

| 예외 | 발생 지점 | 도달성 |
|---|---|---|
| 원시 pymongo 예외(`ServerSelectionTimeoutError`·`AutoReconnect`·`WriteError` 등) | [`memory/mongo_repository.py:88-94`](../../services/application/app/memory/mongo_repository.py#L88-L94) — `put_memory`가 `DuplicateKeyError`만 `DuplicatePromotionRequest`로 감싸고 **나머지는 그대로 통과** | **실질 주 경로.** Mongo 장애·네트워크 단절·쓰기 거부 |
| outbox enqueue 실패 | [`memory/service.py:194,324-332`](../../services/application/app/memory/service.py#L324-L332) — `_enqueue_reindex`는 `put_memory` **이후**에 별도 write | 도달 가능. 이 경우 memory는 있는데 재색인이 유실된다 |
| `MemoryNotFound` | [`memory/service.py:156,161`](../../services/application/app/memory/service.py#L148-L163) — project 불일치 / `_require_memory` | 실질 도달 불가(candidate가 `list_candidates(project_id=...)` 산출물이라 불일치가 성립하지 않음). 다만 방어적 raise이고 `ValueError` 계열이라 **잡히면 404가 자연스럽다** |

### 왜 이게 코드 매핑으로 안 닫히나

승격은 **되돌릴 수 없다**. memory는 append-only이고(Active Decision: "memory는 append-only"), canonical mint는 정책상 삭제 대상이 아니다. 그래서 "실패했으니 아무 일도 없었던 것으로 응답한다"가 A안에서 **거짓말이 된다** — 시스템 상태와 응답이 어긋난다. 반대로 "일부 성공했으니 200"은 인프라 장애를 본문 안에 숨긴다. 어느 쪽을 감수할지가 오너 결정이다.

**단, 복구 경로는 이미 계약에 있다**: SoT v1.6.40 조항이 승격 idempotency를 `(project_id, source_candidate_id)` unique index로 못박고, 재호출은 replay라 재보고하지 않는다. 즉 **어떤 안을 택하든 "그냥 다시 호출한다"가 안전한 복구다.** 이 사실이 A안의 비용을 크게 낮춘다.

## D1. 부분 실패 시 응답 형태

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 전체 실패 (단일 상태코드)** | 루프를 `try`로 감싸 예외를 상태코드로 매핑. 이미 승격된 N-1건은 **영속된 채 남지만 응답에는 담지 않는다**. | 구현이 가장 작다(±10줄). 봉투가 하나로 유지돼 프론트 분기 불필요. 재호출이 idempotent라 복구가 자명하다. | 응답과 실제 상태가 어긋난다 — "실패"인데 canonical이 늘어 있다. 사용자가 `GET /memory`를 보기 전까지 모른다. |
| **B. 부분 성공 봉투 (선례 준수)** | 실패 시에도 `{"auto_promotion_threshold", "promoted":[…이번에 mint된 것], "promotion_error": <str>}`를 실패 상태코드와 함께 반환. | 실제로 mint된 canonical을 숨기지 않는다 → append-only 정책과 정합. **코드 내 직접 선례가 있다**: writing accept의 `WritingAcceptAnalysisError` → 502 + `{"accepted":true,"saved":…,"analysis_error":…}`([`main.py:4110-4121`](../../services/application/app/main.py#L4110-L4121)). 상태코드=기계용/본문=사람용이라는 H3 3층 계약을 지킨다. | 봉투가 성공형·부분형 두 가지가 된다. OpenAPI 재덤프 + 타입 재생성 필요. |
| **C. 200 + 실패 항목 보고** | `{"promoted":[…], "failed":[{candidate_id, error}]}`를 **200**으로. | 배치 연산의 자연스러운 표현. 개별 candidate 실패를 격리해 나머지를 계속 승격할 수 있다. | **H3 계약 위반 소지**: 상태코드가 기계용 의미론인데 인프라 장애를 200으로 감춘다. 클라이언트가 본문을 파싱해야 실패를 안다. Mongo가 죽은 경우 "계속 진행"도 무의미(전건 실패). |
| **D. 전부-또는-전무 (트랜잭션)** | 루프 전체를 하나의 Mongo 트랜잭션으로 묶어 실패 시 롤백. | 부분 상태 자체가 사라져 계약 질문이 소멸한다. | 슬라이스 크기가 다른 안들과 다르다 — `promote_candidate`가 자체 write + outbox enqueue를 하므로 서비스 계층 관통 변경이 필요하고, **non-transaction fallback(single-writer local/test 전용)에서는 보장이 없어** 환경별로 의미가 갈린다. |

**추천: B.**

이유는 세 가지다.

1. **정책 정합.** memory append-only + canonical mint 불가역이라는 확정된 경계 아래에서, mint된 것을 응답에서 지우는 A/D는 시스템 상태와 응답을 어긋나게 한다. B는 "무엇이 남았는지"를 응답이 그대로 말한다.
2. **선례가 이미 이 모양이다.** writing accept의 502 partial은 "정본은 저장됐고 후속만 실패"라는 동일 구조이고, 이미 정본·테스트·프론트 타입에 반영돼 있다. 새 패턴을 만드는 게 아니라 있는 패턴을 적용하는 것이다.
3. **지금이 가장 싸다.** 이 endpoint의 **프론트 소비자가 0건**이다(`grep -rn "auto-promote" frontend/src` → `schema.d.ts` 생성물 외 없음). 봉투를 넓히는 비용이 지금은 타입 재생성뿐이고, dogfood에서 UI가 붙은 뒤에는 그렇지 않다.

**B를 택할 때 선례와 다른 점 하나**는 명시해 둘 값어치가 있다: writing accept는 저장 단위가 1건 고정이라 "정본은 저장됐다"가 단정문인 반면, 여기는 **승격 개수가 가변 N**이다. 그래서 봉투에는 개수를 단정하는 필드를 두지 말고 `promoted[]`(이번 호출에서 새로 mint된 것) 자체를 그대로 담는다 — 가변성이 배열 길이로 자연히 표현되고, 성공형 봉투의 `promoted[]` 의미론(v1.6.40 조항)과 정확히 같은 뜻을 유지한다.

**A를 택할 만한 반론도 실재한다**: 재호출이 idempotent라 실무상 복구가 "다시 누른다"로 끝나고, 그렇다면 부분 상태를 응답에 노출할 실익이 적다는 판단은 성립한다. 이 경우 D2만 결정하면 슬라이스가 절반으로 줄어든다.

## D2. 저장소(Mongo) 장애의 상태코드 — 정본 증보가 필요하다

D1을 무엇으로 정하든 **찍을 코드가 정본에 없다.** 상태코드 의미론 표([`system-contract-sot.md:314-318`](../system-contract-sot.md))에서:

- **502** = "**상류**(LLM provider·gateway·검색·임베딩)가 실패" — Mongo는 상류 협력자가 아니라 **정본 저장소**다.
- **503** = "협력자 **미구성**" 또는 "저장 데이터 **마이그레이션 필요**(`DraftOrderIntegrityError`)" — 둘 다 아니다.

즉 "정본 저장소가 있는데 실패했다"는 얼굴이 표에 없다. 이건 코드가 임의로 고를 문제가 아니라 **계약 공백**이다(CLAUDE.md: spec-silent-but-code-enforced는 계약 증보 요청 대상).

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 503 세 번째 얼굴로 증보** | "503의 두 얼굴"을 **세 얼굴**로 넓혀 "정본 저장소 장애(요청을 고쳐 해결되지 않음)"를 추가. | 503의 정의문 "서버가 **지금** 이 연산을 수행할 수 없다. 요청을 고쳐서는 해결되지 않는다"에 의미가 정확히 들어맞는다. 재시도 가능성을 클라이언트에 정직하게 알린다. | 503이 이미 두 얼굴이라 세 번째를 더하면 "503을 보면 무엇을 해야 하나"가 더 흐려진다. |
| **B. 502 정의 확장** | 502의 "상류"에 정본 저장소를 포함. | 신규 행이 없다. "있는데 실패한 것은 502"라는 v1.7.34의 구분 규칙과 표면적으로 맞는다. | **502는 상류/AI 출력 실패를 뜻하게 설계됐다.** 정본 저장소 장애를 같은 코드에 넣으면 "AI/검색이 이상하다"와 "DB가 죽었다"가 구분 불가가 된다 — 운영상 완전히 다른 대응이다. |
| **C. 500을 계약된 코드로 승격** | "미매핑 누수"가 아니라 "정본 저장소 장애 = 500"으로 정본에 명시. | 의미상 가장 정직하다(서버 내부 실패). 코드 변경이 최소. | H3 페이즈 전체가 **500을 누수로 규정하고 제거해 왔다.** 이제 와서 계약된 500을 만들면 "선언되지 않은 500은 버그"라는 가드의 판정력이 약해진다. |
| **D. 이 슬라이스에서 결정하지 않음** | pymongo 예외를 감싸는 저장소 계층 taxonomy(별도 부채)를 먼저 세우고, 그 위에서 매핑. | 근본 원인(저장소가 pymongo 예외를 안 감싼다)을 먼저 닫는다. 이 endpoint만의 미봉을 피한다. | 이 부채가 계속 열려 있다. 슬라이스가 커지고 범위가 이 endpoint를 넘어간다. |

**추천: A.** 503 정의문이 이미 이 상황을 정확히 기술하고 있고("지금 수행할 수 없다 / 요청을 고쳐서는 해결되지 않는다"), 재시도가 유효한 복구라는 점도 503의 관용적 의미와 맞는다. 세 얼굴이 되는 부담은 **"503의 세 얼굴" 절에 각 얼굴의 해결 주체를 한 줄씩 적어** 상쇄한다 — 배포 구성 / 마이그레이션 스크립트 실행 / 저장소 복구 후 재호출.

D는 방향이 옳지만 **범위가 이 endpoint를 훨씬 넘는다**(모든 `*_mongo.py` 저장소가 같은 상태다). D를 택하겠다면 이 브리프의 슬라이스를 보류하고 저장소 taxonomy 슬라이스를 먼저 열어야 한다 — 그 판단 자체가 오너 몫이라 선택지로 남긴다.

## D3. `MemoryNotFound` 매핑 (부수, 논쟁 없음)

루프 안의 `MemoryNotFound`는 실질 도달 불가지만 방어적으로 존재한다. 잡는다면 **404** — 이 endpoint의 기존 404 절, 그리고 형제인 수동 promote([`main.py:2484`](../../services/application/app/main.py#L2484))가 `MemoryNotFound`를 404로 매핑하는 것과 동일하다. 선언 집합은 이미 `{404}`라 **OpenAPI 변화 없음**. D1/D2와 독립적으로 함께 처리하면 된다.

## Follow-up considerations (열어 둘 문)

- **저장소 예외 taxonomy**(D2-D의 내용)를 나중에 세울 때, 이 슬라이스가 그 자리를 막지 않아야 한다. 매핑을 endpoint의 `except` 절에 인라인으로 박기보다, 잡는 예외 종류를 **한 곳에 상수/헬퍼로** 두면 후속 taxonomy가 그 지점만 교체할 수 있다.
- **outbox enqueue 실패는 `put_memory` 성공 이후**다(`service.py:194`). D1=B의 봉투는 이 경우 "memory는 mint됐고 재색인만 유실"이라는 **세 번째 상태**를 표현하게 된다 — 지금 필드를 만들 필요는 없지만, `promotion_error` 문자열이 이 구분을 삼키지 않도록 메시지에 어느 단계에서 실패했는지 남긴다.
- 이 endpoint는 **아직 프론트 소비자가 없다.** dogfood에서 리뷰 인박스가 auto-promote를 부르기 시작하면 봉투 형태는 훨씬 비싸게 굳는다. 그 전에 정하는 편이 싸다.

## Deferred / out of scope (이 브리프에서 결정하지 않는 것)

- 전 저장소(`*_mongo.py`)의 pymongo 예외 wrapping — D2=D를 택하지 않는 한 별도 슬라이스.
- 승격 루프의 트랜잭션화(D1=D를 택하지 않는 한).
- auto-promotion threshold 실수치 캘리브레이션(품질 fixture 선행, SoT v1.6.39 이래 미확정 유지).
- 프론트 에러 UX — H3 D4=A로 이미 페이즈 밖.
- `analysis/jobs/{id}/apply` 등 다른 배치성 endpoint의 부분 실패 — 같은 질문이 있는지는 이 결정 확정 후 패턴 스윕으로 확인한다.

## 결정 후 해야 할 일

1. 결정과 근거를 `docs/daily_logs/YYYY-MM-DD/work_log.md`에 기록(User Decisions and Rationale).
2. D2가 정본 표를 바꾸므로 **`system-contract-sot.md` 상태코드 의미론 + 503 절을 구현과 같거나 앞선 시점에** 갱신하고 버전을 올린다.
3. 구현 + 회귀: under-strict(루프 절 제거 시 500 재발) · over-strict(절을 `except Exception`으로 넓히면 무관한 오류가 오분류되는 것을 실패시킴) 양방향 가드, D1=B면 부분 봉투 형태 단정 1건.
4. 선언 집합이 바뀌면 `responses=` + [`tests/test_application_api.py:2244`](../../tests/test_application_api.py#L2244) lock + `scripts/dump_openapi.py` 재덤프 + 프론트 `npm run gen:api`.
