"""Client IP 해석 — ``X-Forwarded-For`` 신뢰 정책(Phase S-3, 오너 2026-09-05 = C).

2026-08-22 의 브루트포스 가드(P-6)는 축을 **username** 으로 골랐고, IP 축은
*"nginx 경유(5520)와 직접(8520)의 `X-Forwarded-For` 신뢰가 갈려"* 유예했다
(`docs/plans/auth-signup-approval-decisions.md:92-96`·`:136`). signup 은
username 이 매번 다른 것이 공격 그 자체라 P-6 축을 재사용할 수 없어서, 오너가
이 모듈로 그 유예를 닫았다(`docs/plans/security-phase-s3-signup-throttle-decisions.md`).

**규칙은 하나다 — 헤더는 스스로를 증명하지 못하므로, 헤더를 붙인 홉을 믿을 때만
읽는다.**

1. 소켓의 상대(``peer``)가 신뢰 대역 밖이면 **직결**이다. ``X-Forwarded-For`` 는
   상대가 지어낸 문자열이므로 **통째로 버리고** ``peer`` 를 쓴다.
2. 상대가 신뢰 대역 안이면 리버스 프록시다. XFF 를 **오른쪽에서 왼쪽으로** 걸으며
   신뢰 대역에 드는 항목(= 우리 쪽 홉이 붙인 것)을 건너뛰고, **처음 만나는 신뢰
   밖 주소**를 클라이언트로 본다.
3. 전부 신뢰 대역이거나 XFF 가 없으면 ``peer`` 로 떨어진다.

**왜 오른쪽인가 — 2026-09-05 배포 실측.** 공개 도메인으로 위조 헤더를 보내면
origin nginx 에 이렇게 도착한다::

    curl -H 'X-Forwarded-For: 1.2.3.4' https://<배포 도메인>/…
    → "1.2.3.4,<진짜 클라이언트 IP>"

Cloudflare 엣지는 클라이언트가 보낸 XFF 를 **지우지 않고 오른쪽에 진짜 주소를
덧붙인다.** 즉 **왼쪽은 공격자가 고르고, 오른쪽 끝만 참이다.** 왼쪽을 읽는 흔한
구현(`xff.split(",")[0]`)은 요청마다 다른 버킷을 고를 수 있게 해줘서 IP 축
레이트리밋을 **조용히 0으로 만든다** — 이 모듈이 존재하는 이유다.

같은 실측에서 ``CF-Connecting-IP`` 를 클라이언트가 보내면 엣지가 **403 으로
거절**했다. 그쪽이 더 단단해 보이지만 채택하지 않았다: 그 단단함은 Cloudflare
설정에서 오고 이 저장소가 검증할 수 없는 반면, 위 규칙은 **경로를 몰라도**
성립한다(터널·LAN 직결·프록시 없는 개발 모두 같은 코드).
"""

from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Iterable

# 신뢰 대역 기본값. compose 네트워크(``172.16.0.0/12``)와 loopback 뿐이다 —
# 이 앱 앞에 정당하게 설 수 있는 홉은 같은 compose 네트워크의 frontend nginx
# 하나이고, 그 컨테이너 주소는 재기동마다 바뀌므로 대역으로 잡는다.
#
# **LAN 대역(10/8·192.168/16)은 일부러 빼 뒀다.** 배포 앱은 ``0.0.0.0:8520`` 으로
# 게시돼 있어(D8-7 G1=C, 의도) LAN 에서 nginx 를 우회해 직접 닿을 수 있는데,
# 2026-09-05 실측에서 그 경로의 ``peer`` 는 **SNAT 되지 않고 발신자 주소 그대로**
# 도착했다. 그러니 LAN 을 신뢰 대역에 넣지 않는 한 규칙 1이 걸려 XFF 가 버려지고
# 우회가 성립하지 않는다. 넣는 순간 LAN 의 누구나 자기 버킷을 고를 수 있다.
DEFAULT_TRUSTED_PROXY_CIDRS = ("127.0.0.0/8", "::1/128", "172.16.0.0/12")

# peer 조차 없을 때(ASGI 가 client 를 안 주는 테스트·유닉스 소켓) 쓰는 버킷.
# None 을 돌려주면 호출자마다 "그럼 통과시킬까"를 다시 판단하게 되므로, 여기서
# **하나의 공유 버킷**으로 접는다 — 알 수 없는 발신자끼리 서로를 제한한다.
UNKNOWN_CLIENT = "unknown"


class ClientIpResolver:
    """신뢰 대역을 들고 다니는 해석기. 대역은 기동 시 한 번 파싱한다."""

    def __init__(self, trusted_cidrs: Iterable[str] = DEFAULT_TRUSTED_PROXY_CIDRS) -> None:
        # 깨진 CIDR 는 기동 거부다. 조용히 무시하면 "신뢰 대역이 비었다" = 모든
        # 요청이 직결 취급 = 프록시 뒤 전원이 한 버킷이 되고, 그 상태는 로그로
        # 구분되지 않는다(``AUTH_LOGIN_MAX_FAILURES`` 파싱과 같은 자세).
        self._trusted = tuple(ip_network(cidr, strict=False) for cidr in trusted_cidrs)

    def _is_trusted(self, raw: str) -> bool:
        try:
            address = ip_address(raw)
        except ValueError:
            return False
        return any(address in network for network in self._trusted)

    def resolve(self, *, peer: str | None, forwarded_for: str | None) -> str:
        if not peer:
            return UNKNOWN_CLIENT
        if not self._is_trusted(peer):
            # 직결. 상대가 보낸 XFF 는 상대가 지어낸 것이므로 읽지 않는다.
            return peer
        for entry in reversed((forwarded_for or "").split(",")):
            candidate = entry.strip()
            if not candidate:
                continue
            if self._is_trusted(candidate):
                # 우리 쪽 홉이 붙인 주소다. 계속 왼쪽으로 간다.
                continue
            try:
                ip_address(candidate)
            except ValueError:
                # 형식이 아닌 항목은 신뢰 밖으로 보지 않고 **버린다**. 여기서
                # 멈추면 공격자가 쓰레기 한 글자로 자기 버킷을 만들 수 있다.
                continue
            return candidate
        return peer
