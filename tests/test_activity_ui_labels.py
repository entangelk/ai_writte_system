"""활동 로그의 **두 정본을 잇는 연결선** (Phase 9 Slice 9.1, S4=ⓐ).

오너 결정(2026-08-10): *"서로 다른 섹션의 정본이면(중복된 내용이 아니라면) 정본은 몇 개가
되든 상관없어. **인덱싱만 제대로 되어 있고 연결만 되어 있으면.**"*

두 정본은 중복이 아니다 —

- ``services/application/app/activity/actions.py`` = *"어떤 route 가 무엇을 기록하는가"*(배선·분류)
- ``frontend/src/projects/activityActions.ts`` = *"그 리터럴을 사람에게 뭐라 부르는가"*(UI 문구)

**이 파일이 그 연결이다.** 없으면 백엔드가 21번째 action 을 더해도 프론트는 조용히 원문
폴백을 하고 **아무 테스트도 안 깨진다** — 이 저장소가 ``ObservedProvider`` 계측 누락으로
이미 값을 치른 *"회귀는 green, 배포만 조용히 틀림"* 과 같은 형태다.

**★ 왜 프론트가 아니라 여기(pytest)인가**: 프론트는 백엔드 리터럴 목록을 알 방법이 없다.
``schema.d.ts`` 는 ``action`` 을 ``string`` 으로만 주므로 **타입으로는 못 잡는다**. 두 표를
동시에 볼 수 있는 자리가 여기뿐이다. 파이썬 테스트가 저장소의 비-파이썬 파일을 읽는 것은
``test_docs_indexes.py``(문서)·``test_compose_exposure.py``(compose YAML) 의 선례를 따른다.
"""
from __future__ import annotations

import inspect
import re
import unittest
from pathlib import Path

from services.application.app.activity.actions import (
    ACTIVITY_ACTIONS,
    LOGGED_OPERATIONS,
)
from services.application.app.activity.log import ActivityLogService

_ROOT = Path(__file__).resolve().parents[1]
_UI_TABLE = _ROOT / "frontend" / "src" / "projects" / "activityActions.ts"
_UI_SRC = _ROOT / "frontend" / "src"

#: 상한을 **화면이 말하고 서비스가 서빙하는** 짝. 화면마다 상수가 따로 있고 서빙
#: 메서드도 따로라, 등재되지 않은 세 번째 짝이 생기면 아래 전수 셀이 실패한다.
_CEILINGS = {
    "projects/ActivityTimelinePage.tsx": "list_for_project",
    "me/PersonalHubPage.tsx": "list_for_projects",
}
_CEILING_DECLARATION = re.compile(r"const ACTIVITY_PAGE_SIZE = (\d+);")

#: ``key: "값",`` 한 줄. 라벨표·비링크표가 같은 모양이라 하나로 읽는다.
_ENTRY = re.compile(r'^\s{2}(\w+):\s*"(.*?)",\s*$', re.MULTILINE)
#: ``export const NAME: Record<string, string> = { … };`` 블록
_BLOCK = re.compile(
    r"export const (\w+)(?::[^=]+)? = \{(.*?)\n\};", re.DOTALL
)
#: ``export const NAME = ["a", "b"] as const;``
_ARRAY = re.compile(r'export const (\w+) = \[(.*?)\] as const;', re.DOTALL)


def _blocks() -> dict[str, dict[str, str]]:
    source = _UI_TABLE.read_text(encoding="utf-8")
    return {
        name: dict(_ENTRY.findall(body)) for name, body in _BLOCK.findall(source)
    }


def _arrays() -> dict[str, tuple[str, ...]]:
    source = _UI_TABLE.read_text(encoding="utf-8")
    return {
        name: tuple(re.findall(r'"(.*?)"', body))
        for name, body in _ARRAY.findall(source)
    }


class ActivityUiLabelTableTest(unittest.TestCase):
    """라벨표가 백엔드 분류표와 **전수로** 맞물리는가."""

    def test_the_ui_table_labels_exactly_the_logged_actions(self):
        """★ 양방향이다 — 백엔드가 늘어도, 프론트에 유령 행이 남아도 실패한다.

        under-strict: 백엔드에 21번째 ``logged`` route 가 생기면 라벨이 없어 실패.
        over-strict: 프론트에 백엔드가 모르는 리터럴이 남아 있어도 실패(오타·삭제된
        action 의 잔해). 둘 다 조용한 종류라 여기서만 보인다.
        """
        labels = _blocks()["ACTIVITY_ACTION_LABELS"]
        backend = {action.action for action in ACTIVITY_ACTIONS}

        self.assertEqual(
            set(labels), backend,
            "프론트 라벨표와 백엔드 분류표가 어긋났다 — 한쪽만 고치면 화면이 "
            "원문 리터럴로 폴백하고 아무도 모른다",
        )
        self.assertEqual(len(labels), len(LOGGED_OPERATIONS))

    def test_every_label_is_korean_prose_not_the_literal(self):
        """폴백을 라벨로 착각해 리터럴을 그대로 적어 두는 것을 막는다.

        ``activityActionLabel`` 이 미등재 시 원문을 돌려주므로, 라벨 칸에 리터럴을
        복사해 넣으면 **가드는 통과하는데 화면은 영어 스네이크**가 된다.
        """
        for action, label in _blocks()["ACTIVITY_ACTION_LABELS"].items():
            with self.subTest(action=action):
                self.assertNotEqual(label, action)
                self.assertRegex(label, r"[가-힣]")


class ActivityUiTargetTypeTest(unittest.TestCase):
    """링크 대상 분류가 **전수**인가 (S6). 미등재 ``target_type`` 은 실패다."""

    def test_every_target_type_is_classified_as_linkable_or_not(self):
        """새 ``target_type`` 이 백엔드에 생기면 화면이 판단을 강제받는다.

        ``activity/actions.py``·``quota/billable_actions.py`` 가 mutating route 를
        전수로 등재시키는 것과 같은 관례다 — **빠진 것과 일부러 뺀 것을 구분**한다.
        """
        arrays, blocks = _arrays(), _blocks()
        linkable = set(arrays["LINKABLE_TARGET_TYPES"])
        non_linkable = set(blocks["NON_LINKABLE_TARGET_TYPES"])
        backend = {action.target_type for action in ACTIVITY_ACTIONS}

        self.assertEqual(
            linkable | non_linkable, backend,
            "target_type 분류가 백엔드와 어긋났다 — 새 종류는 링크하거나 "
            "사유와 함께 비링크로 등재해야 한다",
        )
        self.assertEqual(
            linkable & non_linkable, set(),
            "같은 target_type 이 양쪽에 있다",
        )

    def test_each_non_linkable_target_type_carries_a_reason(self):
        """사유 없는 제외는 "빠뜨린 것"과 구분되지 않는다."""
        for target_type, reason in _blocks()["NON_LINKABLE_TARGET_TYPES"].items():
            with self.subTest(target_type=target_type):
                self.assertNotEqual(reason.strip(), "")


class ActivityCeilingClaimTest(unittest.TestCase):
    """화면이 말하는 상한 = 서버가 실제로 주는 상한인가 (S2=ⓐ · 9.2 P2).

    S2=ⓐ 가 요구한 것은 *"화면이 상한을 **문장으로** 말한다"* 까지이고 그 문장은 프론트
    셀이 잠근다. **그러나 두 수는 서로 모르는 독립 하드코딩이다** — 화면 상수와 서비스
    기본값. 서비스 기본이 바뀌면 화면이 **서빙 상한과 다른 수를 사용자에게 말하게 되는데**,
    문구는 남아 있으므로 프론트 셀도 백엔드 셀도 아무것도 못 본다.

    **★ 짝이 둘이다**(2026-08-10 검증 지적으로 넓혔다): 9.1 이 프로젝트별 화면 ↔
    ``list_for_project`` 를 묶었는데, 9.2 가 **허브라는 두 번째 상한**을 만들면서 그
    패턴을 따라가지 않았다 — 허브가 *"최근 100건"* 이라 말하며 50건만 주는 상태가 **어느
    셀도 안 무는 채로** 가능했다(실측). 그래서 **등재된 짝 전수**로 잰다.

    S4 라벨표가 받은 것과 **같은 종류의 연결선**이다: 나누는 것은 옳고(서빙 정책 ≠ UI
    문구), 나누되 **연결**한다.
    """

    def _declared(self, relative: str) -> int:
        found = _CEILING_DECLARATION.search(
            (_UI_SRC / relative).read_text(encoding="utf-8"))
        self.assertIsNotNone(
            found, f"{relative} 의 ACTIVITY_PAGE_SIZE 를 못 찾았다 — 이름이 "
                   "바뀌었으면 이 패턴도 함께 고친다")
        return int(found.group(1))

    def test_every_screen_promises_exactly_what_its_service_serves(self):
        """양방향 — 어느 쪽 수를 바꿔도 그 짝이 실패한다."""
        for relative, method_name in _CEILINGS.items():
            with self.subTest(screen=relative):
                served = inspect.signature(
                    getattr(ActivityLogService, method_name)
                ).parameters["limit"].default
                self.assertEqual(
                    self._declared(relative), served,
                    f"{relative} 이 약속하는 건수와 {method_name} 이 주는 건수가 "
                    "다르다 — 사용자에게 거짓 상한을 말하게 된다",
                )

    def test_no_screen_declares_a_ceiling_without_registering_it(self):
        """★ 세 번째 상한이 **조용히** 생기는 것을 막는다.

        9.2 가 정확히 그 형태였다 — 허브가 새 상수를 두고도 가드에 등재되지 않아
        짝이 풀린 채였다. 등재를 강제하면 다음 화면은 그 자리에서 걸린다.
        """
        declaring = {
            str(path.relative_to(_UI_SRC)).replace("\\", "/")
            for path in _UI_SRC.rglob("*.tsx")
            if _CEILING_DECLARATION.search(path.read_text(encoding="utf-8"))
        }

        self.assertEqual(
            declaring, set(_CEILINGS),
            "상한을 선언한 화면과 등재된 짝이 다르다 — 새 화면이 상한을 두면 "
            "어떤 서비스가 그것을 서빙하는지 여기 함께 적는다",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
