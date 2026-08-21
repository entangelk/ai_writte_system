#!/usr/bin/env bash
# 독립 검증 재현 — 리랭커 슬라이스(7a88ac1·f14917b) + 임베딩 조건 B1 폐쇄(a9bca6d) 재검.
# (docs/verifications/2026-08-20/reranker_slice.md §Reproduction)
#
# 전제: 트리 clean & 커밋됨. verification.md "clean-tree" 브랜치 — 복원은 git checkout --.
# ★ 전수가 돌고 있는 동안은 실행 금지(파일을 뮤테이션한다).
#
# ★ RV-A(text_of 예외)는 이 검증의 조건 C1의 실증이다 — 폐쇄 커밋이 들어오면
# 마지막 줄이 "[ValueError] … 새어나감" → "원래 순서 반환"으로 뒤집혀야 한다.
# ★ RV-B1/B2(조립 가드 우회)는 비차단 H1 — 폐쇄되면 18 passed → 셋째 셀 실패로 뒤집힌다.
#
# 실행: bash docs/verifications/2026-08-20/repro_reranker_slice.sh
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
  python3 -m pytest -q "$TR" 2>&1 | grep -E "FAILED|SUBFAILED|failed|passed" | tail -3
  git checkout -- "$f"; chk; echo "  [restored — tree clean]"
}

echo "═══ Part 0. 기준 ═══"
python3 -m pytest -q tests/test_rerank.py tests/test_eval_retrieval_ranking.py 2>&1 | tail -1  # 28 passed / 26 subtests

echo; echo "═══ Part 1. 조건 C1 실증 — text_of 예외는 검색을 죽인다(런타임) ═══"
PYTHONPATH=. python3 - <<'EOF'
from services.application.app.context_search.rerank import (
    RerankingRetriever, RerankProviderError,
)

class Inner:
    def retrieve(self, *, project_id, query, limit):
        return ({"id": 1}, {"id": 2}, {"id": 3})

class OkProvider:
    def rerank(self, *, query, documents):
        return (2, 0, 1)

def text_of_raises(item):
    raise ValueError(f"payload shape drift: {item}")

r = RerankingRetriever(inner=Inner(), provider=OkProvider(), text_of=text_of_raises)
try:
    r.retrieve(project_id="p", query="q", limit=8)
    print("결과: 정상 반환(fail-open 작동)")
except RerankProviderError as e:
    print(f"결과: RerankProviderError 로 fail-open 캐치 — {e}")
except Exception as e:
    print(f"★ 결과: [{type(e).__name__}] 이(가) 그대로 새어나감 — 검색 경로가 죽는다: {e}")
EOF

echo; echo "═══ Part 2. 조립 가드 우회(H1) — 셋째 셀(유일 생성자)의 맹점 ═══"
echo "── RV-B1: 모듈 속성 경로 _rr.RerankingRetriever(…) → 폐쇄(92b9b24) 후 셋째 셀 실패"
mutfile "$M" 'def _rerank_wrapped(inner, *, text_of):' 'def _bypass_assembly():
    import services.application.app.context_search.rerank as _rr
    return _rr.RerankingRetriever(inner=None, provider=None, text_of=str)


def _rerank_wrapped(inner, *, text_of):'
echo "── RV-B2: 별칭 import RR(…) — B1 과 같은 형태 → 폐쇄(92b9b24) 후 같은 셀 실패"
mutfile "$M" 'def _rerank_wrapped(inner, *, text_of):' 'def _bypass_assembly():
    from services.application.app.context_search.rerank import RerankingRetriever as RR
    return RR(inner=None, provider=None, text_of=str)


def _rerank_wrapped(inner, *, text_of):'

echo; echo "═══ Part 3. 구현자 뮤테이션 R1~R7 같은 diff 로 재유도 ═══"
echo "── R1: 정본 조립 감싸기 누락"
mutfile "$M" '    return _rerank_wrapped(
        inner,
        text_of=lambda memory_entry: derive_memory_index_text(
            memory_entry.memory_type, memory_entry.payload
        ),
    )' '    return inner'
echo "── R2: candidate 조립 감싸기 누락"
mutfile "$M" '    return _rerank_wrapped(inner, text_of=candidate_index_text)' '    return inner'
echo "── R3b: fail-open → fail-closed (92b9b24 가 경계 줄을 바꿔 새 리터럴로 갱신 — 차기 검증자가 이행)"
mutfile "$R" '        except Exception:  # noqa: BLE001 — 결정 4-① 의 fail-open 경계' '        except Exception:
            raise'
echo "── R4: 순열 검사 제거"
mutfile "$R" '        if not _is_permutation(order, len(items)):' '        if False:'
echo "── R5: 0·1개도 provider 호출"
mutfile "$R" '        if len(items) < _MINIMUM_TO_REORDER:' '        if False:'
echo "── R6b: 동률에서 인덱스 역순(★들여쓰기 4칸 — 8칸으로 쓰면 count=0 으로 잡힌다)"
mutfile "$R" '    ranked.sort(key=lambda pair: pair[0], reverse=True)' '    ranked.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)'
echo "── R7: bool 인덱스 거부 제거"
mutfile "$R" '        if isinstance(index, bool) or not isinstance(index, int):' '        if not isinstance(index, int):'

echo; echo "═══ Part 4. 하네스 경계셀 — 저장소에 .jsonl 가 들어오면 실패 ═══"
chk; touch docs/daily_logs/2026-08-20/fake_eval_probe.jsonl
python3 -m pytest -q tests/test_eval_retrieval_ranking.py 2>&1 | grep -E "FAILED|failed|passed" | tail -2
rm docs/daily_logs/2026-08-20/fake_eval_probe.jsonl; chk; echo "  [restored — tree clean]"

echo; echo "═══ 완료 ═══"
