from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml

from app.models import ActionType, Urgency


@dataclass(frozen=True)
class ProposedAction:
    action_type: ActionType
    payload: dict | None
    urgency: Urgency
    confidence: float | None


def _rules_path() -> str:
    # no hardcoding: comes from env, with a reasonable default
    return os.getenv("ACTION_RULES_PATH", "data/action_rules.yaml")


def _load_rules() -> dict[str, Any]:
    path = _rules_path()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict) or "rules" not in data:
        return {"rules": []}
    return data


def _norm(s: str) -> str:
    return (s or "").lower()


def _contains_any(text: str, keywords: list[str]) -> bool:
    t = _norm(text)
    return any(_norm(k) in t for k in keywords if isinstance(k, str) and k.strip())


def propose_actions(*, cluster_title: str, message_subjects: list[str], message_bodies: list[str]) -> list[ProposedAction]:
    """
    Rule-based v1 suggestions:
    - Reads YAML rules from ACTION_RULES_PATH
    - Matches by keywords on cluster_title and message text
    - Returns ProposedAction objects using your DB enums
    """
    cfg = _load_rules()
    rules = cfg.get("rules", [])
    if not isinstance(rules, list):
        return []

    out: list[ProposedAction] = []

    joined_subjects = "\n".join([s for s in message_subjects if s])
    joined_bodies = "\n".join([b for b in message_bodies if b])

    for r in rules:
        if not isinstance(r, dict):
            continue
        if r.get("enabled") is False:
            continue

        match = r.get("match", {}) or {}
        propose = r.get("propose", {}) or {}
        if not isinstance(match, dict) or not isinstance(propose, dict):
            continue

        cluster_keys = match.get("any_cluster_keywords", []) or []
        msg_keys = match.get("any_message_keywords", []) or []

        cluster_hit = bool(cluster_keys) and _contains_any(cluster_title, list(cluster_keys))
        msg_hit = False
        if msg_keys:
            keys = list(msg_keys)
            msg_hit = _contains_any(joined_subjects, keys) or _contains_any(joined_bodies, keys)

        # rule triggers if either cluster or message text hits
        if not (cluster_hit or msg_hit):
            continue

        # validate action_type and urgency against your enums
        try:
            at = ActionType(str(propose.get("action_type")))
        except Exception:
            continue

        try:
            urg = Urgency(str(propose.get("urgency", "low")))
        except Exception:
            urg = Urgency.low

        conf = propose.get("confidence", None)
        conf_f: float | None
        try:
            conf_f = float(conf) if conf is not None else None
        except Exception:
            conf_f = None

        payload = propose.get("payload", None)
        payload_dict = payload if isinstance(payload, dict) else None

        out.append(ProposedAction(action_type=at, payload=payload_dict, urgency=urg, confidence=conf_f))

    return out
