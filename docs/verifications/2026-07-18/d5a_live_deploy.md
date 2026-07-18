# Verification Record — D5=A 재배포 + 라이브 closure (독립 검증)

## Subject metadata

- **날짜**: 2026-07-18
- **요청자**: 오너 ("다른 작업 AI가 작업했다는데 검증 다시 해줘. D5=A 재배포와 라이브 검증까지 완료했습니다...")
- **검증자**: 독립 검증 AI(본 세션). 작업 AI(재배포·라이브 실행 주체)와 별개.
- **대상**: D5=A snapshot-scoped analysis job(`analyze:{snapshot_id}`) 변경의 (a) application/frontend 재배포, (b) 같은 snapshot 재호출 → job 1·candidate 중복 0 라이브 closure. 코드는 이미 커밋 `965e34e`(독립 검증 합격)에 반영.
- **정본 계약 참조**: `docs/system-contract-sot.md:36`(v1.7.7 행), `docs/plans/05-writing-accept-decisions.md`(2026-07-18 D5=A amendment), `docs/verifications/2026-07-18/testbed_abc_slice.md`(v1.7.6 조건부 합격 → closure).
- **소스**: 작업 트리(미커밋 문서 2개 — `HANDOFF.md`, `docs/daily_logs/2026-07-18/work_log.md`) + 실행 중인 라이브 스택(9 컨테이너 + 12B llama). 코드 커밋 `965e34e`는 무변.

## Scope

1. **배포 사실**: application/frontend 컨테이너가 `965e34e` 코드(accept.py `analysis_job_key`)를 실제로 실행하는지.
2. **라이브 closure (독립 재도출)**: 작업 AI가 보고한 snapshot `6a5ae7f6...c` → job 1·candidate 2·중복 0이 Mongo 정본과 일치하는지.
3. **D5=A 일반성**: snapshot당 job이 1개로 수렴하는지, 구버전(랜덤 UUID) 대비 `analyze:{snap}` literal이 실제로 적용되는지.
4. **문서 갱신 정확성**: `HANDOFF.md:9`, `work_log.md:135` 신규 섹션의 사실관계.
5. **운영 false-negative**: frontend compose `unhealthy`가 healthcheck `localhost→::1` false-negative인지.

## Methodology

- 작업 AI 보고를 신뢰하지 않고 Mongo 정본·컨테이너 코드·HTTP에서 재도출.
- **컨테이너 코드 직조회**: `docker exec ai_writte_system-application-1 python3 -c "from ...accept import analysis_job_key; ..."`로 배포 이미지가 새 함수를 로드하는지 확인(`inspect.getsource`).
- **Mongo 정본 직조회**: `docker exec ai_writte_system-mongo-1 mongosh ai_writing_system`(DB명은 `ai_writing`이 아니라 `ai_writing_system`)으로 `analysis_jobs`/`analysis_candidates` 집계.
- **배포 상태**: `docker ps`(컨테이너 Up 시간) + `curl /health`.

## Findings

### 1. 배포 사실 — 확증 (PASS)

- `docker ps`: application/frontend 컨테이너 **Up 8 min**(나머지 7 컨테이너는 Up 3 hours) → 재배포 사실 확인.
- `curl http://localhost:8000/health` → `{"status":"ok"}`. `curl :5173/` → HTTP 200.
- 컨테이너 내 `analysis_job_key('SNAP_TEST')` → `analyze:SNAP_TEST` 반환, `inspect.getsource`가 `f"analyze:{snapshot_id}"` 본문 확인 → **배포 이미지가 `965e34e` 코드를 실행 중**.

### 2. 라이브 closure — 작업 AI 보고와 Mongo 정본 일치 (PASS)

작업 AI 보고 snapshot `6a5ae7f6b339f88750c0a92c` / job `6a5ae7f6b339f88750c0a92f`:

| 항목 | 작업 AI 보고 | Mongo 정본(독립) | 일치 |
|---|---|---|---|
| snapshot의 job 수 | 1 | 1 (`6a5ae7f6...92f`) | ✓ |
| job idempotency_key | (create/run replay) | `analyze:6a5ae7f6...92c` | ✓ D5=A literal |
| job status | succeeded | succeeded | ✓ |
| candidate 수 | 2 → 2 | 2 (`...931`, `...932`) | ✓ |
| candidate 중복 | 0 | ID 서로 다름, unique payload 2 | ✓ |

D5=A의 핵심인 "같은 snapshot 재클릭 → job 1·candidate 중복 0"이 라이브 + Mongo 정본 양쪽에서 확증.

### 3. D5=A 일반성 — 배포 후 literal 적용 확증, 구버전 4-job은 D5=A **이전** 데이터 (PASS, 맥락 주의)

- 독립 검증 시점의 `analyze:{snap}` prefix job은 **정확히 1개**(작업 AI 라이브 검증 job)였다. 이후 §6 accept-report closure와 병행 dogfood가 서로 다른 snapshot에 같은 literal job을 추가했으므로 전역 총수는 가변이다. 현재 전수 aggregation에서 `analyze:` job은 모두 snapshot별 count=1이며 invariant 위반 0. D5=A 배포 후에는 이 literal로만 job이 생성됨.
- **snapshot `6a5ac87ae...b3`에 job 4개** → 모두 **랜덤 UUID key**, 모두 `failed`. 이는 D5=A **배포 전** 구버전 AnalysisTrigger(매번 `crypto.randomUUID()`)로 같은 snapshot을 4번 시도한 흔적. 즉 D5=A가 해결한 "같은 snapshot 재클릭 시 job/candidate 적산" 문제의 **라이브 실증**(배포 전 데이터).
- `deployed-smoke-job-1` key 3개: 모두 **서로 다른 snapshot**이므로 D5=A 일관성(snapshot당 1 job) 위반 아님(별개 smoke 데이터).
- 독립 검증 시점 distinct snapshot 19 / 총 job 22 — 초과 3개는 상기 구버전 4-job snapshot에서 비롯. §6 후속 실행 뒤에는 새 snapshot/job이 각각 1개 늘지만 초과 수는 그대로다.

### 4. 문서 갱신 — 사실관계 정확, 1건 라이브 미실증 주의 (CONDITIONAL)

- `HANDOFF.md:9`, `work_log.md` "D5=A 재배포·라이브 closure" 섹션: 배포 이미지 해시·같은 snapshot 재호출 job 1·candidate 2→2/ID 불변·Mongo job 1/candidate 2·frontend healthcheck false-negative — 모두 독립 재도출로 정확.
- **주의(라이브 미실증)**: `HANDOFF.md:9`·`work_log.md:135`·`testbed_abc_slice.md` closure에 "**accept가 job에 실은 `writing_candidate_report`도 run에서 소비(효율성 #14 부수 해소)**"로 쓰인 부분은 **코드 추론(`runner.py:133` 소비)**이지 라이브 실증이 아니다. Mongo `analysis_jobs` 22개 중 `writing_candidate_report != null`인 job이 **0건** → 이 스택에서 **accept 경로가 단 한 번도 실행되지 않았다**(모든 job이 AnalysisTrigger/직접 create로 생성). 따라서 "accept report 소비"는 라이브에서 입증되지 않았다(코드로는 확증).

### 5. frontend unhealthy — false-negative 확증 (PASS, 비차단)

- `docker ps` frontend `Up 8 min (unhealthy)`이나 `curl :5173/` → 200. nginx healthcheck의 `http://localhost/`가 Alpine 컨테이너에서 `::1`로 해석돼 connection refused → compose status만 unhealthy인 false-negative. D5=A와 무관·기존 설정. 후속 운영 소수정(probe `127.0.0.1` 고정) 후보로 기록된 것과 일치.

### 6. Post-verification hardening closure — accept report 소비 라이브 확증 (PASS)

독립 검증 종료 후 오너가 hardening 보강과 커밋을 요청해, 작업 AI가 별도 프로젝트에서 브라우저 동등 `http://127.0.0.1:5173/api` 경로로 accept→trigger 재사용→run을 실 12B 위에서 관통했다. 독립 검증 시점의 `writing_candidate_report` 보유 job **0/22** 관찰은 당시 사실이며, 아래 후속 실행으로 마지막 미실증 축이 닫혔다.

- 프로젝트 `6a5aeb41b339f88750c0a942`, accept 저장 snapshot `6a5aeb6ab339f88750c0a947`, job `6a5aeb6ab339f88750c0a948`.
- accept Gate `pass` → snapshot 저장 + `pending` analysis job 생성. Mongo job의 key는 `analyze:6a5aeb6ab339f88750c0a947`, `writing_candidate_report != null`.
- report는 claim `민아는 탁자 위에서 은빛 열쇠를 발견했다.`(`narrative_event`)와 analyze-after-save event hint를 실제로 보유했다.
- 동일 snapshot의 AnalysisTrigger 동형 create는 **같은 job ID**를 반환하고 `idempotent_replay=true`; snapshot의 Mongo job 수는 **1**.
- 첫 run은 `idempotent_replay=false`로 pending job을 실제 소비해 succeeded, 두 번째 run은 `true`. 결과 candidate는 **1개**이고 payload `{"event":"민아는 탁자 위에서 은빛 열쇠를 발견했다."}`로 report claim과 일치했다. Mongo candidate 수도 **1**, ID 중복 0.

따라서 `accept.py`가 report를 job에 심는 축, deterministic trigger가 그 job을 재사용하는 축, `runner.py`가 report를 포함한 snapshot으로 extraction하는 축이 코드 추론을 넘어 라이브 결과와 Mongo 정본으로 확증됐다.

## Issues / Risks

### Blocking (계약 의무)

- 없음. D5=A 핵심(snapshot당 job 1·재클릭 중복 0)이 코드·컨테이너·Mongo 정본·라이브에서 일관 확증.

### Hardening recommendations (non-blocking)

- **accept report 소비 라이브 미실증 — 폐쇄됨**: 독립 검증 당시 `writing_candidate_report` 보유 job 0/22였으나, 오너 요청 후 위 §6 accept→save→동일 job trigger→run 라이브 관통으로 닫혔다.
- **구버전 4-job 데이터 잔존**: snapshot `6a5ac87ae...b3`의 failed job 4개가 D5=A 배포 전 데이터로 남음. D5=A 위반 아님(과거 데이터)이나, dogfood 시 잡음이 될 수 있어 정리 후보(snapshot 단위 삭제 또는 별도 smoke DB 분리).

## Verdict

**합격(Pass).** D5=A snapshot-scoped analysis job 변경이 application 컨테이너에 실제로 배포됐고(컨테이너 코드 직조회 확증), 같은 snapshot 재호출이 Mongo 정본에서 job 1·candidate 2·중복 0으로 수렴함을 독립 확증했다(작업 AI 보고와 정확히 일치). 구버전(randomUUID) 4-job 잔존는 D5=A 배포 전 데이터로 D5=A 위반이 아니며, 오히려 D5=A가 해결한 적산 문제의 라이브 실증이다.

독립 검증 시점에는 accept가 심은 `writing_candidate_report`의 run 소비가 코드로만 확증돼 있었으나, 오너 요청 후 §6 후속 라이브로 report 저장·동일 job 재사용·report와 일치하는 candidate 추출까지 확인했다. 최종 판정은 **합격(Pass), 해당 hardening 폐쇄**다.

## Outstanding items

- **라이브 accept report 소비**: §6 후속 보강으로 폐쇄.
- **스택 실행 중**: 오너 종료 미선택(2026-07-17/18 선례 유지).

## Reproduction

```bash
# 1) 배포 코드 확인(컨테이너가 새 analysis_job_key 실행)
docker exec ai_writte_system-application-1 python3 -c \
  "from services.application.app.writing.accept import analysis_job_key; \
   print(analysis_job_key('S')); import inspect; print(inspect.getsource(analysis_job_key))"
#   기대: analyze:S + f"analyze:{snapshot_id}"

# 2) Mongo 정본 직조회(DB명 ai_writing_system)
docker exec ai_writte_system-mongo-1 mongosh --quiet ai_writing_system --eval '
  const s="6a5ae7f6b339f88750c0a92c", j="6a5ae7f6b339f88750c0a92f";
  print("jobs for snap:", db.analysis_jobs.countDocuments({snapshot_id:s}));   // 1
  print("cands for job:", db.analysis_candidates.countDocuments({job_id:j}));  // 2
  print("report jobs:", db.analysis_jobs.countDocuments({writing_candidate_report:{$ne:null}})); // 0
'

# 3) health
curl -fsS http://localhost:8000/health        # {"status":"ok"}
curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:5173/   # 200

# 4) D5=A literal 적용 + snapshot당 1 job 확인
docker exec ai_writte_system-mongo-1 mongosh --quiet ai_writing_system --eval '
  const jobs=db.analysis_jobs.find({idempotency_key:/^analyze:/}).toArray();
  jobs.forEach(j=>print(j._id,j.snapshot_id,j.idempotency_key));
  const grouped=db.analysis_jobs.aggregate([
    {$match:{idempotency_key:/^analyze:/}},
    {$group:{_id:"$snapshot_id", count:{$sum:1}}},
    {$match:{count:{$ne:1}}}
  ]).toArray();
  print("snapshots violating one-job invariant:", grouped.length)'
#   기대: 전역 job 총수와 무관하게 snapshots violating one-job invariant: 0

# 5) 후속 accept-report closure 정본 재조회
docker exec ai_writte_system-mongo-1 mongosh --quiet ai_writing_system --eval '
  const s="6a5aeb6ab339f88750c0a947", j="6a5aeb6ab339f88750c0a948";
  const job=db.analysis_jobs.findOne({_id:j});
  print("jobs for accept snapshot:", db.analysis_jobs.countDocuments({snapshot_id:s})); // 1
  print("report present:", job.writing_candidate_report != null);                       // true
  printjson(job.writing_candidate_report);
  print("candidates:", db.analysis_candidates.countDocuments({job_id:j}));              // 1
'
```
