"""Flat agent loop tool registry and strict argument validation.

Implements AgentLoopRunner A2 from docs/plans/flat-loop-gate.md (§Domain Tool
Registry 계약). The registry is fixed at run start for one task profile. It
admits only the v1 domain tools allowed for that profile, parses raw tool
arguments exactly once as JSON, rejects schema violations without repair, and
normalizes valid calls into the signature consumed by BudgetTracker.

This module intentionally does not execute handlers. Runtime tool errors,
budget-to-decision mapping, retries, and full loop composition belong to later
sub-slices.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

from services.application.app.agent_loop.decision import LoopDecision

_CONTEXT_ONLY_ARGUMENTS = frozenset(
    {
        "project_id",
        "task_id",
        "trace_id",
        "deadline",
        "deadline_ms",
    }
)


class TaskProfile(StrEnum):
    ANALYSIS_COMPARE = "analysis_compare"
    CONTEXT_SEARCH = "context_search"
    WRITING_GENERATE = "writing_generate"


class DomainToolName(StrEnum):
    SEARCH_MEMORY = "search_memory"
    LOAD_MEMORY = "load_memory"
    LOAD_SNAPSHOT = "load_snapshot"
    COMPARE_MEMORY = "compare_memory"
    VALIDATE_CANDIDATE = "validate_candidate"
    VALIDATE_CONTEXT = "validate_context"


DOMAIN_TOOL_ALLOWLISTS: Mapping[TaskProfile, tuple[DomainToolName, ...]] = {
    TaskProfile.ANALYSIS_COMPARE: (
        DomainToolName.SEARCH_MEMORY,
        DomainToolName.LOAD_MEMORY,
        DomainToolName.LOAD_SNAPSHOT,
        DomainToolName.COMPARE_MEMORY,
        DomainToolName.VALIDATE_CANDIDATE,
    ),
    TaskProfile.CONTEXT_SEARCH: (
        DomainToolName.SEARCH_MEMORY,
        DomainToolName.LOAD_MEMORY,
        DomainToolName.VALIDATE_CONTEXT,
    ),
    TaskProfile.WRITING_GENERATE: (),
}


class ToolRegistryError(ValueError):
    """Base class for registry setup and tool-call validation failures."""

    decision: LoopDecision


class ToolBlocked(ToolRegistryError):
    """Raised when a tool is missing, unregistered, or disallowed."""

    decision = LoopDecision.BLOCKED


class InvalidToolArguments(ToolRegistryError):
    """Raised when raw tool arguments are malformed or schema-invalid."""

    decision = LoopDecision.INVALID_TOOL_ARGUMENTS


@dataclass(frozen=True)
class ToolEntry:
    """One registered domain tool contract for the flat loop."""

    name: DomainToolName
    description_by_profile: Mapping[TaskProfile, str]
    argument_schema: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.name, DomainToolName):
            raise ToolBlocked("tool name must be a DomainToolName")
        if not self.description_by_profile:
            raise ToolBlocked(f"{self.name.value} requires task-specific descriptions")
        _validate_schema_contract(self.argument_schema)


@dataclass(frozen=True)
class ValidatedToolCall:
    entry: ToolEntry
    arguments: Mapping[str, object]
    signature: str


class ToolRegistry:
    """Profile-fixed registry used by one AgentLoopRunner run."""

    def __init__(self, profile: TaskProfile, *, entries: Sequence[ToolEntry]) -> None:
        if not isinstance(profile, TaskProfile):
            raise ToolBlocked("profile must be a TaskProfile")

        allowed = DOMAIN_TOOL_ALLOWLISTS[profile]
        entry_by_name: dict[DomainToolName, ToolEntry] = {}
        extra: list[str] = []

        for entry in entries:
            if entry.name not in allowed:
                extra.append(entry.name.value)
                continue
            if profile not in entry.description_by_profile:
                raise ToolBlocked(
                    f"{entry.name.value} has no description for {profile.value}"
                )
            if entry.name in entry_by_name:
                raise ToolBlocked(f"duplicate tool registered: {entry.name.value}")
            entry_by_name[entry.name] = entry

        if extra:
            raise ToolBlocked(
                f"tools not allowed for {profile.value}: {', '.join(sorted(extra))}"
            )

        missing = [name.value for name in allowed if name not in entry_by_name]
        if missing:
            raise ToolBlocked(
                f"missing required tools for {profile.value}: {', '.join(missing)}"
            )

        self._profile = profile
        self._entries = entry_by_name

    @property
    def allowed_tool_names(self) -> tuple[DomainToolName, ...]:
        return DOMAIN_TOOL_ALLOWLISTS[self._profile]

    def validate_call(self, tool_name: str, raw_arguments: str) -> ValidatedToolCall:
        try:
            name = DomainToolName(tool_name)
        except ValueError as exc:
            raise ToolBlocked(f"unregistered tool: {tool_name}") from exc

        entry = self._entries.get(name)
        if entry is None:
            raise ToolBlocked(
                f"{name.value} is not registered for {self._profile.value}"
            )

        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise InvalidToolArguments("tool arguments must be valid JSON") from exc

        if not isinstance(arguments, dict):
            raise InvalidToolArguments("tool arguments must be a JSON object")

        _validate_arguments(entry.argument_schema, arguments, path="$")
        signature = _signature_for(name, arguments)
        return ValidatedToolCall(entry=entry, arguments=arguments, signature=signature)


def _validate_schema_contract(schema: Mapping[str, object], *, path: str = "$") -> None:
    if not schema:
        raise ToolBlocked(f"{path} requires an input JSON Schema")

    schema_type = schema.get("type")
    if schema_type == "object":
        properties = schema.get("properties")
        if not isinstance(properties, Mapping):
            raise ToolBlocked(f"{path} object schema requires properties")
        if schema.get("additionalProperties") is not False:
            raise ToolBlocked(f"{path} object schema must reject unknown fields")

        forbidden = _CONTEXT_ONLY_ARGUMENTS.intersection(properties)
        if forbidden:
            names = ", ".join(sorted(forbidden))
            raise ToolBlocked(
                f"context-only arguments cannot be model arguments: {names}"
            )

        required = schema.get("required", ())
        if not isinstance(required, Sequence) or isinstance(required, (str, bytes)):
            raise ToolBlocked(f"{path} required must be a sequence")
        for name in required:
            if not isinstance(name, str) or name not in properties:
                raise ToolBlocked(f"{path} required fields must name properties")
        for name, field_schema in properties.items():
            if not isinstance(name, str):
                raise ToolBlocked(f"{path} property names must be strings")
            if not isinstance(field_schema, Mapping):
                raise ToolBlocked(f"{path}.{name} schema must be an object")
            _validate_schema_contract(field_schema, path=f"{path}.{name}")
    elif schema_type == "array":
        item_schema = schema.get("items")
        if not isinstance(item_schema, Mapping):
            raise ToolBlocked(f"{path} array schema requires items")
        _validate_schema_contract(item_schema, path=f"{path}[]")
    elif schema_type not in {"string", "integer", "number", "boolean"}:
        raise ToolBlocked(f"{path} has unsupported schema type")


def _validate_arguments(
    schema: Mapping[str, object], value: Mapping[str, object], *, path: str
) -> None:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        raise InvalidToolArguments(f"{path} schema requires properties")
    required = schema.get("required", ())
    if not isinstance(required, Sequence) or isinstance(required, (str, bytes)):
        raise InvalidToolArguments(f"{path} schema required must be a sequence")

    for name in required:
        if name not in value:
            raise InvalidToolArguments(f"{path}.{name} is required")

    for name, item in value.items():
        if name not in properties:
            raise InvalidToolArguments(f"{path}.{name} is not allowed")
        field_schema = properties[name]
        if not isinstance(field_schema, Mapping):
            raise InvalidToolArguments(f"{path}.{name} schema is invalid")
        _validate_value(field_schema, item, path=f"{path}.{name}")


def _validate_value(schema: Mapping[str, object], value: object, *, path: str) -> None:
    expected = schema.get("type")
    if expected == "string":
        if not isinstance(value, str):
            raise InvalidToolArguments(f"{path} must be a string")
    elif expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvalidToolArguments(f"{path} must be an integer")
    elif expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise InvalidToolArguments(f"{path} must be a number")
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise InvalidToolArguments(f"{path} must be a boolean")
    elif expected == "array":
        if not isinstance(value, list):
            raise InvalidToolArguments(f"{path} must be an array")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_value(item_schema, item, path=f"{path}[{index}]")
    elif expected == "object":
        if not isinstance(value, dict):
            raise InvalidToolArguments(f"{path} must be an object")
        if schema.get("additionalProperties") is not False:
            raise InvalidToolArguments(f"{path} object schema must be strict")
        _validate_arguments(schema, value, path=path)
    else:
        raise InvalidToolArguments(f"{path} has unsupported schema type")


def _signature_for(name: DomainToolName, arguments: Mapping[str, object]) -> str:
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    return f"{name.value}:{canonical}"
