#!/usr/bin/env bash
# 독립 검증 재현 — 29299e5(제품명 H2·스윕 가드) + cfcb182(비차단 3건 보강).
# (docs/verifications/2026-08-21/product_name_and_hardening.md §Reproduction)
#
# 전제: 트리 clean & 커밋됨. verification.md "clean-tree" 분기 — 복원은 git checkout --.
# ★ 전수가 돌고 있는 동안은 실행 금지(파일을 뮤테이션한다).
#
# Part 1 M1~M5: 구현 세션과 같은 diff (work_log 2026-08-21 §Verification 표).
# Part 2 M6~M8: 검증자 자체 축 — compose 파일 스캔 여부(M6) · 변형 표기 맹점 실증(M7,
#   침묵이 예상·문언화된 의도) · 서비스 구분자 미잠금 실증(M8, 침묵이 예상).
# Part 3 N1~N4·R6b: 보강 세션과 같은 diff (같은 표) — R6b 는 페어링 1→2 확인.
#
# 실행: bash docs/verifications/2026-08-21/repro_product_name_and_hardening.sh
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1

AM=services/application/app/main.py
EM=services/embedding/app/main.py
GM=services/llm_gateway/app/main.py
MR=services/application/app/core_sot/mongo_repository.py
RR=services/application/app/context_search/rerank.py
IW=scripts/index_sync_worker.py
TC=docker-compose.test.yml

chk() { [ -z "$(git status --short)" ] || { echo "PRE-FLIGHT FAIL(tree dirty)"; exit 1; }; }
mutfile() {  # mutfile <파일> <기존 리터럴> <뮤테이션 리터럴> <포커스 대상>
  local f="$1" old="$2" new="$3" target="$4"
  chk
  python3 - "$f" "$old" "$new" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
assert s.count(sys.argv[2]) == 1, f"literal count={s.count(sys.argv[2])}"
p.write_text(s.replace(sys.argv[2], sys.argv[3]), encoding="utf-8")
PY
  python3 -m pytest -q "$target" 2>&1 | grep -E "FAILED|SUBFAILED|failed|passed" | tail -4
  git checkout -- "$f"; chk; echo "  [restored — tree clean]"
}

echo "═══ Part 0. 기준 ═══"
python3 -m pytest -q tests/test_product_name.py 2>&1 | tail -1   # 3 passed / 3 subtests
python3 -m pytest -q tests/test_rerank.py 2>&1 | tail -1         # 23 passed / 26 subtests

echo; echo "═══ Part 1. 구현자 뮤테이션 M1~M5 같은 diff 재유도 (29299e5) ═══"
echo "── M1: application title 을 옛 이름으로"
mutfile "$AM" '에-라잇 Application' 'AI Writing System Application' tests/test_product_name.py
echo "── M2: embedding title 을 옛 이름으로"
mutfile "$EM" '에-라잇 Embedding Service' 'AI Writing System Embedding Service' tests/test_product_name.py
echo "── M3: gateway title 을 옛 이름으로"
mutfile "$GM" '에-라잇 LLM Gateway' 'AI Writing System LLM Gateway' tests/test_product_name.py
echo "── M4: 무관한 .py 에 옛 이름 주입(scripts/index_sync_worker.py:1)"
mutfile "$IW" '"""Run one Phase 3B index sync worker pass."""' '# AI Writing System
"""Run one Phase 3B index sync worker pass."""' tests/test_product_name.py
echo "── M5 (over-strict): 식별자까지 개명"
mutfile "$MR" 'DEFAULT_DB_NAME = "ai_writing_system"' 'DEFAULT_DB_NAME = "e_right"' tests/test_product_name.py

echo; echo "═══ Part 2. 검증자 자체 축 M6~M8 ═══"
echo "── M6: compose 파일에 옛 이름 주입(docker-compose* 도 스캔 대상인가)"
mutfile "$TC" '# Test-only MongoDB — a single-node replica set on a dedicated port.' '# AI Writing System — test-only MongoDB' tests/test_product_name.py
echo "── M7: 변형 표기(대소문자) 주입 — 침묵이 예상(정확 일치가 문언화된 의도)"
mutfile "$IW" '"""Run one Phase 3B index sync worker pass."""' '# AI writing System
"""Run one Phase 3B index sync worker pass."""' tests/test_product_name.py
echo "── M8: 서비스 구분자 미잠금(title='에-라잇 App') — 침묵이 예상(정확 글자 미단정)"
mutfile "$AM" '에-라잇 Application' '에-라잇 App' tests/test_product_name.py

echo; echo "═══ Part 3. 보강 뮤테이션 N1~N4·R6b 같은 diff 재유도 (cfcb182) ═══"
echo "── N1: 동률을 오름차순 인덱스로 tie-break — 종전 셀이 원리적으로 못 보는 계열"
mutfile "$RR" 'ranked.sort(key=lambda pair: pair[0], reverse=True)' 'ranked.sort(key=lambda p: (-p[0], p[1]))' tests/test_rerank.py
echo "── N2: 동률을 내림차순 인덱스로(변형)"
mutfile "$RR" 'ranked.sort(key=lambda pair: pair[0], reverse=True)' 'ranked.sort(key=lambda p: (p[0], -p[1]), reverse=True)' tests/test_rerank.py
echo "── N3: 순열 검사를 return items 로(경계 밖 배치와 반환값 동형) — 기존 5 subtest 는 green 이어야 한다"
mutfile "$RR" 'raise RerankProviderError(
                    f"rerank order is not a permutation of {len(items)} documents"
                )' 'return items' tests/test_rerank.py
echo "── N4: exc_info 제거(원인이 로그에 안 남는다)"
mutfile "$RR" 'exc_info=True' 'exc_info=False' tests/test_rerank.py
echo "── R6b: 동률 인덱스 역순(원본 리터럴) — 페어링이 1 → 2 로 바뀌는지"
mutfile "$RR" 'ranked.sort(key=lambda pair: pair[0], reverse=True)' 'ranked.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)' tests/test_rerank.py

echo; echo "═══ 완료 ═══"
