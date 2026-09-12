# 랜딩 ③·④ · S-2 — 조건 폐쇄 승격 재검

**합격** — 발행 검증의 조건 둘 **C1(동의 스탬프 Mongo 영속 셀)·C2(확인란 문구·새 탭 링크 셀)** 이 폐쇄 커밋 **`cbd88f7`**(2026-09-12 · test-only)로 닫혔고, 이 재검이 변이 재적용으로 그 폐쇄를 확증했다. 선행 기록 [`landing_l3_gate_and_landing.md`](landing_l3_gate_and_landing.md) 의 판정 **조건부 합격을 합격으로 승격**한다(발행 시점 판정은 인용으로 아래 보존).

- **일시**: 2026-09-12 · **검증자**: 독립 세션 — 구현(세션 68)·발행 검증·조건 폐쇄(`cbd88f7`) 어느 쪽도 아니다
- **검증 트리**: HEAD `24be529`(**승격 재검 세 셋[slice5·slice4b·final_save]을 마친 뒤 같은 세션이 이 축을 이어 받았다** — 세션 72 가 Next Tasks 백로그로 넷을 등재해 둔 것의 마지막 하나). 검증 창 내내 다른 AI 세션들의 미커밋 편집이 같은 트리에 공존했다(아래 Outstanding) — 변이 원복은 대상 파일만 개별 경로로 `git checkout -- <절대경로>` + 백업 `cmp` 바이트 대조, 매 변이 전 대상 파일 diff 0 확인.
- **환경**: WSL2 · `python3 -m pytest`(test-mongo healthy) · 프런트는 `frontend/` 안에서 `npx vitest`(단일 파일)

## 변이 재적용 — 3종 전부 폐쇄 보고와 일치

| 변이 | 적용한 diff(실제 텍스트) | 발행 검증 시점 | 실측(폐쇄 후 현행 트리) |
|---|---|---|---|
| **MV-A** (under·방어 제거) | `auth/users_mongo.py` `_doc` 에서 `"terms_agreed_at": value.terms_agreed_at,`·`"terms_version_agreed": value.terms_version_agreed,` **두 줄 삭제** | **277셀 전건 초록 — 무물림**(이것이 C1 이었다) | **1 실패** `MongoUserRepositoryTest::test_the_write_face_carries_the_consent_stamp_through_insert_and_replace` — `1 failed, 26 passed`. 쓰기면 왕복 셀이 정확히 물었다 |
| **MV-B** (under·방어 제거) | `_entry` 의 `doc.get("terms_agreed_at")`→`doc["terms_agreed_at"]`(`terms_version_agreed` 도 같이) | 4실패 — **전부 타축 legacy 셀, 동의 이름 셀 0** | **5 실패** — 타축 legacy 넷(C-6·승인 status·탈퇴×2) **+ `test_a_row_written_before_the_consent_axis_reads_back_as_not_consenting`**. 폐쇄 보고의 *"legacy 셀 5실패 중 동의 이름 셀이 기명 포함"* 과 정확히 일치 — 발행 검증이 실측한 갭(동의 이름 셀 0)이 메워졌다 |
| **C2 변이** (under) | `AuthGate.tsx` 확인란의 두 링크에서 `target="_blank"` 제거 | **무셀**(조건 ②) | **1 실패** `App routes > … > states the consented version and opens the documents in a new tab` — `1 failed, 33 passed (34)` |

## 폐쇄 ↔ 처방 대조

- **C1**: 처방(같은 파일의 C-6·탈퇴축 선례 모양 그대로 셀 둘 — 쓰기면 왕복 + legacy None 판독) 그대로. MV-A·MV-B 양변이 각각 새 셀을 물었다.
- **C2**: 처방(문구 `버전 1.0`·두 링크 `href`·`target="_blank"` 단정 — `within` 한정) 그대로. `target` 제거 변이가 그 셀 하나만 물었다.
- 발행 검증의 다른 축(400 단일 얼굴·서버 전용 저장·핀 두 곳·랜딩 네 얼굴·nginx server 레벨)은 폐쇄가 건드리지 않았고 이 재검의 범위 밖(변이 MV-C·D·E·F 는 발행 시점에 이미 잠금 확인).

## 기준선(변이 전 초록)

- `tests/test_auth_users_mongo.py` **27 passed**(폐쇄 보고 25→27 과 일치) · `src/App.test.tsx` **34셀**(신규 1 포함 — 폐쇄 보고와 동일 구성).

## Verdict

**합격** — 조건 C1·C2 모두 폐쇄됐고 변이 재적용 세 종이 폐쇄 보고 그대로 문다(MV-A 는 *전건 초록→기명 재실패*, MV-B 는 *동의 이름 셀 0→기명 포함*, C2 는 *무셀→기명 재실패*). 선행 기록 발행 시점 판정 원문:

> **조건부 합격** — 동의 스탬프의 **Mongo 영속 축이 무셀**이다(쓰기면에서 스탬프가 통째로 사라져도 277셀 전건 초록 — MV-A 실측). … 이 둘을 닫으면 합격이다.

이로써 **승격 재검 백로그 넷(랜딩 L3 · Slice 5 · Slice 4b · 최종 저장 6차)이 전부 닫혔다.**

## Outstanding items

- **같은 창에 다른 검증 세션이 새 기록을 등재 중이었다** — `activity_replay_and_dormant_docs.md`(세션 72 슬라이스의 독립 검증, **조건부 합격 — C1 replay 세 갈래 중 둘 무셀**). 그 조건은 아직 폐쇄 전이므로 승격 재검 대상이 아니고, **그 축이 이 저장소의 다음 검증 백로그**다.
- 발행 기록의 하드닝 셋(로그인 폼 h1 무핀 · 랜딩 벤더 금지 부정단정 무셀 · gen:api 드리프트)은 그대로 비차단.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system
git status --short -- services frontend/src        # 변이 대상 diff 0 확인
python3 -m pytest tests/test_auth_users_mongo.py -q   # 27 passed
# MV-A: users_mongo.py _doc 의 동의 두 줄 삭제 → 1 failed(쓰기면 왕복 셀)
# MV-B: _entry 의 doc.get → doc[...] 두 필드 → 5 failed(legacy 넷 + 동의 legacy 셀)
# C2  : AuthGate.tsx 확인란 링크 target="_blank" 제거
#        → cd frontend && npx vitest run src/App.test.tsx  # 1 failed(확인란 셀)
# 매 변이: git checkout -- <절대경로> 원복 + 백업과 cmp 바이트 대조
```
