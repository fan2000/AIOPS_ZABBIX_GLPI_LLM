"""Guardrails de sécurité LLM (OWASP LLM01 anti-prompt-injection, redaction PII/secrets, comptage FinOps)."""

import re

_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above)\s+instructions?\b"),
    re.compile(r"(?i)\bdisregard\s+(?:all\s+|the\s+)?(?:previous|above)\b"),
    re.compile(r"(?i)\bforget\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above\s+)?instructions?\b"),
    re.compile(r"(?i)\boverride\s+(?:the\s+|your\s+)?system(?:\s+prompt|\s+instructions?)?\b"),
    re.compile(r"(?i)\bnew\s+instructions?\s*:"),
    re.compile(r"(?i)\bjailbreak\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+(?:a|an|in)\b"),
    re.compile(r"(?i)<\|\s*(?:im_start|im_end|system|assistant|user|eot_id)\s*\|>"),
    re.compile(r"(?i)\[/?INST\]"),
    re.compile(r"(?im)^\s*(?:system|assistant|developer)\s*:\s*"),
    re.compile(r"(?i)</?untrusted_[a-z0-9_]+>"),
]

_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.MULTILINE,
)
_URL_CRED_RE = re.compile(r"(?i)\b(postgres(?:ql)?|redis|https?|amqp|mysql)://([^:\s/@]+):([^@\s/]+)@")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\b")
_AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_BEARER_RE = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9\-._~+/]+=*")
_KV_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|session[_-]?token)\b(\s*[:=]\s*)([^\s,;\"']+)"
)
_PREFIXED_KEY_RE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{12,}|xox[baprs]-[A-Za-z0-9-]{10,})\b")
_LONG_HEX_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")


def sanitize_untrusted_text(text: str, max_len: int = 1200) -> str:
    """Neutralise les marqueurs d'injection de prompt et caractères de contrôle (OWASP LLM01)."""
    if not text:
        return ""
    cleaned = "".join(ch for ch in str(text) if ch in ("\n", "\t") or ord(ch) >= 32)
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("[FILTERED_DIRECTIVE]", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "..."
    return cleaned


def redact_sensitive_data(text: str) -> str:
    """Masque secrets, clés privées, JWT, clés AWS, credentials URL et mots de passe avant toute inférence LLM."""
    if not text:
        return ""
    out = _PRIVATE_KEY_RE.sub("[REDACTED_PRIVATE_KEY]", str(text))
    out = _URL_CRED_RE.sub(r"\1://\2:[REDACTED]@", out)
    out = _JWT_RE.sub("[REDACTED_JWT]", out)
    out = _AWS_KEY_RE.sub("[REDACTED_AWS_KEY]", out)
    out = _BEARER_RE.sub(r"\1[REDACTED_TOKEN]", out)
    out = _KV_SECRET_RE.sub(r"\1\2[REDACTED]", out)
    out = _PREFIXED_KEY_RE.sub("[REDACTED_API_KEY]", out)
    out = _LONG_HEX_RE.sub("[REDACTED_SECRET_HEX]", out)
    return out


def wrap_untrusted_xml(tag: str, content: str, max_len: int = 1200) -> str:
    """Isole des données non fiables (Zabbix/KB) dans des balises XML sécurisées."""
    safe_tag = re.sub(r"[^a-zA-Z0-9_]", "_", tag).lower()
    secured = sanitize_untrusted_text(redact_sensitive_data(content), max_len=max_len)
    return f"<untrusted_{safe_tag}>\n{secured}\n</untrusted_{safe_tag}>"


def estimate_tokens(text: str) -> int:
    """Estime le nombre de tokens (~4 caractères par token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_cost_usd(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estime le coût d'inférence USD (0.0 pour modèles on-premise Ollama/vLLM)."""
    prov = (provider or "ollama").lower()
    if prov in ("ollama", "disabled", "local", "vllm"):
        return 0.0
    m = (model or "").lower()
    if "4o" in m and "mini" not in m:
        in_rate, out_rate = 2.50, 10.00
    elif "sonnet" in m or "claude" in m:
        in_rate, out_rate = 3.00, 15.00
    else:
        in_rate, out_rate = 0.15, 0.60
    cost = (max(0, prompt_tokens) * in_rate + max(0, completion_tokens) * out_rate) / 1_000_000.0
    return round(cost, 6)
