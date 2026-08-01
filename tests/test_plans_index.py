"""문서 부채 가드: `docs/plans/`의 모든 계획·브리프가 README 인덱스에 등재된다.

오너 지시(2026-07-28) — "`docs/plans/`가 너무 커져서 정리가 필요하다". 실측된 증상은
**인덱스가 실질을 못 따라간다**는 것이었다: 2026-08-02 기준 90개 문서 중 **51개가 미등재**라
오너가 자기 결정 브리프를 찾지 못했다(세션 발화: "문서 정리가 하나도 안 돼서 내가 찾아볼 수가 없네").

브리프는 **오너 결정의 근거 기록**이라 삭제·병합하면 "왜 그렇게 정했는가"가 사라진다. 그래서
이 가드가 요구하는 것은 정리가 아니라 **도달 가능성**이다 — 파일이 어디에 있든 인덱스에서
닿을 수 있어야 한다. 디렉터리 재편(`plans/decisions/` 분리 등)은 여전히 열린 선택지이며
이 가드는 그것을 막지 않는다(경로가 바뀌면 링크도 바뀌고, 아래 두 번째 셀이 그것을 강제한다).

- **under-strict**: 새 브리프를 쓰고 인덱스에 안 넣으면 실패한다. 종전에는 규칙이었고 아무도
  강제하지 않아 51개가 쌓였다 — 이제 강제다.
- **over-strict**: 인덱스가 없는 파일을 가리켜도 실패한다. 파일을 옮기거나 이름을 바꾸고
  링크를 안 고치면 인덱스가 조용히 거짓말을 하는데, 그 방향이 이 셀이다.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_PLANS = Path(__file__).resolve().parents[1] / "docs" / "plans"
_INDEX = _PLANS / "README.md"

# 마크다운 링크의 대상만 뽑는다. 인덱스는 `../system-contract-sot.md`처럼 plans 밖도
# 가리키므로 경로는 README 위치 기준으로 푼다.
_LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")


def _indexed_targets() -> list[str]:
    return _LINK_RE.findall(_INDEX.read_text(encoding="utf-8"))


class PlansIndexTest(unittest.TestCase):
    def test_every_plan_document_is_reachable_from_the_index(self) -> None:
        """README를 안 거치고는 닿을 수 없는 문서가 없어야 한다."""

        on_disk = {
            path.name for path in _PLANS.glob("*.md") if path.name != "README.md"
        }
        indexed = {
            target.rsplit("/", 1)[-1]
            for target in _indexed_targets()
            if not target.startswith("../")
        }

        missing = sorted(on_disk - indexed)
        self.assertEqual(
            missing,
            [],
            f"README 인덱스에 없는 계획 문서 {len(missing)}건 — 새 브리프는 "
            "인덱스에 등재해야 한다(브리프는 오너 결정의 근거라 안 보이면 없는 것과 같다)",
        )

    def test_every_index_link_resolves(self) -> None:
        """인덱스가 없는 파일을 가리키지 않는다 (이름 변경·이동 후 링크 방치 방지)."""

        broken = sorted(
            target
            for target in set(_indexed_targets())
            if not (_INDEX.parent / target).resolve().is_file()
        )
        self.assertEqual(broken, [], f"인덱스의 깨진 링크 {len(broken)}건")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
