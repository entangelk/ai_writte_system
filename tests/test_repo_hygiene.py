"""공개 저장소 위생 가드: 사설 주소·평문 비밀값의 **재유입**을 막는다.

`HANDOFF.md` 머리의 "공개 저장소 보안 규칙"은 2026-08-28에 제정됐지만 **강제하는 것이
없었다**. 그래서 2026-09-05 보안 감사(§B.1~B.4)가 잰 결과는 저장소가 자기 규칙을 어기고
있는 상태였다 — 실주소 3종이 **56파일 134히트**, 그중 87%가 이력 계열이었고, 라이브 스모크
스크립트 3종은 사설 주소를 **동작하는 기본값**으로 들고 있었다.

2026-09-06 Phase S-0(브리프 `docs/plans/security-phase-s0-docs-hygiene-decisions.md`)이
그것을 역할 별칭으로 스윕했다. **★ 스윕은 1회성이고 이 가드가 실제 산출물이다** — 파일에서
지워도 git 이력에는 남으므로(이력 재작성은 2026-08-23에 한 번 했고 비싸다) 이 조치의 값어치는
소급 삭제가 아니라 **앞으로의 커밋을 막는 것**에 있다.

오너 결정 D3=D — **규칙이 둘이고 서로 다른 실패 모드를 각자의 자리에서 막는다.**

- **정확 일치(전건)**: 이번에 걷어낸 실주소·비밀값이 어디로든 되돌아오면 실패한다.
  `scripts/`·`tests/`를 포함한 **모든 추적 파일**이 대상이다 — 이번 사고의 원인 하나가
  정확히 `scripts/`의 하드코딩 기본값이었다.
- **광의 RFC1918(문서 경로만)**: *새* 사설 호스트 주소가 문서에 들어오면 실패한다.
  경로를 `docs/`와 루트 `*.md`로 한정한 이유는 **테스트 픽스처가 일부러 사설 대역을 쓰기
  때문**이다(`tests/test_signup_throttle.py`의 XFF 신뢰 셀). 전건에 광의 규칙을 걸면 정상
  작업이 빨간 불이 되고, 그 압력은 결국 가드를 끄게 만든다.

두 방향을 잠근다.

- **under-strict**: 실주소나 비밀값을 되넣으면 실패한다. 종전에는 규칙이었고 아무도 강제하지
  않아 134히트가 쌓였다 — 이제 강제다.
- **over-strict**: 픽스처가 쓰는 사설 대역 주소와 **계약 literal의 CIDR 표기**는 통과해야
  한다. 과잉 교정으로 그것들을 막으면 XFF 신뢰 정책(Phase S-3)을 검증하는 셀이 통째로
  못 쓰게 된다 — 그 방향이 아래 두 셀이다.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path
from typing import NamedTuple

_ROOT = Path(__file__).resolve().parents[1]

# ★ 금지값을 이 파일에 그대로 적으면 가드가 자기 자신을 문다. 조각으로 조립하는 이유는
# 그래야 **이 파일도 검사 대상에 남길 수 있기** 때문이다 — 가드 파일을 예외로 빼는 순간
# 그 자리가 다음 구멍이 된다.
_FORBIDDEN_VALUES: tuple[tuple[str, str], ...] = (
    ("베타 머신 LLM 호스트(현행) — 별칭 `<베타-LLM>`", "192.168." + "1.22"),
    ("구 검증 머신 LLM 호스트 — 별칭 `<구검증-LLM>`", "192.168." + "1.29"),
    ("배포 호스트 LAN IP — 별칭 `<알파-호스트-LAN>`", "172.30." + "135.149"),
    ("확인용 계정 평문 비밀번호", "timeline-demo" + "-0810"),
)

# 사설 대역의 **호스트 주소**만 본다 — 옥텟 4개를 정확히 요구한다.
# ★ 3~4개를 허용하면 `npm 10.9.8` 같은 버전 문자열이 사설 주소로 잡힌다(실측 4파일).
# 후행 조건이 둘인 이유(2026-09-06 독립 검증 H1):
#   `(?![0-9/])`  — CIDR 대역 표기(`172.16.0.0/12`·`127.0.0.0/8`)는 신뢰 대역 계약
#                   literal 이지 이 집 LAN 의 호스트가 아니라 통과시킨다.
#   `(?!\.[0-9])` — 5옥텟 이상(`192.168.1.2.3`)은 주소가 아니라 통과시킨다.
# ★ 종전에는 이 둘을 `(?![0-9./])` 한 덩어리로 썼는데, 그러면 **문장 끝 마침표가
#   붙은 주소가 통째로 빠져나갔다**(검증자 실측). 마침표는 막고 5옥텟은 통과시키려면
#   "숫자가 뒤따르는 점"만 배제해야 한다.
_PRIVATE_HOST_RE = re.compile(
    r"(?<![0-9.])"
    r"(?:"
    r"192\.168(?:\.[0-9]{1,3}){2}"
    r"|10(?:\.[0-9]{1,3}){3}"
    r"|172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2}"
    r")"
    r"(?![0-9/])(?!\.[0-9])"
)

# 오너 결정 D1=D(2026-09-06) — 이 한 파일만 **두 규칙 모두**에서 예외다. 이 문서가
# **발견의 근거**라 원문을 보존한다: 고쳐 쓰면 발견을 서술한 문서가 발견을 재현할 수
# 없게 된다. ★ 이 예외를 지우거나 넓히지 말 것(넓히면 예외가 곧 다음 구멍이다).
_AUDIT_RECORD = "docs/verifications/2026-09-05/security_audit_dual_workflow.md"

# 광의 규칙만의 예외. **파일 단위이고 이유가 함께 간다** — 이유 없는 행이 생기면 다음
# 스윕이 그것을 지워도 되는지 판단할 수 없다.
_BROAD_RULE_ALLOWLIST: dict[str, str] = {
    _AUDIT_RECORD: "보안 감사 원문 — 발견의 근거라 오너 결정으로 보존",
    # 픽스처 IP 분류표가 이 문서의 내용 자체다(어느 주소가 픽스처이고 어느 것이 실주소인지를
    # 가른 기록). 주소를 지우면 분류가 사라진다.
    "docs/verifications/2026-09-05/phase_s3_signup_throttle.md": (
        "XFF 신뢰 셀의 픽스처 IP 분류표 — 주소가 곧 기록의 내용"
    ),
    # 도커 브리지 네트워크의 컨테이너 IP 추종 기록(172.31.0.x). 홈 LAN 토폴로지가 아니라
    # compose가 매번 새로 배정하는 내부 주소다.
    "docs/daily_logs/2026-07-23/work_log.md": (
        "도커 브리지 컨테이너 IP 추종 기록 — 홈 LAN 호스트가 아니다"
    ),
}


def _tracked_files() -> list[str]:
    """추적 파일 + **아직 add 하지 않은 새 파일**.

    `git ls-files` 만 보면 새로 쓴 파일은 `git add` 전까지 검사 밖이다 — 유출이 들어오는
    순간이 정확히 그 순간이라, 그 창을 열어 두면 가드가 가장 필요한 때 조용하다.
    """
    names: list[str] = []
    for extra in ([], ["--others", "--exclude-standard"]):
        out = subprocess.run(
            ["git", "ls-files", "-z", *extra],
            cwd=_ROOT, capture_output=True, text=True, check=True,
        ).stdout
        names.extend(name for name in out.split("\0") if name)
    return names


def _read(relative: str) -> str | None:
    """텍스트가 아니면 None. 바이너리는 이 가드의 대상이 아니다."""
    try:
        return (_ROOT / relative).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return None


def _is_document(relative: str) -> bool:
    return relative.startswith("docs/") or (
        "/" not in relative and relative.endswith(".md")
    )


# 정확 일치 규칙에서 빠지는 파일의 **전부**. 인라인 `if` 로 흩어 두면 집합 자체를
# 단정할 수 없어 예외 확장이 조용히 통과한다 — 2026-09-06 독립 검증 B1 이 그것을
# 실측했다(가드 파일을 예외로 넣고 금지값을 통째로 심어도 전수가 초록이었다).
_EXACT_RULE_EXCEPTIONS = frozenset({_AUDIT_RECORD})


class _ExactScan(NamedTuple):
    """정확 일치 스캔의 **완전한 회계**.

    셋을 합치면 추적 파일 전건이어야 한다 — 그래야 어떤 방식으로 파일이 스캔에서
    빠지든(예외 확장이든, 루프 어딘가의 `continue` 든) 수가 안 맞아 드러난다.
    검사한 파일 목록만 세면 *왜* 빠졌는지를 못 봐서 자기예외가 통과한다.
    """

    scanned: list[str]
    skipped_as_exception: list[str]
    skipped_as_binary: list[str]
    violations: list[str]


def _run_exact_scan() -> _ExactScan:
    scanned: list[str] = []
    as_exception: list[str] = []
    as_binary: list[str] = []
    violations: list[str] = []
    for relative in _tracked_files():
        if relative in _EXACT_RULE_EXCEPTIONS:
            as_exception.append(relative)
            continue
        text = _read(relative)
        if text is None:
            as_binary.append(relative)
            continue
        scanned.append(relative)
        for label, value in _FORBIDDEN_VALUES:
            if value in text:
                violations.append(f"{relative}: {label}")
    return _ExactScan(scanned, as_exception, as_binary, violations)


class ForbiddenLiteralsTest(unittest.TestCase):
    """정확 일치 — 추적 파일 **전건**. 산문이든 코드든 예외는 감사 기록 하나뿐이다."""

    def test_no_swept_address_or_secret_returns(self) -> None:
        scan = _run_exact_scan()
        for violation in scan.violations:
            with self.subTest(violation=violation):
                self.fail(
                    f"{violation} 가 저장소에 되돌아왔다. "
                    "역할 별칭으로 쓰거나(산문) 환경변수로 받는다(코드) — "
                    "docs/plans/security-phase-s0-docs-hygiene-decisions.md"
                )
        self.assertEqual(scan.violations, [])

    def test_the_exception_set_is_exactly_the_audit_record(self) -> None:
        """★ B1(2026-09-06 독립 검증)이 요구한 셀 — 예외 **집합**을 단정한다.

        종전 셀은 가드 파일이 `_tracked_files()` 에 있는지만 봤다. 그것은 스캔이
        그 파일을 실제로 **읽었는지**와 무관해서, 스캔 루프에 자기예외를 더하면
        조용히 통과했다. 브리프 D3 가 경고한 실패 경로가 정확히 그 모양이다 —
        금지값을 통째로 쓰고, 가드가 물면, 예외로 "해결"한다.
        """
        self.assertEqual(set(_EXACT_RULE_EXCEPTIONS), {_AUDIT_RECORD})

    def test_the_scan_accounts_for_every_tracked_file(self) -> None:
        """어떤 경로로든 파일이 스캔에서 빠지면 회계가 안 맞아 드러난다.

        예외 확장이 아니라 루프 중간의 `continue` 로 빠뜨려도 이 셀이 문다 —
        `test_the_exception_set_is_exactly_the_audit_record` 가 못 보는 방향이다.
        """
        scan = _run_exact_scan()
        counted = (
            set(scan.scanned)
            | set(scan.skipped_as_exception)
            | set(scan.skipped_as_binary)
        )
        self.assertEqual(
            counted, set(_tracked_files()),
            "정확 일치 스캔이 추적 파일 일부를 조용히 건너뛰었다",
        )
        self.assertEqual(
            set(scan.skipped_as_exception), set(_EXACT_RULE_EXCEPTIONS),
            "스캔이 건너뛴 파일과 선언된 예외 집합이 다르다 — "
            "예외는 _EXACT_RULE_EXCEPTIONS 한 곳에서만 선언한다",
        )
        self.assertIn(
            "tests/test_repo_hygiene.py", scan.scanned,
            "가드 파일이 스캔에서 빠졌다 — 조각 조립(_FORBIDDEN_VALUES)은 "
            "이 예외를 만들지 않으려고 치른 비용이다",
        )

    def test_binary_skips_are_only_images(self) -> None:
        """바이너리 예외가 조용히 넓어지지 않게 한다 — 지금은 `docs/img/*.png` 뿐이다."""
        scan = _run_exact_scan()
        unexpected = [p for p in scan.skipped_as_binary if not p.endswith(".png")]
        self.assertEqual(
            unexpected, [],
            "텍스트로 못 읽는 새 파일이 생겼다 — 스캔 밖이라는 뜻이니 "
            "가드 계약(바이너리는 대상이 아니다)이 여전히 맞는지 확인한다",
        )


class PrivateHostAddressInDocsTest(unittest.TestCase):
    """광의 RFC1918 — `docs/` 와 루트 `*.md` 만. 픽스처가 사는 `tests/` 는 대상이 아니다."""

    def test_documents_carry_no_private_host_address(self) -> None:
        for relative in _tracked_files():
            if not _is_document(relative) or relative in _BROAD_RULE_ALLOWLIST:
                continue
            text = _read(relative)
            if text is None:
                continue
            found = _PRIVATE_HOST_RE.findall(text)
            with self.subTest(file=relative):
                self.assertEqual(
                    found, [],
                    f"{relative}: 사설 호스트 주소가 문서에 들어왔다 — {found}. "
                    "역할 별칭으로 쓴다. 문서의 내용 자체가 주소 분류라면 "
                    "_BROAD_RULE_ALLOWLIST 에 **이유와 함께** 등재한다",
                )

    def test_every_allowlist_entry_still_exists(self) -> None:
        """예외가 낡으면 조용한 구멍이다 — 파일이 사라지거나 이미 깨끗해지면 걷는다."""
        for relative, reason in _BROAD_RULE_ALLOWLIST.items():
            with self.subTest(file=relative):
                text = _read(relative)
                self.assertIsNotNone(text, f"{relative}: 예외 대상이 없다 — 행을 지운다")
                assert text is not None
                self.assertTrue(
                    _PRIVATE_HOST_RE.search(text),
                    f"{relative}: 이제 사설 주소가 없다 — 예외({reason})를 걷는다",
                )

    def test_contract_cidr_and_fixture_ranges_are_not_flagged(self) -> None:
        """over-strict 가드: 정상 표기를 막으면 이 셀이 문다.

        신뢰 대역 계약 literal 은 CIDR 이고, 픽스처는 사설 **호스트** 주소를 일부러 쓴다.
        전자는 표기로, 후자는 경로로 걸러진다 — 어느 한쪽을 광의 규칙으로 덮으면
        Phase S-3 의 XFF 신뢰 셀이 통째로 못 쓰게 된다.
        """
        for literal in ("172.16.0.0/12", "127.0.0.0/8", "10.9.0.0/16", "192.168.0.0/16"):
            with self.subTest(cidr=literal):
                self.assertIsNone(
                    _PRIVATE_HOST_RE.search(literal),
                    f"{literal}: CIDR 대역 표기는 계약 literal 이라 통과해야 한다",
                )
        for fixture in ("tests/test_signup_throttle.py",):
            with self.subTest(fixture=fixture):
                self.assertFalse(
                    _is_document(fixture),
                    f"{fixture}: 픽스처가 사는 자리는 광의 규칙의 대상이 아니다",
                )

    def test_trailing_punctuation_does_not_hide_an_address(self) -> None:
        """★ H1(2026-09-06 독립 검증) — 문장 끝 마침표로 빠져나가지 않는다.

        종전 후행 조건 `(?![0-9./])` 은 `.` 을 통째로 배제해서, **문장 끝에 온 새
        사설 주소가 세 대역 모두에서 조용히 빠졌다**(검증자 실측, 당시 실피해 0).
        산문에 주소를 적으면 마침표가 붙는 것이 오히려 보통이라, 이 우회는 광의
        규칙이 가장 필요한 자리에서 정확히 열려 있었다.
        """
        for suffix in (".", ",", ")", "", " 이다", "\n"):
            for network in ("192.168." + "100.50", "10." + "1.2.3", "172.20." + "3.4"):
                with self.subTest(address=network, suffix=repr(suffix)):
                    self.assertTrue(
                        _PRIVATE_HOST_RE.search(network + suffix),
                        f"{network!r} 이 {suffix!r} 뒤에서 빠져나갔다",
                    )

    def test_five_octet_strings_are_still_not_addresses(self) -> None:
        """H1 수정의 짝(over-strict): 마침표를 막느라 5옥텟까지 잡으면 안 된다.

        `(?!\\.[0-9])` 가 "숫자가 뒤따르는 점"만 배제하는 이유가 이것이다 — 전체
        `.` 을 배제하면 H1 이 돌아오고, 아무것도 배제하지 않으면 이 셀이 문다.
        """
        for text in ("192.168.1.2.3", "10.0.0.1.5", "172.16.0.1.9"):
            with self.subTest(text=text):
                self.assertIsNone(
                    _PRIVATE_HOST_RE.search(text),
                    f"{text}: 옥텟 5개는 호스트 주소가 아니다",
                )


if __name__ == "__main__":
    unittest.main()
