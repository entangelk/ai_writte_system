# 검증 기록 — `main.py` 미사용 import 21개 정리 (라우터 분해 Slice 1 뒷정리)

- **날짜**: 2026-08-08
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래")
- **검증자**: Claude Code (독립 검증 — 피검증 슬라이스 비생산, 별개 세션)
- **검증 대상**: 커밋 `3ff4274`(코드) · `7d4bc8d`(기록). 작업 로그
  [`docs/daily_logs/2026-08-08/work_log.md`](../../daily_logs/2026-08-08/work_log.md) Task 1.
- **정본 사양**: 이 슬라이스의 계약은 **"행위 무변"**이다(순수 import 제거). 정본은
  [`docs/verifications/2026-08-05/repro_router_split.py`](../2026-08-05/repro_router_split.py) 가
  정의하는 공개 표면 지문으로 잰다.
- **소스**: `main` 브랜치 HEAD(`7d4bc8d`), 작업 트리 clean.

## Scope

1. **정적 — 제거가 정말 "미사용"이었는가** ★가장 의심축. pyflakes F401 21→0 를 1차 소스에서
   재현하고, pyflakes와 **무관한** 독립 grep 으로 21 심볼이 현재 `main.py`에 잔류하지 않는지 확인.
2. **구조적 — 타 모듈이 `main` 경유로 21 심볼을 참조하는가** ★. `from …main import` ·
   `main.<sym>` · `app.main.<sym>` 전수. (제거 대상을 다른 파일이 import 하면 `ImportError` 회귀.)
3. **행위 무변 — 공개 표면 지문**. `d65a1c9`(정리 전) vs `7d4bc8d`(정리 후) worktree 에서
   `repro_router_split.py` 를 각각 돌려 diff.
4. **뮤테이션 — 가드가 진짜 무는가**. 작업자의 핵심 증거 M4(`LlmCallSite` 제거 → 8 셀) 와
   핵심 부채 M1(`timedelta` 제거 → 안 문다) 를 독립 재현. 추가로 **AUTH_SESSION_TTL_HOURS
   계약이 살아있는지** 적극 증명.
5. **전수 회귀 — 헤드라인 숫자 재현**. test-mongo ON 으로 `2197/4/2168` 재측정.
6. **기록 정확성** — work_log·HANDOFF 의 인용(해시·줄수·기준선) 이 재현 가능한지.

## Methodology

```bash
# 정적 (scratchpad venv — 호스트에 pyflakes 없고 PEP 668 로 거부됨)
python3 -m venv /tmp/vf_venv && /tmp/vf_venv/bin/pip install -q pyflakes
/tmp/vf_venv/bin/python -m pyflakes services/application/app/main.py            # new = 0
git show d65a1c9:services/application/app/main.py > /tmp/old_main.py
/tmp/vf_venv/bin/python -m pyflakes /tmp/old_main.py                            # old = 21

# 독립 잔류 grep (import 는 이미 제거됨 → 잔류 = 사용 = 버그)
grep -nE "\b(datetime|Annotated|Union|Header|BaseModel|ConfigDict|Field|…|BlockKind)\b" services/application/app/main.py

# 구조적 — main 경유 참조 스윕
grep -rnE "main\.(<21심볼>)\b|app\.main\.(<21심볼>)\b" tests scripts services --include=*.py
grep -rnA5 "from services\.application\.app\.main import" tests scripts services --include=*.py

# 행위 무변 — 지문 diff
git worktree add /tmp/repro_pre d65a1c9
(cd /tmp/repro_pre && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/repro_pre.json)
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/repro_post.json
diff /tmp/repro_pre.json /tmp/repro_post.json   # → 동일

# 뮤테이션 (clean tree → mutate → pytest → git checkout -- → status empty)
#   M4: main.py 에서 "    LlmCallSite," 제거 → pytest tests/test_llm_call_sites.py tests/test_llm_call_scope.py
#   M1: main.py 에서 "from datetime import timedelta" 제거 → pytest tests/test_app_import_paths.py tests/test_writing.py

# 계약 라이브 증명
python3 -c "import os; os.environ.pop('CORE_SOT_MONGO_URI',None); os.environ['AUTH_SESSION_TTL_HOURS']='-1'; \
  from services.application.app.main import _default_session_service; _default_session_service()"

# 전수 회귀
docker compose -f docker-compose.test.yml up -d   # test-mongo healthy 대기
python3 -m pytest tests/ -q                        # → 2197 passed, 4 skipped
docker compose -f docker-compose.test.yml down
```

## Findings

### (1) 정적 — 21→0, 1차 소스에서 재현
- **NEW `main.py`(`7d4bc8d`)**: pyflakes **0 건**(F401 0 · F821 0). 작업자 주장과 일치.
- **OLD `main.py`(`d65a1c9`)**: pyflakes **정확히 21 건**. 21 심볼이 작업자 표와 한 치 없이 일치
  (`datetime`·`Annotated`·`Union`·`Header`·`BaseModel`·`ConfigDict`·`Field`·`StringConstraints`·
  `field_validator`·`SESSION_COOKIE_NAME`·`cookie_kwargs`·`AdminAuditEvent`·`aggregate_global_kpi`·
  `BILLABLE_ACTION_BY_OPERATION`·`UnclassifiedBillableAction`·`resolve_dedupe_key`·`AdmissionUnavailable`·
  `QuotaRefusalReason`·`QuotaRefused`·`ErrorDetailResponse`·`BlockKind`).
- **독립 잔류 grep**: 21 심볼 중 **20개 잔류 0건**. 유일 히트 `from datetime import timedelta`(`:7`)의
  `datetime` 은 **모듈명**이지 제거된 클래스가 아니다. 즉 제거된 심볼이 본문에 남은 자리는 없다.
- **diff 순수성**: `3 insertions / 23 deletions` = 수정 3줄(`datetime`·`typing`·`fastapi` 부분제거) +
  순수삭제 20줄. 변경 파일 `main.py` 하나. 모든 변경줄이 import 문에 추적됨(§3).

### (2) 구조적 — main 경유 참조 0건 (위험 제거)
- `main.<sym>` · `app.main.<sym>`: **0건**.
- `from services.application.app.main import` 전수: create_app 등을 가져오되 **21 심볼 중 하나도 안 가져온다**.
  - ★ 검증 중 1회 오탐: `tests/test_observability_kpi.py:44` 의 `aggregate_global_kpi` 가 다중줄 import
    문맥에 걸려 "main 경유"로 보였으나, 실제로는 `:40` 의 `from …observability.kpi import` 하위
    (출처 모듈 직수)였다 — `:39` 의 main import 는 create_app 만 가져온다. 파일을 읽어 해소.
  - 작업자의 "main 경유 0건" 주장은 **정확**했다(단일줄 grep 패턴이 다중줄 import 를 놓칠 뻔한 자리이나,
    이번 21개에는 해당 자리가 없었다).

### (3) 행위 무변 — 지문 바이트 동일
- `d65a1c9`(정리 전) ≡ `7d4bc8d`(정리 후): repro JSON **`diff` 출력 없음(바이트 동일)**.
  양쪽 route **76** · order-sensitive pairs **0** · `openapi_sha256`
  **`f8b42ef191d95a2341debb0c879805b31ebc5c351dac1ca3c4ee51b2f809cfa1`**(2026-08-05 기준값과 동일).

### (4) 뮤테이션 — 핵심 증거·부채 둘 다 재현
- **M4(`LlmCallSite` 제거, 보존 심볼)**: **8 failed, 43 passed**. 실패 8셀이 작업자 보고와 한 치
  오차 없이 일치(`test_report_assembly_is_wrapped`·`test_revision_assembly_is_wrapped`·
  `test_writing_retrieval_planner_assembly_is_wrapped`·`test_extractor_assembly_instruments…`·
  `test_gate_assembly_instruments…` 등). NameError 가 `main.py:671/705/778` 조립부에서 발생 —
  모듈 로드가 아니라 **조립 가드**가 잡는 자리. 작업자의 핵심 증거 재현 완료.
- **M1(`timedelta` 제거, 보존 심볼)**: **71 passed, 29 subtests passed**(작업자 "71 passed" 와 일치).
  timedelta 제거가 **아무 셀도 안 문다** — 부채 주장 재현.
- **★ 계약 라이브 증명(M1 부채의 본질)**: `_default_session_service()` 에 `AUTH_SESSION_TTL_HOURS`
  = `-1`/`0`/`abc` 주입 → **전부 `ValueError`**(계약 LIVE). `=2`/unset → 정상 빌드.
  `grep AUTH_SESSION_TTL_HOURS tests/` = **0건**. 즉 **계약은 살아있으나 회귀 커버리지 0건**.
  보안 근거(2026-07-27 work_log:221 "조용한 fallback 은 무한 세션을 만들 수 있고") 실재·인용 정확.
- M2(`Protocol`)·M3(`AdminAuditService`)는 재현하지 않았다 — pyflakes NEW=0 이 **보존 import 전부
  사용 중**임을 이미 증명하므로, 제거하면 사용처에서 필연적으로 NameError 가 나는 것은 자명하다.

### (5) 전수 회귀 — 헤드라인 숫자 정확 재현
- test-mongo ON, HEAD `7d4bc8d`: **`2197 passed, 4 skipped, 2168 subtests passed` in 172.44s**.
  **FAILED/ERROR = 0**. 작업자 주장(`2197/4/2168`, 193.92s)과 **카운트 한 자리 일치**
  (172s 는 같은 알파 머신 run-to-run 편차).
- **4 skip 의 사유가 환경으로 설명됨**을 독립 확인: 이 호스트 `elasticsearch` 패키지 미설치
  (`python3 -c "import elasticsearch"` → Traceback) → 어휘검색 셀 3건 skip + live Chroma 1건.
  ES 보정하면 `2197+3 / 4−3 = 2200/1` = 기준선. **셀 증감 0**.

### (6) 기록 정확성 — 한 건의 재현 불가능한 인용 발견
- work_log 검증표·HANDOFF:185 가 지문 식별자로 인용한 **`47d78b68…`** 해시가 **재현되지 않는다**.
  시도 8종(전체 sha256=`c3dfb391…` · 개행제거=`22d84fb6…` · git hash-object · routes 필드 ·
  count+pairs · compact · openapi 키 제거 · md5) **전부 불일치**. 저장소 전체에서도 작업자가
  오늘 새로 쓴 3곳에만 등장(기존 관례 아님). 직전 1~4차 검증 기록은 지문을
  **`openapi_sha256=f8b42ef1…` + "diff empty"** 로 인용한다 — `47d78b68` 는 이 관행에서 벗어난
  **orphan 해시**다. (단, 무변 *주장 자체*는 (3) 의 `c3dfb391==c3dfb391` 로 solid 하다 —
  인용 토큰만 틀렸다.)
- 그 외 인용은 정확: HANDOFF 298줄(실측 일치) · 기준선(알파 원시 2197/4 → ES 보정 2200/1,
  베타 843s vs 알파 194s 정정) · 베타 관측 2건 중복 해소 · 기존 F401 3파일/5건 일치 ·
  조립 잔류 심볼(`_default_model_capabilities` def:754/호출:1439·1642 등) 일치.

## Issues / Risks

### Blocking (계약 의무)
- **없다.** 이 슬라이스의 계약("미사용 import 제거, 행위 무변")은 정적·구조적·행위적 3축에서
  모두 충족됐고, 전수 회귀가 0 실패로 재현됐으며 공개 표면이 정리 전과 바이트 동일이다.

### Hardening (비차단)
- **[기록 정확성, 교정 권장] `47d78b68…` orphan 해시**. 코드 검증엔 무영향이나, 감사 추적이
  요구하는 "재현 가능한 인용"에 위배된다 — 다음 검증자가 repro 를 돌려 `c3dfb391` 을 보고
  기록의 `47d78b68` 와 대조 불가능해진다. **권고**: work_log:176·HANDOFF:185 의 `47d78b68…` 를
  관례대로 `openapi_sha256=f8b42ef1… · diff empty(pre≡post)` 로 바꾼다. (어느 토큰을 쓸지는 오너 판단.)
- **[추적 부채, 이 슬라이스 범위 외] `AUTH_SESSION_TTL_HOURS` 계약 회귀 0건**. 작업자가 M1 로
  발견해 부채로 올린 것을 검증자가 **적극 증명**(계약 LIVE · 커버리지 0) 했다. 인증/세션 담당
  슬라이스에서 닫는 것이 자연스럽다(비용 셀 2개). 이 import-정리 슬라이스의 계약 위반이 아니다.
- **[설계상 무가드] 미사용 import 정리에는 회귀 가드가 없다(M5)**. 되돌려 넣어도 139셀 green,
  신호는 스위트 밖 pyflakes 뿐. 작업자가 선택지 3종 + ⓐ 추천으로 남긴 처리가 합리적이다.

## Verdict

**합격** — `main.py` 미사용 import 21개 제거(`3ff4274`)가 정적(pyflakes 21→0 1차 재현 + 독립
잔류 grep 0)·구조적(main 경유 참조 0)·행위적(지문 pre≡post 바이트 동일 · M4 8셀 재현 · 전수
`2197/4/2168` 0실패 재현) 3축에서 모두 입증됐고, blocking 결함이 없다. 단, 기록에 재현 불가능한
orphan 해시(`47d78b68…`) 가 인용된 것은 비차단 교정 권장 항목이다(무변 주장 자체는 solid).

## Outstanding items

- **오너 판단**: `47d78b68…` orphan 해시를 재현 가능한 토큰(`openapi_sha256=f8b42ef1…` 권장)으로
  교정할 것인지. 교정 시 work_log:176·HANDOFF:185.
- **추적 부채 그대로 유지**: AUTH_SESSION_TTL_HOURS 계약 회귀(인증 슬라이스에서) · 미사용 import 가드.
- **컨테이너 상태**: 검증 중 test-mongo 를 올렸다 내려 착수 상태(3개)로 복원했고, 작업 트리 clean.
- 이 슬라이스는 합격이므로, HANDOFF 의 "독립 검증 대기" 표기를 "합격(본 기록)"으로 올려도 된다
  (orphan 해시 교정과 함께 하는 것이 자연스럽다).

## Reproduction

```bash
git checkout 7d4bc8d                         # 코드+기록 커밋
python3 -m venv /tmp/vf_venv && /tmp/vf_venv/bin/pip install -q pyflakes
/tmp/vf_venv/bin/python -m pyflakes services/application/app/main.py      # 0
git show d65a1c9:services/application/app/main.py | /tmp/vf_venv/bin/python -m pyflakes   # 21
git worktree add /tmp/pre d65a1c9
(cd /tmp/pre && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/pre.json)
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/post.json
diff /tmp/pre.json /tmp/post.json && echo IDENTICAL                         # 동일
docker compose -f docker-compose.test.yml up -d && sleep 20                # test-mongo healthy
python3 -m pytest tests/ -q                                                 # 2197 passed, 4 skipped
docker compose -f docker-compose.test.yml down
# 뮤테이션: clean tree 확인 → main.py 편집 → pytest → git checkout -- main.py → status empty
```
