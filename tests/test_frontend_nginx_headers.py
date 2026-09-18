"""프런트 nginx 응답 보안 헤더 (Phase S-2 · 감사 §A.12·§C, 2026-09-05).

감사가 실측한 것: ``frontend/nginx.conf`` 의 server 블록에 ``add_header`` 가
**0건**이라 CSP·X-Frame-Options·X-Content-Type-Options·Referrer-Policy 전무.
이 제품의 핵심 자산이 미공개 원고라 "응답 경화"는 미관이 아니라 방어축이다 —
프레이밍이 가능하면 로그인된 관리자를 클릭재킹으로 콘솔의 승인·승격·파기
버튼에 눌러 붙일 수 있다(SameSite=Lax 쿠키는 최상위 내비게이션에 실린다).

nginx 를 띄우지 않고 **설정 파일 자체**를 재는 이유는 test_compose_exposure
선례와 같다: 배포 조합이 파일로 결정되므로 파일이 그 계약의 정본이다.

여기가 **재지 않는 것** — CSP. 승인 전인 AdSense 크리에이티브 표면을 관측하기
전에는 안전한 script/frame/img 지시문을 쓸 수 없어 일부러 없다(nginx.conf
주석이 같은 사실을 적는다). CSP 를 더하는 날 이 파일에 축이 하나 늘어야 한다.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_CONF = Path(__file__).resolve().parents[1] / "frontend" / "nginx.conf"

#: 감사 권고의 세 헤더. 값은 계약 리터럴(변경은 명시적 결정이다).
_EXPECTED_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _server_level_block() -> str:
    """server 블록에서 중첩 블록(location 등)을 걷어 낸 나머지.

    nginx 의 ``add_header`` 상속 규칙이 이 가드의 두 번째 축이다 — location 이
    자기 ``add_header`` 를 하나라도 가지면 server 레벨 헤더를 물려받지
    **않는다**. 그래서 "헤더가 어딘가에 있다"만으로는 부족하고 **server 레벨에
    있다**(모든 location 이 물려받는 자리)를 재야 한다.

    정규식 한 방으로 location 을 지우는 시도는 greedy 매치가 location 사이의
    server 레범 지시문까지 삼켰다(이 파일을 짜는 자리에서 실제로 그랬다) —
    여기서 재는 것은 *중첩 구조*이므로 중첩을 아는 파서(괄호 깊이)로 센다.
    이 파일의 주석에는 중괄호가 없다는 전제로 줄별 깊이 계산이면 충분하다.
    """
    lines = _CONF.read_text(encoding="utf-8").splitlines()
    server_lines: list[str] = []
    depth = 0
    inside_server = False
    for line in lines:
        if not inside_server and re.match(r"^server\s*\{", line):
            inside_server = True
            continue
        if inside_server:
            depth += line.count("{") - line.count("}")
            if depth < 0:  # server 블록의 닫는 괄호
                break
            if depth == 0:
                # 최상위(= server 레벨) 지시문만 남긴다.
                server_lines.append(line)
    return "\n".join(server_lines)


def _location_block(path: str) -> str:
    """``location <path> {`` 블록 본문을 괄호 깊이로 추출한다.

    ``/api/`` 와 ``/api/admin/`` 을 구분하는 것도 이 정확 매치의 몫이다 —
    접두사 포함 매치로 잡으면 admin 블록의 상한을 잘못 읽는다.
    """
    lines = _CONF.read_text(encoding="utf-8").splitlines()
    body: list[str] = []
    depth = 0
    inside = False
    for line in lines:
        if not inside and re.match(rf"^\s*location {re.escape(path)} \{{", line):
            inside = True
            depth = 1
            continue
        if inside:
            body.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                break
    return "\n".join(body)


class FrontendNginxApiProxyTimeoutTest(unittest.TestCase):
    def test_api_proxy_timeout_sits_above_the_app_worst_case_budget(self) -> None:
        """2026-09-18 실측: 분석 POST /run 은 제공자 불안 구간에서 363s 를
        버티고 **성공**했는데 nginx 의 120s 가 먼저 끊어 브라우저는 504 를 받았다.
        프록시 상한은 앱의 자체 최악 예산(체인 예산 300s × 런당 LLM 호출 ~5회 =
        1500s)보다 높아야 한다 — nginx.conf 의 산술 주석과 같은 근거다.

        under-strict: 120s 로 되돌리면 실패한다.
        over-strict: 상한을 1500s 미만으로 낮춰도 같은 셀이 실패한다.
        LLAMA_TIMEOUT_SECONDS(배포 300s)를 올리면 이 셀이 먼저 깨져 nginx 를
        다시 맞추도록 강제한다.
        """
        block = _location_block("/api/")
        for directive in ("proxy_read_timeout", "proxy_send_timeout"):
            with self.subTest(directive=directive):
                match = re.search(rf"{directive}\s+(\d+)s;", block)
                self.assertIsNotNone(
                    match, f"{directive} 가 /api/ 블록에 없다")
                self.assertGreaterEqual(
                    int(match.group(1)), 1500,
                    "프록시 상한이 앱 최악 예산(300s × 5)보다 낮다 — "
                    "성공할 run 을 504 로 뒤집는다(2026-09-18 실측)",
                )


class FrontendNginxSecurityHeadersTest(unittest.TestCase):
    def test_the_three_audit_headers_are_present_at_the_server_level(self) -> None:
        """under-strict: 헤더가 없거나 location 안에 갇혀 있으면 실패한다."""
        server_level = _server_level_block()
        for header, value in _EXPECTED_HEADERS.items():
            with self.subTest(header=header):
                self.assertIn(
                    f'add_header {header} "{value}"', server_level,
                    f"{header} 가 server 레벨에 없다(또는 값이 다르다) — "
                    "location 블록 안으로 옮겨졌다면 상속이 끊겨 그 location 의 "
                    "응답에서 사라진다",
                )

    def test_every_security_header_carries_always_so_errors_are_covered(self) -> None:
        """오류 응답도 헤더를 달아야 한다.

        ``always`` 가 없으면 nginx 는 200/204/301 등 "정상" 상태에만 헤더를
        붙인다 — 프록시되는 API 의 401/422/500 이 헤드리스로 나가고, 그 응답들이
        정확히 인증을 다루는 응답들이다. under-strict: ``always`` 를 떼면
        실패한다. over-strict: 정상 상태 전용 문법(``expires`` 등)은 여기 안
        걸린다.
        """
        server_level = _server_level_block()
        for header in _EXPECTED_HEADERS:
            with self.subTest(header=header):
                self.assertRegex(
                    server_level,
                    rf'add_header {header} "[^"]+" always;',
                    f"{header} 에 always 가 없다 — 오류 응답에서 헤더가 빠진다",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
