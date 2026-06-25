"""Contract tests for flat agent loop tool registry and signatures.

Locks AgentLoopRunner A2 from docs/plans/flat-loop-gate.md (§Domain Tool
Registry 계약). The guard is two-directional: invalid or out-of-profile tool
calls must not reach handlers, while valid calls keep their JSON type/value and
produce stable signatures without over-collapsing distinct arguments.

Scope: this slice covers registry construction, strict argument validation, and
signature normalization only. Mapping blocked/invalid outcomes into the full
runner trace and budget decisions belongs to A3.
"""

import unittest

from services.application.app.agent_loop.decision import LoopDecision
from services.application.app.agent_loop.registry import (
    DOMAIN_TOOL_ALLOWLISTS,
    DomainToolName,
    InvalidToolArguments,
    TaskProfile,
    ToolBlocked,
    ToolEntry,
    ToolRegistry,
)


def _schema(*, extra_properties=False):
    return {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "flags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["query"],
        "additionalProperties": extra_properties,
    }


def _entry(name=DomainToolName.SEARCH_MEMORY, **overrides):
    base = dict(
        name=name,
        description_by_profile={
            TaskProfile.ANALYSIS_COMPARE: "search memory for analysis",
            TaskProfile.CONTEXT_SEARCH: "search memory for context",
        },
        argument_schema=_schema(),
    )
    base.update(overrides)
    return ToolEntry(**base)


class DomainToolAllowlistTest(unittest.TestCase):
    def test_profile_allowlists_match_contract(self):
        self.assertEqual(
            DOMAIN_TOOL_ALLOWLISTS[TaskProfile.ANALYSIS_COMPARE],
            (
                DomainToolName.SEARCH_MEMORY,
                DomainToolName.LOAD_MEMORY,
                DomainToolName.LOAD_SNAPSHOT,
                DomainToolName.COMPARE_MEMORY,
                DomainToolName.VALIDATE_CANDIDATE,
            ),
        )
        self.assertEqual(
            DOMAIN_TOOL_ALLOWLISTS[TaskProfile.CONTEXT_SEARCH],
            (
                DomainToolName.SEARCH_MEMORY,
                DomainToolName.LOAD_MEMORY,
                DomainToolName.VALIDATE_CONTEXT,
            ),
        )
        self.assertEqual(DOMAIN_TOOL_ALLOWLISTS[TaskProfile.WRITING_GENERATE], ())

    def test_writing_generate_accepts_no_tools(self):
        registry = ToolRegistry(TaskProfile.WRITING_GENERATE, entries=[])
        self.assertEqual(registry.allowed_tool_names, ())

    def test_missing_required_profile_tool_is_blocked_before_provider(self):
        with self.assertRaises(ToolBlocked) as caught:
            ToolRegistry(TaskProfile.ANALYSIS_COMPARE, entries=[_entry()])
        self.assertEqual(caught.exception.decision, LoopDecision.BLOCKED)
        self.assertIn("missing required tools", str(caught.exception))

    def test_tool_from_other_profile_is_not_registered(self):
        with self.assertRaises(ToolBlocked) as caught:
            ToolRegistry(
                TaskProfile.CONTEXT_SEARCH,
                entries=[
                    _entry(),
                    _entry(DomainToolName.LOAD_MEMORY),
                    _entry(DomainToolName.VALIDATE_CONTEXT),
                    _entry(DomainToolName.LOAD_SNAPSHOT),
                ],
            )
        self.assertEqual(caught.exception.decision, LoopDecision.BLOCKED)
        self.assertIn("not allowed", str(caught.exception))


class ToolEntryValidationTest(unittest.TestCase):
    def test_schema_less_tool_cannot_register(self):
        with self.assertRaises(ToolBlocked):
            _entry(argument_schema={})

    def test_schema_must_reject_unknown_fields(self):
        with self.assertRaises(ToolBlocked):
            _entry(argument_schema=_schema(extra_properties=True))

    def test_model_cannot_own_project_or_trace_scope_fields(self):
        schema = {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        }
        with self.assertRaises(ToolBlocked):
            _entry(argument_schema=schema)

    def test_nested_object_schema_must_be_strict_at_registration(self):
        schema = {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "object",
                    "properties": {"status": {"type": "string"}},
                }
            },
            "required": ["filter"],
            "additionalProperties": False,
        }
        with self.assertRaises(ToolBlocked):
            _entry(argument_schema=schema)

    def test_array_schema_requires_items_at_registration(self):
        schema = {
            "type": "object",
            "properties": {"flags": {"type": "array"}},
            "required": ["flags"],
            "additionalProperties": False,
        }
        with self.assertRaises(ToolBlocked):
            _entry(argument_schema=schema)


class StrictArgumentValidationTest(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry(
            TaskProfile.CONTEXT_SEARCH,
            entries=[
                _entry(),
                _entry(DomainToolName.LOAD_MEMORY),
                _entry(DomainToolName.VALIDATE_CONTEXT),
            ],
        )

    def test_valid_json_object_reaches_entry_with_parsed_arguments(self):
        call = self.registry.validate_call(
            "search_memory", '{"query":"alpha","limit":2,"flags":["fresh"]}'
        )
        self.assertEqual(call.entry.name, DomainToolName.SEARCH_MEMORY)
        self.assertEqual(
            call.arguments, {"query": "alpha", "limit": 2, "flags": ["fresh"]}
        )

    def test_invalid_json_is_invalid_tool_arguments_not_empty_object(self):
        with self.assertRaises(InvalidToolArguments) as caught:
            self.registry.validate_call("search_memory", "{")
        self.assertEqual(caught.exception.decision, LoopDecision.INVALID_TOOL_ARGUMENTS)

    def test_non_object_json_is_invalid(self):
        with self.assertRaises(InvalidToolArguments):
            self.registry.validate_call("search_memory", "[]")

    def test_unknown_field_is_rejected_without_repair(self):
        with self.assertRaises(InvalidToolArguments):
            self.registry.validate_call(
                "search_memory", '{"query":"alpha","limit":2,"project_id":"evil"}'
            )

    def test_missing_required_field_is_rejected_without_default(self):
        with self.assertRaises(InvalidToolArguments):
            self.registry.validate_call("search_memory", '{"limit":2}')

    def test_type_coercion_is_rejected(self):
        with self.assertRaises(InvalidToolArguments):
            self.registry.validate_call(
                "search_memory", '{"query":"alpha","limit":"2"}'
            )

    def test_unregistered_or_out_of_profile_tool_is_blocked_not_invalid_args(self):
        with self.assertRaises(ToolBlocked) as caught:
            self.registry.validate_call("compare_memory", '{"query":"alpha"}')
        self.assertEqual(caught.exception.decision, LoopDecision.BLOCKED)


class ToolSignatureTest(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry(
            TaskProfile.CONTEXT_SEARCH,
            entries=[
                _entry(),
                _entry(DomainToolName.LOAD_MEMORY),
                _entry(DomainToolName.VALIDATE_CONTEXT),
            ],
        )

    def test_same_tool_and_canonical_arguments_have_same_signature(self):
        left = self.registry.validate_call(
            "search_memory", '{"limit":2,"query":"alpha"}'
        )
        right = self.registry.validate_call(
            "search_memory", '{"query":"alpha","limit":2}'
        )
        self.assertEqual(left.signature, right.signature)
        self.assertEqual(
            left.signature, 'search_memory:{"limit":2,"query":"alpha"}'
        )

    def test_different_argument_value_keeps_distinct_signature(self):
        left = self.registry.validate_call(
            "search_memory", '{"query":"alpha","limit":1}'
        )
        right = self.registry.validate_call(
            "search_memory", '{"query":"alpha","limit":2}'
        )
        self.assertNotEqual(left.signature, right.signature)

    def test_different_json_type_keeps_distinct_signature(self):
        first = self.registry.validate_call("search_memory", '{"query":"1"}')
        second = self.registry.validate_call("search_memory", '{"query":"01"}')
        self.assertNotEqual(first.signature, second.signature)

    def test_different_tool_keeps_distinct_signature(self):
        left = self.registry.validate_call("search_memory", '{"query":"alpha"}')
        right = self.registry.validate_call("load_memory", '{"query":"alpha"}')
        self.assertNotEqual(left.signature, right.signature)


if __name__ == "__main__":
    unittest.main()
