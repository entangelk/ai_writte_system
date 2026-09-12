"""서비스 정책 계약 문서가 코드와 갈라지지 않는지 (오너 지시 2026-09-05).

**왜 필요한가 — 이 문서는 값을 옮겨 적었다.** `docs/service-policy-contract.md` 는
*"이 서비스가 회원에게 무엇을 약속하는가"* 를 한 장에서 답하는 것이 목적이라, 값을
안 적으면 목적을 못 이룬다. 그런데 값을 적는 순간 **두 번째 정본**이 되고, 상수를
고친 사람은 문서를 안 고친다(이 저장소에서 실제로 일어난 계열: README 절차 표의 SoT
버전이 v1.7.89 동안 v1.7.87 이었다).

그래서 문서를 **파생본으로 만든다** — 각 행이 자기 정본을 `모듈::상수` 로 가리키고,
이 가드가 그 상수를 실제로 import 해서 문서에 적힌 수와 대조한다. 상수를 고치고
문서를 안 고치면 전수가 빨개진다.

**양방향**:
- under-strict — 상수를 고치고 문서를 안 고치면 2번이 실패한다.
- under-strict — 정본을 잘못 가리키면(오타·이름 변경) 1번이 실패한다.
- over-strict — 값을 안 바꾸고 문장만 다듬는 것은 통과해야 한다. 그래서 재는 것은
  **셀 안의 수**이지 문장이 아니다.

★ **한계를 적어 둔다**: 이 가드는 *문서에 있는 행* 만 본다. 행을 통째로 지우면
아무것도 실패하지 않는다(`typeScale.test.ts` 의 M5 와 같은 계열). 거기를 닫으려면
"정책 상수의 전집합"을 코드에서 유도해야 하는데 그 집합의 정의가 없다 —
`DEFAULT_*`·`MAX_*` 를 전부 긁으면 정책이 아닌 상수가 섞인다. 행 삭제는 사람이
읽어서 잡는다.
"""

from __future__ import annotations

import importlib
import re
import unittest
from datetime import timedelta
from pathlib import Path

from services.application.app.auth.users import TERMS_VERSION

_ROOT = Path(__file__).resolve().parents[1]
_DOC = _ROOT / "docs" / "service-policy-contract.md"
_LEGAL_MAP = _ROOT / "docs" / "legal" / "README.md"
_PACKAGE = "services.application.app"

#: 표 한 행: | 축 | 값 | `모듈::상수`(들) |
_ROW = re.compile(r"^\|(?P<axis>[^|]+)\|(?P<value>[^|]+)\|(?P<sources>[^|]*)\|")
_POINTER = re.compile(r"`([a-z_0-9/]+\.py)::([A-Z_][A-Z_0-9]*)`")

#: 법적 문서 초안 둘. 값·표식 가드가 같은 목록을 쓴다.
_DRAFTS = ("terms-of-service-draft.md", "privacy-policy-draft.md")

#: 오너만 채울 수 있어 대괄호로 비워 두었던 값 (브리프 landing-page-scope, 2026-09-08).
#: `[시행일]` 은 2026-09-09 오너 결정으로 합류했다 — 시행 전제(파기 데몬·동의 게이트)가
#: 안 끝났지만 **포트폴리오 단계라 문서를 붙잡지 않는다**(그 사실은 문서 머리말이 적는다).
_PROCURED = {
    "`[운영자]`": "entangelk",
    "`[문의 연락처]`": "kdtyohan@gmail.com",
    "`[추론 서비스 사업자]`": "Google",
    "`[시행일]`": "2026-09-08",
}

#: 시행 표기의 두 리터럴. 버전 문자열은 **동의 게이트가 저장할 값**이라 계약이다.
#: 동의 게이트(2026-09-12)가 상수를 만들었으므로 이제 이 핀은 그 상수를 가리킨다 —
#: 여기서 값을 직접 들던 종전의 핀 방식(문서가 유일한 정본이었기 때문)의 자리를
#: `auth/users.py::TERMS_VERSION` 이 이어받았고, 아래 셀들이 문서와 그 상수를 묶는다.
_ENFORCED_VERSION = TERMS_VERSION
_ENFORCED_DATE = "2026-09-08"

#: 부칙이 자기 버전을 다시 적는 줄(문서마다 표기가 다르다). 머리말과 **같은 값**을
#: 말해야 한다 — 2026-09-10 독립 검증 B1 실측: 시행 표기 커밋이 머리말·상태줄만
#: 고쳐 부칙만 `draft-0` (미시행) 로 남았고, 문서가 자기 지위를 두 가지로 말했다.
_ADDENDUM_VERSION_LINES = {
    "terms-of-service-draft.md": f"- 이 약관 버전: `{_ENFORCED_VERSION}`",
    "privacy-policy-draft.md": f"- 이 방침 버전: `{_ENFORCED_VERSION}`",
}

#: 시행 전 판본의 버전 문자열. 문서 어디에도 남아 있으면 안 된다.
_DRAFT_VERSION = "draft-0"

#: 코드가 시행하지만 약관·방침이 아직 적지 않은 제한(Slice 5 가 발견 · 검증 하드닝 H2).
#: 대조표가 **빠진 것** 을 적는 행이고, 축 이름이 그 행의 앵커다.
_UNDISCLOSED_AXIS = "유예 중에는 쓰기와 유료 경로가 막힌다"

#: 그 제한을 실제로 시행하는 자리. 이것이 사라지면 위 행도 사라져야 한다(양방향).
_UNDISCLOSED_GUARD = ("api/dependencies.py", "require_active_user_for_write")

#: 탈퇴 유예 기간을 적는 조항(문서마다 문장이 다르다). **수가 없는 부분**을 앵커로
#: 쓴다 — 수를 포함하면 값이 바뀔 때 앵커가 먼저 죽어 진단이 바뀐다.
_GRACE_CLAUSE_ANCHORS = {
    "terms-of-service-draft.md": "3. **회원은 탈퇴를 요청할 수 있습니다.**",
    "privacy-policy-draft.md": "3. **탈퇴를 요청하면",
}

#: **공개면에 가면 안 되는 편집 어휘** (오너 결정 2026-09-11 = 갈래 ⓑ).
#:
#: 약관·방침은 이제 프런트에도 실려 **회원이 읽는 화면**이 된다. 바이트 대조 가드는
#: 두 사본이 *같은가* 만 알고 *무엇이 실렸는가* 를 모르므로, 개발 과정의 서술이
#: 문서로 되돌아와도 전 셀이 초록이었다(독립 검증 H2 · 변이 ML-10 실측).
#:
#: 고른 어휘는 **저장소 안에서만 뜻이 있는 말**이다 — 회원에게는 뜻이 없거나,
#: 약관이 제 권위를 스스로 깎는 말이다. 법률 문장에 정상적으로 나올 수 없는
#: 것만 담아 거짓양성을 피한다(`세션` 처럼 본문이 실제로 쓰는 말은 넣지 않는다).
#: `README` 가 목록에 있는 이유는 두 가지다 — 회원이 읽는 면에 저장소 파일을
#: 가리키는 말이 나올 수 없고, **`근거:` 제외가 실제로 일을 하는지 이 어휘가
#: 증명한다**(제외를 없애면 머리말의 `근거:` 줄이 이 셀을 문다 = 제외가 무잠금이
#: 아니다).
_EDITORIAL_VOCABULARY = (
    "오너", "브리프", "HANDOFF", "SoT", "work_log", "커밋",
    "저장소", "포트폴리오", "구현 중", "미착수", "README",
)

#: 렌더러가 공개면에서 걷어내는 머리말 줄(`frontend/src/legal/markdown.tsx` 와 같은 접두).
#: 여기는 저장소 경로를 가리켜도 되는 유일한 자리라 어휘 검사에서 빼고 센다.
_STRIPPED_PREFIX = "근거:"


def _rows() -> list[tuple[str, str, list[tuple[str, str]]]]:
    """문서에서 정본 포인터를 가진 표 행만 걷는다."""
    found = []
    for line in _DOC.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        pointers = _POINTER.findall(match["sources"])
        if not pointers:
            continue
        found.append((match["axis"].strip(), match["value"].strip(), pointers))
    return found


#: 표의 머리 행(대조 대상이 아니다).
_HEADERS = {"축", "정책", "정책 문서의 축", "조항", "구분", "공백"}


def _axes() -> list[str]:
    """정책 문서의 **모든 표 행**에서 축 이름을 걷는다.

    `_rows()` 와 달리 정본 포인터를 요구하지 않는다 — §8(정해졌으나 미시행)은
    아직 상수가 없어 포인터가 없지만, **약관이 담아야 하는 정책이라는 점은 같다.**
    """
    found = []
    for line in _DOC.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        axis = match["axis"].strip().strip("*").strip()
        if axis in _HEADERS or set(axis) <= {"-", ":", " "}:
            continue
        found.append(axis)
    return found


def _mapped_axes() -> set[str]:
    """대조표가 **첫 칸으로** 이름을 든 축.

    본문 어디든 문자열이 있으면 통과하게 두면 안 된다 — 변이 ML-1 실측: 행
    이름을 `계정 탈퇴` → `계정 탈퇴(미기재)` 로 바꿔도 부분 문자열이라 초록이었다.
    표의 첫 칸을 **정확히** 대조해야 잠긴다.
    """
    mapped = set()
    for line in _LEGAL_MAP.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        mapped.add(match["axis"].strip().strip("*").strip())
    return mapped


def _load(module_path: str, name: str) -> object:
    dotted = f"{_PACKAGE}.{module_path[:-len('.py')].replace('/', '.')}"
    return getattr(importlib.import_module(dotted), name)


def _numbers(text: str) -> list[int]:
    """셀에서 사람이 읽는 수를 뽑는다(`3600초당 5건` → [3600, 5])."""
    return [int(one.replace(",", "")) for one in re.findall(r"\d[\d,]*", text)]


def _as_number(value: object) -> int | None:
    """상수를 문서가 적을 법한 수 하나로 환산한다."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, timedelta):
        # 문서는 사람이 읽는 단위로 적는다 — 일이 떨어지면 일, 아니면 시간.
        if value % timedelta(days=1) == timedelta(0):
            return value.days
        return int(value.total_seconds() // 3600)
    return None


class ServicePolicyContractTest(unittest.TestCase):
    """`docs/service-policy-contract.md` 는 코드의 파생본이다."""

    def test_the_document_exists_and_carries_pinned_rows(self):
        self.assertTrue(_DOC.exists(), "정책 계약 문서가 없다")
        # 0행이면 아래 두 셀이 공허하게 만족된다 — 포인터를 다 걷어낸 것도 결함이다.
        # ★ 하한은 **디스크 실제 수**여야 일을 한다(검증 하드닝 H3, 2026-09-12):
        # 종전 `>= 10` 은 실제 14행보다 넉넉해서 행을 하나 지워도 아무도 안 물었다.
        # 행을 **의도적으로 지울 때** 이 수를 함께 내린다(늘 때는 그대로 통과한다).
        self.assertGreaterEqual(len(_rows()), 14)

    def test_every_row_points_at_a_constant_that_still_exists(self):
        for axis, _value, pointers in _rows():
            for module_path, name in pointers:
                with self.subTest(axis=axis, source=f"{module_path}::{name}"):
                    try:
                        _load(module_path, name)
                    except (ImportError, AttributeError) as exc:  # noqa: PERF203
                        self.fail(f"정본 포인터가 죽었다: {exc}")

    def test_every_stated_number_matches_the_constant_it_cites(self):
        for axis, value, pointers in _rows():
            stated = _numbers(value)
            with self.subTest(axis=axis):
                actual = [_as_number(_load(*pointer)) for pointer in pointers]
                # 수가 아닌 상수(시간대 등)는 이 셀의 대상이 아니다.
                if any(one is None for one in actual):
                    continue
                self.assertEqual(
                    stated, actual,
                    f"'{axis}' 행이 {stated} 라고 적었는데 상수는 {actual} 다 —"
                    " 값의 정본은 상수 쪽이므로 문서를 고친다",
                )


class LegalDraftCoverageTest(unittest.TestCase):
    """약관 초안이 **우리가 정한 것을 담았는가**(오너 합격 기준 2026-09-07).

    오너가 약관 초안을 요구하며 낸 기준이 *"중요한건 우리가 정해놓은걸 제대로
    담았는가"* 였다. 그것을 **대조표의 존재**로 기계화한다 — `docs/legal/README.md`
    가 정책 문서의 각 축을 어느 조항이 받는지 적고, 이 셀이 **빠진 축이 있는지**만
    본다.

    ★ **조항의 내용이 맞는지는 재지 않는다.** 문장이 정책을 정확히 옮겼는지는
    사람이 읽어야 한다. 이 셀이 막는 것은 다른 것이다 — **정책이 늘었는데 약관이
    안 따라가는 것**(이 저장소에서 가장 흔한 문서 부패 방향이다).

    **양방향**: 정책 문서에 축을 더하고 대조표에 안 더하면 실패한다(under).
    대조표에서 행을 지우거나 **이름을 바꿔도** 실패한다(under — 변이 ML-1 이 이
    자리를 열었다: 종전 구현은 본문 부분 문자열을 봐서 이름 변경이 초록이었다).
    조항 번호만 고치는 것은 통과한다(over) — 재는 것은 **표 첫 칸의 축 이름**이지
    조항 번호가 아니다.
    """

    def test_the_mapping_table_covers_every_policy_axis(self):
        mapped = _mapped_axes()
        axes = _axes()
        # 0개면 공허하게 만족된다.
        self.assertGreaterEqual(len(axes), 15)
        missing = [axis for axis in axes if axis not in mapped]
        self.assertEqual(
            missing, [],
            "정책 문서에는 있는데 약관 대조표에 없는 축이다 — 약관 초안이 "
            "그 정책을 담았는지 확인하고 docs/legal/README.md 에 행을 더한다",
        )

    def test_the_undisclosed_restriction_keeps_its_row_while_code_enforces_it(self):
        """코드가 시행하는데 약관이 **안 적은** 제한은 대조표에 흔적이 남아야 한다.

        **왜 필요한가 — 이 행이 유일한 흔적이다.** Slice 5(2026-09-12)가 승격하면서
        *유예 중 일반 쓰기·유료 경로 403* 이 약관·방침 어디에도 없다는 것을 발견했고,
        조항 문장은 오너 몫이라 대조표에 `미기재` 행으로만 세웠다. 독립 검증 하드닝
        **H2** 가 그 다음을 짚었다 — **그 행을 지워도 전 셀이 초록**이었다(변이 MX-I).
        고지 없는 제한이 조용히 잊히는 경로가 그것이다.

        **양방향**:
          · under — 행을 지우면 실패한다(시행 중인 제한의 기록이 사라지는 것).
          · over — 제한을 **코드에서 걷으면** 행도 없어야 한다. 가드 심볼이 사라진
            세계에서는 이 셀이 *행이 없을 것* 을 요구하므로, 제한을 없앤 사람이
            대조표를 청소하지 않고 지나가지 못한다.

        ★ **조항이 실제로 쓰이는 날 이 셀도 바뀐다** — 그때는 행의 조항 칸이 채워지고
        이 셀의 뜻이 *"제한이 고지됐다"* 로 옮겨간다. 이름과 이 docstring 을 함께
        고치는 것이 그 작업의 일부다(지우는 것이 아니다).
        """
        try:
            _load(*_UNDISCLOSED_GUARD)
        except (ImportError, AttributeError):
            enforced = False
        else:
            enforced = True

        mapped = _mapped_axes()
        if enforced:
            self.assertIn(
                _UNDISCLOSED_AXIS, mapped,
                "코드가 유예 중 쓰기를 막는데 대조표에 그 행이 없다 — 고지되지 않은 "
                "제한의 유일한 기록이므로 지우려면 약관에 문언을 먼저 넣는다",
            )
        else:
            self.assertNotIn(
                _UNDISCLOSED_AXIS, mapped,
                "유예 쓰기 가드가 코드에서 사라졌는데 대조표가 아직 그 제한을 "
                "미기재로 적는다 — 없는 제한을 빠진 고지로 세어 두면 거짓이다",
            )

    def test_the_length_limits_in_the_terms_match_the_constants(self):
        """약관 제5조 1항의 두 수를 **상수와** 대조한다(핀이 아니라 상징 참조).

        ★ 2026-09-10 독립 검증(B2)이 실측한 결함: 약관이 원고 본문 상한을
        **4,000자**라고 적는 동안 시행값은 이미 **6,000자**였다(`97bc149`,
        2026-09-08 상향). 정책 문서(`service-policy-contract.md`)의 같은 축은
        정본 포인터를 달고 있어 위 셀이 잡았지만, **약관 본문의 수는 아무도 안
        봤다** — 대조표는 *어느 조항이 받는지*만 재고 조항의 내용은 사람이 읽기
        때문이다. 회원에게 보이는 문장이 시행값과 다르면 그 자체로 거짓 고지다.

        **양방향**:
          · under — 상수가 오르는데 약관을 안 고치면 실패한다(이번 병).
          · over — 약관만 고치고 상수를 안 올려도 실패한다. 값의 정본은 상수다.

        ★ 이 셀은 **이 한 축만** 잠근다. 약관·방침의 나머지 수(사용자명 64자 ·
        비밀번호 12/256자 · 대기 200건 · 5건/3,600초 · 5회/300초 · 세션 7일 ·
        하루 20/주 100 · 승격 1시간)는 2026-09-10 검증이 손으로 훑어
        전부 일치를 확인했을 뿐 기계가 보지 않는다 — 축마다 조항 앵커가 달라서
        일반화하려면 조항 ↔ 상수 표가 따로 필요하다(HANDOFF 잔여 부채).
        **유예 30일은 그 목록을 떠났다** — 아래 `...grace_period...` 셀이 같은
        모양으로 잠근다(Slice 5 가 그 축을 시행 중으로 올렸기 때문이다). 부채를
        닫은 것이 아니라 **축 하나를 덜어낸 것**이다.
        """
        text = (_LEGAL_MAP.parent / "terms-of-service-draft.md").read_text(
            encoding="utf-8"
        )
        clause = [
            line for line in text.splitlines()
            if line.startswith("1. 원고 한 단위의 본문은")
        ]
        self.assertEqual(
            len(clause), 1,
            "약관 제5조 1항(길이 제한)의 자리를 못 찾았다 — 문장을 고쳤다면 이 "
            "앵커도 함께 고친다. 앵커가 헛돌면 이 셀은 아무것도 잠그지 않는다",
        )

        self.assertEqual(
            # 목록 번호(`1.`)는 조항의 값이 아니다.
            _numbers(clause[0].removeprefix("1.")),
            [
                _load("env.py", "DRAFT_RAW_TEXT_MAX_CHARS"),
                _load("core_sot/service.py", "SCENE_NOTE_MAX_CHARS"),
            ],
            "약관 제5조 1항이 시행값과 다른 수를 적는다 — 값의 정본은 상수이므로 "
            "약관 문장을 고친다",
        )

    def test_the_withdrawal_grace_period_matches_the_constant(self):
        """탈퇴 유예 **30일**을 두 문서에서 상수와 대조한다(Slice 5, 2026-09-12).

        **왜 이 축이 이제 여기 있는가.** 승격(§8 → §6) 전에는 정책 문서에 포인터가
        없어 값을 핀 셀 하나가 들었고, 약관·방침이 적는 *문장의 수* 는 아무도 보지
        않았다 — 위 셀의 docstring 이 그 목록에 `유예 30일` 을 적어 둔 자리다.
        승격이 그 공백을 드러냈다: 시행되는 축이 되면 **회원에게 보이는 수**가
        시행값과 갈라질 수 있고, 제5조 1항이 실제로 그렇게 갈라졌다(4,000 대 6,000).

        **두 문서를 함께 본다.** 같은 값을 둘이 나눠 드는 구조라 한쪽만 고치는 것이
        실제로 일어나는 실수다(`_PROCURED` 셀이 같은 이유로 문서별로 가른다).

        **양방향**:
          · under — 상수가 60일로 바뀌고 문서를 안 고치면 문서별로 실패한다.
          · over — 문서만 고치고 상수를 안 바꿔도 실패한다. 값의 정본은 상수다.
          · over — 수를 그대로 둔 문장 다듬기는 통과한다(세는 것은 **수의 집합**
            이므로 조항이 `30일` 을 몇 번 말하는지는 묶지 않는다).

        ★ 앵커는 **수가 없는 부분**으로 잡는다 — 수를 포함하면 값이 바뀔 때 앵커가
        먼저 죽어 *"조항을 못 찾았다"* 로 실패하는데, 그것은 값 불일치와 다른
        진단이다. 조항 문장을 고쳤다면 이 앵커도 함께 고친다.
        """
        grace = _as_number(_load("auth/users.py", "WITHDRAWAL_GRACE_PERIOD"))
        for name, anchor in _GRACE_CLAUSE_ANCHORS.items():
            with self.subTest(document=name):
                text = (_LEGAL_MAP.parent / name).read_text(encoding="utf-8")
                clause = [
                    line for line in text.splitlines() if line.startswith(anchor)
                ]
                self.assertEqual(
                    len(clause), 1,
                    f"{name}: 탈퇴 유예 조항의 자리를 못 찾았다 — 문장을 고쳤다면 "
                    "이 앵커도 함께 고친다. 앵커가 헛돌면 이 셀은 아무것도 "
                    "잠그지 않는다",
                )
                # 목록 번호(`3.`)는 조항의 값이 아니다.
                stated = set(_numbers(clause[0].removeprefix("3.")))
                self.assertEqual(
                    stated, {grace},
                    f"{name}: 탈퇴 조항이 {sorted(stated)} 을 적는데 시행값은 "
                    f"{grace}일이다 — 값의 정본은 "
                    "`auth/users.py::WITHDRAWAL_GRACE_PERIOD` 이므로 문장을 고친다",
                )

    def test_both_documents_carry_the_enforced_version_and_date(self):
        """시행 표기와 **버전·시행일 리터럴**을 잠근다(오너 2026-09-09).

        종전 셀은 `미시행` 표식이 남아 있는지만 봤고, 그 docstring 이
        *"실제 시행은 오너가 이 표식을 걷어내는 것으로 시작하며, 그때 이 셀도
        함께 고친다"* 라고 예고했다 — 지금이 그때다.

        ★ **버전 문자열이 계약 리터럴이다.** 가입 동의 게이트(HANDOFF 10번,
        2026-09-12 구현)가 회원의 동의 시각과 **함께 이 문자열을 저장**하므로,
        문서에서 조용히 바뀌면 저장된 동의가 어느 판본에 대한 것인지 갈라진다.
        게이트가 `auth/users.py::TERMS_VERSION` 상수를 만들었고 이 셀은 그
        상수와 문서를 묶는다 — 버전을 올리려면 상수와 두 문서(그리고 프런트
        상수, `frontend/src/legal/legalSource.test.ts` 핀)가 함께 움직여야 한다.

        ★★ **2026-09-10 독립 검증(B1)이 이 셀의 사각을 실측했다.** 종전에는 옛
        상태줄의 **정확한 문구**(`Draft — 법률 검토 전 · 미시행`)만 부정하고
        버전은 *어디든* 문자열이 있으면 통과시켰다. 그래서 시행 표기 커밋이
        머리말만 고치고 **부칙에 `draft-0` (미시행) 를 남긴 채로도 초록**이었다.
        지금은 셋을 함께 본다:

        - `draft-0` **토큰이 문서 어디에도 없다**(부칙 잔류를 곧바로 잡는다).
        - 머리말 버전은 **줄 전체**로 대조한다 — 부분 문자열로 재면 부칙 줄
          (`- 이 약관 버전: \`1.0\``)이 머리말을 대신 만족시켜, 머리말이 다른
          판본을 말해도 초록이 된다.
        - 부칙 버전 줄도 **같은 리터럴**을 든다(문서 안 두 자리가 함께 움직인다).
        """
        for name in _DRAFTS:
            with self.subTest(document=name):
                text = (_LEGAL_MAP.parent / name).read_text(encoding="utf-8")
                lines = text.splitlines()
                self.assertNotIn(
                    "Draft — 법률 검토 전 · 미시행", text,
                    f"{name}: 미시행 표식이 남았다 — 시행 표기와 섞이면 문서가 "
                    "자기 지위를 두 가지로 말한다",
                )
                self.assertNotIn(
                    _DRAFT_VERSION, text,
                    f"{name}: 시행 전 버전 문자열 {_DRAFT_VERSION!r} 이 남았다 — "
                    "머리말이 시행을 말하는데 다른 자리가 초안을 말한다",
                )
                self.assertIn(f"버전: `{_ENFORCED_VERSION}`", lines)
                self.assertIn(_ADDENDUM_VERSION_LINES[name], lines)
                self.assertIn(f"시행 — {_ENFORCED_DATE}", text)
                self.assertIn(f"- 시행일: {_ENFORCED_DATE}", text)


class LegalDraftProcuredValuesTest(unittest.TestCase):
    """오너가 조달한 값 넷이 문서에 실제로 들어갔는가 (2026-09-08 확정 · 09-09 반영).

    이 값들은 **코드에서 유도할 수 없다** — 없는 운영자·연락처를 지어내면 그 자체가
    허위 문서라 초안이 일부러 대괄호로 비워 두었고, 오너가 브리프
    (`docs/plans/landing-page-scope-decisions.md`)에서 채웠다. 정본이 문서뿐이므로
    상징 참조로는 잠글 수 없고 **핀 셀**이 값을 직접 든다(`MIN_PASSWORD_LENGTH`
    선례와 같은 이유).

    ★ **`[추론 서비스 사업자]` 는 배포 설정이 정하는 값**이다(방침 제4조 3항이 그
    사실을 문장으로 적는다). 벤더를 바꾸면 **이 셀과 방침이 함께** 바뀌어야 한다 —
    셀이 있어야 그 연결이 끊긴 것을 전수가 말해 준다.
    """

    def test_the_procured_values_are_filled_in_both_documents(self):
        # 값이 들어갔는가(under) + 대괄호가 남아 있지 않은가(같은 축의 반대편).
        # 셋을 한 번에 재지 않고 문서별로 가르는 이유: 한쪽만 채우고 다른 쪽을
        # 빠뜨리는 것이 실제로 일어나는 실수다(약관·방침이 같은 값을 나눠 든다).
        seen = {value: False for value in _PROCURED.values()}
        for name in _DRAFTS:
            text = (_LEGAL_MAP.parent / name).read_text(encoding="utf-8")
            for placeholder, value in _PROCURED.items():
                with self.subTest(document=name, placeholder=placeholder):
                    self.assertNotIn(
                        placeholder, text,
                        f"{name} 에 {placeholder} 가 남아 있다 — 오너가 채운 값을 "
                        "본문에 반영한다",
                    )
                if value in text:
                    seen[value] = True
        for value, found in seen.items():
            with self.subTest(value=value):
                self.assertTrue(
                    found, f"조달된 값 {value!r} 이 어느 초안에도 없다"
                )

    def test_the_effective_date_and_the_unenforced_marker_move_together(self):
        """시행일을 채우는 것과 `미시행` 표식을 걷는 것은 **한 걸음**이다.

        갈라지면 문서가 자기 지위를 두 가지로 말한다 — 날짜만 채우면 *"시행일이
        지났는데 미시행"*, 표식만 걷으면 *"시행 중인데 시행일이 대괄호"*. 둘 다
        읽는 사람에게 거짓이라 **양방향으로** 잠근다.

        - under-strict: `[시행일]` 을 채우면서 표식을 안 걷으면 실패한다.
        - over-strict: 표식만 걷고 날짜를 안 채우면 실패한다.

        ★ 진짜 시행은 이 셀을 **삭제**하는 것이 아니라 그때의 사실로 고치는 것이다.
        시행 전제(README `시행 전제` 열)는 **계정 탈퇴 축이 2026-09-12 에 닫혀**
        가입 절차의 동의 기록 한 줄만 남았다 — 그 줄이 닫히는 날 README 표와 두
        문서 머리말의 미제공 고지가 함께 움직인다.

        ★★ **이 셀이 못 보는 것 — 변이가 실제로 드러냈다(2026-09-09).** 재는 것은
        대괄호 *문자열의 존재*라, 머리말이 설명하려고 대괄호 표기를 **언급**하면
        본문의 자리를 다 채워도 초록이다(첫 변이가 그렇게 통과했다). 그래서 두
        초안의 머리말은 자리를 가리킬 때 대괄호 표기를 쓰지 않고 *"시행일 자리"*
        라고 쓴다 — **이 규칙이 깨지면 이 셀도 함께 눈이 먼다.**
        """
        for name in _DRAFTS:
            with self.subTest(document=name):
                text = (_LEGAL_MAP.parent / name).read_text(encoding="utf-8")
                self.assertEqual(
                    "`[시행일]`" in text,
                    "Draft — 법률 검토 전 · 미시행" in text,
                    f"{name}: 시행일 대괄호와 미시행 표식이 갈라졌다 — 둘은 함께 "
                    "움직인다",
                )

    def test_the_public_documents_carry_no_editorial_vocabulary(self):
        """공개면에 **개발 과정의 말**이 실리지 않는가 (오너 결정 2026-09-11, 갈래 ⓑ).

        **왜 필요한가 — 바이트 가드가 못 보는 축이다.** 약관·방침은 프런트에도 실려
        회원이 읽는 화면이 되었고, 프런트 사본과 정본이 같은지는
        `frontend/src/legal/legalSource.test.ts` 가 바이트로 잠근다. 그러나 그 가드는
        *"두 사본이 같은가"* 만 말한다 — 편집 메모를 **양쪽에 일관되게** 되돌리면
        전 셀이 초록이고(독립 검증 H2, 변이 ML-10 실측) 회원은 *"랜딩 페이지 푸터에도
        싣는다(오너 2026-09-07)"* 같은 운영 지시를 약관에서 읽는다. 실제로 한 번
        실려 있었고 세션 58 이 손으로 걷어냈다.

        **오너 결정(2026-09-11)은 갈래 ⓑ** — 머리말 고지에서 오너·날짜 서술을 걷고
        그 뒤 어휘를 금지한다. 그래서 두 머리말은 이제 *"시행일 2026-09-08 · 버전
        `1.0` 로 시행합니다"* 만 말하고, **왜 그렇게 정했는지는
        [`docs/legal/README.md`](../docs/legal/README.md) 와 브리프가 든다**(정본은
        그쪽이고 여기는 회원이 읽는 면이다).

        **양방향**:
        - under-strict — 편집 서술이 어느 한 문서로 되돌아오면 그 문서·그 어휘
          이름으로 실패한다(ML-10 이 더는 조용하지 않다).
        - over-strict — 본문이 정상적으로 쓰는 말(`세션`·`관리자`·`기록`)은 목록에
          없다. 그리고 저장소 경로를 가리켜도 되는 `근거:` 머리말 줄은 **렌더러가
          공개면에서 걷는 줄**이라 같은 접두로 빼고 센다 — 빼지 않으면 이 셀이
          화면에 없는 것을 문다.
        """
        for name in _DRAFTS:
            text = (_LEGAL_MAP.parent / name).read_text(encoding="utf-8")
            public = "\n".join(
                line for line in text.splitlines()
                if not line.startswith(_STRIPPED_PREFIX)
            )
            for word in _EDITORIAL_VOCABULARY:
                with self.subTest(document=name, word=word):
                    self.assertNotIn(
                        word, public,
                        f"{name}: 회원이 읽는 면에 개발 과정의 말 {word!r} 이 "
                        "실렸다 — 그 서술의 자리는 docs/legal/README.md 다",
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
