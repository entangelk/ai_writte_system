#!/usr/bin/env bash
# 독립 검증 재현 — 폐쇄 커밋 92b9b24 (조건 C1 + H1·H2) 자체의 검증.
# (docs/verifications/2026-08-21/reranker_c1_h1_h2_closure.md §Reproduction)
#
# 전제: 트리 clean & 커밋됨. verification.md "clean-tree" 브랜치 — 복원은 git checkout --.
# ★ 전수가 돌고 있는 동안은 실행 금지(파일을 뮤테이션한다).
#
# 폐쇄 세션이 자체 재검 표로 주장한 C1-M1~M3 을 검증자가 같은 diff 로 재유도하고,
# H1 잔여(할당 별칭 — 문언에 명시된 안 잡는 형태)가 문언 그대로 침묵하는지 확인한다.
# RV-B1/B2 와 R1~R7 은 2026-08-20 스크립트(repro_reranker_slice.sh)가 이미 덮는다 —
# 단 그 스크립트의 R3b 블록 리터럴은 92b9b24 로 낡았다(아래 C1-M1 이 새 형태다).
#
# 실행: bash docs/verifications/2026-08-21/repro_reranker_c1_closure.sh
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1

R=services/application/app/context_search/rerank.py
M=services/application/app/main.py
TR=tests/test_rerank.py

chk() { [ -z "$(git status --short)" ] || { echo "PRE-FLIGHT FAIL(tree dirty)"; exit 1; }; }
mutfile() {  # mutfile <파일> <기존 리터럴> <뮤테이션 리터럴>
  local f="$1" old="$2" new="$3"
  chk
  python3 - "$f" "$old" "$new" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
assert s.count(sys.argv[2]) == 1, f"literal count={s.count(sys.argv[2])}"
p.write_text(s.replace(sys.argv[2], sys.argv[3]), encoding="utf-8")
PY
  python3 -m pytest -q "$TR" 2>&1 | grep -E "FAILED|SUBFAILED|failed|passed" | tail -5
  git checkout -- "$f"; chk; echo "  [restored — tree clean]"
}

echo "═══ Part 0. 기준 ═══"
python3 -m pytest -q tests/test_rerank.py 2>&1 | tail -1

echo; echo "═══ C1-M1: 조건 재도입 — 경계를 다시 RerankProviderError 로 ═══"
mutfile "$R" '        except Exception:  # noqa: BLE001 — 결정 4-① 의 fail-open 경계' '        except RerankProviderError:'

echo; echo "═══ C1-M2: 경고 로그 제거(조용한 fail-open) ═══"
mutfile "$R" '            _log.warning("reranking failed; falling back to fusion order",
                         exc_info=True)
            return items' '            return items'

echo; echo "═══ C1-M3: 정상 경로에서도 경고(로그 소음 방향) ═══"
mutfile "$R" '        return reordered' '        _log.warning("reranking failed; falling back to fusion order")
        return reordered'

echo; echo "═══ H1 잔여 확인: 할당 별칭(X = RerankingRetriever; X(…))은 문언대로 침묵 ═══"
mutfile "$M" 'def _rerank_wrapped(inner, *, text_of):' 'def _bypass_assembly():
    from services.application.app.context_search.rerank import RerankingRetriever
    X = RerankingRetriever
    return X(inner=None, provider=None, text_of=str)


def _rerank_wrapped(inner, *, text_of):'

echo; echo "═══ 완료 ═══"
