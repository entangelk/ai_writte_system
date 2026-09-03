"""B1 probe — 가시 roster 밖 pair 근거 차단의 행동 확인(Slice 3 검증).

계획 §Slice 3 완료 기록·SoT v1.8.25 리터럴 ③: ``identity_rationale_summary``는
"이 후보와 **가시 roster**를 잇는 ``same`` relation"에서만 온다. 13셀 어디도
"same relation의 상대가 검토함을 떠난(stale) 뒤에도 그룹이 살아 있는(가시 ≥2)
경우 → 근거는 ``null``" 분기를 잠그지 않는다(검증자 변이 VM1: 해당 필터를
지워도 13 passed). 이 probe는 행동이 계약대로임을 실측한다 — 빈 것은
잠금뿐이다(Slice 1 B1~B3·Slice 2 B1과 같은 모양). 폐쇄 셀의 본체로도 쓸 수 있다.

실행: python3 docs/verifications/2026-09-04/repro_rationale_out_of_roster.py
기대 출력: PROBE-OK: stale-pair relation은 근거가 되지 않는다 (rationale=None)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.test_review_inbox_identity_groups import (
    _build, _by_id, _items, _open_group, _same_relation, _seed_candidate,
)


def main() -> int:
    client, analysis, groups, _clock, project_id = _build()
    a = _seed_candidate(analysis, project_id=project_id, logical_key="a",
                        payload={"name": "Ariel", "observation": "brave"})
    b = _seed_candidate(analysis, project_id=project_id, logical_key="b",
                        payload={"name": "Ariel", "observation": "brave"})
    c = _seed_candidate(analysis, project_id=project_id, logical_key="c",
                        payload={"name": "Ariel", "observation": "brave"})
    _open_group(groups, project_id, a, b, c)
    _same_relation(groups, project_id, a, b, "judged while b was visible")
    rejected = client.post(
        f"/projects/{project_id}/analysis/candidates/{b.id}/reject"
    )
    assert rejected.status_code == 200, rejected.text

    items = _by_id(_items(client, project_id))

    # roster는 가시 {a, c} — 그룹은 살아 있다(가시 2명 ≥ 2).
    summary = items[a.id]["identity_group"]
    assert summary is not None, "가시 2명 그룹이 ungrouped로 읽혔다"
    assert summary["group_member_ids"] == sorted([a.id, c.id])
    # a-b same relation의 상대 b는 가시 roster 밖 — 근거가 될 수 없다.
    assert summary["identity_rationale_summary"] is None, (
        "가시 roster 밖 pair의 rationale이 새었다(정본 위반): "
        f"{summary['identity_rationale_summary']!r}"
    )
    print("PROBE-OK: stale-pair relation은 근거가 되지 않는다 (rationale=None)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
