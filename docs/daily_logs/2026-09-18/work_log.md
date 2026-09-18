# 2026-09-18 Work Log

## Goals

- 배포 환경에서 재발한 분석 `/run` 504의 원인을 읽기 전용 실측으로 확정한다.
- 오너가 확정한 세 방향을 구현한다: ① nginx 호출 대기 상한 대폭 확대, ② 분석 출력 문장의 한국어 생성, ③ /review 페이지 컨테이너 폭 확대.

## Completed work

### 504 진단 (읽기 전용)

- **타임라인(UTC, KST=+9)**: 01:17:39 오너가 재시도(`/retry` 200 → PENDING) → UI `POST /run`. 제공자(gemma-4-31b-it)가 불안 구간이어서 key0이 ~215초 걸려 01:21:15 `provider_unavailable`, key1 22초(01:21:37), key2 64초(01:22:41). **01:19:39 — run 시작 후 정확히 120초에 frontend nginx가 `upstream timed out`으로 브라우저에 504 반환**(nginx error log 실측; global-nginx 아님). 서버 작업은 계속돼 key3이 통과, **01:23:42 추출+보고 호출 4건 전부 성공(gemma-4-31b-it)** — 잡 `succeeded`, 후보 7건 저장.
- **핵심 사실**: 504는 실패가 아니라 **거짓 실패**였다. 클라이언트 절단이 서버 작업을 취소하지 않아(plain endpoint) 결과는 버려지고(앱 access log에 `/run` 완료 라인 없음 — 응답 전달 불가 시 uvicorn이 남기지 않는다) 데이터는 살았다. 화면을 새로고침하면 저장된 후보가 보인다.
- **구조 원인 둘**: ① 외부 — 제공자의 시간대별 불안(어제는 429, 오늘은 장기 hang 후 `provider_unavailable`). ② 내부 — `/run`이 동기인데 최악 소요가 nginx 창을 크게 넘는다: 체인 총예산 `LLAMA_TIMEOUT_SECONDS`(배포 300s) × 런당 LLM 호출 ~5회(추출+repair+판단/보고) = 1500s ≫ 120s. nginx 120s는 Writing 루프 60s 예산(v1.6.89)에 맞춘 값이라 분석 체인은 그 산술에 없었다. 어제 배포된 3모델 폴백이 "느리지만 성공"하는 경로를 현실로 만들면서 노출됐다.
- 코드·운영 데이터 변경 없음(진단 단계).

### ① nginx /api/ 프록시 상한 120s→3600s (SoT v1.8.76)

- 오너 결정: "없애거나 대폭 늘려야겠네" — `proxy_read_timeout`/`proxy_send_timeout`을 `frontend/nginx.conf`의 `/api/` location에서 3600s로. 산술 주석(최악 예산 1500s 대비 2배+ 여유, `LLAMA_TIMEOUT_SECONDS` ~700s 초과 인상 시 재검토)을 같이 남겼다. 일반 요청 응답 속도는 무변(상한일 뿐).
- 신규 가드 `FrontendNginxApiProxyTimeoutTest`(`tests/test_frontend_nginx_headers.py`): `/api/` 블록의 read/send 상한 ≥1500s — 되돌림(under)과 예산 미달(over) 둘 다 실패시킨다. env 인상 시 이 셀이 먼저 깨져 재검토를 강제한다.

### ② 분석 출력 한국어 (SoT v1.8.75)

- **관측**: 검토함·상세·작업 패널에 후보 payload 문장(observation/event/question)이 영어로 노출. 원인은 프롬프트에 출력 언어 지시가 없어 모델 기본값(영어)으로 쓰인 것 — 오너 지시 "사용자에게 보여줘야 하는 부분이니 한글로 생성".
- **노출면 전수 확인**: payload 문장(검토함 미리보기·상세·승격 결과) + 판단자 rationale(그룹 행 "근거 — …" 로 노출, `review_inbox.py`가 relation rationale을 자름). `aspect`는 라벨 매핑이 없어 원문 노출이므로 한국어 지시에 포함(스키마는 free string — 무변). `writing_candidate_report`는 프런트 비노출(그레프 0)이라 범위 밖.
- **구현(세 경계 모두 버전 발행)**: 추출 `analysis_extract_v8`(payload 문장 **값만** 한국어 — 구조·키·열거·source_ref 순번 계약·`logical_key` 무변), compare 판단 `analysis_compare_v2`·identity 판단 `analysis_identity_v2`(rationale에 "written in Korean", action/verdict 열거 무변), extractor `_REPAIR_SYSTEM_PROMPT`에 같은 지시(repair 재생성도 같은 언어 계약). 판단자 seed 함수는 v1(동결)+v2(현행)을 한 번에 시드하도록 바꿨고 main.py 두 경로에 v8 시드를 추가했다.
- **동결 핀**: v7은 기존 다이제스트 그대로(변경 없음 확인), v8 신규 핀. 판단자 v1은 **이번에 처음** 다이제스트 핀을 얻었다(배포 Mongo가 v1 본문을 저장했으므로 코드에서 고치면 재기동 시 `PromptTemplateConflict`로 부팅 사망 — extract 축과 같은 실패 방식을 사전에 잠근다).
- 어댑터 기본 버전이 상수를 따라가므로 배선 무변. v7만 시드하던 어댑터 기본 테스트(`test_analysis_extractor_schema`·`test_llm_call_scope`)는 v8로 이관(빌더 테스트 6곳은 시드 반환값을 직접 쓰므로 무변).

### ③ 작업 화면 공용 폭 76rem→100rem

- 오너 관측: "/review에서 인물이 묶였을 때 기본 페이지 넓이가 좁아서 양쪽이 좁아 보인다 — 컨테이너 좌우 폭을 더 넓혀라". "기본 페이지 폭"은 공용 컨테이너(76rem)라서, **공용 폭 자체를 100rem으로** 올렸다(2026-08-26 오너 결정 68→76rem 전례와 같은 결). 개별 화면 폭 오버라이드는 "폭을 정하는 자리는 하나"(10.4) 원칙과 pageLayout 가드 셋 둘 다 깨는 길이라 열지 않았다.
- 다섯 리터럴 일괄 이동: `main`·`.app-header`·`.header-alert`·`.landing-page`의 `max-width`, `.workspace-page,.admin-page`의 `width: min(100%, 100rem)`. 결정 이력을 10.4 주석에, 법률 페이지 주석의 참조값(100rem)도 동기화.

### Verification

| 변이 | 대상 | 기대한 실패 | 결과 |
|---|---|---|---|
| `/api/` read 상한을 3600s→120s로 되돌림 | `frontend/nginx.conf:99` | `FrontendNginxApiProxyTimeoutTest`(read subtest) | 재실패 후 원복 |
| v8에서 한국어 지시 문장 제거 | `prompt_templates.py` `ANALYSIS_EXTRACT_TEMPLATE` | `test_v8_writes_payload_text_in_korean_and_v7_stays_english_neutral` + `test_shipped_template_bodies_are_immutable`(v8 subtest) | 2셀 재실패 후 원복 |
| compare v2 rationale에서 ", written in Korean" 제거 | `compare_judge.py:69` | `test_judge_rationales_are_korean_in_current_and_frozen_in_v1` | 재실패 후 원복 |
| repair 시스템 프롬프트에서 한국어 문단 제거 | `extractor.py` `_REPAIR_SYSTEM_PROMPT` | `test_versioned_prompt_adapter_repairs_invalid_provider_json_once` | 재실패 후 원복 |
| `main`의 max-width만 76rem으로 되돌림 | `styles.css` | pageLayout `keeps the container width equal to the shell it sits in` | 재실패 후 원복 |
| 판단자 seed에서 v1 시딩 제거 | `compare_judge.py` `seed_analysis_compare_template` | `test_judge_seed_replays_both_versions_against_deployed_storage` | 재실패 후 원복 |

- 변이 중 하나(⑥)는 교체문을 잘못 써서 클래스 선언줄이 지워진 적이 있다 — `git checkout`으로 즉시 원복 후 `ast.parse`로 무결 확인, 정확한 변이를 다시 적용했다. 커밋 선행(4c3b77a)이 이 사고를 무해하게 만들었다.
- 전 변이 후 `git status --short` 빈 트리 확인.
- 회귀: 집중(프롬프트·extractor·판단자·스코프·nginx) 61+75+44 passed, 프런트 `pageLayout` 8 passed → **백엔드 전체 3091 passed/1 skipped/4282 subtests**, **프런트 전체 42파일 492 passed**.

## Issues found

| 문제 | 원인 | 해소/대응 | 결과 |
|---|---|---|---|
| 분석 `/run` 504 재발 | 동기 엔드포인트의 최악 소요(체인 300s×~5호출) ≫ nginx 120s — 제공자 불안 구간에 성공 경로조차 창을 넘음 | 오너 결정으로 상한 3600s + ≥1500s 가드 | 느린 run도 끝까지 기다려 실결과 반환. 504 재발 시 env 상한-가드 정합부터 확인 |
| 분석 문장이 영어로 노출 | 프롬프트에 출력 언어 지시 부재(모델 기본 영어) | v8·판단자 v2·repair에 한국어 지시, v7/v1 동결 핀 | 다음 분석부터 한국어. 기존 저장 후보는 그대로(재분석 시 갱신) |
| 판단자 템플릿에 불변 핀 없음 | extract 축만 다이제스트 핀을 가져왔다 | v1 본문 다이제스트 핀 추가 | 본문 무단 수정이 테스트에서 즉시 발각 |
| 감사 레코드가 호출 시작/소요를 기록 안 함 | `llm_call_audits`가 스코프 종료 시 생성 시각만 남김(4건이 3-9ms 간격 배치) | 이번엔 변경 없음 — gateway 로그로 진단 가능했음 | per-call 시작·지연 필드는 별도 관측 슬라이스 재료 |

## Decisions

- **오너(nginx)**: "없애거나 대폭 늘려야겠네" — 3600s로 확대(값은 최악 예산 산술에서 도출). 분석은 느려도 성공함을 확인하고 내린 결정이다.
- **오너(한국어)**: 사용자에게 보여주는 분석 문장은 한글 생성. 구조 계약은 무변.
- **오너(폭)**: /review의 묶임 뷰가 빡빡하니 컨테이너 폭 확대 — "기본 페이지 폭"의 정본(공용 컨테이너)을 넓히는 것으로 해석해 전역 100rem. 개별 화면 예외는 규칙 위반이라 안 함.
- 진단은 읽기 전용으로 마쳤고(재시작·재배포·데이터 수정 없음), 구현은 오너 메시지로 확정된 세 방향만.
- HANDOFF 무변 — 세 변경 모두 완결됐고 지속 상태가 아니며, 배포 대기 절차는 아래 Next steps와 CHANGELOG가 운반한다.

## Next steps

- **배포(오너 push 후, 어제와 같은 절차)**: 배포 서버 `main` fast-forward → 공유 앱 이미지 재빌드 후 다섯 서비스 재생성(한국어 프롬프트 v8·판단자 v2·repair — 부팅 시 `prompt_templates`에 v8/v2 seed, 신규 버전이라 conflict 없음) → **frontend 컨테이너도 재생성**(nginx.conf가 이미지에 구웠다) → `/health` 200·restart 0·로그 오류 없음 확인. 배포 Mongo에 `analysis_extract_v8`·`analysis_compare_v2`·`analysis_identity_v2` seed 확인.
- 배포 뒤 검증: ① 이어지는 분석의 후보 문장·그룹 "근거 —"가 한국어인지, ② 제공자 불안 시 `/run`이 504 없이(장시간 대기 후) 완결되는지, ③ /review가 넓은 폭으로 보이는지. 브라우저→frontend 443 경로에 다른 절단점이 있는지(오늘 실측은 frontend 120s가 먼저였음)도 함께 본다.
- 기존 영어 후보는 재분석해야 한국어로 갱신된다(같은 snapshot 재분석은 재시도 경로, 저장 없이 가능).
