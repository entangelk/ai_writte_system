# 재감사 조건 AC1 승격 재검 — 폐쇄(`88a16fe`·`a1d71fc`)를 변이 재적용으로 확증

**합격** — 조건을 닫은 세션(`88a16fe` 폐쇄 보고)이 자기 판정을 올리면 독립성이 사라지므로 남아 있던 마지막 검증 축(승격 재검)을 독립 세션이 닫았다. **AC1 폐쇄를 세 층으로 확인했다**: ① diff 1차 소스 — 선행 기록 머리 요약 줄과 §Verdict 줄 **둘 다** 승격됐고 발행 시점 판정 원문은 두 자리 모두 인용(`>`)으로 보존돼 있다(선례 `2e025dc` 모양 그대로). ② 전수 대조 — 인덱스 311행의 판정 열 ↔ 각 기록의 선두 판정 토큰을 기계 대조해 **병 0건**(선두 토큰이 없는 옛 영어 병기 220건은 이 대조의 범위 밖 — 폐쇄 보고가 "형식을 먼저 정해야 한다"고 적은 그 집합이다). ③ 폐쇄 보고의 패턴 스윕이 부채로 등재한 **선재 5건은 `a1d71fc`가 정합**했다(그 커밋은 검증 기록 본문만 고쳤고 백엔드 소스·테스트 0줄). 변이 재적용은 **감사가 새로 찍은 MA-2~MA-5 넷 + 재현된 MP 열한 종 중 표본 여섯(MP-1·MP-2·MP-3·MP-7·MP-8b·MP-11b), 열 회 전부 건수·기명 셀까지 일치**했다. 승격의 실체(C1 폐쇄 잠금)가 AC1 폐쇄 뒤에도 그대로 살아 있다.

## Subject metadata

- **검증일**: 2026-09-13 · **요청자**: 오너(이 세션 지시 — "감사기록 승격이고 검증확인해줘. 변이 재적용 대상은 그 기록의 MA-2~MA-5 + 재현된 MP-1~MP-11b 중 표본").
- **검증자**: 독립 세션. 구현(`7979ff2`·`68aedf3`) · 발행 검증(세션 72) · 조건 폐쇄(`70efc23`) · 승격 재검(`432f790`) · 재감사(`88a16fe`, 세션 75) · 선재 5건 정합(`a1d71fc`) 어느 것도 이 세션이 아니다. 이 축의 코드·테스트·기록을 한 줄도 쓰지 않았다.
- **대상**: 폐쇄 커밋 **`88a16fe`**(AC1 — 감사 기록 자신의 폐쇄 보고) · 대조용 **`a1d71fc`**(선재 5건 본문 판정 줄 정합). 검증 트리 기준은 `88a16fe`(a1d71fc는 검증 기록 본문만 고쳤고 `services/`·`tests/` 0줄 — 변이·기준선 불변의 근거).
- **정규 스펙(계약 스코프)**: [`guides/verification.md`](../../guides/verification.md) §Required sections(판정 어휘·인덱스 일치) · §Mutation testing(원복 규칙 · `grep FAILED` 맹점) · §"Recording a measurement". 감사 기록 [`activity_replay_c1_promotion_audit.md`](../2026-09-12/activity_replay_c1_promotion_audit.md) §Issues AC1 처방 · §3 MA-2~MA-5 · §2 MP 표.
- **검증 트리**: 변이·기준선은 탈치 워크트리 `/tmp/verify_ac1`(`88a16fe` detached)에서 돌린 뒤 `worktree remove --force` 했다. **본 트리에 `git checkout`·`restore`·`stash`·`reset`을 한 번도 쓰지 않았다.**
- **환경**: WSL2 · 호스트 `python3 -m pytest`(user-site). **이 세션의 호스트에는 Mongo가 도달하지 않았다** — 넓은 셋의 `test_activity_log.py` 1셀이 `no MongoDB reachable` 로 skip 됐다(감사 환경은 도달, "238 passed" 는 passed+skip 합산). skip 1 = 알려진 구성(가이드 §"Recording a measurement" — 셀·서브테스트·기명 셀은 무변).
- **공유 트리 관찰**: 검증 중 다른 작업 AI 가 같은 축의 미수리 둘(HP-1·HA-1)을 본 트리에서 보강했다(미커밋 관찰 → 커밋 **`5a8e8c7`** 확정 — diff 확인만, 손대지 않았다). 그래서 기준선 양단 실측은 탈치 워크트리(`88a16fe`)에서, 확정 측정은 문서 가드로 했다.

## Scope

1. **AC1 폐쇄 확인** — diff 1차 소스 + 인덱스 판정 열 ↔ 본문 선두 토큰 전수 대조(311행).
2. **변이 재적용** — MA-2·MA-3·MA-4·MA-5(감사가 새로 찍은 휴면 절 가드 경계 넷) + MP-1·MP-2·MP-3·MP-7·MP-8b·MP-11b(표본 여섯 — C1 폐쇄의 실체 잠금 둘 · 세 갈래 분리 하나 · over 방향 둘 · 처분표 층 하나 · 제목 경계 하나).
3. 기준선 재측정(문서 가드 · 두 파일 · 넓은 셋 · quota)과 감사 실측치 대조.

## Methodology

- 변이는 `python3` 헬퍼 하나로만 적용했다 — 「앵커 `count == 1` 단정 → `shutil.copy2` 백업(`/tmp`) → `pathlib.write_text` 치환 → 초점 실행 → 백업 복원 → **바이트 동일성 단정** → `git status --short` 빈 것 확인」 여섯 단계가 스크립트에 단정으로 박혀 있다. `sed -i`·`perl -i`는 쓰지 않았다(저장소 규칙).
- 결과는 **요약 줄 + `FAILED|SUBFAILED`** 를 함께 읽었다(가이드 §★).
- 전수 대조는 산문을 읽지 않고 인덱스 표를 파싱해 센 뒤, 각 기록의 **머리 12줄 + §Verdict 첫 줄(비인용)** 에서 세 토큰(`**합격**`·`**조건부 합격**`·`**불합격**`)·승격 모양(`**최종 판정은 합격이다**`)으로 선두 시작하는 줄을 맞댔다 — 폐쇄 보고의 패턴 스윕과 같은 기준.

## Findings

### 1. AC1 폐쇄 — 세 층 확인

- **① diff 1차 소스**: `git show 88a16fe -- …/activity_replay_and_dormant_docs.md` — 머리 3행이 `**최종 판정은 합격이다** — 조건 C1 은 폐쇄 커밋 … 승격 재검 … 이 판정을 올렸다. 아래 본문은 발행 시점 그대로다.` 로, §Verdict 첫 줄이 `**합격**(승격 — …) 발행 시점 판정 원문:` 로 바뀌었고 **발행 시점 판정 원문은 두 자리 모두 인용 블록으로 보존**돼 있다. 선례 `2e025dc`가 승격 넷에서 쓴 모양과 정확히 같다.
- **② 전수 대조(311행)**: 인덱스 판정 열 ↔ 본문 선두 토큰 — **불일치 0건**. 선두 토큰이 있는 기록 91건 전부 일치한다. 감사가 AC1 으로 지적했던 불일치 1건은 사라졌다.
- **③ 선재 5건**: 폐쇄 보고가 부채로 등재한 다섯(`2026-09-11/landing_l2_terms_privacy.md` · `2026-08-20/mypy_guard_slice.md` · `2026-08-20/embedding_adapter_slice.md` · `2026-08-20/reranker_slice.md` · `2026-08-23/llm_key_fallback_slice.md`)은 `a1d71fc`(커밋 메시지 *"승격 기록 선재 5건 본문 판정 줄 정합 — 인덱스와 선두 토큰 일치"*)가 닫았다. 내 대조에서도 이 다섯은 병으로 검출되지 않는다. `a1d71fc`의 `--stat`은 검증 기록 본문만(백엔드 소스·테스트 0줄).
- **범위 한계(정직 기재)**: 나머지 220건은 판정 줄이 옛 영어 병기(`**합격(PASS)**` · `**조건부 합격(conditional pass)**` 류)로 시작해 세 토큰 선두 규칙이 못 본다. 이들은 인덱스와 **뜻**이 같아 병이 아니고(2026-08-06 어휘 통일 이전 발행분), 폐쇄 보고가 이미 "217건이 판정 토큰을 줄머리에 두지 않아 형식을 먼저 정해야 (가드를) 세울 수 있다"고 적은 그 집합이다 — 이 재검의 범위 밖이다.

### 2. ★ 변이 재적용 — 열 회 전건 일치

> 전부 `/tmp/verify_ac1`(`88a16fe` detached). "기대"는 감사 기록 §2·§3 표의 실측치다. diff 원문은 감사 표의 문구를 그대로 적용했다(MP-2 는 "record 호출을 `if not result.idempotent_replay:` 로 감쌈" — 감싸기 변이, 주석줄 포함 블록으로 유일화).

| # | 방향 | 파일 / 조작 | 감사 실측(기대) | **내 실측** | 일치 |
|---|---|---|---|---|---|
| **MP-1**(=MB-8) | under | `writing.py` `if result.saved is not None:` → `… and not result.idempotent_replay:` | 1 failed · `test_resending_the_same_accept_key_still_records_a_second_row` | **1 failed, 236 passed, 1 skipped, 694 subtests** · 같은 기명 셀 | ✅ |
| **MP-2**(=MB-9) | under | `drafts.py` 수동 저장 `activity.record(` 를 `if not result.idempotent_replay:` 로 감쌈 | 1 failed · `test_resending_the_same_save_key_still_records_a_second_row` | **1 failed, 236 passed, 1 skipped, 694 subtests** · 같은 기명 셀 | ✅ |
| **MP-3**(=MV-1) | under | `drafts.py` finalize `if not finalized.idempotent_replay:` → `if True:`(주석줄 앵커로 유일화) | 1 failed · `test_resending_the_same_final_save_key_leaves_no_second_row` · 76 passed | **1 failed, 76 passed, 19 subtests** · 같은 셀 | ✅ |
| **MP-7** | over | 지시 문장을 두 낱말(`verifications/`·`전신`)을 지키며 다듬음 | 전건 초록 | **20 passed / 324 subtests** | ✅ |
| **MP-8b** | 층 확인 | `quota/dedupe.py` `KEY_REPLAY_ACTIONS["writing_accept"]` `"handler"`→`"consume"` | 2 failed(`KeyConsumptionTest` 두 셀) · 52 passed | **2 failed, 52 passed, 2 subtests** · 같은 두 셀 | ✅ |
| **MP-11b** | 경계 | `## 휴면 디렉터리 (한 번 쓰고 멈춘 것)` → `## 휴면 디렉터리 (보존)` | 전건 초록 | **20 passed / 324 subtests** | ✅ |
| **MA-2** | 사각 | 지시 문장에서 `` `verifications/` `` 낱말만 제거(`전신` 유지) | 전건 초록(무가드) | **20 passed / 324 subtests** | ✅ |
| **MA-3** | 경계 | 절 제목 꼬리 통째 제거(`## 휴면 디렉터리`) | 전건 초록 | **20 passed / 324 subtests** | ✅ |
| **MA-4** | 경계 | 접두 뒤 글자 추가(`## 휴면 디렉터리들 (…)`) | 전건 초록 | **20 passed / 324 subtests** | ✅ |
| **MA-5** | 경계 | 접두 내부 공백 추가(`## 휴면  디렉터리 (…)`) | 1 failed — H3 셀 | **1 failed, 19 passed** · `test_the_dormant_section_says_what_the_old_name_was` | ✅ |

**기명 셀까지 전부 일치한다.** under 방향(MP-1·MP-2·MP-3)은 C1 폐쇄가 만든 특성 셀 셋이 AC1 폐쇄(문서 변경) 뒤에도 정확히 그 셀만 물고, over 방향(MP-7)은 정상 편집을 계속 놓아주며, 경계 넷(MA-2~MA-5·MP-11b)은 감사가 확정한 경계 — **"문자열 `\n## 휴면 디렉터리` 보존 여부 하나"** — 를 그대로 재현한다. MA-2 의 초록(사각 HA-1)도 재현됐다. **시점 주의**: 그 초록은 `88a16fe`(HA-1 폐쇄 전) 기준 실측이다 — 병행 세션이 HA-1 을 닫는 `5a8e8c7`(가드 범위를 `verification_briefs/` 행 하나로 좁힘)을 실은 뒤에는 같은 방향이 **1 failed** 가 된다(그 세션 MA 변이 실측). 사각이 닫혔다는 뜻이지, 감사 실측의 재현이 틀렸다는 뜻이 아니다.

### 3. 기준선 재측정(`88a16fe` 트리)

| 초점 | 감사 실측(`432f790`) | 내 실측(`88a16fe`) | 비고 |
|---|---|---|---|
| `test_docs_indexes.py` | 20 / 323 | **20 / 324** | +1 = 감사 기록 자신의 등재분(인덱스 행) |
| `test_activity_api` + `test_writing_accept` | 77 / 19 | **77 / 19** | 무변 |
| 넓은 셋(활동 3 + accept + application) | 238 / 694 | **237 passed + 1 skipped / 694** | 이 호스트 Mongo 미도달 skip(§환경) — 셀 총수·서브테스트 무변 |
| `test_quota_enforcement.py` | (54셀) | **54 passed / 2 subtests** | MP-8b 변이 시 2 failed + 52 passed = 같은 54 |

`88a16fe`·`a1d71fc` 둘 다 백엔드 소스·테스트 0줄(각각 `--stat` 확인)이므로 코드 축 기준선의 불변은 구조적으로도 성립한다.

## Issues / Risks

### Blocking (계약 의무)

없다. AC1 폐쇄가 계약(`guides/verification.md` §Required sections — 인덱스 판정 열과 본문 판정 첫 줄의 일치)을 회복했고, 전수 대조로 같은 병이 남아 있지 않음을 확인했다.

### Hardening (비차단)

- 새로 연 것은 없다. 감사가 연 **HA-1**(H3 가드 `verifications/` 쪽 무가드)·**HP-1**(수동 저장 특성 셀의 action 단정)은 검증 중 병행 세션이 닫았다(**`5a8e8c7`** — HA-1 은 가드 범위를 `verification_briefs/` 행 하나로 좁히고, HP-1 은 replay 행의 `action`·`target_type` 단정을 더했다). 그 세션 산출의 독립 검증은 그 세션의 서브에이전트 몫이다(이 기록 범위 밖). **HA-2**(승격 줄 머리 토큰)는 이번 승격에서 감사 자신의 처방대로 `**합격**` 으로 시작하게 적용했다.
- **`a1d71fc`의 선재 5건 정합 방식은 이 재검의 확인 범위를 벗어난다**(본문 줄이 인덱스와 선두 토큰 일치로 바뀐 것만 확인 — 각 기록의 승격 근거까지 재검하지는 않았다).

## Verdict

**합격**

승격의 근거:

1. **AC1 이 실제로 닫혔다** — diff 1차 소스에서 머리·§Verdict 둘 다 승격 + 발행 시점 원문 인용 보존(선례 모양), 전수 대조 311행 병 0건, 폐쇄 보고가 부채로 등재한 선재 5건도 `a1d71fc` 로 닫혀 내 대조에서 검출되지 않는다.
2. **승격의 실체가 폐쇄 뒤에도 살아 있다** — C1 폐쇄 잠금(MP-1·MP-2)·세 갈래 분리(MP-3)·처분표 층(MP-8b)이 기명 셀까지 같게 재실패한다.
3. **감사의 경계 서술이 정확하다** — MA-2~MA-5·MP-7·MP-11b 여섯이 초록/1실패로 갈라지는 지점이 감사 표와 한 치도 다르지 않다("접두가 사라지는 쪽만 닫혔다 · 정상 다듬기는 안 문다"의 재확증).
4. **기준선 산술이 성립한다** — 문서 가드 323→324(+1 = 감사 기록 등재분), 나머지 무변(백엔드 소스·테스트 0줄 커밋 둘).

## Outstanding items

1. **이 기록(+2: `test_repo_hygiene` +1 · 검증 인덱스 행 1 = `test_docs_indexes` +1)과 오늘 신규 work_log 파일(+1 — 병행 세션 76 과 공유)이 기준선을 +3 한다** — HANDOFF 회귀 기준선 줄과 루트 README ②행을 **4,229 → 4,232** 로 같이 올렸다(실측: 문서 가드 둘 952 → 955 · passed 무변 · 백엔드 소스 무변).
2. **감사 기록의 판정을 조건부 합격 → 합격으로 승격**하고 인덱스 70행(감사 기록 행)의 판정 열·요약 셀을 같이 올렸다 — 감사 자신의 처방(HA-2)대로 머리 판정 줄이 `**합격**` 토큰으로 시작한다. 발행 시점 판정 원문은 인용으로 보존했다.
3. HA-1·HP-1·HP-2·H1(남은 절반)·H2·H4·HA-2(선례 넷의 머리 줄)는 그대로 — 병행 세션이 HA-1·HP-1 을 보강 중이었다(관찰 기록). 오너 결정 대기 두 건(활동 로그 D2 · 파기 청구 뒤 탈퇴 취소)도 그대로.
4. 검증 인덱스 머리·분포 표·루트 README·docs/README 의 건수·분포를 이 승격과 이 기록 등재에 맞춰 갱신했다(311→312건 · 72→73일치 · 합격 213 / 조건부 94 / 불합격 5 · 조건부 30%).

## Reproduction

```bash
# 0) 본 트리를 건드리지 않는다 — 변이는 탈치 워크트리에서만
cd /mnt/f/devel/ai_writte_system
git status --short                      # 다른 세션의 미커밋이 보여도 손대지 않는다
git worktree add --detach /tmp/verify_ac1 88a16fe
cd /tmp/verify_ac1

# 1) 기준선(이 세션 실측치)
PYTHONPATH=$PWD python3 -m pytest tests/test_docs_indexes.py -q                    # 20 / 324
PYTHONPATH=$PWD python3 -m pytest tests/test_activity_api.py tests/test_writing_accept.py -q   # 77 / 19
PYTHONPATH=$PWD python3 -m pytest tests/test_activity_api.py tests/test_activity_actions.py \
    tests/test_activity_log.py tests/test_writing_accept.py tests/test_application_api.py -q  # 237+1skip / 694
PYTHONPATH=$PWD python3 -m pytest tests/test_quota_enforcement.py -q               # 54 / 2

# 2) 변이 — 매번 「앵커 count==1 단정 → copy2 백업 → write_text 치환 → 초점 재실행 →
#    백업 복원 → 바이트 대조 → git status 확인」. diff 원문은 §2 표. 결과는 요약 줄과
#    FAILED|SUBFAILED 를 함께 읽는다.
PYTHONPATH=$PWD python3 -m pytest <초점> -q 2>&1 | grep -E "^(FAILED|SUBFAILED)|passed|failed"

# 3) AC1 폐쇄 확인
git -C /mnt/f/devel/ai_writte_system show 88a16fe -- \
    docs/verifications/2026-09-12/activity_replay_and_dormant_docs.md   # 머리+Verdict 승격·인용 보존
# 인덱스 판정 열 ↔ 본문 선두 토큰 전수 대조: 각 행의 링크를 열어 머리 12줄+§Verdict 첫 줄에서
# 세 토큰/승격 모양 선두를 찾아 맞댄다 → 불일치 0건(선두 토큰 있는 91건 기준)

# 4) 정리
git worktree remove --force /tmp/verify_ac1
```
