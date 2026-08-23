# extractor 안정화 슬라이스(8192 + 프롬프트 v5 + 열린 펜스 가드) — 독립 검증

## Subject metadata

- 날짜: 2026-08-23 (검증 세션 — 구현 세션(같은 날 세션 6)과 다른 AI 세션)
- 요청자: 오너 — *"작업 AI가 작업한거 검증하고 의심하고 또 의심해줄래?"*
  (HANDOFF 관례: 오늘 슬라이스는 다음 검증자의 반증 대상).
- 대상: `bb1ac41`(구현) + `6567286`(v5 시드 누락 보충) — **검증 단위는 둘의 합**.
  `bb1ac41` 단독은 red 2셀이다(아래 Findings 4에서 재현). `22ff6c6`(docs)는 문서만.
- 정규 스펙: SoT **v1.7.99** 변경이력 + 오너 결정 원문(*"a는 넉넉하게 8192까지 하고
  b는 프롬포트 내 명시 뿐만 아니라 파싱 가드 처리도 해야할꺼같은데?"*) +
  [`daily_logs/2026-08-23/work_log.md`](../../daily_logs/2026-08-23/work_log.md) 세션 5(원인 규명)·6(시행).
- 소스: 커밋 `bb1ac41`·`6567286`, HEAD(`22ff6c6`) 클린 트리에서 검증.

## Scope

- 계약: SoT v1.7.99의 처방 셋을 경계 행렬로 먼저 세웠다 — ① 조립 기본 2048→**8192**
  (env 기본은 조립 지점에만 존재) ② 프롬프트 **v5** "raw JSON only, 펜스 금지" 명시
  (v4 본문 보존 sha `b946a7…`·v5 핀 `bc2a0b…`·seed 체인 v1~v5) ③ `strip_code_fence`
  **열린 펜스 회복** — 선두 펜스 뒤 나머지 전체가 하나의 온전 JSON 문서일 때만
  (미완결 JSON·trailing prose는 여전히 거부 — extraction not relaxation), ③은
  gate·report·compare·extractor·planner·retrieval 전 파서 공유.
- ★ 최우선 의심 축: (i) 열린 펜스 회복이 사실상 relaxation으로 샌다는 가능성
  (over-strict), (ii) 8192가 실제 조립에 반영됐는가(소스 스캔 셀의 정당성),
  (iii) v4 본문 보존·v5 핀 무결(immutable 절차 — 옛 볼륨 부팅 충돌의 뿌리),
  (iv) 6567286이 정말 bb1ac41의 red를 닫았는가.
- 구현: `writing/json_extract.py`(열린 펜스)·`application/app/main.py`(기본 8192·
  seed v5 양쪽 조립 분기)·`analysis/prompt_templates.py`(v4 상수화·v5 신규).
- 회귀셀: `test_json_extract.py` 신규 6셀·`AssemblyDefaultTest` 1셀·핀 셀 확장·
  시드 체인 갱신 3파일(`test_analysis_extractor_schema`·`test_prompt_templates`·
  `test_llm_call_scope`) — 감사의 대상으로 전수 정독.
- 전수 수트: HEAD에서 백엔드 전수 독립 재실측(기준선 2489 검산).
- 라이브 관통(알파 phase2a 3회 연속 성공 등)은 **본 검증 범위 밖** — 구현자 기록으로만 확인.

## Methodology

재현 환경(측정의 일부): 폴백 슬라이스 검증 기록(같은 날)과 동일 — WSL2, 메인 스택
기동 중, test-mongo 기동·healthy 대기, `mypy` 설치됨, `.env` 14키. 뮤테이션 절차도
동일(tree clean 게이트 → Edit 변이 → 요약 count 줄 + `FAILED|SUBFAILED` 판독 →
`git checkout --` → 클린 확인). sha 재계산은 브리프/SoT의 핀 값을 신뢰하지 않고
직접 다시 섰다.

```bash
git status --short                                        # 빈 것 확인
python3 -c "import hashlib; from services.application.app.analysis.prompt_templates import \
  ANALYSIS_EXTRACT_TEMPLATE_V4 as v4, ANALYSIS_EXTRACT_TEMPLATE as v5; \
  print('v4', hashlib.sha256(v4.encode()).hexdigest()); \
  print('v5', hashlib.sha256(v5.encode()).hexdigest())"
# → v4 b946a70514de99c2fbe84fbef1f1e41cd6086e496fb0a2642cffa6045e3fd6bd
#   v5 bc2a0b126fe3342a31da2fcc566cd29eb5557ea83add13838dbc290400834751  (핀과 일치)
python3 -m pytest -q tests/test_json_extract.py tests/test_prompt_templates.py \
  tests/test_analysis_extractor_schema.py tests/test_analysis_prompt_builder.py \
  tests/test_llm_call_scope.py
# → 66 passed, 23 subtests (4.7s)
docker compose -f docker-compose.test.yml up -d           # healthy 대기
python3 -m pytest -q                                      # 2489 passed, 4 skipped, 2718 subtests (229.8s)
docker compose -f docker-compose.test.yml down
grep -rn "strip_code_fence" services/ --include="*.py"    # 공유 6호출부 확인
```

## Findings

### 1. 정량·정성 클레임 — 전부 재현

| 클레임 | 실측 | 판정 |
|---|---|---|
| v4 핀 `b946a7…` 무변 | 재계산 일치 + v4↔v5 본문 diff가 명시된 2줄("as raw JSON text only" 추가·펜스 금지 문장 신설)뿐 | 일치 |
| v5 핀 `bc2a0b…` 추가 | 재계산 일치 (`test_prompt_templates` 핀 셀 green) | 일치 |
| seed 체인 v1~v5 + 조립 양쪽 분기 | `main.py` 두 `_default_prompt_template_service` 분기에 `seed_analysis_extract_v5()` | 일치 |
| "전 파서 공유 적용" | grep — `gate_prompt.py`·`report.py`·`compare_judge.py`·`extractor.py`·`planner.py`·`retrieval.py` 정확히 6호출부 | 일치 |
| 신규 7셀(json_extract 6·조립 스캔 1)·subtest +1(핀 v5) | 셀 수 실측 일치(6+1), 핀 딕셔너리 +1 항목 | 일치 |
| 전수 2489 passed / skip 4 / subtest 2718 (234초) | **2489 / 4 / 2718 (229.8s, exit 0)** — skip 4 구성(Chroma 1 + ES 3)도 실측 | 일치 |

### 2. 열린 펜스 회복 — 경계 행렬 전 셀 충족, relaxation 아님

정독 + 변이 케이스 분석: 닫힌 펜스는 종전 정규식 우선(`_CODE_FENCE_RE`)·회복은
`_OPEN_CODE_FENCE_RE`이 잔여를 통째로 잡아 `json.loads` 로 온전성을 **먼저** 검사한다.
잔여에 trailing prose가 붙으면 파싱 실패로 원문 그대로 반환(하위 strict 검사가 거부)·
본문 자체가 끊겨도 마찬가니다. 잔여가 빈 문자열이면 `[\s\S]+` 미매치로 회복 없음.
펜스가 JSON 문자열 값 안에 등장하는 형태(`{"a": "```x"}`)는 회복 정상 작동.
llamacpp 형식에서 게이트웨이가 content 를 고치지 않는 것과 별개로, 앱 파서 6곳은
형식 무관하게 같은 회복을 받는다 — SoT v1.7.99 문술과 정확히 일치.

### 3. 뮤테이션 5종 — 전부 표적 셀 재실패

| id | 적용한 diff | 물린 셀 |
|---|---|---|
| X1 | `json_extract.py` 열린 펜스 분기 `return body` → `return content` (회복 무력화) | 1셀 `test_an_open_fence_with_complete_json_body_is_recovered` |
| X2 | `json_extract.py` `try: json.loads(body) / except ValueError: return content` 4줄 삭제 → 무조건 `return body` | 2셀 `…truncated_json…`·`…trailing_prose…` (over-strict 양쪽) |
| X3 | `main.py` `os.environ.get("ANALYSIS_EXTRACT_MAX_TOKENS", "8192")` → `"2048"` 원복 | 1셀 `AssemblyDefaultTest…` (소스 스캔 — 리터럴 핀이므로 값이 커지는 방향도 잡힘) |
| X4 | `prompt_templates.py` v5에서 `Do not wrap the JSON in markdown code fences: …` 문장 삭제 | 1 SUBFAILED `test_shipped_template_bodies_are_immutable`(version='analysis_extract_v5') |
| X5 | `test_llm_call_scope.py`에서 `templates.seed_analysis_extract_v5()` 1행 삭제(= 6567286 거꾸로 적용) | 2셀 `ExtractorRepairIsRecordedTest::test_a_clean_extraction…`·`…repaired…` |

전 뮤테이션 후 `git status --short` 빈 것 확인(5회 전부 복구·클린).

### 4. bb1ac41 단독 red 경위 — 재현 확인

X5(=6567286 취소)에서 정확히 그 2셀이 실패했다(`extractor.py:127
AnalysisExtractionError` — 어댑터가 v5 시드 없는 fixture에서 현재 버전을 못 찾는다).
구현자 기록 *"전수에서만 드러난 2셀… fixture 변수명(templates)이 첫 패치 조건을 피해
간 자리"* 와 사실로 일치한다. 즉 **`bb1ac41` 단독은 green 이 아니었고 `6567286`이
닫았다** — 검증 단위를 둘의 합으로 잡은 이유. 이 경위 자체는 work_log·HANDOFF에
정직하게 기록돼 있었다(2487+2 → 2489).

### 5. 문서 정합성

- SoT v1.7.99 항목과 코드·테스트가 문장 단위로 대응(처방 셋·공유 6파서·"빈 답" 부수
  실측 언급 포함). 세션 5가 처방 C(열린 펜스 확장)를 "끊긴 케이스는 JSON 자체도
  무효"라 각하 권고했으나 세션 6 실측이 그 전제를 뒤집고 오너 결정문이 파싱 가드를
  명시적으로 요구했다 — 문서 간 모순 없이 일관되게 수렴했다.
- `test_analysis_prompt_builder` 의 `prompt_version` 비교가 상수→`template.version`로
  바뀌어 이 파일의 현재-버전 핀이 사라졌으나, 현재 버전 리터럴("analysis_extract_v5")과
  본문 다이제스트는 `test_prompt_templates`(핀 셀·seed 체인 셀)이 잠근다 — 구멍 아님.

## Issues / Risks

### Blocking (계약 의무)

- 없음.

### Hardening recommendations (비차단)

- 없음. (참고로 게이트웨이의 thought 걷기 미종결 케이스와 이 슬라이스의 열린 펜스
  회복은 같은 "상한 끊김" 원인의 양쪽 절반이는데, 각자의 셀이 요지를 잠그고 있다 —
  폴백 슬라이스 검증 기록의 M5와 본 기록의 X1/X2.)

## Verdict

**합격**

근거: 정량 클레임 전부 재현(핀 sha 재계산 일치·전수 2489/4/2718·신규 7셀), 처방 셋의
경계 행렬에 빈 칸 없음(회복 under/over 양방향·기본값 리터럴·immutable 핀 각각 잠금),
bb1ac41 단독 red 경위 재현·6567286 폐쇄 확인. 단 라이브 관통 주장(알파 phase2a 3회
연속 성공 후보 6·5·6·배포 1회 후보 4)은 구현자 기록 수용이지 본 검증의 실측이 아니다.

## Outstanding items

- 없음. (폴백 슬라이스 검증 기록의 B1(쿨다운 조항 모순)은 이 슬라이스가 아니라
  `d8ba6e7…7bf07c9` 쪽 조항이다.)

## Reproduction

```bash
git status --short                                  # 빈 것 확인
python3 -m pytest -q tests/test_json_extract.py tests/test_prompt_templates.py \
  tests/test_analysis_extractor_schema.py tests/test_analysis_prompt_builder.py \
  tests/test_llm_call_scope.py                      # 66 passed / 23 subtests
# sha 재계산: 위 Methodology 의 python3 -c 한 줄
docker compose -f docker-compose.test.yml up -d && \
  until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done
python3 -m pytest -q                                # 2489 / 4 / 2718
docker compose -f docker-compose.test.yml down
# 뮤테이션 X1~X5: Findings 3 표의 diff 를 그대로 Edit → 표적 파일 pytest →
#   git checkout -- <path> → git status --short 빈 확인 (X4·X5 판독은 SUBFAILED 포함)
```
