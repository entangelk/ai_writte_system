"""Code-fence extraction guard for the shared terminal-JSON helper.

2026-08-23 extractor slice: ``gemma-4-31b-it`` wraps JSON in a ```json fence by
habit, and when the output hits the token ceiling the *closing* fence is what
gets cut — the JSON body may already be complete. ``strip_code_fence`` learned
to unwrap that shape; this file pins both directions so the guard cannot
silently regress or over-relax.
"""

from __future__ import annotations

import unittest

from services.application.app.writing.json_extract import strip_code_fence


class WholeFenceTest(unittest.TestCase):
    """기존 동작 — 전체가 하나의 완전한 펜스일 때만 벗긴다."""

    def test_a_complete_fence_with_language_tag_is_stripped(self):
        # under-strict: 완전 펜스 처리를 잃으면 이 셀이 문다 (v1.6.86 이래 계약).
        self.assertEqual(
            strip_code_fence('```json\n{"a": 1}\n```'), '{"a": 1}'
        )

    def test_a_complete_fence_without_language_tag_is_stripped(self):
        self.assertEqual(strip_code_fence('```\n{"a": 1}\n```'), '{"a": 1}')

    def test_unfenced_json_passes_through_verbatim(self):
        self.assertEqual(strip_code_fence('{"a": 1}'), '{"a": 1}')


class OpenFenceTest(unittest.TestCase):
    """신규(2026-08-23) — 닫는 펜스가 상한 끊김으로 없는 형태."""

    def test_an_open_fence_with_complete_json_body_is_recovered(self):
        # under-strict: 열린 펜스 회복을 없애면(원복) 이 셀이 문다 — 그것이
        # 배포 서버·알파 관통에서 후보 0을 만든 경로다.
        self.assertEqual(
            strip_code_fence('```json\n{"candidates": []}'), '{"candidates": []}'
        )

    def test_an_open_fence_with_truncated_json_is_not_recovered(self):
        # over-strict 방향 ①: JSON 본문 자체가 끊긴 것은 회복 대상이 아니다 —
        # 성급한 부분 salvage가 strict 검사를 우회하게 둬선 안 된다.
        self.assertEqual(
            strip_code_fence('```json\n{"candidates": [{"a": 1'),
            '```json\n{"candidates": [{"a": 1',
        )

    def test_an_open_fence_with_trailing_prose_is_not_recovered(self):
        # over-strict 방향 ②: 선두 펜스 뒤에 prose가 붙은 경우 전체가 하나의
        # JSON 문서가 아니므로 벗기지 않는다 — prose 구제는 relaxation이다.
        content = '```json\n{"a": 1}\n\nSorry, here is the JSON above.'
        self.assertEqual(strip_code_fence(content), content)


if __name__ == "__main__":
    unittest.main()
