"""리랭커 seam·데코레이터·어댑터 회귀 — 리랭커 슬라이스 결정 2=A · 3=A · 4-①.

**결정 4-① 이 이번 슬라이스에서 잠그기로 한 것은 품질이 아니라 배선·안전성 셋이다**:
① 리랭커가 **순서를 실제로 바꾸는가** ② **끌 수 있는가**(감싸지 않으면 없다)
③ **리랭커가 실패해도 검색이 죽지 않는가**. 품질 판정(*"좋아졌는가"*)은 dogfood 뒤이며
이 파일은 그것을 재지 않는다 — 재는 척도 하지 않는다.

**★ 평가셋을 여기 넣지 않는다.** 브리프 결정 4-② 의 경계다: 정답을 회귀에 넣으면
그 정답이 잠기고, 그것이 바로 4-② 가 피하려는 편향이다(구현자가 채점표를 만들면
*"리랭커가 좋은가"* 가 아니라 *"리랭커가 구현자 생각과 같은가"* 를 재게 된다).
"""

from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

import httpx

from services.application.app.context_search.rerank import (
    HttpRerankProvider,
    RerankingRetriever,
    RerankProviderError,
    build_rerank_provider_from_env,
)

_ROOT = Path(__file__).resolve().parent.parent


class _Inner:
    """순서를 확인할 수 있게 항목이 곧 글자인 최소 retriever."""

    def __init__(self, items):
        self.items = tuple(items)
        self.calls = []

    def retrieve(self, *, project_id, query, limit):
        self.calls.append({"project_id": project_id, "query": query, "limit": limit})
        return self.items


class _Provider:
    def __init__(self, order=None, error=None):
        self._order = order
        self._error = error
        self.seen = []

    def rerank(self, *, query, documents):
        self.seen.append({"query": query, "documents": list(documents)})
        if self._error is not None:
            raise self._error
        return self._order


def _wrapped(items, provider):
    inner = _Inner(items)
    return inner, RerankingRetriever(
        inner=inner, provider=provider, text_of=lambda item: f"본문:{item}"
    )


class ReorderingTest(unittest.TestCase):
    """① 순서를 실제로 바꾸는가."""

    def test_the_returned_order_follows_the_provider(self):
        provider = _Provider(order=(2, 0, 1))
        inner, retriever = _wrapped(("a", "b", "c"), provider)

        result = retriever.retrieve(project_id="p1", query="아린", limit=8)

        self.assertEqual(result, ("c", "a", "b"))
        # 안쪽 seam 은 그대로 통과한다 — 데코레이터는 질의도 limit 도 안 바꾼다.
        self.assertEqual(inner.calls, [{"project_id": "p1", "query": "아린", "limit": 8}])

    def test_the_provider_reads_the_projection_the_index_used(self):
        """리랭커가 색인이 본 것과 **같은 글**을 읽어야 비교가 성립한다."""
        provider = _Provider(order=(0, 1))
        _, retriever = _wrapped(("a", "b"), provider)

        retriever.retrieve(project_id="p1", query="아린은 누구인가", limit=8)

        self.assertEqual(provider.seen[0]["query"], "아린은 누구인가")
        self.assertEqual(provider.seen[0]["documents"], ["본문:a", "본문:b"])

    def test_nothing_to_reorder_never_reaches_the_provider(self):
        # 0·1개는 순서가 하나뿐이다. 부르면 요금만 나간다.
        for items in ((), ("only",)):
            with self.subTest(size=len(items)):
                provider = _Provider(order=())
                _, retriever = _wrapped(items, provider)
                self.assertEqual(
                    retriever.retrieve(project_id="p", query="q", limit=8), items)
                self.assertEqual(provider.seen, [])


class FailOpenTest(unittest.TestCase):
    """③ 리랭커가 실패해도 검색이 죽지 않는가.

    재정렬은 품질 향상이지 정확성 요건이 아니다 — 그것 때문에 검색이 죽으면 손해가
    이득보다 크다. 그래서 **모든 실패가 원래 순서로 떨어진다.**
    """

    def test_a_provider_error_returns_the_original_order(self):
        provider = _Provider(error=RerankProviderError("down"))
        _, retriever = _wrapped(("a", "b", "c"), provider)
        self.assertEqual(
            retriever.retrieve(project_id="p", query="q", limit=8), ("a", "b", "c"))

    def test_a_response_that_is_not_a_permutation_returns_the_original_order(self):
        """부분 응답(`top_n`)을 그대로 받으면 **검색 결과가 조용히 줄어든다.**

        그것은 재정렬이 아니라 필터링이고 이 seam 이 약속한 일이 아니다. 항목이
        빠지거나 겹치는 응답은 전부 같은 이유로 fail-open 한다.
        """
        cases = {
            "짧다(top_n 응답)": (1, 0),
            "길다": (0, 1, 2, 0),
            "중복": (0, 0, 1),
            "범위 밖": (0, 1, 7),
            "빈 응답": (),
        }
        for name, order in cases.items():
            with self.subTest(response=name):
                _, retriever = _wrapped(("a", "b", "c"), _Provider(order=order))
                self.assertEqual(
                    retriever.retrieve(project_id="p", query="q", limit=8),
                    ("a", "b", "c"))


class FailOpenScopeTest(unittest.TestCase):
    """★ fail-open 은 프로바이더가 아니라 **이 단계 전체**를 덮는다 (검증 조건 C1).

    종전에는 `RerankProviderError` 만 잡아서 **텍스트 투영이 던지면 검색 경로가
    죽었다.** 투영은 이 슬라이스가 검색 경로에 **새로 넣은 호출**이므로 그 길도 이
    슬라이스가 만든 것이다 — 독립 검증이 런타임으로 실증했고 그것이 조건이었다.

    셀 문언이 *"모든 실패가 원래 순서로 떨어진다"* 라고 단정했는데 잠금은 프로바이더
    하나였다 — **계약 문언이 잠금보다 넓은 실수의 네 번째다**(오늘 앞선 셋: 정본
    산출물 문언 · 셀 실패 메시지 · 조립 가드). 네 번 다 폐쇄는 **검사를 넓히는 쪽**이다.
    """

    def _raising_text_of(self, exception):
        def text_of(_item):
            raise exception
        return text_of

    def test_a_projection_failure_returns_the_original_order(self):
        for exception in (ValueError("bad payload"), KeyError("name"),
                          TypeError("not a memory")):
            with self.subTest(raised=type(exception).__name__):
                inner = _Inner(("a", "b", "c"))
                retriever = RerankingRetriever(
                    inner=inner, provider=_Provider(order=(2, 1, 0)),
                    text_of=self._raising_text_of(exception))
                self.assertEqual(
                    retriever.retrieve(project_id="p", query="q", limit=8),
                    ("a", "b", "c"))

    def test_a_provider_raising_something_unexpected_still_fails_open(self):
        # 어댑터가 RerankProviderError 로 감싸지 못한 예외를 흘릴 수 있다.
        _, retriever = _wrapped(("a", "b"), _Provider(error=RuntimeError("boom")))
        self.assertEqual(
            retriever.retrieve(project_id="p", query="q", limit=8), ("a", "b"))

    def test_the_fallback_is_logged_rather_than_swallowed(self):
        """★ fail-open 이 조용하면 리랭킹이 영원히 no-op 인 채로 아무도 모른다.

        오늘 이 저장소가 네 번 만난 실패 모양(*"green 이 말하지 않은 것"*)이 정확히
        그것이다. 그래서 경계는 넓히되 **로그는 남긴다** — `activity/log.py` 의
        A4=A 격리 경계와 같은 형태다.
        """
        _, retriever = _wrapped(("a", "b"), _Provider(error=RuntimeError("boom")))
        with self.assertLogs(
                "services.application.app.context_search.rerank", level="WARNING"
        ) as captured:
            retriever.retrieve(project_id="p", query="q", limit=8)
        self.assertIn("reranking failed", captured.output[0])
        # 원인이 남아야 한다 — 메시지만 있으면 무엇이 터졌는지 모른다.
        self.assertIn("RuntimeError", captured.output[0])

    def test_a_response_that_is_not_a_permutation_is_logged_too(self):
        """순열 검사가 `try` **안**에 있다는 주장의 관측 가능한 차이가 이것이다.

        계약(fail-open)은 검사가 경계 **밖**에 있어도 만족한다 — 두 배치의 반환값이
        같기 때문이다(둘 다 원래 순서). 갈리는 것은 **로그뿐**이고, 그래서 이 경로가
        조용하면 *"한 곳에서 떨어진다"* 는 서술을 아무도 확인할 수 없다
        (2026-08-21 검증이 관측으로 남긴 자리).
        """
        _, retriever = _wrapped(("a", "b", "c"), _Provider(order=(1, 0)))
        with self.assertLogs(
                "services.application.app.context_search.rerank", level="WARNING"
        ) as captured:
            self.assertEqual(
                retriever.retrieve(project_id="p", query="q", limit=8),
                ("a", "b", "c"))
        self.assertIn("reranking failed", captured.output[0])
        # 원인이 "순열이 아니다" 로 남아야 한다 — 프로바이더 장애와 구별되지 않으면
        # 운영에서 부분 응답(`top_n`)을 장애로 오진한다.
        self.assertIn("not a permutation", captured.output[0])

    def test_a_healthy_reranking_logs_nothing(self):
        # over-strict: 정상 경로가 경고를 내면 로그가 곧 소음이 되고 아무도 안 본다.
        import logging as _logging

        _, retriever = _wrapped(("a", "b"), _Provider(order=(1, 0)))
        with self.assertNoLogs(
                "services.application.app.context_search.rerank",
                level=_logging.WARNING):
            self.assertEqual(
                retriever.retrieve(project_id="p", query="q", limit=8), ("b", "a"))


class SwitchedOffTest(unittest.TestCase):
    """② 끌 수 있는가 — 주소가 없으면 조립이 감싸지 않는다."""

    def setUp(self):
        self._saved = {
            name: os.environ.pop(name, None)
            for name in ("RERANK_API_URL", "RERANK_API_MODEL", "RERANK_API_KEY",
                         "RERANK_TIMEOUT_SECONDS", "RERANK_TRUST_ENV")
        }

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_no_address_means_no_provider_at_all(self):
        """`None` 이 정상값이다 — 로컬 기본은 no-op 이다(결정 2=A).

        임베딩 헬퍼가 fake 로 내려가는 것과 다르다: 리랭킹에는 "가짜 재정렬" 이라는
        쓸모 있는 대체물이 없고, 무작위로 섞는 것은 no-op 보다 나쁘다.
        """
        self.assertIsNone(build_rerank_provider_from_env())

    def test_an_address_without_a_model_fails_fast(self):
        # 모델은 요청마다 보내므로 기본값이 있을 수 없다.
        os.environ["RERANK_API_URL"] = "https://rerank.example.com"
        with self.assertRaises(ValueError) as raised:
            build_rerank_provider_from_env()
        self.assertIn("RERANK_API_MODEL", str(raised.exception))

    def test_a_configured_address_builds_the_http_adapter(self):
        os.environ["RERANK_API_URL"] = "https://rerank.example.com/v1"
        os.environ["RERANK_API_MODEL"] = "rerank-v3"
        os.environ["RERANK_API_KEY"] = "sk-r"
        provider = build_rerank_provider_from_env()
        self.assertIsInstance(provider, HttpRerankProvider)
        # 벤더 문서가 인쇄하는 접미 `/v1` 은 벗긴다(임베딩과 같은 관례).
        self.assertEqual(provider._base_url, "https://rerank.example.com")
        self.assertEqual(provider._model, "rerank-v3")

    def test_a_v1_inside_the_path_is_not_stripped(self):
        # over-strict: 접미가 아닌 `v1` 은 주소의 일부다.
        os.environ["RERANK_API_URL"] = "https://proxy.example.com/v1/rerankers"
        os.environ["RERANK_API_MODEL"] = "m"
        self.assertEqual(
            build_rerank_provider_from_env()._base_url,
            "https://proxy.example.com/v1/rerankers")


def _adapter(handler, **kwargs):
    kwargs.setdefault("model", "rerank-v3")
    return HttpRerankProvider(
        base_url="https://rerank.example.com",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


class HttpRerankProviderTest(unittest.TestCase):
    """generic rerank wire — Cohere 가 낸 형태(Jina·Voyage·TEI 가 같은 모양)."""

    def test_posts_the_rerank_shape_and_returns_indices_best_first(self):
        seen = {}

        def handler(request):
            import json as _json
            seen["path"] = request.url.path
            seen["body"] = _json.loads(request.read().decode())
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"results": [
                {"index": 0, "relevance_score": 0.2},
                {"index": 1, "relevance_score": 0.9},
            ]})

        order = _adapter(handler, api_key="sk-r").rerank(
            query="아린", documents=["가", "나"])

        self.assertEqual(seen["path"], "/v1/rerank")
        self.assertEqual(seen["body"], {
            "model": "rerank-v3", "query": "아린", "documents": ["가", "나"]})
        self.assertEqual(seen["auth"], "Bearer sk-r")
        # 서버가 점수 순으로 안 보내줘도 우리가 정렬한다 — 계약이 순서를 약속하지 않는다.
        self.assertEqual(order, (1, 0))

    def test_no_api_key_sends_no_authorization_header(self):
        seen = {}

        def handler(request):
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"results": [
                {"index": 0, "relevance_score": 1.0}]})

        _adapter(handler).rerank(query="q", documents=["가"])
        self.assertIsNone(seen["auth"])

    def test_transport_and_status_failures_map_to_rerank_error(self):
        def timeout(_request):
            raise httpx.ConnectTimeout("slow")

        def refused(_request):
            raise httpx.ConnectError("refused")

        def rate_limited(_request):
            return httpx.Response(429, json={"message": "slow down"})

        for name, handler in (("timeout", timeout), ("refused", refused),
                              ("429", rate_limited)):
            with self.subTest(failure=name):
                with self.assertRaises(RerankProviderError):
                    _adapter(handler).rerank(query="q", documents=["가", "나"])

    def test_the_error_message_carries_the_status_and_not_the_body(self):
        def handler(_request):
            return httpx.Response(400, json={"message": "bad request: 아린은 항구에"})

        with self.assertRaises(RerankProviderError) as raised:
            _adapter(handler).rerank(query="q", documents=["아린은 항구에", "나"])
        self.assertIn("400", str(raised.exception))
        self.assertNotIn("아린은 항구에", str(raised.exception))

    def test_malformed_bodies_are_rejected_rather_than_coerced(self):
        cases = {
            "not json": httpx.Response(200, content=b"nope"),
            "not an object": httpx.Response(200, json=[1, 2]),
            "no results": httpx.Response(200, json={"meta": {}}),
            "results holds scalars": httpx.Response(200, json={"results": [1]}),
            "index missing": httpx.Response(
                200, json={"results": [{"relevance_score": 1.0}]}),
            "index out of range": httpx.Response(
                200, json={"results": [{"index": 9, "relevance_score": 1.0}]}),
            # bool 은 int 의 하위형이라 걸러내지 않으면 인덱스 0/1 로 들어온다.
            "index is bool": httpx.Response(
                200, json={"results": [{"index": True, "relevance_score": 1.0}]}),
            "score missing": httpx.Response(200, json={"results": [{"index": 0}]}),
            "score is string": httpx.Response(
                200, json={"results": [{"index": 0, "relevance_score": "1.0"}]}),
        }
        for name, response in cases.items():
            with self.subTest(body=name):
                with self.assertRaises(RerankProviderError):
                    _adapter(lambda _r, _resp=response: _resp).rerank(
                        query="q", documents=["가", "나"])

    def test_ties_keep_the_response_order(self):
        """동률에서 잠그는 성질은 **"같은 응답이 언제나 같은 순서를 낸다"** 하나다.

        **★ "요청 순서 유지" 가 아니다** — 안정 정렬이 보존하는 것은 **응답에 담긴
        순서**이고, 요청 순서와 겹치는 것은 정합 서버가 동률을 요청 순서로 보내 줄
        때뿐이다(계약은 그것을 약속하지 않는다). 2026-08-20 검증 H2 가 주석을 그렇게
        정정했고, **셀 이름과 입력에는 정정 전 문언이 남아 있었다**(2026-08-21 검증
        H2-a·H2-b). 그래서 이름을 성질에 맞추고 **두 해석이 갈리는 입력**을 더한다 —
        종전 입력은 둘이 우연히 겹쳐서 어느 쪽을 잠갔는지 구별하지 못했다.
        """
        def _handler(indices):
            def handler(_request):
                return httpx.Response(200, json={"results": [
                    {"index": index, "relevance_score": 0.5} for index in indices
                ]})
            return handler

        cases = {
            # 두 해석이 겹치는 입력(종전 셀). 회귀로 남긴다.
            "응답이 요청 순서로 왔다": ((0, 1, 2), (0, 1, 2)),
            # ★ 갈리는 입력. 요청 순서를 잠그고 있었다면 여기서 실패한다.
            "응답이 다른 순서로 왔다": ((2, 0, 1), (2, 0, 1)),
        }
        for name, (response_order, expected) in cases.items():
            with self.subTest(response=name):
                self.assertEqual(
                    _adapter(_handler(response_order)).rerank(
                        query="q", documents=["가", "나", "다"]),
                    expected)


class AssemblyGuardTest(unittest.TestCase):
    """감싸기를 빠뜨려도 스위트는 green 이고 **배포에서만 검색이 조용히 나빠진다**.

    이 저장소는 정확히 그 사고를 `ObservedProvider` 로 겪었고 처방이 조립 가드였다
    (브리프 결정 3 이 A 의 단점으로 적어 둔 자리이기도 하다). 리랭커는 더 조용하다 —
    계측이 사라지면 대시보드가 비지만, **재정렬이 사라지면 아무것도 비지 않고 순위만
    예전으로 돌아간다.**

    등재 목록이 아니라 **AST 로 조립 함수를 직접 본다** — 임베딩 조립 가드에서 배운
    형태다(목록은 새 자리 등재를 잊으면 침묵한다).
    """

    ASSEMBLY = _ROOT / "services" / "application" / "app" / "main.py"

    #: 리랭킹이 걸려야 하는 조립 함수. 여기 없는 세 번째 검색 계열이 생기면
    #: `test_every_retriever_assembly_is_listed` 가 문다.
    WRAPPED = ("_build_canonical_memory_retriever", "_build_candidate_memory_retriever")

    def _functions(self):
        tree = ast.parse(self.ASSEMBLY.read_text(encoding="utf-8"))
        return {node.name: node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)}

    def test_both_assembly_sites_go_through_the_wrapper(self):
        """under-strict: 한 자리라도 감싸기를 잃으면 이 셀이 실패한다."""
        functions = self._functions()
        for name in self.WRAPPED:
            with self.subTest(assembly=name):
                self.assertIn(name, functions, "조립 함수가 사라졌거나 이름이 바뀌었다")
                calls = {
                    node.func.id for node in ast.walk(functions[name])
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                }
                self.assertIn(
                    "_rerank_wrapped", calls,
                    f"{name} 이 리랭킹을 안 씌운다 — 감싸지 않으면 검색이 조용히 "
                    "예전 순위로 돌아간다")

    def test_every_retriever_assembly_is_listed(self):
        """새 검색 계열이 목록에 조용히 안 빠지게 한다.

        `_build_*_memory_retriever` 를 이름으로 훑어, 위 목록에 없는 것이 생기면
        분류를 강요한다. "세 번째 compose 파일" 계열의 같은 처방이다.
        """
        found = {
            name for name in self._functions()
            if name.startswith("_build_") and name.endswith("_memory_retriever")
        }
        self.assertEqual(
            found, set(self.WRAPPED),
            "새 retriever 조립 함수다 — WRAPPED 에 넣어 리랭킹을 씌우거나, "
            "안 씌우는 이유를 여기 적는다")

    def test_the_wrapper_is_the_only_place_that_builds_the_decorator(self):
        """조립이 데코레이터를 직접 만들면 끄기 경로가 둘이 된다.

        ★ 별칭(`import … as RR`)과 모듈 속성(`rerank.RerankingRetriever(…)`)까지
        센다 — 원이름만 보던 초판은 둘 다 침묵했다(2026-08-20 검증 H1). 임베딩
        조립 가드가 **같은 날** B1 으로 배운 것인데 이 파일에 적용되지 않았다:
        **한 곳에서 배운 것은 같은 형태의 다른 가드에도 옮겨야 한다.**

        **잔여는 임베딩 가드와 같다** — 할당 별칭(`X = RerankingRetriever; X()`)은
        안 잡는다. 이름 재결합 추적은 타입체커의 일이다.
        """
        tree = ast.parse(self.ASSEMBLY.read_text(encoding="utf-8"))
        names = {"RerankingRetriever"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "RerankingRetriever" and alias.asname:
                        names.add(alias.asname)
        builders = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and (
                (isinstance(node.func, ast.Name) and node.func.id in names)
                or (isinstance(node.func, ast.Attribute)
                    and node.func.attr == "RerankingRetriever")
            )
        ]
        self.assertEqual(
            len(builders), 1,
            "RerankingRetriever 는 _rerank_wrapped 안에서만 만든다 — "
            "별칭·모듈 속성 호출도 같은 자리다")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
