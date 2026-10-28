# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parse one training record, retaining recoverable structural errors as signals."""

import json
import math
from typing import cast

from pydantic import JsonValue

from datakeel.core.llm_data_models import ParsedTrainingRecord, TrainingFormat, TrainingIssue


def issue(code: str, field: str, message: str) -> TrainingIssue:
    """Construct a rule finding without copying untrusted payload into its message."""
    return TrainingIssue(code=code, field=field, message=message)


def _string(value: JsonValue, field: str) -> str:
    if not isinstance(value, str):
        message = f"{field} must be a string"
        raise TypeError(message)
    return value


def _nonempty(value: JsonValue, field: str) -> str:
    result = _string(value, field)
    if not result.strip():
        message = f"{field} must not be empty"
        raise ValueError(message)
    return result


def _content(value: JsonValue, *, tool_call: bool = False) -> str:
    if value is None and tool_call:
        return ""
    if isinstance(value, list):
        blocks = [
            _string(block.get("text"), "content.text")
            for block in value
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if len(blocks) != len(value):
            message = "Only text content blocks are supported"
            raise ValueError(message)
        return "\n".join(blocks)
    return _string(value, "content")


def _tool_call_ids(value: JsonValue, role: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if role != "assistant" or not isinstance(value, list):
        message = "tool_calls must be an array on an assistant message"
        raise TypeError(message)
    identities: list[str] = []
    for call in value:
        if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
            message = "tool_calls entries must contain a function object"
            raise TypeError(message)
        function = cast("dict[str, JsonValue]", call["function"])
        identities.append(_nonempty(call.get("id"), "tool_calls.id"))
        if call.get("type") != "function":
            message = "tool_calls.type must be function"
            raise ValueError(message)
        _nonempty(function.get("name"), "tool_calls.function.name")
        _string(function.get("arguments"), "tool_calls.function.arguments")
    if len(set(identities)) != len(identities):
        message = "tool_calls ids must be unique"
        raise ValueError(message)
    return tuple(identities)


def _tool_findings(messages: list[JsonValue], field: str) -> list[TrainingIssue]:
    pending: set[str] = set()
    seen: set[str] = set()
    findings: list[TrainingIssue] = []
    for offset, raw in enumerate(messages):
        message = cast("dict[str, JsonValue]", raw)
        role = _string(message.get("role"), "role")
        ids = _tool_call_ids(message.get("tool_calls"), role)
        position = f"{field}.{offset}"
        if pending and role != "tool":
            findings.append(
                issue(
                    "role_order", position, "All requested tool results must precede the next turn"
                )
            )
            pending.clear()
        if role == "tool":
            identity = _nonempty(message.get("tool_call_id"), "tool_call_id")
            if identity not in pending:
                findings.append(
                    issue("role_order", position, "Tool result has no matching outstanding call")
                )
            pending.discard(identity)
        if set(ids) & seen:
            findings.append(issue("role_order", position, "Tool call ids cannot be reused"))
        pending.update(ids)
        seen.update(ids)
    if pending:
        findings.append(issue("role_order", field, "Tool calls have missing results"))
    return findings


def _role_findings(
    roles: list[str], calls: list[bool], field: str, final_role: str, previous: str
) -> list[TrainingIssue]:
    findings: list[TrainingIssue] = []
    for offset, role in enumerate(roles):
        invalid = role not in {"system", "user", "assistant", "tool"}
        invalid |= role == "system" and offset != 0
        invalid |= role == "user" and previous not in {"system", "assistant"}
        invalid |= role == "assistant" and previous not in {"user", "tool"}
        if role == "tool":
            invalid |= offset == 0 or (
                previous != "tool" and not (previous == "assistant" and calls[offset - 1])
            )
        if invalid:
            findings.append(issue("role_order", f"{field}.{offset}.role", "Invalid role order"))
        previous = role
    if not roles or roles[-1] != final_role or calls[-1]:
        code = "missing_final_assistant" if final_role == "assistant" else "role_order"
        findings.append(issue(code, field, f"The last turn must answer as {final_role}"))
    return findings


def _messages(
    value: JsonValue, field: str, *, final_role: str = "assistant", previous: str = "system"
) -> tuple[str, str, str, list[TrainingIssue]]:
    if not isinstance(value, list) or not value:
        message = f"{field} must be a nonempty messages array"
        raise ValueError(message)
    prompts: list[str] = []
    answers: list[str] = []
    text: list[str] = []
    roles: list[str] = []
    calls: list[bool] = []
    findings: list[TrainingIssue] = []
    for offset, message in enumerate(value):
        if not isinstance(message, dict):
            error = f"{field} entries must be objects"
            raise TypeError(error)
        role = _string(message.get("role"), "role")
        tool_call = bool(_tool_call_ids(message.get("tool_calls"), role))
        content = _content(message.get("content"), tool_call=tool_call)
        roles.append(role)
        calls.append(tool_call)
        text.append(content)
        if role == "user":
            prompts.append(content)
        if role == "assistant":
            answers.append(content)
        if not content.strip() and not tool_call:
            findings.append(
                issue("empty_turn", f"{field}.{offset}.content", "Empty message content")
            )
    findings.extend(_role_findings(roles, calls, field, final_role, previous))
    findings.extend(_tool_findings(value, field))
    return "\n".join(prompts), "\n".join(answers), "\n".join(text), findings


def _branch(value: JsonValue) -> tuple[list[JsonValue] | None, JsonValue]:
    if not isinstance(value, list) or not value:
        return None, value
    if not all(isinstance(turn, dict) for turn in value):
        message = "Preference message entries must be objects"
        raise TypeError(message)
    if cast("dict[str, JsonValue]", value[0]).get("role") == "assistant":
        return None, value
    last_user = max(
        (
            offset
            for offset, turn in enumerate(value)
            if isinstance(turn, dict) and turn.get("role") == "user"
        ),
        default=-1,
    )
    return value[: last_user + 1], value[last_user + 1 :]


def _context(value: JsonValue, field: str) -> tuple[str, list[TrainingIssue]]:
    if isinstance(value, str):
        return value, []
    _prompt, _answer, text, findings = _messages(value, field, final_role="user")
    return text, findings


def _completion(value: JsonValue, field: str) -> tuple[str, list[TrainingIssue]]:
    if isinstance(value, str):
        return value, []
    if value is None or value == []:
        return "", []
    _prompt, answer, _text, findings = _messages(value, field, previous="user")
    return answer, findings


def _preference(payload: dict[str, JsonValue]) -> ParsedTrainingRecord:
    chosen_prefix, chosen_value = _branch(payload.get("chosen"))
    rejected_prefix, rejected_value = _branch(payload.get("rejected"))
    raw_prompt = payload.get("prompt", payload.get("messages"))
    if raw_prompt is None:
        raw_prompt = chosen_prefix if chosen_prefix is not None else rejected_prefix or ""
    prompt, findings = _context(raw_prompt, "prompt")
    for prefix, field in ((chosen_prefix, "chosen"), (rejected_prefix, "rejected")):
        if prefix is not None:
            context, context_findings = _context(prefix, f"{field}.prompt")
            findings.extend(context_findings)
            consistent = prefix == raw_prompt if isinstance(raw_prompt, list) else context == prompt
            if not consistent:
                findings.append(
                    issue(
                        "preference_prompt_mismatch",
                        field,
                        "Preference branches must share identical prompt turns",
                    )
                )
    chosen, chosen_findings = _completion(chosen_value, "chosen")
    rejected, rejected_findings = _completion(rejected_value, "rejected")
    findings.extend((*chosen_findings, *rejected_findings))
    if not prompt.strip():
        findings.append(issue("empty_prompt", "prompt", "Preference prompt is empty"))
    if not chosen.strip():
        findings.append(issue("chosen_empty", "chosen", "Chosen answer is empty"))
    if not rejected.strip():
        findings.append(issue("empty_turn", "rejected", "Rejected answer is empty"))
    return ParsedTrainingRecord(
        format="preference",
        payload=payload,
        prompt=prompt,
        answer=chosen,
        rejected=rejected,
        text=f"{prompt}\n{chosen}\n{rejected}",
        issues=tuple(findings),
    )


def _reject_constant(_value: str) -> float:
    message = "Non-finite JSON numbers are not permitted"
    raise ValueError(message)


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        return _reject_constant(value)
    return result


def parse_record(raw: str, selected: TrainingFormat = "auto") -> ParsedTrainingRecord:
    """Recognize supported JSON objects; malformed lines fail independently of their file."""
    value = cast(
        "JsonValue", json.loads(raw, parse_constant=_reject_constant, parse_float=_finite_float)
    )
    if not isinstance(value, dict):
        message = "A training record must be a JSON object"
        raise TypeError(message)
    detected = selected
    if selected == "auto":
        if "chosen" in value or "rejected" in value:
            detected = "preference"
        elif "messages" in value:
            detected = "messages"
        elif "instruction" in value:
            detected = "instruction"
        else:
            message = "Unrecognized training record format"
            raise ValueError(message)
    if detected == "preference":
        return _preference(value)
    if detected == "messages":
        prompt, answer, text, findings = _messages(value.get("messages"), "messages")
    else:
        instruction = _string(value.get("instruction"), "instruction")
        context = _string(value.get("input", ""), "input")
        answer = _string(value.get("output"), "output")
        prompt = "\n".join(part for part in (instruction, context) if part)
        text = f"{prompt}\n{answer}"
        findings: list[TrainingIssue] = []
        if not instruction.strip():
            findings.append(issue("empty_prompt", "instruction", "Instruction is empty"))
        if not answer.strip():
            findings.append(issue("empty_turn", "output", "Empty instruction output"))
    return ParsedTrainingRecord(
        format=detected,
        payload=value,
        prompt=prompt,
        answer=answer,
        text=text,
        issues=tuple(findings),
    )
