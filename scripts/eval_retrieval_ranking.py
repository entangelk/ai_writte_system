"""검색 순위 평가 하네스 — 리랭커 슬라이스 결정 4-② (틀만, 정답은 안 채운다).

**이 도구가 재는 질문 하나**: *"검색 순위가 정답을 얼마나 앞에 두는가."*

**★ 리랭커 전용이 아니다.** 같은 질문이 **임베딩 모델 교체 · RRF `k` 조정 · top-k
변경**에도 똑같이 유효하므로, 입력을 *"리랭킹 전/후"* 가 아니라 **"두 검색 구성의
순위 비교"** 로 잡았다(브리프 §후속 고려가 열어 두라고 한 문). 일반화 코드를 미리
쓰지는 않는다 — **포맷만 중립**이다.

**★ 이 파일은 정답(gold)을 만들지 않는다.** 브리프 결정 4-② 의 경계다: 구현자가
질의도 만들고 정답도 붙이면 그 평가셋은 *"리랭커가 좋은가"* 가 아니라 **"리랭커가
구현자가 관련있다고 생각한 것과 같은 판단을 하는가"** 를 잰다 — 붙이는 쪽과 채점표를
만드는 쪽이 같은 닫힌 고리라 숫자는 나오는데 그 숫자가 아무것도 뜻하지 않는다.
정답은 **dogfood 실사용 질의에 오너가** 붙인다(결정 4-③, 트리거 = GATE-1 착수).

**★ 그리고 지금 돌리면 아무 숫자도 안 나온다.** 로컬 기본이 no-op 이라(결정 2=A)
외부 리랭커 키가 오기 전에는 **no-op 대 no-op 비교**다. 순서는
**하네스 작성 → 키 조달 → dogfood 질의·정답 축적 → 판정** 이다.

입력(JSONL, 한 줄이 질의 하나):

    {"query": "아린은 왜 항구에 갔나",
     "gold": ["mem-1", "mem-7"],
     "ranked": {"before": ["mem-3", "mem-1", "mem-9"],
                "after":  ["mem-1", "mem-3", "mem-7"]}}

`ranked` 의 키 이름은 자유다 — 두 개든 셋이든 **구성 이름 → 순위 목록**이면 된다.
"before"/"after" 는 예시일 뿐이고, `bge-m3` vs `openai-3-small` 이어도 똑같이 돈다.

    python3 scripts/eval_retrieval_ranking.py --input eval.jsonl --k 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_K = 5


def recall_at_k(ranked: Sequence[str], gold: Sequence[str], k: int) -> float:
    """상위 k 안에 들어온 정답의 **비율**. 정답이 없으면 판정 대상이 아니다."""

    if not gold:
        raise ValueError("gold must not be empty")
    hit = len(set(ranked[:k]) & set(gold))
    return hit / len(gold)


def reciprocal_rank(ranked: Sequence[str], gold: Sequence[str]) -> float:
    """첫 정답의 순위 역수. 정답이 하나도 없으면 0.

    k 로 자르지 않는다 — MRR 은 *"첫 정답이 얼마나 앞인가"* 이고, k 밖이면 그
    사실 자체가 작은 값으로 나타나야 한다(0 으로 뭉개면 3위와 30위가 같아진다).
    """

    gold_set = set(gold)
    for position, item in enumerate(ranked, 1):
        if item in gold_set:
            return 1.0 / position
    return 0.0


def _dcg(ranked: Sequence[str], gold_set: set[str], k: int) -> float:
    from math import log2

    return sum(1.0 / log2(position + 1)
               for position, item in enumerate(ranked[:k], 1)
               if item in gold_set)


def ndcg_at_k(ranked: Sequence[str], gold: Sequence[str], k: int) -> float:
    """이상적 배치 대비 얼마나 앞에 뒀는가. 정답 간 등급 차이는 두지 않는다.

    등급(2점짜리 정답 / 1점짜리 정답)을 두지 않는 이유: **정답을 붙이는 사람이
    오너**이고, 이분법(`관련 있다/없다`)이 등급보다 훨씬 붙이기 쉽다. 등급이 필요할
    만큼 평가셋이 자라면 그때 여는 것이 맞다.
    """

    if not gold:
        raise ValueError("gold must not be empty")
    gold_set = set(gold)
    ideal = _dcg(list(gold_set)[: min(k, len(gold_set))], gold_set, k)
    return _dcg(ranked, gold_set, k) / ideal if ideal else 0.0


def evaluate(rows: Iterable[Mapping[str, Any]], *, k: int) -> dict[str, Any]:
    """구성마다 세 지표의 평균. 구성 이름은 입력이 정한다."""

    per_config: dict[str, list[dict[str, float]]] = {}
    counted = 0
    for number, row in enumerate(rows, 1):
        gold = row.get("gold")
        ranked_by_config = row.get("ranked")
        if not isinstance(gold, list) or not gold:
            raise ValueError(f"line {number}: 'gold' must be a non-empty list")
        if not isinstance(ranked_by_config, dict) or not ranked_by_config:
            raise ValueError(f"line {number}: 'ranked' must be a non-empty object")
        counted += 1
        for config, ranked in ranked_by_config.items():
            if not isinstance(ranked, list):
                raise ValueError(
                    f"line {number}: ranked[{config!r}] must be a list")
            per_config.setdefault(config, []).append({
                f"recall@{k}": recall_at_k(ranked, gold, k),
                "mrr": reciprocal_rank(ranked, gold),
                f"ndcg@{k}": ndcg_at_k(ranked, gold, k),
            })

    summary = {}
    for config, scores in per_config.items():
        if len(scores) != counted:
            # 어떤 질의에는 있고 어떤 질의에는 없는 구성은 평균이 서로 다른 표본을
            # 비교하게 만든다 — 그 비교는 숫자가 나오지만 뜻이 없다.
            raise ValueError(
                f"config {config!r} appears in {len(scores)} of {counted} queries "
                "— every configuration must rank every query")
        summary[config] = {
            metric: sum(score[metric] for score in scores) / len(scores)
            for metric in scores[0]
        }
    return {"queries": counted, "k": k, "configs": summary}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {number}: not valid JSON") from exc
    if not rows:
        raise ValueError("input has no rows")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="두 검색 구성의 순위를 정답 대비로 비교한다")
    parser.add_argument("--input", required=True, help="JSONL 평가셋")
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    args = parser.parse_args()
    result = evaluate(_read_jsonl(Path(args.input)), k=args.k)
    # 판정을 대신하지 않는다 — 숫자만 낸다. "좋아졌다" 는 사람이 말한다.
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
