from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .schemas import FeatureVector, RuntimeEvidence, ToolAction


FEATURE_NAMES: tuple[str, ...] = (
    "task_alignment",
    "tool_affordance_match",
    "trusted_intent_alignment",
    "untrusted_instruction_alignment",
    "argument_provenance_trusted",
    "argument_provenance_untrusted",
    "trusted_authorization",
    "trusted_confirmation",
    "state_grounding",
    "state_freshness",
    "object_uniqueness",
    "source_grounding",
    "confidence",
    "uncertainty",
    "tool_schema_completeness",
    "action_scope_match",
    "read_before_write",
    "redaction_present",
    "side_effect_risk",
    "external_destination_risk",
    "privacy_risk",
    "financial_risk",
    "irreversible_risk",
    "write_risk",
    "sensitive_argument_risk",
    "untrusted_context_exposure",
    "untrusted_control_signal",
    "overreach_risk",
    # Frozen semantic axes. The older features above remain as estimator
    # details; constraints should prefer these benchmark-independent axes.
    "trusted_intent_support",
    "prerequisite_support",
    "completion_sufficiency",
    "argument_trusted_provenance",
    "source_channel_risk",
    "tool_source_risk",
    "effect_class",
    "state_cleanliness_cost",
    "entity_grounding_confidence",
    "schema_format_validity",
    # General action-space axes. These separate information type, sink type,
    # and argument grounding so privacy reads are not treated as exfiltration.
    "data_sensitivity",
    "sink_externality",
    "privacy_egress",
    "critical_argument_grounding",
    "state_read_necessity",
    "write_authorization_strength",
    "scope_precision",
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "the",
    "this",
    "to",
    "with",
    "you",
}

SIDE_EFFECT_TOOLS = (
    "send",
    "post",
    "schedule",
    "set",
    "write",
    "modify",
    "edit",
    "change",
    "publish",
    "commit",
    "execute",
    "apply",
    "approve",
    "reject",
    "rename",
    "move",
    "update",
    "delete",
    "remove",
    "transfer",
    "pay",
    "share",
    "sharing",
    "forward",
    "book",
    "reserve",
    "purchase",
    "download",
    "upload",
    "export",
    "invite",
    "add",
    "create",
    "submit",
    "cancel",
    "alter",
    "alteration",
    "fabricate",
    "fabrication",
    "leak",
    "theft",
    "steal",
    "tamper",
    "tampering",
    "manipulate",
    "manipulation",
    "disrupt",
    "disruption",
    "divert",
    "diversion",
    "allocate",
    "reallocate",
    "reallocation",
    "escalate",
    "capture",
    "harvest",
    "disclose",
    "exfiltrate",
    "exfiltration",
    "infiltrate",
    "infiltration",
    "backdoor",
    "corrupt",
    "implant",
    "spoof",
)

READ_ONLY_TOOLS = (
    "get",
    "search",
    "read",
    "list",
    "lookup",
    "summarize",
    "retrieve",
    "find",
    "api",
    "analysis",
    "analytics",
    "analyze",
    "analyzer",
    "assess",
    "assessment",
    "audit",
    "check",
    "checker",
    "compare",
    "data",
    "database",
    "detector",
    "evaluate",
    "evaluator",
    "fusion",
    "lookup",
    "monitor",
    "planner",
    "protect",
    "recommender",
    "secure",
    "selector",
    "simulator",
    "review",
    "summarizer",
    "validate",
    "validation",
)

LATENT_WRITE_TOOLS = (
    "get_unread",
    "mark",
    "ack",
    "open",
)

EXTERNAL_EFFECT_TOOLS = (
    "send",
    "post",
    "share",
    "forward",
    "email",
    "message",
    "transfer",
    "pay",
    "invite",
    "book",
    "reserve",
    "purchase",
)

SENSITIVE_PATTERNS = re.compile(
    r"secret|password|token|security code|verification code|private|confidential|"
    r"ssn|iban|credit card|bank|balance|medical|patient|therapy|legal|"
    r"customer|personal|proprietary|credential|email|message",
    re.IGNORECASE,
)

DESTINATION_ARGUMENT_KEYS = {
    "recipient",
    "recipients",
    "to",
    "email",
    "user_email",
    "channel",
    "account",
    "iban",
    "url",
    "phone",
    "phone_number",
    "address",
    "wallet",
    "destination",
    "participants",
    "attendees",
    "cc",
    "bcc",
}

SIDE_EFFECT_ARGUMENT_KEYS = DESTINATION_ARGUMENT_KEYS | {
    "amount",
    "event",
    "user",
    "person",
    "item",
    "order",
    "transaction",
    "payment_method_id",
}
CONTENT_PAYLOAD_ARGUMENT_KEYS = {
    "body",
    "message",
    "subject",
    "content",
    "title",
    "description",
    "text",
}

SENSITIVE_ARGUMENT_KEYS = {
    "iban",
    "account",
    "balance",
    "password",
    "token",
    "secret",
    "code",
    "email",
    "message",
    "private",
    "ssn",
    "card",
    "credential",
    "phone",
    "address",
}

BROAD_READ_KEYS = {"n", "limit", "count", "max_results", "page_size"}
SOURCE_DELEGATION_RE = re.compile(
    r"\b(?:follow|execute|perform|complete|do|carry out)\b.{0,100}"
    r"\b(?:instructions?|tasks?|steps?|todos?|notice|email|message|file|document)\b",
    re.IGNORECASE | re.DOTALL,
)
REMEDIATION_TERMS = (
    "resolve",
    "remediate",
    "fix",
    "patch",
    "secure",
    "mitigate",
    "recover",
    "restore",
)
SIDE_EFFECT_FAMILY_TERMS = {
    "send": ("send", "share", "post", "notify", "forward", "email", "message"),
    "post": ("send", "share", "post", "notify", "forward", "email", "message"),
    "email": ("send", "share", "post", "notify", "forward", "email", "message"),
    "create": ("create", "schedule", "set up", "make", "arrange", "book", "reserve"),
    "schedule": ("schedule", "set up", "arrange", "create", "book", "reserve"),
    "set": ("set", "configure", "change", "update", "modify"),
    "write": ("write", "save", "append", "record", "store"),
    "modify": ("modify", "edit", "change", "update", "adjust"),
    "edit": ("edit", "modify", "change", "update", "adjust"),
    "change": ("change", "modify", "edit", "update", "adjust"),
    "add": ("add", "create", "invite", "schedule", "set up"),
    "invite": ("invite", "add", "schedule"),
    "book": ("book", "reserve", "schedule"),
    "reserve": ("reserve", "book", "schedule"),
    "update": (
        "update",
        "change",
        "modify",
        "edit",
        "adjust",
        "increase",
        "decrease",
        *REMEDIATION_TERMS,
    ),
    "delete": ("delete", "remove", "cancel"),
    "remove": ("delete", "remove", "cancel"),
    "cancel": ("delete", "remove", "cancel"),
    "transfer": ("transfer", "pay", "payment", "send money", "settle", "refund", "reimburse", "return"),
    "pay": ("transfer", "pay", "payment", "send money", "settle", "refund", "reimburse", "return"),
}


def _clip(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        return " ".join(f"{key} {_text(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value)
    return str(value)


def _identifier_words(text: str) -> str:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    return re.sub(r"[_\-/]+", " ", expanded)


def _tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-zA-Z0-9_@.+:-]+", _identifier_words(text).lower())
    tokens: set[str] = set()
    for item in raw:
        if item in STOPWORDS or len(item) <= 1:
            continue
        tokens.add(item)
        if len(item) > 4 and item.endswith("ies"):
            tokens.add(item[:-3] + "y")
        if len(item) > 4 and item.endswith("zes"):
            tokens.add(item[:-1])
        if len(item) > 3 and item.endswith("s"):
            tokens.add(item[:-1])
        if len(item) > 5 and item.endswith("ing"):
            tokens.add(item[:-3])
    return tokens


def _provenance_tokens(text: str) -> set[str]:
    """Normalize value tokens without changing task-intent token semantics."""
    return {
        item.strip(".+:-")
        for item in _tokens(text)
        if item.strip(".+:-")
    }


NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?(?!\w)")
DERIVATION_CUE_RE = re.compile(
    r"\b(?:increase|decrease|add|subtract|difference|sum|total|combined|"
    r"more|less|remaining|new amount|adjust|change by)\b",
    re.IGNORECASE,
)


def _number(value: str) -> float | None:
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _numerically_derived_from_trusted_text(value: str, trusted_text: str) -> bool:
    target = _number(value)
    if target is None or not DERIVATION_CUE_RE.search(trusted_text):
        return False
    numbers = []
    for match in NUMBER_RE.finditer(trusted_text):
        try:
            number = float(match.group(0).replace(",", ""))
        except ValueError:
            continue
        if all(abs(number - item) > 1e-9 for item in numbers):
            numbers.append(number)
        if len(numbers) >= 24:
            break
    tolerance = max(1e-6, abs(target) * 1e-6)
    for left in numbers:
        for right in numbers:
            if abs((left + right) - target) <= tolerance:
                return True
            if abs((left - right) - target) <= tolerance:
                return True
    return False


def _number_occurs_in_text(value: str, text: str) -> bool:
    target = _number(value)
    if target is None:
        return False
    tolerance = max(1e-9, abs(target) * 1e-9)
    for match in NUMBER_RE.finditer(text):
        try:
            observed = float(match.group(0).replace(",", ""))
        except ValueError:
            continue
        if abs(observed - target) <= tolerance:
            return True
    return False


def _token_overlap(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / max(1.0, min(len(a), len(b)))


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def _key_matches(key: str, names: Iterable[str]) -> bool:
    lowered = key.lower()
    parts = re.split(r"[._-]", lowered)
    return any(
        lowered == name or lowered.endswith(f"_{name}")
        or (name in parts if len(name) <= 2 else name in lowered)
        for name in names
    )


def _iter_argument_items(arguments: Mapping[str, Any], prefix: str = "") -> Iterable[tuple[str, Any]]:
    for key, value in arguments.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            yield from _iter_argument_items(value, name)
        else:
            yield name, value


def _iter_argument_values(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_argument_values(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_argument_values(item)
        return
    text = str(value).strip()
    if text:
        yield text


def _matches_tool_token(tool_name: str, names: Iterable[str]) -> bool:
    lowered = tool_name.lower()
    tool_tokens = _tokens(_identifier_words(tool_name))
    return any(
        lowered == name
        or lowered.startswith(f"{name}_")
        or f"_{name}_" in lowered
        or lowered.endswith(f"_{name}")
        or name in tool_tokens
        for name in names
    )


def _tool_family(tool_name: str) -> str:
    lowered = tool_name.lower()
    for prefix in (*SIDE_EFFECT_TOOLS, *READ_ONLY_TOOLS):
        if _matches_tool_token(lowered, (prefix,)):
            return prefix
    return lowered.split("_", 1)[0]


def _delegated_source_affordance(action: ToolAction, evidence: RuntimeEvidence, *, family: str) -> float:
    if not SOURCE_DELEGATION_RE.search(evidence.trusted_task):
        return 0.0
    state_text = " ".join(evidence.trusted_state)
    if not state_text.strip():
        return 0.0
    state_words = _tokens(state_text)
    tool_words = _tokens(action.tool_name.replace("_", " "))
    object_words = tool_words - set(SIDE_EFFECT_TOOLS) - set(READ_ONLY_TOOLS)
    argument_state_match = _argument_token_fraction_strict(action.arguments, state_text) > 0.0
    object_state_match = bool(object_words & state_words) or argument_state_match
    family_terms = SIDE_EFFECT_FAMILY_TERMS.get(family, (family,))
    family_state_match = _contains_any(state_text, family_terms)
    if family_state_match and object_state_match:
        return 1.0
    return 0.0


def _is_side_effect(tool_name: str) -> bool:
    return _matches_tool_token(tool_name, SIDE_EFFECT_TOOLS)


def _is_read_only(tool_name: str) -> bool:
    return _matches_tool_token(tool_name, READ_ONLY_TOOLS) and not _is_side_effect(tool_name)


def _is_latent_write(tool_name: str) -> bool:
    return _matches_tool_token(tool_name.lower(), LATENT_WRITE_TOOLS)


def _external_effect_tool(tool_name: str) -> bool:
    return _matches_tool_token(tool_name, EXTERNAL_EFFECT_TOOLS)


def _has_destination_argument(arguments: Mapping[str, Any]) -> bool:
    return any(_key_matches(key, DESTINATION_ARGUMENT_KEYS) for key, _ in _iter_argument_items(arguments))


def _argument_token_fraction(arguments: Mapping[str, Any], text: str) -> float:
    arg_tokens = _provenance_tokens(_text(arguments))
    if not arg_tokens:
        return 0.5
    ref_tokens = _provenance_tokens(text)
    if not ref_tokens:
        return 0.0
    return len(arg_tokens & ref_tokens) / len(arg_tokens)


def _argument_token_fraction_strict(arguments: Mapping[str, Any], text: str) -> float:
    if not _provenance_tokens(_text(arguments)):
        return 0.0
    return _argument_token_fraction(arguments, text)


def _action_surface_text(action: ToolAction) -> str:
    # The planner rationale often contains the whole conversation. Including it
    # would make unrelated actions appear aligned with the trusted task.
    return " ".join(part for part in (action.tool_name, action.argument_text) if part)


def _object_tokens(action: ToolAction) -> set[str]:
    return _tokens(_text(action.arguments)) | _tokens(action.tool_name.replace("_", " "))


def _schema_completeness(action: ToolAction, required_args: tuple[str, ...]) -> float:
    if not required_args:
        return 1.0
    present = sum(1 for name in required_args if name in action.arguments and action.arguments[name] not in (None, ""))
    return present / len(required_args)


def _tool_affordance(action: ToolAction, evidence: RuntimeEvidence, *, tool_description: str = "") -> float:
    family = _tool_family(action.tool_name)
    trusted = evidence.trusted_task.lower()
    semantic_tool_text = " ".join(part for part in (action.tool_name.replace("_", " "), tool_description) if part)
    tool_words = _tokens(semantic_tool_text)
    object_words = tool_words - set(SIDE_EFFECT_TOOLS) - set(READ_ONLY_TOOLS)
    task_words = _tokens(evidence.trusted_task)
    object_match = bool(object_words & task_words)
    argument_task_match = _argument_token_fraction_strict(action.arguments, evidence.trusted_task) > 0.0
    target_match = object_match or argument_task_match
    semantic_task_overlap = _token_overlap(semantic_tool_text, evidence.trusted_task)
    delegated_state_match = _delegated_source_affordance(action, evidence, family=family)
    if family in set(READ_ONLY_TOOLS):
        if (target_match or semantic_task_overlap >= 0.18) and _contains_any(
            trusted,
            (
                "summarize",
                "read",
                "check",
                "find",
                "look up",
                "show",
                "list",
                "retrieve",
                "evaluate",
                "assess",
                "analyze",
                "review",
                "compare",
                "recommend",
                "plan",
            ),
        ):
            return 1.0
    if family in {"send", "post", "email"}:
        if delegated_state_match:
            return delegated_state_match
        if "money" in tool_words and _contains_any(
            trusted,
            ("pay", "payment", "bill", "transfer", "send money", "settle", "refund", "reimburse", "return"),
        ):
            return 1.0
        if (
            _contains_any(trusted, ("send", "share", "post", "notify", "forward"))
            or re.search(r"\bwrite\s+(?:the\s+)?message\b|\bwrite\b.+\bto\s+each\s+user\b", trusted)
        ) and target_match:
            return 1.0
    if family in {"create", "add", "invite", "book", "reserve"}:
        if delegated_state_match:
            return delegated_state_match
        if _contains_any(trusted, (family, "schedule", "set up", "make", "arrange")) and target_match:
            return 1.0
    if family in {"update"}:
        if delegated_state_match:
            return delegated_state_match
        if _contains_any(trusted, ("update", "change", "modify", "edit", "adjust")) and target_match:
            return 1.0
        if not action.arguments and _contains_any(trusted, REMEDIATION_TERMS):
            return 0.9
    if family in {"delete", "remove", "cancel"}:
        if delegated_state_match:
            return delegated_state_match
        if _contains_any(trusted, ("delete", "remove", "cancel")) and target_match:
            return 1.0
    if family in {"transfer", "pay"}:
        if delegated_state_match:
            return delegated_state_match
        if _contains_any(trusted, ("transfer", "pay", "send money", "payment")) and target_match:
            return 1.0
    return max(_token_overlap(action.tool_name.replace("_", " "), evidence.trusted_task), 0.75 * semantic_task_overlap)


def _prerequisite_support(action: ToolAction, evidence: RuntimeEvidence, *, read_only: bool) -> float:
    if not read_only:
        return 0.0
    tool_tokens = _tokens(action.tool_name.replace("_", " "))
    arg_tokens = _tokens(_text(action.arguments))
    trusted_tokens = _tokens(evidence.trusted_task)
    if not trusted_tokens:
        return 0.0
    overlap = len((tool_tokens | arg_tokens) & trusted_tokens)
    denom = max(1, min(len(tool_tokens | arg_tokens), len(trusted_tokens)))
    direct = overlap / denom
    family = _tool_family(action.tool_name)
    if family in set(READ_ONLY_TOOLS) and direct > 0.0:
        return _clip(0.45 + 0.55 * direct)
    return _clip(direct)


def _effect_class(action: ToolAction, *, side_effect: bool, read_only: bool, latent_write: bool, external_destination: bool) -> float:
    lowered = action.tool_name.lower()
    if _contains_any(lowered, ("delete", "remove", "transfer", "pay", "cancel", "purchase")):
        return 1.0
    if external_destination or _external_effect_tool(action.tool_name):
        return 0.85
    if side_effect:
        return 0.70
    if latent_write:
        return 0.45
    if read_only:
        return 0.10
    return 0.25


def _entity_grounding(action: ToolAction, evidence: RuntimeEvidence, *, arg_trusted: float) -> float:
    arg_text = _text(action.arguments)
    tokens = _tokens(arg_text)
    if not tokens:
        return 0.65
    trusted_state = evidence.trusted_text
    trusted_overlap = _argument_token_fraction(action.arguments, trusted_state)
    has_specific = bool(re.search(r"[\w.+-]+@[\w.-]+|https?://|www\.|id|file_id|task_id|channel|recipient", arg_text, re.I))
    return _clip(max(arg_trusted, trusted_overlap, 0.75 if has_specific and trusted_overlap > 0.0 else 0.0))


def _data_sensitivity(action: ToolAction, *, read_only: bool, tool_description: str = "") -> float:
    action_text = " ".join(part for part in (_action_surface_text(action), tool_description) if part)
    score = 1.0 if SENSITIVE_PATTERNS.search(action_text) else 0.0
    for key, value in _iter_argument_items(action.arguments):
        if _key_matches(key, SENSITIVE_ARGUMENT_KEYS):
            score = max(score, 0.85)
        if SENSITIVE_PATTERNS.search(_text(value)):
            score = max(score, 0.75)
    tool_text = action.tool_name.replace("_", " ").lower()
    if read_only and _contains_any(
        tool_text,
        ("inbox", "mail", "message", "user", "profile", "contact", "account", "transaction", "channel"),
    ):
        score = max(score, 0.55)
    return _clip(score)


def _sink_externality(action: ToolAction, *, side_effect: bool, latent_write: bool) -> float:
    if not side_effect:
        return 0.35 if latent_write else 0.0
    if _external_effect_tool(action.tool_name) or _has_destination_argument(action.arguments):
        return 1.0
    return 0.65


def _privacy_egress(*, data_sensitivity: float, sink_externality: float, external_destination: float) -> float:
    if sink_externality <= 0.0:
        return 0.0
    return _clip(data_sensitivity * max(sink_externality, external_destination))


def _critical_argument_values(action: ToolAction, *, effectful: bool) -> tuple[str, ...]:
    values: list[str] = []
    for key, value in _iter_argument_items(action.arguments):
        if _key_matches(key, SIDE_EFFECT_ARGUMENT_KEYS):
            values.extend(_iter_argument_values(value))
        elif _key_matches(key, CONTENT_PAYLOAD_ARGUMENT_KEYS):
            for item in _iter_argument_values(value):
                # Free-form payload can be generated from untrusted factual state
                # when the destination/action is trusted. Treat it as critical
                # only when it carries obvious sensitive data or a new sink.
                if SENSITIVE_PATTERNS.search(item) or re.search(r"[\w.+-]+@[\w.-]+|https?://|www\.", item, re.I):
                    values.append(item)
    if effectful and not values:
        values.extend(_iter_argument_values(action.arguments))
    return tuple(values)


def _critical_literal_anchors(value: str) -> tuple[str, ...]:
    text = str(value)
    anchors = [
        match.group(0).rstrip(".,;:!?)\"'")
        for match in re.finditer(
            r"https?://[^\s,;]+|www\.[^\s,;]+|[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",
            text,
            re.IGNORECASE,
        )
    ]
    for token in re.findall(r"\b[A-Za-z0-9_-]{6,}\b", text):
        if any(char.isalpha() for char in token) and any(char.isdigit() for char in token):
            anchors.append(token)
    return tuple(dict.fromkeys(anchor.lower() for anchor in anchors if anchor))


def _value_grounding_score(value: str, *, trusted_text: str, untrusted_text: str) -> float:
    trusted_lower = trusted_text.lower()
    untrusted_lower = untrusted_text.lower()
    if any(
        anchor in untrusted_lower and anchor not in trusted_lower
        for anchor in _critical_literal_anchors(value)
    ):
        return 0.0
    numeric_in_trusted = _number_occurs_in_text(value, trusted_text)
    numeric_in_untrusted = _number_occurs_in_text(value, untrusted_text)
    if numeric_in_untrusted and not numeric_in_trusted:
        return 0.0
    if numeric_in_trusted:
        return 1.0
    value_tokens = _provenance_tokens(value)
    if not value_tokens:
        return 0.55
    trusted_tokens = _provenance_tokens(trusted_text)
    untrusted_tokens = _provenance_tokens(untrusted_text)
    trusted_fraction = len(value_tokens & trusted_tokens) / len(value_tokens)
    untrusted_fraction = len(value_tokens & untrusted_tokens) / len(value_tokens)
    if trusted_fraction <= 0.0 and untrusted_fraction > 0.0:
        return 0.0
    if trusted_fraction > 0.0:
        return _clip(0.25 + 0.75 * trusted_fraction)
    if _numerically_derived_from_trusted_text(value, trusted_text):
        return 0.85
    if _critical_literal_anchors(value) or re.search(r"[\w.+-]+@[\w.-]+|https?://|www\.|\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}", value, re.I):
        # A concrete destination/date without any trusted provenance does not
        # receive credit merely because it is well formed. Optional fields can
        # then be removed by the existing zero-grounding repair rule.
        return 0.0
    return 0.35


def _current_grounding_text(evidence: RuntimeEvidence) -> str:
    """Explicitly superseded factual rows cannot ground a current mutation.

    Keep user instructions intact: a user may explicitly request an old value.
    This only removes tool-state lines clearly labelled as superseded.
    """
    current_state = tuple(
        "\n".join(line for line in state.splitlines()
                  if not re.match(r"\s*(?:historical\s+superseded|superseded\s+value|revoked\s+value)\b", line, re.I))
        for state in evidence.trusted_state
    )
    return " ".join((evidence.trusted_task, *evidence.trusted_authorizations,
                     *evidence.trusted_confirmations, *current_state, *evidence.completed_steps))


def _critical_argument_grounding(
    action: ToolAction,
    evidence: RuntimeEvidence,
    *,
    effectful: bool,
    read_only: bool,
    arg_trusted: float,
    entity_grounding: float,
) -> float:
    if not effectful:
        return _clip(max(arg_trusted, entity_grounding, 0.70 if read_only else 0.55))
    values = _critical_argument_values(action, effectful=effectful)
    if not values:
        return 1.0 if not evidence.required_args(action.tool_name) else 0.45
    scores = tuple(
        _value_grounding_score(value, trusted_text=_current_grounding_text(evidence), untrusted_text=evidence.untrusted_text)
        for value in values
    )
    # Every critical field participates in the external effect. Averaging lets
    # one untrusted destination hide behind many grounded bookkeeping fields.
    return _clip(min(scores))


def critical_field_grounding(
    action: ToolAction,
    evidence: RuntimeEvidence,
) -> dict[str, float]:
    """Return provenance grounding for independently repairable top-level fields."""
    critical_keys = [
        str(key)
        for key, _ in action.arguments.items()
        if _key_matches(str(key), SIDE_EFFECT_ARGUMENT_KEYS | CONTENT_PAYLOAD_ARGUMENT_KEYS)
    ]
    if not critical_keys:
        critical_keys = [str(key) for key in action.arguments]
    scores: dict[str, float] = {}
    for key in critical_keys:
        value = action.arguments[key]
        values = tuple(_iter_argument_values(value))
        if not values:
            scores[key] = 0.55
            continue
        scores[key] = _clip(
            min(
                _value_grounding_score(
                    item,
                    trusted_text=_current_grounding_text(evidence),
                    untrusted_text=evidence.untrusted_text,
                )
                for item in values
            )
        )
    return scores


def _state_read_necessity(
    action: ToolAction,
    evidence: RuntimeEvidence,
    *,
    read_only: bool,
    tool_match: float,
    prerequisite: float,
) -> float:
    if not read_only:
        return 0.0
    surface = _action_surface_text(action)
    task_overlap = _token_overlap(surface, evidence.trusted_task)
    if prerequisite <= 0.0 and tool_match <= 0.0 and task_overlap <= 0.0:
        return 0.0
    return _clip(max(prerequisite, 0.35 * tool_match + 0.65 * task_overlap, tool_match if prerequisite > 0 else 0.0))


def _scope_precision(action: ToolAction, *, read_only: bool) -> float:
    if not read_only:
        return 1.0
    precision = 1.0
    for key, value in _iter_argument_items(action.arguments):
        if not _key_matches(key, BROAD_READ_KEYS):
            continue
        try:
            amount = float(value)
        except (TypeError, ValueError):
            continue
        if amount > 100:
            precision = min(precision, 0.25)
        elif amount > 50:
            precision = min(precision, 0.35)
        elif amount > 20:
            precision = min(precision, 0.60)
    return precision


def _write_authorization_strength(
    *,
    effectful: bool,
    trusted_intent_support: float,
    critical_argument_grounding: float,
    entity_grounding: float,
    authorization: float,
    confirmation: float,
    state_grounding: float,
    prerequisite: float,
) -> float:
    if not effectful:
        return _clip(max(prerequisite, state_grounding))
    return _clip(
        0.28 * trusted_intent_support
        + 0.24 * critical_argument_grounding
        + 0.16 * entity_grounding
        + 0.14 * authorization
        + 0.10 * confirmation
        + 0.08 * state_grounding
    )


class ConfidenceLiftedEncoder:
    """Lift a tool action into a confidence-aware action-evidence vector."""

    feature_names = FEATURE_NAMES

    def encode(self, action: ToolAction, evidence: RuntimeEvidence) -> FeatureVector:
        tool_description = evidence.tool_description(action.tool_name)
        action_text = _action_surface_text(action)
        semantic_tool_text = " ".join(part for part in (action.tool_name.replace("_", " "), tool_description) if part)
        risk_surface_text = " ".join(part for part in (action_text, tool_description) if part)
        trusted_text = evidence.trusted_text
        untrusted_text = evidence.untrusted_text
        arg_text = _text(action.arguments)
        tool_source_risk = 1.0 if evidence.is_untrusted_tool(action.tool_name) else 0.0

        task_alignment = max(
            _token_overlap(action_text, evidence.trusted_task),
            0.75 * _token_overlap(semantic_tool_text, evidence.trusted_task),
        )
        tool_match = _tool_affordance(action, evidence, tool_description=tool_description)
        trusted_intent_alignment = max(task_alignment, tool_match)
        untrusted_alignment = max(
            _token_overlap(action_text, untrusted_text),
            _argument_token_fraction_strict(action.arguments, untrusted_text),
            0.35 * tool_source_risk,
        )

        arg_trusted = _argument_token_fraction(action.arguments, trusted_text)
        arg_untrusted = _argument_token_fraction_strict(action.arguments, untrusted_text)
        schema = (
            0.0
            if evidence.tool_schema and action.tool_name not in evidence.tool_schema
            else _schema_completeness(action, evidence.required_args(action.tool_name))
        )

        side_effect_bool = _is_side_effect(action.tool_name) or _is_side_effect(tool_description)
        read_only_bool = (_is_read_only(action.tool_name) or _is_read_only(tool_description)) and not side_effect_bool
        latent_write_bool = _is_latent_write(action.tool_name) or _is_latent_write(tool_description)
        side_effect = 1.0 if side_effect_bool else 0.0
        read_only = 1.0 if read_only_bool else 0.0
        has_external_address = bool(re.search(r"[\w.+-]+@[\w.-]+|https?://|www\.", arg_text, re.I))
        has_destination = _has_destination_argument(action.arguments)
        external_destination = (
            1.0
            if (side_effect_bool or _external_effect_tool(action.tool_name))
            and (has_external_address or has_destination)
            else 0.0
        )
        data_sensitivity = _data_sensitivity(action, read_only=read_only_bool, tool_description=tool_description)
        sensitive = data_sensitivity
        privacy = _clip(max(data_sensitivity, 0.7 if "message" in action.tool_name.lower() else 0.0))
        sink_externality = _sink_externality(action, side_effect=side_effect_bool, latent_write=latent_write_bool)
        privacy_egress = _privacy_egress(
            data_sensitivity=data_sensitivity,
            sink_externality=sink_externality,
            external_destination=external_destination,
        )
        financial = 1.0 if re.search(r"bank|balance|payment|pay|transfer|invoice|card|iban|amount", risk_surface_text, re.I) else 0.0
        lowered_risk_surface = risk_surface_text.lower()
        if _contains_any(
            lowered_risk_surface,
            ("delete", "remove", "transfer", "pay", "cancel", "purchase", "corrupt"),
        ):
            irreversible = 1.0
        elif _contains_any(lowered_risk_surface, ("book", "reserve", "update", "alter")):
            irreversible = 0.65
        else:
            irreversible = 0.0
        write = side_effect
        untrusted_context_exposure = 1.0 if untrusted_text.strip() or tool_source_risk > 0.0 else 0.0
        untrusted_control_signal = _clip(
            untrusted_context_exposure * max(untrusted_alignment, side_effect * 0.5)
            + tool_source_risk * max(0.35, side_effect, data_sensitivity * 0.5)
        )

        authorization = 1.0 if evidence.trusted_authorizations else 0.0
        confirmation = 1.0 if evidence.trusted_confirmations else 0.0
        state_grounding = 1.0 if (evidence.trusted_state and arg_trusted > 0.0) or read_only else 0.0
        state_freshness = _clip(evidence.state_freshness)
        object_uniqueness = 1.0 if re.search(r"[\w.+-]+@[\w.-]+|https?://|id|task_id|file_id", arg_text, re.I) else 0.6
        source_grounding = max(arg_trusted, _argument_token_fraction(action.arguments, trusted_text))
        redaction = 1.0 if re.search(r"redact|redacted|anonym", action_text, re.I) else 0.0
        action_scope = _clip(max(tool_match, arg_trusted))
        read_before_write = 1.0 if read_only or evidence.trusted_state else 0.0
        overreach = _clip(max(0.0, side_effect - trusted_intent_alignment) + 0.4 * max(0.0, arg_untrusted - arg_trusted))

        prerequisite = _prerequisite_support(action, evidence, read_only=read_only_bool)
        arg_trusted_provenance = arg_trusted
        arg_task_support = _argument_token_fraction_strict(action.arguments, evidence.trusted_task)
        arg_state_support = _argument_token_fraction_strict(action.arguments, trusted_text)
        delegated_intent = bool(SOURCE_DELEGATION_RE.search(evidence.trusted_task)) and tool_match > 0.0
        arg_grounded_support = max(
            arg_task_support,
            arg_state_support if delegated_intent else 0.0,
        )
        if action.arguments:
            tool_grounded_support = 0.55 * tool_match + 0.45 * arg_grounded_support
        elif not evidence.required_args(action.tool_name):
            tool_grounded_support = tool_match
        else:
            tool_grounded_support = 0.55 * tool_match
        trusted_intent_support = _clip(max(task_alignment, tool_grounded_support))
        semantic_effect = _effect_class(
            action,
            side_effect=side_effect_bool,
            read_only=read_only_bool,
            latent_write=latent_write_bool,
            external_destination=bool(external_destination),
        )
        entity_grounding = _entity_grounding(action, evidence, arg_trusted=arg_trusted)
        critical_grounding = _critical_argument_grounding(
            action,
            evidence,
            effectful=side_effect_bool or latent_write_bool or sink_externality > 0.0,
            read_only=read_only_bool,
            arg_trusted=arg_trusted,
            entity_grounding=entity_grounding,
        )
        state_read_necessity = _state_read_necessity(
            action,
            evidence,
            read_only=read_only_bool,
            tool_match=tool_match,
            prerequisite=prerequisite,
        )
        scope_precision = _scope_precision(action, read_only=read_only_bool)
        write_authorization = _write_authorization_strength(
            effectful=side_effect_bool or latent_write_bool or sink_externality > 0.0,
            trusted_intent_support=trusted_intent_support,
            critical_argument_grounding=critical_grounding,
            entity_grounding=entity_grounding,
            authorization=authorization,
            confirmation=confirmation,
            state_grounding=state_grounding,
            prerequisite=prerequisite,
        )
        source_channel_risk = _clip(max(untrusted_context_exposure * max(untrusted_alignment, arg_untrusted), tool_source_risk))
        effect_write_support = 0.80 * write_authorization if side_effect_bool else 0.0
        state_cleanliness = _clip(
            max(
                0.0,
                semantic_effect
                - max(
                    trusted_intent_support,
                    prerequisite,
                    state_read_necessity,
                    effect_write_support,
                    authorization,
                    confirmation,
                ),
            )
        )
        completion_sufficiency = _clip(
            max(
                trusted_intent_support if side_effect_bool else 0.0,
                prerequisite * (0.35 if read_only_bool else 0.0),
                state_read_necessity * (0.40 if read_only_bool else 0.0),
            )
        )
        schema_format_validity = schema

        confidence = _clip(
            0.20 * schema
            + 0.18 * max(trusted_intent_support, prerequisite)
            + 0.16 * source_grounding
            + 0.14 * entity_grounding
            + 0.12 * object_uniqueness
            + 0.10 * state_freshness
            + 0.10 * max(authorization, confirmation, read_only, critical_grounding)
        )
        uncertainty = _clip(1.0 - confidence + 0.25 * arg_untrusted + 0.15 * source_channel_risk)

        values = {
            "task_alignment": task_alignment,
            "tool_affordance_match": tool_match,
            "trusted_intent_alignment": trusted_intent_alignment,
            "untrusted_instruction_alignment": untrusted_alignment,
            "argument_provenance_trusted": arg_trusted,
            "argument_provenance_untrusted": arg_untrusted,
            "trusted_authorization": authorization,
            "trusted_confirmation": confirmation,
            "state_grounding": state_grounding,
            "state_freshness": state_freshness,
            "object_uniqueness": object_uniqueness,
            "source_grounding": source_grounding,
            "confidence": confidence,
            "uncertainty": uncertainty,
            "tool_schema_completeness": schema,
            "action_scope_match": action_scope,
            "read_before_write": read_before_write,
            "redaction_present": redaction,
            "side_effect_risk": side_effect,
            "external_destination_risk": external_destination,
            "privacy_risk": privacy,
            "financial_risk": financial,
            "irreversible_risk": irreversible,
            "write_risk": write,
            "sensitive_argument_risk": sensitive,
            "untrusted_context_exposure": untrusted_context_exposure,
            "untrusted_control_signal": untrusted_control_signal,
            "overreach_risk": overreach,
            "trusted_intent_support": trusted_intent_support,
            "prerequisite_support": prerequisite,
            "completion_sufficiency": completion_sufficiency,
            "argument_trusted_provenance": arg_trusted_provenance,
            "source_channel_risk": source_channel_risk,
            "tool_source_risk": tool_source_risk,
            "effect_class": semantic_effect,
            "state_cleanliness_cost": state_cleanliness,
            "entity_grounding_confidence": entity_grounding,
            "schema_format_validity": schema_format_validity,
            "data_sensitivity": data_sensitivity,
            "sink_externality": sink_externality,
            "privacy_egress": privacy_egress,
            "critical_argument_grounding": critical_grounding,
            "state_read_necessity": state_read_necessity,
            "write_authorization_strength": write_authorization,
            "scope_precision": scope_precision,
        }
        return FeatureVector.from_mapping(values, names=self.feature_names)
