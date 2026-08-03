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


# "검증 기록 N건"을 세 문서가 각자 적는다. 세는 사람이 셋이면 반드시 갈라진다 —
# 실제로 2026-08-02 하루에 세 번 갈라졌고, 매번 최상위 README 하나만 뒤처졌다
# (검증자는 자기 인덱스를, 구현자는 자기 것을 고치기 때문이다).
# 링크는 가드가 보고 있었는데 **숫자는 아무도 안 보고 있었다.**
_COUNT_CLAIMS = (
    ("docs/verifications/README.md", r"\d+일치 · (\d+)건"),
    ("docs/README.md", r"독립 검증 기록 (\d+)건"),
    ("README.md", r"\*\*(\d+)건 / \d+일치\*\*"),
    ("README.md", r"독립 검증 기록 \((\d+)건\)"),
)

# 같은 문장의 **일수**. 종전에는 이 자리가 `39일치` 리터럴이라 가드 밖이었고, 그래서
# 디스크가 40일이 된 뒤에도 두 문서가 39에 얼어 있었다(2026-08-03 독립 검증 H3).
# 리터럴로 고정하면 "숫자를 못 잡는" 것에 그치지 않고 **고치는 쪽이 깨진다** —
# 40으로 바로잡는 순간 패턴이 매칭에 실패했다. 건수와 같은 규칙으로 디스크에서 센다.
_DAY_COUNT_CLAIMS = (
    ("docs/verifications/README.md", r"(\d+)일치 · \d+건"),
    ("README.md", r"\*\*\d+건 / (\d+)일치\*\*"),
)

# 같은 병(가드 밖의 숫자 주장)이 `docs/plans/` 쪽에도 있었다 — 2026-08-03에 H3를
# 고치다 발견했다. 두 문서가 브리프 수를 각자 적는데 둘 다 뒤처져 있었다(73개라
# 적힌 동안 디스크는 75개). 세는 규칙을 여기 한 곳에 고정한다:
#   전체 = docs/plans/*.md 에서 인덱스 자신(README.md)을 뺀 수
#   브리프 = 그중 *-decisions.md
_PLANS_TOTAL_CLAIMS = (
    ("README.md", r"계획 · 결정 브리프 인덱스 \((\d+)개\)"),
    ("docs/plans/README.md", r"\((\d+)개 중 \d+개\)"),
)
_PLANS_BRIEF_CLAIMS = (
    ("README.md", r"추측 구현 금지 \|[^|]*\| \*\*(\d+)개\*\*"),
    ("docs/plans/README.md", r"\(\d+개 중 (\d+)개\)"),
)


class VerificationCountClaimsTest(unittest.TestCase):
    """문서가 적은 검증 기록 수가 디스크의 실제 파일 수와 같다.

    under-strict: 기록을 추가하고 어느 한 인덱스만 고치면 실패한다.
    over-strict: 파일을 지우고 숫자를 안 내려도 실패한다(양쪽 다 거짓말이다).
    """

    def setUp(self) -> None:
        records = list(_VERIFICATIONS.glob("*/*.md"))
        self.actual = len(records)
        # 일수 = 기록을 가진 날짜 디렉터리 수. 빈 디렉터리는 "N일치"가 세는 대상이
        # 아니므로 파일에서 유도한다(디렉터리를 직접 세면 빈 날이 끼어든다).
        self.actual_days = len({record.parent.name for record in records})

    def test_every_stated_count_matches_the_files_on_disk(self) -> None:
        for relative, pattern in _COUNT_CLAIMS:
            with self.subTest(document=relative, pattern=pattern):
                text = (_ROOT / relative).read_text(encoding="utf-8")
                found = re.findall(pattern, text)
                self.assertEqual(
                    len(found), 1,
                    f"{relative}: 이 주장을 정확히 한 번 찾지 못했다 — 문구가 "
                    "바뀌었으면 위 _COUNT_CLAIMS 도 함께 고친다",
                )
                self.assertEqual(
                    int(found[0]), self.actual,
                    f"{relative}가 {found[0]}건이라 적었지만 실제는 {self.actual}건",
                )

    def test_every_stated_day_count_matches_the_directories_on_disk(self) -> None:
        # 건수와 같은 규칙. under-strict: 새 날짜에 기록을 넣고 일수를 안 올리면
        # 실패한다. over-strict: 실제보다 큰 일수를 적어도 실패한다.
        for relative, pattern in _DAY_COUNT_CLAIMS:
            with self.subTest(document=relative, pattern=pattern):
                text = (_ROOT / relative).read_text(encoding="utf-8")
                found = re.findall(pattern, text)
                self.assertEqual(
                    len(found), 1,
                    f"{relative}: 이 주장을 정확히 한 번 찾지 못했다 — 문구가 "
                    "바뀌었으면 위 _DAY_COUNT_CLAIMS 도 함께 고친다",
                )
                self.assertEqual(
                    int(found[0]), self.actual_days,
                    f"{relative}가 {found[0]}일치라 적었지만 실제는 "
                    f"{self.actual_days}일치",
                )

    def test_every_stated_plans_count_matches_the_files_on_disk(self) -> None:
        # 검증 기록과 같은 병, 같은 처방. 브리프를 추가하고 두 문서 중 하나만
        # 고치면 실패한다(under-strict). 실제보다 크게 적어도 실패한다(over-strict).
        plans = _ROOT / "docs" / "plans"
        documents = [p for p in plans.glob("*.md") if p.name != "README.md"]
        expected = {
            "전체": (len(documents), _PLANS_TOTAL_CLAIMS),
            "브리프": (
                len([p for p in documents if p.name.endswith("-decisions.md")]),
                _PLANS_BRIEF_CLAIMS,
            ),
        }
        for label, (actual, claims) in expected.items():
            for relative, pattern in claims:
                with self.subTest(kind=label, document=relative):
                    text = (_ROOT / relative).read_text(encoding="utf-8")
                    found = re.findall(pattern, text)
                    self.assertEqual(
                        len(found), 1,
                        f"{relative}: 이 주장을 정확히 한 번 찾지 못했다 — 문구가 "
                        "바뀌었으면 위 _PLANS_* 도 함께 고친다",
                    )
                    self.assertEqual(
                        int(found[0]), actual,
                        f"{relative}가 {label} {found[0]}개라 적었지만 실제는 "
                        f"{actual}개",
                    )

    def test_the_verdict_distribution_adds_up_to_the_total(self) -> None:
        # 판정 분포(합격·조건부·서술형)는 전체와 맞아야 한다. 한 건을 등재하면서
        # 총계만 올리고 분포를 안 고치면 여기서 잡힌다 — 그리고 그 분포는 최상위
        # README 가 "조건부 합격이 27%"라는 주장의 분모/분자이기도 하다.
        index = (_VERIFICATIONS / "README.md").read_text(encoding="utf-8")
        counts = [
            int(value)
            for value in re.findall(r"^\| \*{0,2}[^|]+\*{0,2} \| \*{0,2}(\d+)\*{0,2} \|",
                                    index, re.MULTILINE)
        ]
        self.assertEqual(len(counts), 4, f"판정 4종을 못 읽었다: {counts}")
        self.assertEqual(sum(counts), self.actual)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
