# 미승인 후보 정체성 그룹 Slice 0(저장 모델과 수명) 독립 검증

- 일자: 2026-09-02
- 요청자: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래")
- 검증자: Claude Code(독립 검증 세션 — 슬라이스 구현과 무관)
- 대상: identity group 저장 슬라이스. 코드 커밋 `183af60`(Add candidate identity group storage (Slice 0)), 문서 커밋 `ea29bb5`(SoT v1.8.17). 착수 전 baseline `e3d782c`. 트리 clean.
- 정본 계약: [`docs/plans/pending-candidate-identity-grouping-implementation-phases.md`](../../plans/pending-candidate-identity-grouping-implementation-phases.md) Slice 0(§"Slice 0 — 저장 모델과 수명") + [`docs/system-contract-sot.md`](../../system-contract-sot.md) v1.8.17 라이브 조항(`:733`)·변경이력(`:36`) + 결정 브리프 [`pending-candidate-identity-grouping-decisions.md`](../../plans/pending-candidate-identity-grouping-decisions.md)(C 채택).

## Scope

1. 계약 정합 — 계획 Slice 0 ↔ SoT v1.8.17 라이브 조항·변경이력 ↔ 오너 결정(relation `candidate_type` 상위집합) 상호 무모순.
2. 구현 코드 — `services/application/app/analysis/identity_groups.py`(도메인·서비스·in-memory)·`identity_groups_mongo.py`(3컬렉션 어댑터)·`main.py` 배선·`routers/admin.py`·`routers/projects.py` 파기 그래프 합류.
3. 회귀 테스트 — `tests/test_identity_groups.py`(14셀)·`tests/test_identity_groups_mongo.py`(fake 5 + 실몽고 1)·`tests/test_owner_project_purge.py`·`tests/test_auth_api.py`(admin purge 스파이)·`tests/test_purge_project_coverage.py`(로스터 가드).
4. 카운트 검산 — 전수 결과와 컬렉션 수 증분의 독립 재실측.
5. 공개 계약 무변 — OpenAPI dump·`schema.d.ts`가 baseline 대비 무변인지.
6. 변이 스팟체크 — 검증자 독립 변이 7종(작업자 9종 중 4종 재현 + 신규 3종).
7. 문서 — SoT 버전 헤더·변경이력·work_log(오너 결정 기록)·CHANGELOG·HANDOFF(기준선·분량)·`docs/plans/README.md` 색인.

## Methodology

계약 범위를 먼저 읽고(계획 Slice 0 § 전문, SoT 라이브 조항 전문, 결정 브리프 전문) 경계 행렬을 세운 뒤 코드·테스트에 대조했다. 모든 측정의 환경: test-mongo rs-test 기동(`docker compose -f docker-compose.test.yml up -d`, `127.0.0.1:27020`, 컨테이너 `ai_writte_system-test-mongo-1` 확인), 이 머신 ES 패키지 탑재(베타 관례 — skip 1은 live Chroma 셀). 전수·변이가 서로 오염되지 않게 변이는 별도 worktree(`/tmp/verify-mut` @ `ea29bb5`)에서 수행했다(메인 트리에서 전수 실행 중).

- Focused: `python3 -m pytest -q tests/test_identity_groups.py tests/test_identity_groups_mongo.py`
- Docs 가드: `python3 -m pytest -q tests/test_docs_indexes.py`
- 카운트 검산: `git worktree add /tmp/verify-pre-slice0 e3d782c` 후 `python3 -m pytest --collect-only -q tests/ | tail -1` → **2677**; HEAD에서 `--collect-only` → **2697**; 전수 `PYTHONPATH=. python3 -m pytest -q tests/`(nohup 분리 실행, 2046.65s)
- OpenAPI: `python3 scripts/dump_openapi.py`을 `e3d782c`·`ea29bb5` 각 worktree에서 실행 → `diff` + `git diff e3d782c ea29bb5 -- frontend/src/api/schema.d.ts`
- 실몽고 datetime 프로브: `MongoCandidateIdentityGroupRepository`를 27020 rs-test의 uuid DB에 연결, group 생성·`set_group_status`·relation 기록 후 read-back의 `tzinfo`·동등성 출력, 종료 시 `drop_database`
- 변이: worktree에서 `git status --short` 0줄 확인(사전 게이트) → 소스 1곳 변이 → focused 재실행 → `git checkout -- <path>` 복원 → `git status --short` 0줄 재확인. 적용 diff 는 아래 표에 기록.

## Findings

### 1. 계약 정합 — 이상 없음

- 세 저장 단위 필드 목록이 계획(`:31-33`)·SoT 라이브 조항(`:733`)·`CandidateIdentityGroup/Member/Relation` 데이터클래스(`identity_groups.py:58-92`)에서 문자 그대로 일치한다. relation의 `candidate_type`은 오너 결정(2026-09-02)으로 양쪽 정본에 반영됐다.
- 계약 리터럴 전수 대조: `status` `open|contradicted|closed`(`identity_groups.py:38-43`), verdict `same|different|uncertain`(`:46-49`), Slice 0 유일 `member_status`=`active`(`:52-55`), `revision` 0 시작(`:319`)·변경마다 +1(`:350`), member unique 축 `(project_id, candidate_type, group_id, candidate_id)`(`identity_groups_mongo.py:66-75`), relation unique 축 `(project_id, candidate_type, left, right)`(`:76-85`) — 요구 문장("모든 unique/index 축에 포함")과 일치.
- 오너 결정 기록: `work_log.md:60-65`(대안 명시: 필드 목록 우선) + SoT 변경이력·라이브 조항 반영. "candidate purge 경로는 현재 없다"는 범위 근거도 `work_log.md:66-68`에 기록돼 있다.
- 계획↔SoT 자기모순: 발견 안 함(계획의 원래 긴장은 오너 결정으로 해소된 상태).

### 2. 구현·배선 — 이상 없음(비차단 2건은 Issues)

- relation pair 정규화: `normalize_relation_pair`(`identity_groups.py:94-107`)가 `A==B` 거부 후 좌우 정렬. 재기록 upsert에서 `created_at` 첫 판정 보존(`:420-423`).
- member 멱등: 기존 행 조기 반환, `added_at` 불변(`:370-375`). type 불일치 거부(`:365-369`).
- 배선: `_default_candidate_identity_group_service`(`main.py:373-391`)가 `CORE_SOT_MONGO_URI/DB` 관례로 review_queue 선례와 동일. `create_app` 파라미터→`register_admin`·`register_projects` 양쪽 전달.
- 파기 그래프: 소유자·admin 양 경로가 공유 `execute_project_purge`(`routers/admin.py`)를 타며 `identity_groups.purge_project` 호출이 그 사이에 끼었다. 어댑터 `purge_project`(`identity_groups_mongo.py:179-183`)가 3컬렉션 `delete_many`. 로스터 가드 10계약/22컬렉션 갱신(`test_purge_project_coverage.py:8-10,54-84`), 양 경로 스파이 단언(`test_owner_project_purge.py:104`, `test_auth_api.py:1118`).
- 패턴 스윕: "19컬렉션" 낡은 표기 전수 확인 — v1.8.11 변경이력(역사 기록, 정상) 외 없음.

### 3. 경계 행렬 — 계약 요구 분기 전부 기명 셀에 배정(1개 빈 칸 = Issues B1)

| 계약 요구(계획 Slice 0 "검증" 축) | 잠근 셀 |
|---|---|
| in-memory round-trip 3단위 | `test_create_group_round_trip`·`test_member_round_trip`·`test_relation_round_trip` |
| project/type 격리 | `test_get_group_is_project_scoped`·`test_relations_are_type_and_project_scoped`·`test_members_do_not_leak_across_groups`·`test_set_group_status_is_project_scoped` |
| member 재추가 멱등(`added_at` 불변) | `test_add_member_is_idempotent` |
| relation pair 정규화·upsert·`created_at` 보존 | `test_relation_pair_is_normalized_across_directions`·`test_relation_re_record_same_pair_updates_verdict_in_place` |
| `contradicted` 상태 round-trip(+revision) | `test_group_status_round_trip_including_contradicted` |
| Mongo round-trip | fake 5셀 + `MongoCandidateIdentityGroupLiveRoundTripTest::test_round_trip_isolation_and_purge` — **단, 필드 충실도는 미잠금(B1)** |
| project purge 정리(인접 무변 = 과잉 방향 포함) | `test_purge_project_clears_groups_members_and_relations`·fake `test_purge_project_deletes_all_three_collections`·실몽고 동일 셀·양 HTTP 경로 스파이 |
| OpenAPI/`schema.d.ts` 무변 | dump diff 실측(아래 5) |

셀 수 검산: 도메인 14 + fake 5 + 실몽고 1 = 20 — 전부 이 슬라이스 신규, 컬렉션 증분과 정확히 일치.

### 4. 전수 스위트·카운트 — 주장 전부 재현

- 전수(HEAD `ea29bb5`, test-mongo ON, nohup 2046.65s): **2696 passed / 1 skipped / 3124 subtests, EXIT=0** — 작업자 기록과 한 자리도 다르지 않다.
- 검산: baseline `e3d782c` 컬렉션 실측 **2677** → HEAD **2697** = 순수 +20(신규 두 파일 전부, 기존 셀 증감 0).
- Focused 20 passed(8.53s)·docs 가드 13 passed/284 subtests(284는 검증 기록 추가에 따른 기계적 증가 — 작업자 측정 시점 282와 다른 것이 정상).

### 5. OpenAPI/`schema.d.ts` 무변 — 재현

`e3d782c`와 `ea29bb5` 각각 `scripts/dump_openapi.py` 출력 384,414B 바이트 동일(`diff -q` IDENTICAL), `git diff e3d782c ea29bb5 -- frontend/src/api/schema.d.ts` 빈 diff. 작업자의 "HEAD stash 대비"보다 강한 pre-slice↔post-slice 비교로 재현.

### 6. 변이 스팟체크 — 독립 7종 전부 기명 재실패(작업자 9종 중 4종 재현 + 신규 3종)

| 변이 | 적용 diff(요지) | 재실패 셀 | 결과 |
|---|---|---|---|
| V1 정규화 제거(=I1+I1') | `normalize_relation_pair` 두 번째 return을 `return left_candidate_id, right_candidate_id`로(스왑 제거) | `test_relation_pair_is_normalized_across_directions`·`test_relation_round_trip`·실몽고 `test_round_trip_isolation_and_purge` | 3 failed |
| V2 멱등 제거(=I2) | `add_member`의 `existing is not None → return existing` 블록 삭제 | `test_add_member_is_idempotent` | 1 failed |
| V3 created_at 리셋(=I3) | `created_at=(existing.created_at if … else self._clock())` → `created_at=self._clock()` | `test_relation_pair_is_normalized_across_directions` | 1 failed |
| V4 과잉 파기(**신규**) | in-memory `purge_project`의 3개 딕셔너리 재구성 → `{}` 통째 클리어(프로젝트 필터 소실) | `test_purge_project_clears_groups_members_and_relations`(인접 project 무변 단언) | 1 failed |
| V5 revision +1 제거(**신규**) | `revision=group.revision + 1` → `revision=group.revision` | `test_group_status_round_trip_including_contradicted` | 1 failed |
| V6 purge 호출 누락(=I7) | `execute_project_purge`에서 `identity_groups.purge_project(project_id=project_id)` 3줄 삭제 | `OwnerProjectPurgeTest::test_owner_purge_returns_204_and_destroys_the_graph`·`AdminProjectPurgeTest::test_admin_purge_fans_out_to_derived_services` | 2 failed |
| V7 self-pair 방어 제거(**신규**) | `normalize_relation_pair`의 `A==B` ValueError 블록 삭제 | `test_relation_rejects_self_pair` | 1 failed |

각 변이 후 `git checkout --` 복원·`git status --short` 0줄 확인. V1에서 실몽고 셀의 실패 메커니즘을 직접 확인했다 — `AssertionError: 2 != 1`(len 단언)이지 unique 인덱스 위반이 아니다(정규화가 없으면 `(b,a)`/`(a,b)`는 서로 다른 인덱스 키라 유일성 위반이 안 일어난다). 가드는 물었으나 작업자 변이 표 I1'의 관측 주석이 부정확하다(H3).

### 7. 문서 — 의무 전부 이행

SoT 버전 헤더 v1.8.17(`:4`)·변경이력(`:36`)·라이브 조항(`:733`), 계획 완료 기록(구현 페이즈 `:25,48-56`), work_log 오너 결정·검증 섹션, CHANGELOG, HANDOFF 회귀 기준선(`:89`)·분량 기록(`:8`), `docs/plans/README.md:73-74` 색인. 공통 작업 규칙(Slice 0은 SoT·daily_logs·HANDOFF 동일 커밋 계열 갱신) 충족.

## Issues / Risks

### Blocking (contract obligations)

- **B1 — 실몽고 읽기 경계의 datetime 정규화 누락 + Mongo round-trip 충실도 미잠금.** 측정(2026-09-02, 27020 rs-test): group `created_at` 쓸 때 `tzinfo=timezone.utc`, 실몽고에서 읽으면 `tzinfo=None`(naive); `svc.get_relation(...) == 기록한 relation` → **False**(데이터클래스 동등성 자체가 깨짐). `identity_groups_mongo.py`의 `_to_group/_to_member/_to_relation`(`:226-289`)이 `doc["created_at"]`을 그대로 통과시킨다. 이 저장소의 datetime 저장 어댑터 12개 중 10개가 경계에서 `_aware()` 재라벨링을 하며(`auth/sessions_mongo.py:11-21`은 "in-memory fake는 통과·실몽고 매 읽기 500"이었던 실제 사고를 문서화), 작업자가 선례로 인용한 scene_notes도 실제로는 `core_sot/mongo_repository.py:906-920`에서 `_aware`로 정규화한다 — 인용 선례 어느 쪽도 이 구현을 뒷받침하지 않는다. fake 셀은 직렬화가 없어 이 경계를 구조적으로 못 잡고, 유일한 실몽고 셀은 개수·상태만 단언하므로 계획 검증 축 "in-memory**과** Mongo round-trip"의 충실도 칸이 비어 있다. 유일한 비정규화 선례 `writing/generation_job_mongo.py`(기존 부채)로 미루어 볼 때 Slice 1+가 시각 비교에 닿는 순간 sessions 사고와 같은 형태로 재현된다. 참고: 정규화만으로는 부족하다 — BSON 날짜는 ms 절단이라(프로브: 760724µs→760000µs) µs 정밀 clock의 `==` round-trip은 여전히 안 된다. 폐쇄는 정규화 + 실몽고 셀의 충실도 잠금(동등성 기준 명시: ms 절단 clock 또는 필드별 비교)이 한 벌이다.

### Hardening recommendations (non-blocking)

- **H1 — groups 컬렉션의 `_id`가 `group_id` 단독**(`identity_groups_mongo.py:91-94,216`). SoT "모든 unique/index 축에 project_id·candidate_type 포함"을 초문자적으로 읽으면 기본 unique 인덱스인 `_id`도 해당 문장에 걸린다. 실질 위험은 없다(server 생성 uuid4 id, 서비스의 모든 읽기가 project 검사 `identity_groups.py:326-334`, 동일 형태의 `review_queue` 선례 `_id: entry.id`) — SoT에 "groups의 문서 정체성은 server 생성 group_id" 한 문장을 보태 그 긴장을 명시적으로 닫기를 권장.
- **H2 — self-pair(A==B) 거부가 정본에 미기재.** `ValueError`는 코드가 시행하고 셀(`test_relation_rejects_self_pair`)이 잠그나 SoT 라이브 조항엔 없다. 계획 Slice 1의 "같은 candidate id는 제외한다"와 상보하는 저장측 방어라 자연스럽지만, 계약 문장 하나로 명시 권장.
- **H3 — 변이 기록의 관측 주석 부정확.** 작업자 변이 표 I1'의 "unique 인덱스 위반"·테스트 주석 `test_identity_groups_mongo.py:293-294`("정규화가 없으면 여기서 유일성 위반이 난다")는 실측과 다르다(실제 재실패 = len 단언 `2 != 1`). 가드 자체는 유효(V1 실측)하나 다음 검증자가 같은 오독을 반복할 수 있어 주석 정정 권장.
- **H4 — "member는 참조만"(미존재 candidate 추가 허용)의 명시 셀 없음.** `test_member_round_trip`이 존재하지 않는 candidate id로 추가하며 암묵적으로만 잠긴다. 존재 검사를 추가하는 과잉 교정이 들어오면 실패할 기명 셀을 권장.

## Verdict

**조건부 합격** — B1(실몽고 datetime 경계 정규화 누락 + 실몽고 round-trip 충실도 미잠금)을 폐쇄해야 한다.

그 외 모든 표면에서 작업자 주장은 전부 독립 재현됐다: 전수 2696/1/3124·EXIT=0, +20셀 순수 증가 검산, OpenAPI/`schema.d.ts` 무변(바이트 실측), 변이 독립 7종 전부 기명 재실패(과잉 파기·revision·self-pair 방향 포함), 파기 그래프 10계약/22컬렉션·양 경로 스파이, 오너 결정·문서 의무 전부. B1은 green bar와 무관하게 "실몽고 round-trip" 계약 축의 빈 칸이며 실측 프로브로 값 수준 위반이 확인된 상태다.

## Outstanding items

- B1 폐쇄 전까지 Slice 1 착수 보류를 권장(Slice 1은 relation 재사용·판정 시각을 다루어 B1에 더 가까워진다).
- 트리 clean, 커밋 `183af60`·`ea29bb5` — push는 오너 몫(관례).
- 이 검증 기록 등재로 docs 가드 판정 열 subtest +1(기계적 증가 — 다음 전수 예상 3125).

## Reproduction

```bash
# 환경: test-mongo rs-test (127.0.0.1:27020) — 없으면
docker compose -f docker-compose.test.yml up -d

# focused 20셀
python3 -m pytest -q tests/test_identity_groups.py tests/test_identity_groups_mongo.py

# 카운트 검산 (baseline vs HEAD)
git worktree add /tmp/pre e3d782c && (cd /tmp/pre && python3 -m pytest --collect-only -q tests/ | tail -1)  # 2677
python3 -m pytest --collect-only -q tests/ | tail -1                                                       # 2697

# 전수 (~35분)
PYTHONPATH=. python3 -m pytest -q tests/    # 2696 passed, 1 skipped, 3124 subtests

# OpenAPI 무변
python3 scripts/dump_openapi.py > /tmp/a.json   # e3d782c worktree에서
python3 scripts/dump_openapi.py > /tmp/b.json   # ea29bb5 worktree에서
diff /tmp/a.json /tmp/b.json                    # identical

# B1 프로브 (실몽고에서 naive datetime 실측)
python3 - <<'EOF'
import uuid
from pymongo import MongoClient
from services.application.app.analysis.identity_groups import (
    CandidateIdentityGroupService)
from services.application.app.analysis.identity_groups_mongo import (
    MongoCandidateIdentityGroupRepository)
from services.application.app.analysis.models import AnalysisCandidateType
c = MongoClient("mongodb://localhost:27020/?replicaSet=rs-test",
                serverSelectionTimeoutMS=800)
db = f"probe_identity_{uuid.uuid4().hex}"
svc = CandidateIdentityGroupService(
    MongoCandidateIdentityGroupRepository(c, db_name=db))
g = svc.create_group("p1", AnalysisCandidateType.CHARACTER_OBSERVATION)
back = svc.get_group("p1", g.group_id)
print("tzinfo:", back.created_at.tzinfo)          # None (naive) — B1
print("equal:", back.created_at == g.created_at)  # False — B1
c.drop_database(db); c.close()
EOF

# 변이(예: V4 과잉 파기) — clean 게이트 후 적용·복원
git status --short                       # 0줄 확인
python3 - <<'EOF'
import pathlib
p = pathlib.Path("services/application/app/analysis/identity_groups.py")
s = p.read_text(encoding="utf-8")
old = """        self._groups = {
            gid: group
            for gid, group in self._groups.items()
            if group.project_id != project_id
        }
        self._members = {
            key: member
            for key, member in self._members.items()
            if member.project_id != project_id
        }
        self._relations = {
            key: relation
            for key, relation in self._relations.items()
            if relation.project_id != project_id
        }"""
assert s.count(old) == 1
p.write_text(s.replace(old, """        self._groups = {}
        self._members = {}
        self._relations = {}"""), encoding="utf-8")
EOF
python3 -m pytest -q tests/test_identity_groups.py | tail -1   # 1 failed
git checkout -- services/application/app/analysis/identity_groups.py
git status --short                       # 0줄 재확인
```
