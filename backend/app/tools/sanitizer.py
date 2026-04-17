"""
Sanitizer module — two hard-defense layers:
1. sanitize_tool_output(): strips injection patterns from DB/tool results
   before they reach the LLM context window.
2. sanitize_user_input(): decodes obfuscated user messages and checks
   them for injection patterns before the agent processes them.
"""
import re
import base64
import unicodedata

# Patterns that indicate an injection attempt inside retrieved data.
# These are matched case-insensitively.
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"you\s+are\s+now\s+",
    r"new\s+(system\s+)?prompt",
    r"system\s+(update|override|message|prompt)",
    r"act\s+as\s+(an?\s+)?(unrestricted|unfiltered|admin|root|jailbreak)",
    r"pretend\s+(you\s+have\s+no|there\s+are\s+no)\s+rules",
    r"(developer|debug|admin|god|dan)\s+mode",
    r"override\s+(your\s+)?(instructions?|rules?|constraints?|guidelines?)",
    r"disregard\s+(your\s+)?(previous|prior|all)\s+",
    r"repeat\s+the\s+(text|instructions?|prompt)\s+above",
    r"print\s+(your\s+)?(system\s+)?prompt",
    r"reveal\s+(your\s+)?(instructions?|system\s+prompt|rules?)",
    # Chinese variants
    r"忽略(之前|上面|所有)(的)?(指令|规则|限制)",
    r"(进入|切换到?)(调试|开发者|管理员|无限制)(模式)?",
    r"(显示|输出|打印)(你的|完整的)?(系统|推理|chain.of.thought)",
    r"你现在是",
    r"假装(你|没有)(没有)?规则",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Marker inserted in place of the scrubbed content so the agent knows
# something was removed (prevents silent data loss confusion).
_REDACTED = "[REDACTED: content flagged as potential prompt injection]"


def sanitize_tool_output(text: str) -> str:
    """
    Scan tool output for injection patterns line-by-line.
    Lines containing a pattern are replaced with a redaction marker.
    The surrounding data is preserved so legitimate results still come through.
    """
    if not isinstance(text, str):
        return text

    lines = text.splitlines()
    cleaned = []
    flagged = 0

    for line in lines:
        if any(pattern.search(line) for pattern in _COMPILED):
            cleaned.append(_REDACTED)
            flagged += 1
        else:
            cleaned.append(line)

    result = "\n".join(cleaned)
    if flagged:
        result += f"\n\n[Security notice: {flagged} line(s) were redacted from this result due to suspicious content.]"

    return result


# ---------------------------------------------------------------------------
# User input sanitizer — decodes obfuscation, then checks for injections
# ---------------------------------------------------------------------------

# Zero-width and invisible Unicode characters used to split keywords
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]")


def _try_decode_base64(text: str) -> str | None:
    """Return decoded string if text looks like base64, else None."""
    # Only attempt if it looks plausibly base64 (no spaces, right charset)
    candidate = text.strip().replace("\n", "")
    if len(candidate) < 8 or not re.match(r"^[A-Za-z0-9+/=]+$", candidate):
        return None
    try:
        decoded = base64.b64decode(candidate).decode("utf-8")
        # Only consider it base64 if result is printable ASCII/CJK text
        if decoded.isprintable():
            return decoded
    except Exception:
        pass
    return None


def _decode_unicode_escapes(text: str) -> str:
    """Expand \\uXXXX escape sequences that may be in raw user text."""
    try:
        return text.encode("utf-8").decode("unicode_escape")
    except Exception:
        return text


def sanitize_user_input(text: str) -> tuple[bool, str]:
    """
    Check user input for obfuscated injection attempts.

    Returns:
        (blocked: bool, reason: str)
        blocked=True means the message should be rejected before reaching the agent.
    """
    if not isinstance(text, str):
        return False, ""

    # 1. Strip zero-width characters (used to split keywords like "i​gnore")
    cleaned = _ZERO_WIDTH.sub("", text)

    # 2. Normalize unicode (e.g., fullwidth chars → ASCII)
    cleaned = unicodedata.normalize("NFKC", cleaned)

    # 3. Check plain text first
    for pattern in _COMPILED:
        if pattern.search(cleaned):
            return True, f"Message blocked: contains disallowed pattern."

    # 4. Check if any word-length token looks like base64
    for token in cleaned.split():
        decoded = _try_decode_base64(token)
        if decoded:
            for pattern in _COMPILED:
                if pattern.search(decoded):
                    return True, "Message blocked: contains obfuscated injection (base64)."

    # 5. Check unicode-escape decoded version
    ue_decoded = _decode_unicode_escapes(cleaned)
    if ue_decoded != cleaned:
        for pattern in _COMPILED:
            if pattern.search(ue_decoded):
                return True, "Message blocked: contains obfuscated injection (unicode escape)."

    return False, ""
