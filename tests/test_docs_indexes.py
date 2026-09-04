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


# 계획 문서 머리의 상태 선언. `상태:` 와 `Status:` 를 모두 받고, 굵게·백틱은 껍데기다.
_STATUS_LINE_RE = re.compile(r"^\**(?:상태|Status)\**\s*[:：]\s*(.{0,90})", re.M | re.I)

# 인덱스 표의 `| [`문서`](링크) | 설명 | 상태 |` 행에서 문서명과 상태 칸을 뽑는다.
_STATUS_ROW_RE = re.compile(
    r"^\| \[`([^`]+\.md)`\]\([^)]*\) \| [^|]* \| ([^|]*) \|", re.M
)

# 이 저장소가 **실제로 쓰고 있는** 어휘다. 통일하지 않은 것은 의도이며(오너 2026-08-06 —
# 검증 판정 어휘 소급 정리 없음), 새 값을 쓰려면 여기 먼저 더한다. 긴 것이 짧은 것을
# 가리지 않도록 **긴 순서로** 본다(`구현 완료` 가 `완료` 보다 먼저).
_STATUS_VOCABULARY: tuple[str, ...] = (
    "이행됨",
    "구현 완료",
    "Partially",
    "Discussion",
    "Implemented",
    "Proposed",
    "Resolved",
    "Approved",
    "Reviewed",
    "Verified",
    "Planned",
    "Active",
    "Draft",
    "Done",
    "확정",
    "완료",
)


def _token_of(status: str) -> str | None:
    """상태 문자열의 **선두 토큰**만 돌려준다(꼬리 서술은 자유롭게 둔다)."""

    stripped = status.strip().strip("*`·— ")
    for word in _STATUS_VOCABULARY:
        if stripped.lower().startswith(word.lower()):
            return word
    return None


def _leading_status_token(document: Path) -> str | None:
    match = _STATUS_LINE_RE.search(document.read_text(encoding="utf-8"))
    return _token_of(match.group(1)) if match else None


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

    def test_every_plan_document_declares_a_status(self) -> None:
        """모든 계획 문서가 **머리에 상태를 선언한다**(어휘는 `_STATUS_VOCABULARY`).

        왜 필요한가 — 2026-09-05 전수에서 **13개 문서가 `Draft`·`Proposed`·`Discussion`
        에 두 달 넘게 멈춰 있었다**. 그중 12개가 기술한 시스템은 구현·독립 검증까지
        끝난 상태였고, 실제 진행이 `*-decisions.md` 브리프로 옮겨가면서 부모 계획의
        상태 마커만 안 따라간 것이다. 인덱스 가드는 **도달 가능성**만 봤기 때문에
        전부 통과했다 — 문서는 찾아지는데 **그 문서가 지금 무엇인지는 아무도 안 봤다**.

        상태 어휘를 새로 통일하지 **않은 것은 의도다**(오너 2026-08-06 선례 — 검증 판정
        어휘를 소급 정리하지 않기로 했다). 이 셀이 요구하는 것은 통일이 아니라 **선언**
        이며, 기존 표현(`Resolved`·`확정`·`구현 완료` …)을 그대로 받는다.
        """

        missing = sorted(
            path.name
            for path in _PLANS.glob("*.md")
            if _leading_status_token(path) is None
        )
        self.assertEqual(
            missing,
            [],
            f"상태를 선언하지 않은 계획 문서 {len(missing)}건 — 머리에 "
            "`상태: <어휘>` 를 적는다. 인식되는 어휘는 tests/test_docs_indexes.py 의 "
            f"_STATUS_VOCABULARY: {', '.join(_STATUS_VOCABULARY)}",
        )

    def test_the_index_status_column_matches_the_document(self) -> None:
        """인덱스 상태 열과 문서 안 상태가 **같은 것을 말한다**.

        이 저장소에는 상태 정본이 둘이다 — 문서 머리의 `상태:` 줄과 이 인덱스의 상태
        열. 2026-09-05 실측에서 **120행 중 23행이 갈라져 있었다**(예: 스키마 중복
        전수조사가 인덱스에서는 *"구현 대기"* 인데 문서는 *"시행 완료 2026-09-03"*).
        둘을 묶지 않으면 한쪽만 고치는 일이 반복된다. 선례는 `_COUNT_CLAIMS`(주장↔디스크)
        와 `test_design_token_provenance`(스크립트↔CSS)다.

        **양방향**:
          · under-strict — 문서 상태를 바꾸고 인덱스를 안 고치면 실패한다(이번 병).
          · over-strict — 그 반대도 실패한다. 그리고 **꼬리는 자유다**: 비교 대상은
            선두 토큰뿐이라 인덱스가 `Resolved — D1=A(2026-08-05)` 처럼 자세히 적는
            것은 통과해야 한다. 전체 문자열 일치로 조이면 그 자유가 사라지고, 인덱스가
            요약을 못 실어 **읽는 자리로서 쓸모가 없어진다.**
        """

        rows = _STATUS_ROW_RE.findall(self.index.read_text(encoding="utf-8"))
        self.assertGreater(len(rows), 100, "인덱스 표 파싱이 깨졌다")
        drifted: list[str] = []
        for name, cell in rows:
            document = _PLANS / name
            if not document.is_file():
                continue
            in_file = _leading_status_token(document)
            in_index = _token_of(cell)
            if in_file != in_index:
                drifted.append(f"{name}: 문서={in_file} · 인덱스={in_index}")
        self.assertEqual(
            drifted,
            [],
            f"상태가 갈라진 행 {len(drifted)}건 — 문서와 인덱스는 같은 상태를 말해야 "
            "한다(꼬리 서술은 달라도 된다)",
        )


class VerificationsIndexTest(unittest.TestCase):
    """`docs/verifications/` — 독립 검증 기록(날짜 디렉터리 하위)."""

    index = _VERIFICATIONS / "README.md"

    def test_every_verification_record_is_reachable_from_the_index(self) -> None:
        _assert_all_reachable(
            self, self.index, set(_VERIFICATIONS.glob("*/*.md")), "검증 기록"
        )

    def test_every_index_link_resolves(self) -> None:
        _assert_links_resolve(self, self.index)

    def test_every_record_row_states_a_verdict(self) -> None:
        """모든 기록 행이 **판정 열에 실제 판정을 적는다**(오너 2026-08-06 = 최종 판정).

        왜 필요한가 — 2026-08-06에 두 가지가 한꺼번에 드러났다:
          · 판정 절이 있는데 인덱스는 `—`(서술형)인 행이 **14건**이었다. 분포의 합만
            맞으면 되므로 `VerificationCountClaimsTest` 는 통과했다.
          · 새 행 하나가 **파이프를 빠뜨려 2열**이었고(판정이 설명 칸에 먹힘) 역시 통과했다.
        둘 다 "합계는 맞는데 내용이 틀린" 형태다. 여기서는 **행 구조와 판정 값 자체**를 본다.

        판정 문구를 파싱하지 않는 것이 의도다 — 기록 본문의 판정 표현이 영·한 혼용에
        형식도 제각각이라(`PASS`·`Conditional pass`·`조건부 승인`) 정규식으로 분류하면
        규칙을 바꿀 때마다 다른 숫자가 나온다(2026-08-06 실측: 두 번 시도해 각각 5건·4건
        오분류). 그래서 **분류는 사람이 하고, 가드는 "비어 있지 않은가"만 잠근다.**

        under-strict: 새 기록을 `—` 로 등재하거나 판정 열을 빠뜨리면 실패한다.
        over-strict: 세 판정 중 무엇이든 적혀 있으면 통과한다 — 어떤 판정이어야 하는지는
        가드가 정하지 않는다(그것은 기록 본문과 사람의 몫이다).
        """
        allowed = {"합격", "조건부 합격", "불합격"}
        index = self.index.read_text(encoding="utf-8")
        rows = [line for line in index.splitlines() if line.startswith("|")]
        for record in sorted(_VERIFICATIONS.glob("*/*.md")):
            link = f"({record.parent.name}/{record.name})"
            with self.subTest(record=f"{record.parent.name}/{record.name}"):
                row = next((r for r in rows if link in r), None)
                self.assertIsNotNone(row, "인덱스에 행이 없다")
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                self.assertEqual(
                    len(cells), 3,
                    f"행이 3열이 아니다({len(cells)}열) — 판정 열 앞의 `|` 를 빠뜨렸는지 "
                    f"본다:\n{row[:160]}",
                )
                self.assertIn(
                    cells[-1].strip("*"), allowed,
                    "판정 열이 비어 있거나 알 수 없는 값이다 — 기록 본문의 **최종** 판정을 "
                    f"적는다({'·'.join(sorted(allowed))})",
                )


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

    def _distribution(self) -> list[int]:
        index = (_VERIFICATIONS / "README.md").read_text(encoding="utf-8")
        counts = [
            int(value)
            for value in re.findall(r"^\| \*{0,2}[^|]+\*{0,2} \| \*{0,2}(\d+)\*{0,2} \|",
                                    index, re.MULTILINE)
        ]
        # 판정은 셋뿐이다(합격·조건부 합격·불합격). 2026-08-06 에 `서술형` 을 걷어냈다
        # — 정의는 인덱스 표에만 있고 가이드에 없었으며, 222 전수 확인 결과 해당
        # 기록이 0건이었다(모든 기록이 판정 절과 판정 문구를 갖는다).
        self.assertEqual(len(counts), 3, f"판정 3종을 못 읽었다: {counts}")
        return counts

    def test_the_verdict_distribution_adds_up_to_the_total(self) -> None:
        # 판정 분포(합격·조건부 합격·불합격)는 전체와 맞아야 한다. 한 건을 등재하면서
        # 총계만 올리고 분포를 안 고치면 여기서 잡힌다 — 그리고 그 분포는 최상위
        # README 가 "조건부 합격이 N%"라는 주장의 분모/분자이기도 하다.
        self.assertEqual(sum(self._distribution()), self.actual)

    def test_the_readme_prose_repeats_the_distribution_verbatim(self) -> None:
        # 독립 검증 2026-08-04 H-3이 손으로 잡은 자리. **건수 주장은 가드 안에
        # 있었는데 분포 서술 문장은 밖이었다** — 그래서 8.3·8.2b 합격 +2가
        # 검증 인덱스 표에는 올랐는데 최상위 README 문장만 `합격 142`에 얼어
        # 있었고, 아무 테스트도 실패하지 않았다. 같은 병("세는 사람이 둘")이고
        # 처방도 같다: 분포의 정본은 검증 인덱스 표 하나이며 README 는 그것을
        # 그대로 되뇐다.
        readme = (_ROOT / "README.md").read_text(encoding="utf-8")
        found = re.search(
            r"합격 (\d+) · 조건부 합격 (\d+) · 불합격 (\d+)", readme
        )
        self.assertIsNotNone(
            found, "README 의 판정 분포 문장을 못 찾았다 — 문구가 바뀌었으면 "
                   "이 패턴도 함께 고친다",
        )
        self.assertEqual(
            [int(value) for value in found.groups()], self._distribution(),
            "README 분포 문장이 docs/verifications/README.md 표와 다르다",
        )

    def test_the_conditional_pass_percentage_follows_the_distribution(self) -> None:
        # 같은 문장의 파생값. 분포를 고치면서 이 백분율만 두면 "조건부 27%"가
        # 조용히 낡는다 — 이 주장은 포트폴리오 정문에서 **절차가 형식적이지
        # 않다는 근거**로 쓰이므로 낡은 채 두면 근거가 아니라 흠이 된다.
        readme = (_ROOT / "README.md").read_text(encoding="utf-8")
        stated = re.search(r"조건부 합격이 (\d+)%", readme)
        self.assertIsNotNone(stated, "README 의 조건부 합격 비율 문장을 못 찾았다")
        conditional = self._distribution()[1]
        self.assertEqual(
            int(stated.group(1)), round(conditional / self.actual * 100),
            f"조건부 {conditional}/{self.actual} = "
            f"{conditional / self.actual * 100:.1f}%",
        )

    def test_the_readme_names_the_current_contract_version(self) -> None:
        # 같은 형태의 세 번째 자리. README 절차 표의 ④ 칸이 SoT 버전을 적는데,
        # 그 버전은 슬라이스마다 오르고 README 는 아무도 안 고친다(실측: SoT 가
        # v1.7.89 인 동안 README 는 v1.7.87 이었다). 정본은 SoT 헤더 한 곳이다.
        sot = (_ROOT / "docs" / "system-contract-sot.md").read_text(encoding="utf-8")
        current = re.search(r"계약 버전: `(v[\d.]+)`", sot)
        self.assertIsNotNone(current, "SoT 헤더의 계약 버전을 못 읽었다")
        readme = (_ROOT / "README.md").read_text(encoding="utf-8")
        stated = re.search(r"\*\*(v[\d.]+)\*\*, 변경이력 전량 보존", readme)
        self.assertIsNotNone(stated, "README 절차 표의 SoT 버전 칸을 못 찾았다")
        self.assertEqual(stated.group(1), current.group(1))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
