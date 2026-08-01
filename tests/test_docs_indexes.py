"""문서 부채 가드: 인덱스가 실질을 따라가고, 링크가 실제 파일을 가리킨다.

오너 지시(2026-07-28) — "`docs/plans/`가 너무 커져서 정리가 필요하다". 실측된 증상은
**인덱스가 실질을 못 따라간다**는 것이었다: 2026-08-02 기준 계획 문서 90개 중 **51개가 미등재**라
오너가 자기 결정 브리프를 찾지 못했다(세션 발화: "문서 정리가 하나도 안 돼서 내가 찾아볼 수가 없네").
같은 부채가 검증 기록에도 있었다 — **202건이 인덱스 없이** 쌓여 있었다.

브리프와 검증 기록은 **왜 그렇게 정했는가 · 무엇을 확인했는가**의 유일한 출처다. 삭제·병합하면
그 이력이 사라지므로, 이 가드가 요구하는 것은 정리가 아니라 **도달 가능성**이다 — 파일이 어디에
있든 인덱스에서 닿을 수 있어야 한다. 디렉터리 재편은 여전히 열린 선택지이며 이 가드는 그것을
막지 않는다(경로가 바뀌면 링크도 바뀌고, 링크 해석 셀이 그것을 강제한다).

각 인덱스에 대해 두 방향을 잠근다.

- **under-strict**: 새 문서를 쓰고 인덱스에 안 넣으면 실패한다. 종전에는 규칙이었고 아무도
  강제하지 않아 51건이 쌓였다 — 이제 강제다.
- **over-strict**: 인덱스가 없는 파일을 가리켜도 실패한다. 파일을 옮기거나 이름을 바꾸고
  링크를 안 고치면 인덱스가 조용히 거짓말을 하는데, 그 방향이 이 셀이다.

최상위 `README.md`도 링크 해석만 잠근다 — **포트폴리오 진입점이라 깨진 링크의 비용이 가장 크다**.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PLANS = _ROOT / "docs" / "plans"
_VERIFICATIONS = _ROOT / "docs" / "verifications"

# 마크다운 링크의 `.md` 대상만 뽑는다. 외부 URL·디렉터리·LICENSE 는 대상이 아니다.
# `#절-제목` 앵커는 떼고 **파일 경로만** 본다 — 앵커가 붙었다는 이유로 검사에서 빠지면
# 파일이 사라진 링크가 조용히 통과한다.
_LINK_RE = re.compile(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)")


def _links_in(index: Path) -> list[str]:
    return _LINK_RE.findall(index.read_text(encoding="utf-8"))


def _assert_all_reachable(
    case: unittest.TestCase, index: Path, documents: set[Path], what: str
) -> None:
    """`documents` 전부가 `index` 에서 링크된다."""

    indexed = {(index.parent / target).resolve() for target in _links_in(index)}
    missing = sorted(
        str(path.relative_to(_ROOT)) for path in documents if path.resolve() not in indexed
    )
    case.assertEqual(
        missing,
        [],
        f"{index.relative_to(_ROOT)} 에 없는 {what} {len(missing)}건 — 새 문서는 "
        "인덱스에 등재해야 한다(안 보이면 없는 것과 같다)",
    )


def _assert_links_resolve(case: unittest.TestCase, index: Path) -> None:
    broken = sorted(
        target
        for target in set(_links_in(index))
        if not (index.parent / target).is_file()
    )
    case.assertEqual(
        broken, [], f"{index.relative_to(_ROOT)} 의 깨진 링크 {len(broken)}건"
    )


class PlansIndexTest(unittest.TestCase):
    """`docs/plans/` — 계획 문서와 착수 결정 브리프."""

    index = _PLANS / "README.md"

    def test_every_plan_document_is_reachable_from_the_index(self) -> None:
        _assert_all_reachable(
            self,
            self.index,
            {path for path in _PLANS.glob("*.md") if path.name != "README.md"},
            "계획 문서",
        )

    def test_every_index_link_resolves(self) -> None:
        _assert_links_resolve(self, self.index)


class VerificationsIndexTest(unittest.TestCase):
    """`docs/verifications/` — 독립 검증 기록(날짜 디렉터리 하위)."""

    index = _VERIFICATIONS / "README.md"

    def test_every_verification_record_is_reachable_from_the_index(self) -> None:
        _assert_all_reachable(
            self, self.index, set(_VERIFICATIONS.glob("*/*.md")), "검증 기록"
        )

    def test_every_index_link_resolves(self) -> None:
        _assert_links_resolve(self, self.index)


class RepositoryReadmeTest(unittest.TestCase):
    """최상위 `README.md` — 저장소를 처음 보는 사람이 닿는 곳."""

    def test_every_readme_link_resolves(self) -> None:
        _assert_links_resolve(self, _ROOT / "README.md")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
