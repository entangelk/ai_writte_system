import unittest
from datetime import UTC, datetime

from services.application.app.context_search.gate_findings import (
    GateFindingService, GateFindingStatus, InMemoryGateFindingRepository,
    InvalidGateFindingTransition,
)
from services.application.app.context_search.models import (
    ContextBudget, ContextNeed, ContextPackage, ContextSearchPurpose,
    ContextSearchRequest, GateDecision, GateFinding,
)


def request(project="p"):
    return ContextSearchRequest(
        project_id=project, purpose=ContextSearchPurpose.WRITING_CONTEXT,
        needs=(ContextNeed.CURRENT_SCENE,), query="continue",
        current_position=None, context_budget=ContextBudget(max_tokens=100),
    )


def package(project="p"):
    return ContextPackage(
        project_id=project, purpose=ContextSearchPurpose.WRITING_CONTEXT,
        macro_items=(), micro_evidence=(), constraints=(), do_not_use=(),
        token_estimate_total=0, degraded=False,
    )


class GateFindingServiceTest(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryGateFindingRepository()
        self.service = GateFindingService(
            self.repo, clock=lambda: datetime(2026, 7, 12, tzinfo=UTC)
        )

    def test_pass_is_not_stored_and_reject_replay_is_idempotent(self):
        self.assertEqual(self.service.persist_rejection(
            request=request(), idempotency_key="run-1", package=package(),
            gate=GateDecision(decision="pass"),
        ), ())
        gate = GateDecision(decision="reject", findings=(
            GateFinding(check="stale_item", detail="stale"),
            GateFinding(check="budget_exceeded", detail="large"),
        ))
        first = self.service.persist_rejection(
            request=request(), idempotency_key="run-1", package=package(), gate=gate
        )
        replay = self.service.persist_rejection(
            request=request(), idempotency_key="run-1", package=package(), gate=gate
        )
        self.assertEqual(tuple(item.id for item in first), tuple(item.id for item in replay))
        self.assertEqual(len(self.repo.entries), 2)
        self.assertTrue(all(item.request_fingerprint for item in first))
        self.assertTrue(all(item.result_fingerprint for item in first))

    def test_project_scope_and_terminal_transitions(self):
        [finding] = self.service.persist_rejection(
            request=request("p1"), idempotency_key="same", package=package("p1"),
            gate=GateDecision(decision="reject", findings=(
                GateFinding(check="x", detail="y"),
            )),
        )
        [other] = self.service.persist_rejection(
            request=request("p2"), idempotency_key="same", package=package("p2"),
            gate=GateDecision(decision="reject", findings=(
                GateFinding(check="x", detail="y"),
            )),
        )
        self.assertNotEqual(finding.id, other.id)
        resolved, replay = self.service.transition(
            project_id="p1", finding_id=finding.id,
            target=GateFindingStatus.RESOLVED,
        )
        self.assertFalse(replay)
        self.assertEqual(resolved.status, GateFindingStatus.RESOLVED)
        _, replay = self.service.transition(
            project_id="p1", finding_id=finding.id,
            target=GateFindingStatus.RESOLVED,
        )
        self.assertTrue(replay)
        with self.assertRaises(InvalidGateFindingTransition):
            self.service.transition(
                project_id="p1", finding_id=finding.id,
                target=GateFindingStatus.DISMISSED,
            )
