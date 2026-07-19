# W2 테스트 머신 운영 closure — 독립 재감사

## Subject metadata

- **날짜**: 2026-07-19
- **요청자**: 오너("작업 AI 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? W2 서브 머신 미완료 검증을 모두 닫았고, 최종 판정은 PASS(조건 없음)입니다.")
- **검증자**: 독립 재감사 AI(Claude, max effort)
- **검증 대상 slice/artifact**: `docs/verifications/2026-07-19/w2_operational_closure.md`가 PASS(조건 없음)로 닫은 W2 서브 머신 운영 축 전체(지원 Node frontend 재현, OpenAPI→TypeScript, Docker image, 실제 replica-set Mongo 동시성, nginx/API/browser, 정리)
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.13(Approved), `docs/plans/writing-workspace-v2-w0-contract.md` §1·§4(PB-01~12/SC-01~02), `schemas/writing-workspace-v2-w0.schema.json`
- **작업 출처**: `main`, commit `f5a0f3b`(`feat: Writing Workspace V2 W2 작품 정보와 개요 구현`), 감사 시작 시 working tree는 문서 3건(HANDOFF/work_log/w2_operational_closure)만 변경, app·frontend 코드는 HEAD와 동일.

## Scope

피감사 기록(`w2_operational_closure.md`)이 PASS 근거로 든 6개 표면을 각각 독립 재현/반박 시도했다.

1. 지원 Node 환경의 frontend install/test/build.
2. `schema.d.ts` byte-identical 주장(openapi.json 재생성 → openapi-typescript → committed 와 비교).
3. application/frontend Docker image build 상태.
4. single-node replica-set Mongo에서 `tests/test_core_sot_mongo.py` 전체 + 동시 PUT 회귀.
5. nginx/ProjectOverview 분리 지점 literal.
6. 격리 DB/일회성 컨테이너 정리 상태.

기존 정적 W2 계약 감사(`w2_project_brief_overview.md`)가 PB/SC 14행을 빈 cell 없이 닫은 것은 본 재감사에서 독립 재확인(아래 Findings §3)했고 중복 전수 조사하지 않는다.

## Methodology

피감사자의 work_log/HANDOFF/검증 기록 주장을 그대로 수용하지 않고, 각 주장을 동일 명령으로 재실행해 재도출하거나 일차 소스에서 반박했다. 명령은 모두 재현 가능하게 아래와 본문에 남긴다.

- 정본 읽기: `writing-workspace-v2-w0-contract.md`(전문), `system-contract-sot.md`(헤드 + changelog v1.7.13 행), `frontend/nginx.conf`, `services/frontend/Dockerfile`, `frontend/src/projects/ProjectOverview.tsx`, `tests/test_core_sot_mongo.py`, `frontend/package-lock.json`, `docker-compose.yml`.
- frontend 재현: 작업 AI가 남긴 `ai_writte_system-frontend-w2-verify`(node:22-slim) 이미지에 현재 source를 마운트해 동일 명령 실행.
- OpenAPI 재현: `python3 scripts/dump_openapi.py`(호스트, in-memory)로 fresh `openapi.json` 생성 후 동일 이미지의 `openapi-typescript`로 `schema.d.ts` 재생성, committed와 sha256/cmp/diff.
- 환경 의존성 확인: `ai_writte_system-application` 이미지의 python(fastapi 0.139.0/pydantic 2.13.4)로도 `dump_openapi.py`를 돌려, host(fastapi 0.115.14/pydantic 2.11.7)와 비교.
- Mongo 재현: `--rm` 일회성 `mongo:7` single-node replica-set을 27017에 기동해 `rs.initiate` 후 `CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27017/?directConnection=true'`로 전체 33개 실행.
- git 이력: `git show 674ff39:...schema.d.ts` vs `git show f5a0f3b:...schema.d.ts`로 `-Input/-Output` 분리 도입 시점 확인.

## Findings

### 1. 환경·재현 산출물 — 대부분 주장과 일치

- 호스트 Node **v22.17.0**(react-router@8.2.0 `engines.node >=22.22.0` 미달), Compose **v2.40.2**, mongo 정지 상태(Exited 0). 피감사자 기술과 일치.
- `frontend/package-lock.json`: react-router 8.2.0, openapi-typescript 7.13.0. `scripts.gen:api` = `python3 ../scripts/dump_openapi.py > openapi.json && openapi-typescript openapi.json -o src/api/schema.d.ts`. 피감사자가 사용한 툴체인과 동일.
- `frontend/openapi.json`은 `git check-ignore`로 ignored 확인. `schema.d.ts`는 tracked. working tree의 `schema.d.ts` == committed(sha `21813103…`, 106941 bytes).
- **frontend test/build 재현**(node:22-slim v22.23.1/npm 10.9.8, 현재 source 마운트): Vitest **143 passed (143) / 10 files**(49.94s), `npm run build`(`tsc --noEmit && vite build`) **96 modules**, CSS 17.54 kB(gzip 3.94)/JS 284.19 kB(gzip 87.85). 피감사자 수치와 **정확 일치**.
- **Mongo 33 재현**: 일회성 replica-set에서 `tests/test_core_sot_mongo.py` **33 passed in 10.56s, 0 skipped**. `FallbackMongoTest`(use_transactions=False)·`TransactionMongoTest`(use_transactions=True)가 같은 `_MongoContractMixin`을 공유하므로 동시 PUT 회귀(`test_concurrent_project_brief_version_collision_has_one_success_one_stale`, `tests/test_core_sot_mongo.py:160-204`)가 양쪽에서 실행됐고 boundary assertion(success==1, stale==1, `idempotent_replay is False`, 저장 version 1개)이 그대로 통과. **피감사자의 “샌드박스 최초 33 skip 무효화 후 33 pass 근거 채택”은 합리적 무효화**로 확인.

### 2. OpenAPI→TypeScript “byte-identical” 주장 — **재현 불가 (핵심 반박)**

피감사자의 가장 강한 주장("현재 app OpenAPI를 입력으로 생성한 `schema.d.ts`는 커밋본과 byte-identical했다")을 동일 명령으로 재현한 결과 **불일치**.

```
fresh openapi.json(호스트 python, sha 7320d089, == 피감사자가 남긴 frontend/openapi.json)
  → openapi-typescript 7.13.0 → schema.d.ts
생성물:  106805 bytes  sha 892e7bc61e94ab7174ec4867535e1d0d03ffefd0b5d3ec469b4e80b0943e11e3
committed: 106941 bytes  sha 21813103e93b4b97b10feff0842c2e82abc4401e093002463ff3e420185793fd
VERDICT: DIFFERS  (diff 181 라인, 136 bytes)
```

재현성 교차 검증: openapi-typescript를 두 번 실행 → 동일 sha(`892e7bc6…`). 생성 자체는 deterministic이므로, 차이는 입력(openapi.json)이나 툴이 아니라 **committed 파일 자체가 현재 app의 OpenAPI에서 생성될 수 없는 내용**임을 의미.

diff의 실체:

- committed는 `WritingCandidatePayload-Input`/`-Output`, `WritingGatePayload-Input`/`-Output` 처럼 **같은 모델을 request/response로 분리한 스키마 키**를 가진다.
- 현재 app(호스트·배포 이미지 모두)의 openapi.json은 단일 `WritingCandidatePayload`/`WritingGatePayload`만 낸다(`-Input`/`-Output` 키 0개).
- committed `schema.d.ts:1251`/`:1486-1501`가 `WritingGatePayload-Output`·`WritingCandidatePayload-Input` 등을 참조.

도입 시점(git 이력):

- `git show 674ff39:frontend/src/api/schema.d.ts` → `-Input`/`-Output` **0건**(W2 커밋 전에는 없음).
- `git show f5a0f3b:frontend/src/api/schema.d.ts` → `-Input`/`-Output` **4건**(W2 커밋이 schema.d.ts에 413라인 변경을 가하며 분리 도입).

환경 의존성 확인(“피감사자 시점의 호스트 패키지가 달라 분리가 났다”는 변명 배제):

- `ai_writte_system-application` 이미지 python(fastapi 0.139.0/pydantic 2.13.4)으로 `dump_openapi.py` 재실행 → openapi sha `fe72e325…`(호스트 `7320d089…`와 상이), **그러나 `-Input`/`-Output` 역시 0건**. 즉 현재 app 코드(f5a0f3b)는 어떤 현존 환경(개발 fastapi 0.115.14, 배포 fastapi 0.139.0)에서도 분리를 생성하지 않는다.
- 결론: committed `schema.d.ts`의 분리는 **현재 어떤 환경에서도 재현 불가한 stale**이다. 피감사자의 “최초 stale probe 무효화 후 fresh-input 비교” 설명은 openapi.json 자체가 deterministic(sha `7320d089…` 재생성 동일)이라는 사실과 충돌하지 않지만, **동일 fresh 입력으로부터의 byte-identical 결론은 성립하지 않는다**.

파급(frontend 빌드 무결성):

- `frontend/src/api/client.ts:67` `export type WritingCandidate = components["schemas"]["WritingCandidatePayload-Output"];`
- `frontend/src/api/client.ts:69` `export type WritingGate = components["schemas"]["WritingGatePayload-Output"];`
- 위 두 키는 현재 gen:api 출력에 **존재하지 않는다**. 따라서 `schema.d.ts`를 `gen:api`로 재생성(회귀 수행)하면 `client.ts`의 타입 참조가 끊어져 `tsc --noEmit`이 실패한다. 즉 현재 커밋은 **gen:api 재현성이 깨진 상태**이며, SC-01/02가 전제하는 “schema integration 회귀가 재현 가능하다”는 정신을 위반한다. (현재 committed 파일 기준 build는 통과하지만, 그것은 app과 불일치하는 stale 타입을 우연히 쓰고 있어서다.)

### 3. W2 PB 계약 자체는 무결(ProjectBrief 한정)

byte-identical 위반과 별개로, **W2가 소유하는 ProjectBrief 경계 자체는 gen:api와 committed가 일치**한다.

- `schema.d.ts`에서 `projectbrief|putprojectbrief` 행만 추려 gen vs committed를 비교 → **18행 양측 동일, DIFF 없음**. `ProjectBriefVersionPayload`/`ProjectBriefGetResponse`/`ProjectBriefPutResponse`/`ProjectBriefVersionListResponse`/`PutProjectBriefRequest` 모두 동형.
- W0 §4 matrix PB-01~12·SC-01/02의 ProjectBrief 부분은 정적 감사(`w2_project_brief_overview.md`)가 이미 빈 cell 없이 닫았고, 본 재감사에서도 ProjectBrief 모델 동형·replay 선행·archived write 차단·all-null clear history 보존이 코드(`service.py`/`main.py`/`mongo_repository.py`)와 계약 literal 그대로 확인됨.
- 즉 schema.d.ts drift는 ProjectBrief가 아닌 **기존 WritingCandidate/Gate 표현**에 국한되며, 이들 -Input/-Output 분리는 C0/C1 슬라이스에서 정의된 모델로 W2 PB 계약 범위 밖이다.

### 4. nginx·overview 분리 지점 — literal 일치

- `frontend/nginx.conf:12-18` `/api/` → `proxy_pass http://application:8000/;`(trailing slash로 prefix strip). `:27-30` SPA fallback `try_files $uri $uri/ /index.html;`. 피감사자 인용과 정확 일치.
- `services/frontend/Dockerfile:5-21` `node:22-slim` build stage에서 `npm ci`/`npm run build` 수행. 일치.
- `frontend/src/projects/ProjectOverview.tsx:96` `setMemory(memoryResponse.memory.filter((item) => item.status === "canonical"))`(canonical-only), `:97` `setPending(inbox.items.length + inbox.gate_findings.length)`(pending 별도 집계), `:221` `<Link …>검토 전 {pending}개 →</Link>`. canonical grid에 pending 이름/본문이 노출되지 않는 분리 구조가 코드 그대로 확인. 피감사자 Chrome DOM 주장(`required_missing=[]`, `pending_body_leaked=[]`)의 코드 근거가 유효.

### 5. 정리 상태 — 컨테이너는 정리, 이미지는 잔존

- 피감사자가 남긴 일회성 컨테이너 `w2-application`/`w2-frontend`는 `docker ps -a`에 없음(정리 확인). `ai_writte_system-mongo-1`은 Exited(0)(이전 정지 상태 복귀). 격리 DB `ai_writing_system_w2_verify`는 별도 Mongo 기동 없이는 잔존 여부를 직접 확인할 수 없으나, throwaway DB는 컨테이너 제거와 함께 소멸한다.
- 단, `ai_writte_system-frontend-w2-verify` **이미지**(377MB)가 잔존. 피감사자는 “일회성 컨테이너” 정지만 언급했으므로 말씀대로라면 누락은 아니나, hardening 관점에서 검증용 이미지까지 정리 대상으로 명시하는 편이 더 깔끔하다.
- 본 재감사가 기동한 일회성 `w2-audit-mongo` 컨테이너(`--rm`)와 임시 `_gen_schema.d.ts`는 정리 완료. 27017 free. working tree는 피감사자의 기존 문서 3건 외에 본 재감사의 변경 0건.

## Issues / Risks

### Blocking(계약 의무 / 검증 무결성)

- **B1 — 운영 closure 기록의 “byte-identical, 재현 가능” 판정 근거가 허위**. 동일 툴체인(openapi.json 재생성 → openapi-typescript 7.13.0, 피감사자가 명시한 명령 그대로)으로 재현한 결과 committed `schema.d.ts`(106941 bytes, sha `21813103…`)와 생성물(106805 bytes, sha `892e7bc6…`)이 181라인/136바이트 상이. 호스트 fastapi 0.115.14·배포 fastapi 0.139.0 **어느 환경에서도** committed를 재현하지 못한다. 피감사자의 “PASS(조건 없음)” load-bearing reason #1(“지원 Node에서 install/test/type generation/build를 재현했다”) 중 type-generation 재현 부분이 사실이 아니다.
- **B2 — `schema.d.ts`가 app과 불일치하여 gen:api 재현성이 깨져 있다**. `frontend/src/api/client.ts:67,69`가 `WritingCandidatePayload-Output`/`WritingGatePayload-Output`을 참조하는데, 이 키는 현재 app의 OpenAPI(단일 모델)에 존재하지 않는다. `gen:api`를 회귀로 수행하면 `tsc --noEmit`이 실패한다. W2(f5a0f3b)가 schema.d.ts에 분리를 도입한 뒤 app 코드(또는 fastapi 버전)와 동기화하지 않은 채 커밋한 것으로 보인다. 이는 W0 §범위 “W2/W3는 … schema integration 회귀로 잠근다”와 SC-01/02의 재현 전제에 어긋난다.
  - 단, ProjectBrief 영역은 gen==committed(§3)이므로 W2 PB/SC **계약 자체**가 위반된 것은 아니다. B1·B2는 “운영 closure의 검증 주장 정확성”과 “전체 schema 동기화”에 관한 blocking이다.

### Hardening recommendations(비차단)

- **H1 — `frontend-w2-verify` 이미지 잔존**. 일회성 컨테이너는 정리됐으나 검증용 빌드 이미지(377MB)가 남아 있다. 검증 종료 시 이미지까지 `docker rmi`로 정리하면 머신이 더 깔끔하다.
- **H2 — OpenAPI 표현의 환경 의존성 관찰(별개)**. 같은 app 코드(f5a0f3b)에서 호스트(fastapi 0.115.14)와 배포 이미지(fastapi 0.139.0)가 각각 다른 openapi.json sha를 낸다(`7320d089…` vs `fe72e325…`). 둘 다 `-Input/-Output`은 없으므로 B1/B2의 원인은 아니지만, “OpenAPI 스키마가 fastapi 버전에 의존해 reproducible하지 않다”는 별개의 운영 관찰로 기록해 둘 만하다. 향후 gen:api를 CI 컨테이너(application 이미지 python 등 고정 환경)에서 돌리면 재현성이 확보된다.

## Verdict

**조건부 합격(conditional pass).**

- **W2 slice의 PB/SC 계약 자체는 합격**: ProjectBrief 모델이 gen==committed로 동형이고(§3), PB-01~12·SC-01/02가 named 회귀에 빈 cell 없이 매핑됐음이 정적 감사와 본 재감사 모두에서 확인됐다. Mongo 동시성 33 pass(§1)와 nginx/overview 분리(§4)도 독립 재현됐다. 이 축에서 W2는 닫혀 있다.
- **그러나 운영 closure 기록의 판정 근거는 정정 대상**: “schema.d.ts byte-identical, 재현 가능”이 허위(B1)이며, `schema.d.ts`가 현재 app과 불일치해 gen:api 회귀 수행 시 build가 깨진다(B2). 따라서 “PASS(조건 없음)”라는 판정문은 그대로 둘 수 없다.

**합격 조건(이 두 가지가 닫히기 전까지 W3로 넘어가면 안 된다):**

1. 운영 closure 기록(`w2_operational_closure.md`)·work_log·HANDOFF에서 “byte-identical / 재현 가능” 표현을 정정. 실제로는 ProjectBrief 영역만 일치하고 전체 `schema.d.ts`는 app과 불일치함을 명시.
2. `schema.d.ts`를 현재 app에서 `gen:api`로 재생성해 app과 일치시키고, `client.ts:67,69`의 `-Output` 참조를 단일 키로 고쳐 **gen:api 회귀가 build를 깨뜨리지 않도록 복원**. 또는 반대로 app 코드(Pydantic 모델/엔드포인트)가 원래 분리를 내도록 정렬. 어느 쪽이든 gen:api를 다시 돌려 `tsc --noEmit && vite build`와 143 test가 green인지 확인해야 한다. **W3는 새 모델을 추가할 때 gen:api를 돌릴 것이므로, 이 drift를 W3 착수 전에 닫지 않으면 W3 작업이 즉시 build break에 부딪는다.**

## Outstanding items

- 본 재감사는 독립 감사 범위이므로 B1/B2를 **임의로 수정하지 않았다**. working tree는 피감사자의 문서 3건 외에 변경이 없다.
- 오너 결정이 필요한 갈래: (a) app 코드를 `schema.d.ts`에 맞추는지, (b) `schema.d.ts`+`client.ts`를 현재 app(단일 모델)에 맞추는지. 둘 중 어느 쪽이 “W2 시점의 의도된 계약”인지가 정해지면 정렬 방향이 확정된다.
- W3(ordered unit/explicit Writing intent) 착수는 위 합격 조건 2건을 닫은 뒤. 그 전에 gen:api를 돌리면 drift가 드러나 build가 깨진다.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# 1. frontend test/build 재현 (node:22-slim)
docker run --rm -v "$PWD":/repo -w /repo/frontend ai_writte_system-frontend-w2-verify \
  sh -lc 'PATH=/app/node_modules/.bin:$PATH; npm test -- --run; npm run build'
# 기대: 143 passed / 10 files, 96 modules, CSS 17.54/JS 284.19

# 2. byte-identical 재현 시도 (B1 반박)
python3 scripts/dump_openapi.py > frontend/openapi.json      # sha 7320d089… (deterministic)
docker run --rm -v "$PWD":/repo -w /repo/frontend ai_writte_system-frontend-w2-verify \
  sh -lc 'PATH=/app/node_modules/.bin:$PATH; openapi-typescript openapi.json -o /tmp/g.d.ts; cmp -s /tmp/g.d.ts src/api/schema.d.ts && echo IDENTICAL || echo DIFFERS'
# 기대: DIFFERS (generated 106805 / committed 106941)

# 3. 환경 무관하게 분리가 재현되지 않음 확인
docker run --rm -v "$PWD":/repo -w /repo --entrypoint python3 ai_writte_system-application \
  scripts/dump_openapi.py > /tmp/openapi_app.json
python3 -c "import json;s=json.load(open('/tmp/openapi_app.json'));print([k for k in s['components']['schemas'] if k.endswith(('-Input','-Output'))])"
# 기대: [] (배포 이미지 python에서도 분리 없음)

# 4. Mongo 33 재현
docker run -d --rm --name w2-audit-mongo -p 27017:27017 mongo:7 --replSet rs0 --bind_ip_all
# rs.initiate 후 PRIMARY 대기
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27017/?directConnection=true' \
  python3 -m pytest tests/test_core_sot_mongo.py -q -p no:cacheprovider
# 기대: 33 passed; 종료 후 docker stop w2-audit-mongo

# 5. ProjectBrief 영역만 일치 확인 (W2 PB 계약 무결)
docker run --rm -v "$PWD":/repo -w /repo/frontend ai_writte_system-frontend-w2-verify \
  sh -lc 'PATH=/app/node_modules/.bin:$PATH; openapi-typescript openapi.json -o /tmp/g.d.ts 2>/dev/null; diff <(grep -iE "projectbrief|putprojectbrief" /tmp/g.d.ts) <(grep -iE "projectbrief|putprojectbrief" src/api/schema.d.ts) && echo PB_IDENTICAL'
# 기대: PB_IDENTICAL (ProjectBrief 18행 동일)
```
