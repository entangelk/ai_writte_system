# identity group Slice 3(Review Inbox 읽기면)— 독립 검증

**조건부 합격** — **가시 roster 밖 pair의 근거 차단 무셀**(B1). 계획 §Slice 3 완료 기록·SoT v1.8.25 리터럴 ③이 "`identity_rationale_summary`는 이 후보와 **가시 roster**를 잇는 `same` relation 중 최신"을 확정 리터럴로 주장하나, 13셀 어디도 "same relation의 상대가 검토함을 떠난(stale) 뒤에도 그룹이 살아 있는(가시 ≥2) 경우 → 근거는 `null`" 분기를 잠그지 않는다. 검증자 변이 VM1(`review_inbox.py`의 relation 양끝 roster_set 필터 제거)이 **13 passed**로 입증했다. 행동 자체는 계약대로다(검증자 probe 실측 — rationale `null`). 셀 1개 추가로 폐쇄 가능하다(Slice 1 B1~B3·Slice 2 B1과 같은 "빈 것은 잠금" 모양). 그 외 구현 주장 전부(전수 산술·OpenAPI 경계 바이트·셀 13·변이 표의 재유도 5종·RED 선행·기록 문서)는 재현됐다.

## Subject metadata

- 검증일: 2026-09-04
- 요청자: 오너 — "작업 ai가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? identity group Slice 3 (Review Inbox 읽기면) 완료 — 커밋 3개, 트리 clean."
- 검증자: 이 세션(구현 세션 1과 다른 세션). 구현자 보고(work_log 세션 1·SoT v1.8.25 행·커밋 메시지·HANDOFF)는 전부 **가설**로 취급해 원본에서 재유도했다.
- 대상: 커밋 3개 — `90cc4dd`(구현+셀 13종)·`e9680e4`(기록: SoT v1.8.25·계획 완료 기록·work_log 세션 1·HANDOFF·CHANGELOG)·`2223ba3`(README ④ 가드). HEAD `2223ba3`, 트리 clean. 코드 기준선은 `4ace6c4`(`90cc4dd^` — 구현과 문서가 같은 계열 3커밋이므로 경계는 유일).
- 정규 계약: `docs/plans/pending-candidate-identity-grouping-implementation-phases.md` §Slice 3(계약·검증 문장 + 완료 기록 리터럴 ①~③) · `docs/system-contract-sot.md` **v1.8.25**(변경이력 행 + §Phase 2A "identity group 메타데이터가 Review Inbox 읽기면에 실렸다" 조항 — 리터럴 ①~④) · 결정 정본 `pending-candidate-identity-grouping-decisions.md` C(방향 참조만 — 읽기면 리터럴에 직접 개입 없음).

## Scope

1. 경계 행렬 — 계획 §Slice 3 계약/검증 문장 + 완료 기록 리터럴 + SoT v1.8.25 리터럴 ①~④를 should/should-NOT/리터럴로 전개해 셀 대응표를 만든다.
2. 구현 코드 감사 — `analysis/review_inbox.py`(소속 정본·roster 교집합·<2 가드·근거 선택·절단)·`routers/analysis.py`(공통 빌더·additive 키·detail 경계)·`main.py`(조립·기본 서비스)·`identity_judging._group_of` semantics 일치 주장·검토함 population 정의(`list_needs_review_candidates`)·edit 이탈 경로(계약의 세 이탈 원인 열거가 사실인지).
3. 테스트 코드 감사 — 신규 13셀 각각의 단정이 계약 조항을 잠그는지(under/over 방향).
4. 뮤테이션 — 구현자 표 9종 중 핵심 5종(M1·M2·M5·M7·M8) 재유도(정확 diff로) + 검증자 신설 1종(VM1 — 구현자 표에 없는 축).
5. RED 선행 재현 — 구현 3파일을 부모로 되돌려 13 failed(KeyError) 확인.
6. 전수 회귀 재실행 + OpenAPI 덤프 **코드 경계**(`4ace6c4` ↔ HEAD `2223ba3`) 대조 + `schema.d.ts` 무변 확인 + 문서 가드.
7. 기록 감사 — SoT v1.8.25 행(실측 지문·전수 산술·변이 표 요약)·README ④·HANDOFF 착수점 갱신·CHANGELOG·work_log 세션 1(변이 표·전수 1차 기각 사유의 정당성).

## Methodology

환경(측정의 일부): WSL2(Linux 6.18.33.2-microsoft-standard-WSL2), Python 3.12.3 / pytest 9.0.2, `.env` 없음(compose 기본값), test-mongo(`ai_writte_system-test-mongo-1`, 127.0.0.1:27020, rs-test)은 검증 개시 시점에 **이미 healthy**(Up 2 hours)였다 — 구현자의 "전수 1차 2743/12 기각(test-mongo 기동 경합)" 사유와 일관되게, 이 검증의 전수는 healthy 상태에서 개시했다. 이 머신 관례 skip 1.

- 트리 게이트: `git status --short` empty(개시 시·변이마다 복원 후 재확인). 검증 대상이 커밋됐고 트리가 clean하므로 clean-tree 분기(`git checkout -- <path>` 복원)를 썼다.
- 집중: `python3 -m pytest -q tests/test_review_inbox_identity_groups.py`.
- RED 재현: `git checkout 90cc4dd^ -- services/application/app/analysis/review_inbox.py services/application/app/main.py services/application/app/routers/analysis.py`(테스트 파일은 HEAD 유지) → 집중 실행 → `git checkout HEAD -- <같은 3파일>`.
- 뮤테이션(본 트리 4종: RED·VM1·VM2·VM3): 전수 백그라운드 개시 **전에** 완료 — 변이 창과 전수 창이 본 트리에서 겹치지 않았다. 잔여 3종(M2·M5·M8)은 전수 진행 중 `git worktree add --detach /tmp/slice3_mut HEAD`에서 실행(본 트리 무손상). 적용 diff는 아래 표에 축약 없이 기재. 판독은 요약줄+FAILED 행 함께.
- probe 1종(비커밋 축 검증): [`repro_rationale_out_of_roster.py`](repro_rationale_out_of_roster.py) — 기록 옆에 커밋(선례 `repro_judge_not_configured_isolation.py`).
- OpenAPI: `python3 scripts/dump_openapi.py | md5sum`·`| wc -c`를 본 트리(HEAD `2223ba3`)와 `git worktree add --detach /tmp/pre_slice3_4ace6c4 4ace6c4`에서 각각 실행. `schema.d.ts`는 `git diff --stat 4ace6c4 HEAD -- '**/schema.d.ts'`가 비어있는 것으로 무변 확인(생성물이 커밋돼 있으므로).
- 전수: test-mongo healthy 확인 뒤 `python3 -m pytest -q 2>&1 | tail -15`(백그라운드).

## Findings

### 1. 경계 행렬 — 계약 ↔ 셀 대응

계획 §Slice 3(행 153~187)과 SoT v1.8.25 §Phase 2A 조항에서 유도한 분기와 13셀의 대응. 필드 리터럴(5키 열거·ungrouped null)은 셀 1·13이 전체 dict 동등성으로, 소속 정본(open non-closed·member 행·relation.group_id 불사용)은 셀 4·5·12가, roster 교집합·<2 가드는 셀 6·7이, 근거 선택(최신·same 한정·200자·null)은 셀 10·11·13이, 혼합 목록·개별 소비자 면 유지는 셀 3이, project 격리는 셀 8이, detail 동일 payload는 셀 9가 잠근다. **행렬의 빈칸 1곳 = 아래 B1.** 나머지는 전부 대응 셀이 있다.

### 2. 구현 코드 감사 — 계약 리터럴과의 일치

- 필드명 5종은 계획의 열거와 문자 그대로 일치(`routers/analysis.py:789-800` `_identity_group_payload` — `group_id`·`group_size`·`group_status`·`group_member_ids`·`identity_rationale_summary`). `group_size`는 **가시 roster 크기**(len(member_ids))로, 계획의 "stale member는 group_member_ids/group_size에 싣지 않는다"와 일치.
- 소속 정본: `review_inbox.py` `_identity_summaries` — `group.status is not IdentityGroupStatus.CLOSED` 필터(open·contradicted 포함) + member 행. 판정면 `identity_judging.py:267-282 _group_of`(CLOSED만 제외·member 행 기준)와 같은 semantics임을 확인했다(구현 주장 재유도).
- relation.group_id 불사용: 소속은 list_groups/list_members에서, 근거 선택은 `verdict`/양끝 pair 멤버십/`created_at`에서만 결정 — `relation.group_id`를 읽는 경로가 없다(코드 전수 확인).
- roster 교집합·<2 가드·절단 리터럴(`IDENTITY_RATIONALE_SUMMARY_MAX_CHARS = 200`, `review_inbox.py:20-25` — 활동 로그 "짧은 값"·장면 메모 미리보기와 같은 값이라는 주석의 정당성은 SoT v1.8.25 행이 열거) 전부 코드와 일치.
- **public service 전용**(Slice 0 인계 조항): `review_inbox.py`의 import는 `analysis/identity_groups`뿐 — `identity_groups_mongo`/컬렉션 직접 접근 없음. 조립(`main.py:1814-1839`)은 기본 경로에서 `_default_candidate_identity_group_service()`를 쓰고 주입 경로(테스트)를 함께 허용.
- detail 경계·기존 필드 무변: additive 키는 공통 빌더 `_review_inbox_payload`에만 추가(`routers/analysis.py:819-821`), `include_detail` 블록 무변. list(`analysis.py:853-864`)·detail(`analysis.py:873-886`) 모두 같은 빌더를 지난다.
- 검토함 population: `analysis/service.py:545-551 list_needs_review_candidates` — needs_review 상태 전수(승격 시 이탈). roster 교집합의 population이 응답과 동일 소스(`list_items`가 받은 같은 `candidates` 튜플)라 구조적으로 일치.
- 계약의 stale 이탈 원인 열거(confirm/reject/edit): edit 경로는 `routers/analysis.py:383` "edit → new confirmed candidate version + promotion"으로 confirmed 전이 — 세 원인 모두 needs_review 이탈로 수렴하고, 교집합은 이탈 원인 불문 동일 분기다(셀 6·7가 confirm·reject로 잠금; edit는 H2).

### 3. 테스트 코드 감사

13셀 전부 읽었다. 단정은 전부 공개 면(HTTP payload의 `identity_group` 키)을 겨냥하고, 셀 1·6·13은 전체 dict 동등성으로 키 누락·과잉 양방향을 잡는다. 셀 3은 기존 개별 소비자 면(필드·affordance 3종)을 그대로 대조 — 계획 §검증의 "기존 후보 액션 affordance 유지" 문장의 직접 시행. 셀 10은 같은 그룹 안 후보별로 서로 다른 최신 same을 주장(b="older pair" 유지) — different relation이 근거를 덮지 않는 것까지 잠근다.

### 4. 뮤테이션

구현자 표 9종 중 5종을 정확한 diff로 재유도 — 전부 표의 기록(재실패 셀 수·이름)과 일치:

| 변이 | 적용 diff(`review_inbox.py`) | 실측 | 구현자 표 |
|---|---|---|---|
| M1 | `if group.status is not IdentityGroupStatus.CLOSED\n` 행 제거 | 1 failed(closed 셀) | 1 failed ✓ |
| M2 | roster 컴프리헨션에서 `if member.candidate_id in visible` 행 제거 | 2 failed(stale 셀·가시<2 셀) | 2 failed ✓ |
| M5 | `rationale.rationale[:IDENTITY_RATIONALE_SUMMARY_MAX_CHARS]` → `rationale.rationale` | 1 failed(절단 셀) | 1 failed ✓ |
| M7 | roster_set 양끝 필터 블록 → `if relation.group_id != group.group_id:\n    continue` | 4 failed(메타데이터·group_id 셀·절단·최신) | 4 failed ✓ |
| M8 | `is not IdentityGroupStatus.CLOSED` → `is IdentityGroupStatus.OPEN` | 1 failed(contradicted 셀) | 1 failed ✓ |

**검증자 신설 VM1(구현자 표에 없는 축)** — 근거 선택의 relation 양끝 가시 roster 필터 제거:

```diff
-                if (relation.left_candidate_id not in roster_set
-                        or relation.right_candidate_id not in roster_set):
-                    continue
```

실측: **13 passed(물지 않음)** → B1. 이 필터가 관측 가능한 입력 모양(그룹 가시 ≥2 유지 + same relation의 상대만 이탈)이 13셀 어디에도 없다 — 셀 6은 relation 자체가 없고 셀 7은 <2로 그 전에 묶인다.

RED 재현: 구현 3파일을 `90cc4dd^`로 되돌리면 **13 failed**(`KeyError: 'identity_group'` 계열) — 구현자의 "테스트 먼저 RED 확인" 주장과 일치.

### 5. 공개 envelope(OpenAPI·schema.d.ts)

`4ace6c4`↔HEAD `2223ba3` 덤프 **바이트 동일** — md5 `10978d55571a90ccd52f65220fc354d3`·**384,414B** 양쪽(Slice 2 검증이 확정한 지문과 동일 — 덤프 방법 동일성 교차). review-inbox 응답이 `dict[str, object]`로 선언돼 additive payload가 선언 schema에 나타나지 않는다는 구현자 설명과 일치한다. `schema.d.ts`는 `git diff 4ace6c4 HEAD`가 비어 무변. 프론트 재생성 불요 판정은 타당.

### 6. 전수 회귀

test-mongo healthy 상태 개시. 실측: **2752 passed / 9 failed / 1 skipped, 3128 subtests passed(+7 SUBFAILED), 1858.78초**. 실패 9건은 전부 `tests/test_docs_indexes.py`(부모 2 + subTest 7)이며 원인은 이 검증의 진행 방식 자체다 — 검증 기록을 인덱스에 등재하기 **전에** 디스크에 둔 채 전수를 돌려, 카운트·분포·등재 가드가 279번째 기록을 본 것(전수 개시 시점엔 기록이 없었고 문서 가드가 도달한 시점에 있었다). 동일 디스크 상태에서 문서 가드 단독 재실행이 **같은 9개를 그대로 재현**했다(부모: `test_every_verification_record_is_reachable_from_the_index`·`test_the_verdict_distribution_adds_up_to_the_total` / subTest: record-row-verdict 1·건수 주장 4·일수 주장 2). 코드 축 산술이 자릿수까지 맞는다 — passed 2752 = 구현자 기대 2754 − 문서 가드 부모 2, subtest 3128+7 = 3134 + 이 기록 1건의 가드 subTest. 따라서 **코드·테스트 축 회귀는 0**이고 구현자의 전수 2754/1/3134는 성립한다. skip 1은 이 머신 관례(ES 패키지). 인덱스·분포 갱신 뒤 문서 가드는 green(아래 Reproduction). Slice 2 검증은 기록을 인덱스에 넣은 뒤 전수를 돌려 이 충돌을 피했다 — 이 검증은 전수를 먼저 시작했으므로 가드 반응이 관측됐고, 위처럼 전량 귀속시켰다.

### 7. 기록 감사

- SoT v1.8.25 행: 리터럴 ①~③·OpenAPI 지문·전수 산술(2741+13=2754 ✓)·변이 표 요약이 구현·실측과 일치. §Phase 2A 조항도 동일.
- README ④ 셀 v1.8.25(`2223ba3`) — 문서 가드(`tests/test_docs_indexes.py:309-319`)가 SoT 헤더와 대조한다. 검증 세션의 문서 갱신(판정 분포)도 같은 가드가 잡는다.
- HANDOFF 착수점: "Slice 3 완료(…전수 2754/1/3134; 1차 기각 사유 포함) + 다음 작업 = Slice 3 독립 검증 후 Slice 4(활동 로그 브리프 명시)" 갱신 확인 — 구현자 보고와 일치.
- work_log 세션 1: 변이 9종 표(위 5종 재유도와 전부 일치)·전수 1차(2743/12) 기각·재실측(2754/1) 사유(test-mongo 기동 경합 — 이 검증은 healthy 개시로 재현 불가능했고, 2차 수치가 재현됐다)·"비정상 이중 소속 시 오래된 그룹 first" 방어를 셀 없이 둔 이유(불변식 위반 상태에 대한 over-speculation 회피) 기록 확인.

## Issues / Risks

### Blocking

- **B1 — 가시 roster 밖 pair의 근거 차단 무셀.** 계획 §Slice 3 완료 기록·SoT v1.8.25 리터럴 ③("이 후보와 가시 roster를 잇는 same relation")의 should-NOT 분기(상대가 이탈한 same relation은 근거가 될 수 없다)에 대응 셀이 없다. VM1 실증(13 passed). 행동은 계약대로(probe `repro_rationale_out_of_roster.py` — trio 그룹에서 b 거절 후 a의 rationale `null`). 폐쇄: probe 본체를 기명 셀로 추가(예: `test_rationale_ignores_relations_to_members_outside_the_roster`) + VM1 재실측으로 물림 확인. **추가 셀은 Slice 4 착수 전에**(같은 "빈 것은 잠금" 선례: Slice 1 B1~B3, Slice 2 B1).

### Hardening recommendations (non-blocking)

- **H1 — created_at 동률 tie-break(pair id 순) 무셀·방향 미기재.** 완료 기록·SoT가 "동률 pair id 순"을 리터럴로 열거하나 (a) 동률 시나리오 셀이 없고 (b) "순"의 방향(오름/내림 — 코드는 큰 pair id 승리, `review_inbox.py` `order >` 비교)을 문서가 명시하지 않는다. Slice 0의 클록 해상도 BSON ms 때문에 동률은 실운영에서 가능하다. 동률 셀+방향 한 단어로 폐쇄 가능.
- **H2 — stale 이탈 세 번째 원인(edit) 무셀.** 계획·SoT가 이탈 원인을 confirm/reject/edit으로 열거하고 셀은 confirm(셀 6)·reject(셀 7)뿐. edit도 confirmed 전이로 같은 분기에 수렴하므로 잠금은 유효하나, 열거의 세 번째 원인을 찍는 셀이면 문서-셀 대응이 완전해진다.
- **H3 — relation `candidate_type` 필터 무셀.** `_identity_summaries`의 `relation.candidate_type is not group.candidate_type` 제외는 같은 project에서 다른 type의 relation이 roster 후보 id를 참조하는 행(서비스 오용으로만 생성 가능 — 판정 경로는 같은 type pool만 짝짓는다)에 대한 방어다. 계약이 이 방어를 요구하지 않으므로(spec-silent-but-code-enforced) 셀을 추가하거나 계획에 한 줄로 근거를 남기는 쪽을 권한다.
- **H4 — 이중 non-closed 소속 시 "오래된 그룹 first" 규칙의 계약 미기재.** work_log는 의도를 기록했으나 계획·SoT의 리터럴 열거에는 없다. Slice 4·5가 그룹 상태를 다루기 시작하면 이 규칙이 노출된다 — 완료 기록에 한 줄 추가하거나 방어를 제거하는 결정이 있으면 좋다.

## Outstanding items

- B1 폐쇄(셀 1개 + VM1 재실측) 전에 Slice 4 착수하지 않는다(위 Blocking).
- 이 검증 세션은 test-mongo를 띄운 채 뒀다(`ai_writte_system-test-mongo-1`, healthy). 정리: `docker compose -f docker-compose.test.yml down`.
- README 절차 표 ② 셀의 회귀 수수(2,702 passed/3,132 subtests)는 Slice 1~3을 지나 낡았다(현 전수와 52 차이). 문서 가드가 ④ 버전·판정 분포만 검사하도록 설계돼 있어 잡히지 않는다 — Slice 3의 문제는 아니고(② 갱신 관례는 2026-09-03 `7ab3df6`이 마지막), 다음 문서 마감 때 함께 맞추면 된다.
- 푸시는 오너 몫(커밋 3개 + 이 검증 기록).

## Reproduction

```bash
# 환경: test-mongo healthy(이 검증은 이미 떠 있는 컨테이너에서 개시)
docker compose -f docker-compose.test.yml up -d
docker inspect --format '{{.State.Health.Status}}' ai_writte_system-test-mongo-1   # healthy

# 집중 13셀
python3 -m pytest -q tests/test_review_inbox_identity_groups.py        # 13 passed

# RED 재현(구현 되돌리기 — 트리 clean 필수)
git checkout 90cc4dd^ -- services/application/app/analysis/review_inbox.py \
  services/application/app/main.py services/application/app/routers/analysis.py
python3 -m pytest -q tests/test_review_inbox_identity_groups.py        # 13 failed
git checkout HEAD -- services/application/app/analysis/review_inbox.py \
  services/application/app/main.py services/application/app/routers/analysis.py

# B1 probe(행동) + VM1(잠금 없음 — 13 passed로 입증)
python3 docs/verifications/2026-09-04/repro_rationale_out_of_roster.py # PROBE-OK
python3 - <<'EOF'   # VM1: 이 스크립트 적용 후 pytest → 13 passed(안 물면 B1)
import pathlib
p = pathlib.Path("services/application/app/analysis/review_inbox.py")
s = p.read_text()
old = """                if (relation.left_candidate_id not in roster_set
                        or relation.right_candidate_id not in roster_set):
                    continue
"""
assert s.count(old) == 1
p.write_text(s.replace(old, ""))
EOF
python3 -m pytest -q tests/test_review_inbox_identity_groups.py        # 13 passed = B1
git checkout -- services/application/app/analysis/review_inbox.py

# OpenAPI 경계 대조
git worktree add --detach /tmp/pre 4ace6c4 && (cd /tmp/pre && python3 scripts/dump_openapi.py | md5sum)
python3 scripts/dump_openapi.py | md5sum   # 둘 다 10978d55571a90ccd52f65220fc354d3

# 전수(측정·실패 9건의 전량 귀속은 §Findings 6; 재실행 시 문서 가드 충돌을 피하려면
# 아래 문서 갱신 뒤에 돌린다)
python3 -m pytest -q
```
