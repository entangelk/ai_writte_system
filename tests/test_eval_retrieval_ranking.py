"""평가 하네스 회귀 — 리랭커 슬라이스 결정 4-②.

**★ 잠그는 것은 "포맷을 읽고 지표를 옳게 계산하는가" 뿐이다.** 브리프가 그은 경계
그대로다: **평가셋 자체를 회귀에 넣지 않는다** — 넣는 순간 정답이 잠기고, 그것이
4-② 가 피하려는 편향이다(구현자가 채점표를 만들면 *"리랭커가 좋은가"* 가 아니라
*"리랭커가 구현자 생각과 같은가"* 를 재게 된다).

그래서 아래 표본은 **지표 계산을 확인하기 위한 산술 픽스처**이지 평가셋이 아니다.
어떤 셀도 *"리랭킹이 더 낫다"* 를 단정하지 않는다.
"""

from __future__ import annotations

import unittest

from scripts.eval_retrieval_ranking import (
    evaluate,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


class MetricArithmeticTest(unittest.TestCase):
    def test_recall_counts_gold_inside_the_cut_only(self):
        self.assertEqual(recall_at_k(["a", "b", "c"], ["a", "c"], 3), 1.0)
        self.assertEqual(recall_at_k(["a", "b", "c"], ["a", "c"], 2), 0.5)
        self.assertEqual(recall_at_k(["x", "y"], ["a"], 2), 0.0)

    def test_recall_rejects_an_empty_gold_instead_of_dividing_by_zero(self):
        # 정답이 없는 줄은 판정 대상이 아니다. 0.0 으로 돌려주면 그 줄이 평균을
        # 조용히 끌어내린다 — 없는 질문에 답한 셈이 된다.
        with self.assertRaises(ValueError):
            recall_at_k(["a"], [], 3)

    def test_reciprocal_rank_uses_the_first_hit_and_is_not_cut_by_k(self):
        self.assertEqual(reciprocal_rank(["a", "b"], ["a"]), 1.0)
        self.assertEqual(reciprocal_rank(["b", "a"], ["a"]), 0.5)
        self.assertEqual(reciprocal_rank(["b", "c", "d", "a"], ["a"]), 0.25)
        self.assertEqual(reciprocal_rank(["x"], ["a"]), 0.0)

    def test_ndcg_is_one_when_gold_sits_on_top_and_falls_as_it_sinks(self):
        self.assertEqual(ndcg_at_k(["a", "b", "c"], ["a"], 3), 1.0)
        sunk = ndcg_at_k(["b", "a", "c"], ["a"], 3)
        self.assertLess(sunk, 1.0)
        self.assertGreater(sunk, 0.0)
        # 정답이 컷 밖이면 0 이다.
        self.assertEqual(ndcg_at_k(["b", "c", "a"], ["a"], 2), 0.0)

    def test_ndcg_rewards_putting_more_gold_higher(self):
        both_on_top = ndcg_at_k(["a", "b", "x"], ["a", "b"], 3)
        one_on_top = ndcg_at_k(["a", "x", "b"], ["a", "b"], 3)
        self.assertGreater(both_on_top, one_on_top)


class InputContractTest(unittest.TestCase):
    """포맷은 **구성 이름 → 순위 목록**이다 — "리랭킹 전/후" 로 굳지 않는다."""

    ROWS = [
        {"query": "q1", "gold": ["m1"],
         "ranked": {"bge-m3": ["m1", "m2"], "openai-3-small": ["m2", "m1"]}},
        {"query": "q2", "gold": ["m3"],
         "ranked": {"bge-m3": ["m3", "m4"], "openai-3-small": ["m4", "m3"]}},
    ]

    def test_configuration_names_are_free_form(self):
        """리랭커 전용이 아니다 — 임베딩 모델 비교에도 그대로 쓰인다."""
        result = evaluate(self.ROWS, k=2)
        self.assertEqual(set(result["configs"]), {"bge-m3", "openai-3-small"})
        self.assertEqual(result["queries"], 2)
        self.assertEqual(result["k"], 2)

    def test_more_than_two_configurations_are_fine(self):
        rows = [{"query": "q", "gold": ["m1"],
                 "ranked": {"a": ["m1"], "b": ["m1"], "c": ["m1"]}}]
        self.assertEqual(len(evaluate(rows, k=1)["configs"]), 3)

    def test_a_configuration_missing_from_some_queries_is_rejected(self):
        """서로 다른 표본의 평균을 비교하면 숫자는 나오는데 뜻이 없다."""
        rows = [
            {"query": "q1", "gold": ["m1"], "ranked": {"a": ["m1"], "b": ["m1"]}},
            {"query": "q2", "gold": ["m2"], "ranked": {"a": ["m2"]}},
        ]
        with self.assertRaises(ValueError) as raised:
            evaluate(rows, k=2)
        self.assertIn("every configuration must rank every query",
                      str(raised.exception))

    def test_malformed_rows_name_the_line(self):
        cases = {
            "gold 없음": {"query": "q", "ranked": {"a": ["m1"]}},
            "gold 빈 목록": {"query": "q", "gold": [], "ranked": {"a": ["m1"]}},
            "ranked 없음": {"query": "q", "gold": ["m1"]},
            "ranked 빈 객체": {"query": "q", "gold": ["m1"], "ranked": {}},
            "순위가 목록이 아님": {"query": "q", "gold": ["m1"],
                                    "ranked": {"a": "m1"}},
        }
        for name, row in cases.items():
            with self.subTest(row=name):
                with self.assertRaises(ValueError) as raised:
                    evaluate([row], k=2)
                self.assertIn("line 1", str(raised.exception))


class HarnessBoundaryTest(unittest.TestCase):
    def test_the_repository_ships_no_evaluation_set(self):
        """★ 결정 4-② 의 경계를 셀로 잠근다.

        하네스가 있다는 사실은 *"평가했다"* 가 아니다. 정답이 저장소에 들어오는
        순간 그것은 **구현자가 만든 채점표**가 되고, 그 숫자는 리랭커가 아니라
        구현자의 관련성 판단을 재게 된다. 정답은 dogfood 실사용 질의에 **오너가**
        붙인다(결정 4-③).
        """
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        found = [p for p in root.rglob("*.jsonl")
                 if "node_modules" not in p.parts and ".git" not in p.parts]
        self.assertEqual(
            [str(p.relative_to(root)) for p in found], [],
            "평가셋으로 보이는 파일이 저장소에 들어왔다 — 정답은 구현자가 "
            "채우지 않는다(브리프 결정 4-②)")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
