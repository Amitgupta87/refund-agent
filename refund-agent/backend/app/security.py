"""Prompt-injection / policy-override detection.

A lightweight heuristic layer that flags attempts to make the agent ignore or
override the refund policy. It does NOT decide outcomes — the deterministic
policy engine and the server-side tool guardrails do that. Its job is to raise
`security_flag` so such turns are visible in the admin dashboard.
"""

from __future__ import annotations

import re

# Each pattern targets a common manipulation tactic. Matching is case-insensitive.
_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bignore\b.{0,40}\b(policy|policies|rule|rules|instruction|instructions|previous|above)\b",
        r"\bdisregard\b.{0,40}\b(policy|rule|rules|instruction|instructions)\b",
        r"\b(override|bypass|circumvent|get around)\b.{0,40}\b(policy|rule|rules|check|eligibility|system)\b",
        r"\bforget\b.{0,40}\b(rule|rules|policy|instruction|instructions)\b",
        r"\bskip\b.{0,40}\b(eligibility|policy|check|step|verification)\b",
        r"\b(do ?n['o]?t|never)\b.{0,20}\bcheck\b",
        r"\bapprove\b.{0,40}\b(anyway|regardless|no matter|even if|without)\b",
        r"\b(just|simply|please) approve\b",
        r"\byou (must|have to|should|need to) approve\b",
        r"\b(i am|i'm|as)\b.{0,20}\b(the |an |your )?(admin|administrator|ceo|owner|manager|developer|engineer|supervisor)\b",
        r"\b(developer|system|admin) (mode|prompt|message|override)\b",
        r"\bjailbreak\b",
        r"\bpretend\b.{0,40}\b(you|policy|rule)\b",
        r"\b(reveal|show|print|repeat)\b.{0,30}\b(system prompt|instructions|policy text)\b",
        r"\boverride code\b",
    ]
]


def detect_injection(message: str) -> tuple[bool, list[str]]:
    """Return (flagged, matched_snippets) for a user message."""
    matched: list[str] = []
    for pattern in _PATTERNS:
        found = pattern.search(message)
        if found:
            snippet = found.group(0).strip()
            if snippet and snippet.lower() not in (m.lower() for m in matched):
                matched.append(snippet)
    return (len(matched) > 0, matched)
