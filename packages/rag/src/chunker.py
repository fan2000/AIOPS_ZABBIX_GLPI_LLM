"""Chunking sémantique structuré (HTML/Markdown, code/listes) et Contextual Retrieval."""

from datetime import datetime, timezone
import html as html_lib
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

SOURCE_LABELS: Dict[str, str] = {
    "glpi_kb": "GLPI KB",
    "resolved_ticket": "Ticket Résolu GLPI",
    "runbook_doc": "Runbook Certifié",
    "wiki": "Wiki Interne",
}

_LINUX_HINTS = (
    "/var/log",
    "systemctl",
    "systemd",
    "ubuntu",
    "debian",
    "rhel",
    "centos",
    "bash",
    "df -h",
    "du -sh",
    "journalctl",
    "linux",
    "apt-get",
    "chmod",
)
_WINDOWS_HINTS = (
    "get-process",
    "get-service",
    "restart-service",
    "powershell",
    "eventvwr",
    "spooler",
    "wuauserv",
    "windows",
    ".exe",
    "c:\\",
)
_NETWORK_HINTS = (
    "cisco",
    "bgp",
    "vlan",
    "ospf",
    "fortigate",
    "pfsense",
    "ipsec",
    "router",
    "switch",
)

_SERVICE_TOKENS: List[tuple[str, str]] = [
    ("nginx", r"\bnginx\b"),
    ("apache2", r"\bapache2?\b"),
    ("postgresql", r"\b(?:postgres|postgresql|pgvector)\b"),
    ("mariadb", r"\bmariadb\b"),
    ("mysql", r"\bmysql\b"),
    ("redis", r"\bredis\b"),
    ("zabbix-agent", r"\bzabbix[-_ ]agent2?\b"),
    ("docker", r"\bdocker\b"),
    ("spooler", r"\bspooler\b"),
    ("wuauserv", r"\bwuauserv\b"),
    ("postfix", r"\bpostfix\b"),
    ("ssh", r"\b(?:sshd?|openssh)\b"),
    ("bgp", r"\bbgp\b"),
    ("vpn", r"\b(?:vpn|ipsec|wireguard)\b"),
    ("glpi", r"\bglpi\b"),
]


class SemanticChunk(BaseModel):
    """Segment structuré avec section active et métadonnées opérationnelles filtrables."""

    chunk_index: int
    text: str
    raw_text: str
    section: Optional[str] = None
    has_code_block: bool = False
    has_list: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


def clean_html(text: str) -> str:
    """Supprime les balises HTML et décode les entités issues de GLPI en texte propre."""
    if not text:
        return ""
    cleaned = html_lib.unescape(str(text))
    cleaned = re.sub(
        r"<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>|</pre>",
        "\n",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return re.sub(r"\n\s*\n", "\n\n", cleaned).strip()


def html_to_structured_text(text: str) -> str:
    """Convertit un contenu HTML ou Markdown en texte structuré préservant titres, code et listes."""
    if not text:
        return ""
    src = html_lib.unescape(str(text)).replace("\r\n", "\n")

    # 1. Protéger les blocs <pre><code>...</code></pre> ou <pre>...</pre> en blocs Markdown ```
    def _replace_pre(match: re.Match) -> str:
        inner = re.sub(r"<br\s*/?>", "\n", match.group(1), flags=re.IGNORECASE)
        inner = re.sub(r"<[^>]+>", "", inner)
        inner = inner.strip("\n")
        return f"\n\n```\n{inner}\n```\n\n" if inner else "\n\n"

    src = re.sub(r"<pre[^>]*>\s*(?:<code[^>]*>)?([\s\S]*?)(?:</code>)?\s*</pre>", _replace_pre, src, flags=re.IGNORECASE)

    # 2. Code inline <code>...</code>
    src = re.sub(
        r"<code[^>]*>([\s\S]*?)</code>",
        lambda m: f"`{re.sub(r'<[^>]+>', '', m.group(1)).strip()}`",
        src,
        flags=re.IGNORECASE,
    )

    # 3. Titres <h1..h6> -> Markdown # .. ######
    def _replace_heading(match: re.Match) -> str:
        lvl = min(6, max(1, int(match.group(1))))
        body = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        return f"\n\n{'#' * lvl} {body}\n\n" if body else "\n\n"

    src = re.sub(r"<h([1-6])[^>]*>([\s\S]*?)</h\1>", _replace_heading, src, flags=re.IGNORECASE)

    # 4. Items de liste <li> -> ligne '- ...'
    def _replace_li(match: re.Match) -> str:
        body = re.sub(r"<br\s*/?>", " ", match.group(1), flags=re.IGNORECASE)
        body = re.sub(r"<[^>]+>", "", body)
        body = re.sub(r"\s+", " ", body).strip()
        return f"\n- {body}" if body else ""

    src = re.sub(r"<li[^>]*>([\s\S]*?)</li>", _replace_li, src, flags=re.IGNORECASE)

    # 5. Paragraphes et retours de ligne HTML
    src = re.sub(r"<br\s*/?>", "\n", src, flags=re.IGNORECASE)
    src = re.sub(r"</(?:p|div|ul|ol|table|blockquote|tr)>", "\n\n", src, flags=re.IGNORECASE)
    src = re.sub(r"<[^>]+>", "", src)

    # Normaliser les lignes blanches hors blocs de code
    parts = re.split(r"(```[\s\S]*?```)", src)
    normalized_parts: List[str] = []
    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            normalized_parts.append(part.strip())
        else:
            cleaned_part = re.sub(r"[ \t]+\n", "\n", part)
            cleaned_part = re.sub(r"\n{3,}", "\n\n", cleaned_part).strip()
            if cleaned_part:
                normalized_parts.append(cleaned_part)
    return "\n\n".join(normalized_parts).strip()


def extract_operational_metadata(
    title: str,
    text: str,
    source_type: str = "glpi_kb",
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extrait les métadonnées filtrables (os, service, site_code, category, updated_at)."""
    extra = dict(extra_metadata or {})
    combined = f"{title}\n{text}"
    lower = combined.lower()

    # Détection OS
    has_linux = any(h in lower for h in _LINUX_HINTS) or bool(re.search(r"\btop\b", lower))
    has_windows = any(h in lower for h in _WINDOWS_HINTS)
    has_network = any(h in lower for h in _NETWORK_HINTS)

    if has_linux and has_windows:
        inferred_os = "cross_platform"
    elif has_linux:
        inferred_os = "linux"
    elif has_windows:
        inferred_os = "windows"
    elif has_network:
        inferred_os = "network"
    else:
        inferred_os = "all"

    # Détection services
    services: List[str] = []
    for svc_name, pattern in _SERVICE_TOKENS:
        if re.search(pattern, lower):
            services.append(svc_name)

    # Détection catégorie
    if any(k in lower for k in ("cpu", "load average", "processeur")):
        inferred_cat = "cpu"
    elif any(k in lower for k in ("disque", "disk", "/var/log", "inode", "partition", "espace", "df -h")):
        inferred_cat = "disk"
    elif any(k in lower for k in ("ram", "mémoire", "memoire", "swap", "oom")):
        inferred_cat = "memory"
    elif any(k in lower for k in ("postgresql", "mariadb", "mysql", "pgvector", "deadlock", "base de données")):
        inferred_cat = "database"
    elif any(k in lower for k in ("bgp", "vpn", "vlan", "dns", "latence", "packet loss", "icmp")):
        inferred_cat = "network"
    elif any(k in lower for k in ("tls", "certificat", "pare-feu", "firewall", "rbac", "cve")):
        inferred_cat = "security"
    elif any(k in lower for k in ("service", "systemctl", "systemd", "get-service", "restart-service", "daemon")):
        inferred_cat = "service"
    else:
        inferred_cat = "general"

    # Site / Zone
    site_match = re.search(r"\b((?:DC|SITE|OT|BR|HUB)-[A-Z0-9_-]{2,20}|HQ)\b", combined)
    inferred_site = site_match.group(1) if site_match else "GLOBAL"

    meta: Dict[str, Any] = {
        "os": str(extra.get("os") or inferred_os).lower(),
        "services": list(extra.get("services") or services),
        "service": str(extra.get("service") or (services[0] if services else "general")).lower(),
        "category": str(extra.get("category") or inferred_cat).lower(),
        "site_code": str(extra.get("site_code") or inferred_site).upper(),
        "updated_at": str(extra.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        "source_type": str(extra.get("source_type") or source_type or "glpi_kb"),
    }
    if title and title.strip():
        meta["title"] = title.strip()
    if "is_faq" in extra:
        meta["is_faq"] = bool(extra["is_faq"])
    return meta


def build_contextual_prefix(
    title: str = "",
    source_type: str = "",
    meta: Optional[Dict[str, Any]] = None,
    section: Optional[str] = None,
) -> str:
    """Construit l'en-tête contextuel (Contextual Retrieval Anthropic) préfixant chaque chunk."""
    clean_title = (title or "").strip()
    if not source_type and meta is None:
        return f"[Titre: {clean_title}] " if clean_title else ""

    m = meta or {}
    parts: List[str] = []
    if source_type:
        parts.append(f"Source: {SOURCE_LABELS.get(source_type, source_type)}")
    os_val = m.get("os")
    if os_val:
        parts.append(f"OS: {os_val}")
    svc_val = m.get("service")
    if svc_val and svc_val != "general":
        parts.append(f"Service: {svc_val}")
    cat_val = m.get("category")
    if cat_val and cat_val != "general":
        parts.append(f"Catégorie: {cat_val}")
    site_val = m.get("site_code")
    if site_val and site_val != "GLOBAL":
        parts.append(f"Site: {site_val}")
    if section and section.strip():
        parts.append(f"Section: {section.strip()}")
    if clean_title:
        parts.append(f"Titre: {clean_title}")

    return f"[{' | '.join(parts)}] " if parts else ""


class TextChunker:
    """Découpeur sémantique HTML/Markdown avec overlap 15-20% et Contextual Retrieval."""

    def __init__(self, chunk_size: int = 600, chunk_overlap: int = 108):
        self.chunk_size = max(100, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))

    def _extract_overlap_tail(self, text: str) -> str:
        """Extrait un suffixe d'au plus `chunk_overlap` caractères aligné sur une frontière de mot."""
        if self.chunk_overlap <= 0 or not text:
            return ""
        if len(text) <= self.chunk_overlap:
            return text.strip()
        tail = text[-self.chunk_overlap :]
        first_space = tail.find(" ")
        if 0 <= first_space < len(tail) - 1:
            tail = tail[first_space + 1 :]
        return tail.strip()

    def _parse_semantic_blocks(self, structured_text: str) -> List[Dict[str, str]]:
        """Segmente le texte structuré en blocs typés : heading, code_block, list_block, paragraph."""
        blocks: List[Dict[str, str]] = []
        segments = re.split(r"(```[\s\S]*?```)", structured_text)

        for seg in segments:
            if not seg or not seg.strip():
                continue
            if seg.startswith("```") and seg.endswith("```"):
                blocks.append({"type": "code_block", "content": seg.strip()})
                continue

            for para in re.split(r"\n{2,}", seg):
                lines = [ln.rstrip() for ln in para.strip().splitlines() if ln.strip()]
                if not lines:
                    continue

                buf_lines: List[str] = []
                buf_mode: Optional[str] = None  # "list_block" | "paragraph"

                def _flush_buf() -> None:
                    if buf_lines and buf_mode:
                        blocks.append({"type": buf_mode, "content": "\n".join(buf_lines)})
                        buf_lines.clear()

                for line in lines:
                    heading_m = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
                    is_list = bool(re.match(r"^(?:[-*]|\d+\.)\s+", line.strip()))
                    if heading_m:
                        _flush_buf()
                        buf_mode = None
                        blocks.append({"type": "heading", "content": heading_m.group(2).strip()})
                    elif is_list:
                        if buf_mode != "list_block":
                            _flush_buf()
                            buf_mode = "list_block"
                        buf_lines.append(line.strip())
                    else:
                        if buf_mode != "paragraph":
                            _flush_buf()
                            buf_mode = "paragraph"
                        buf_lines.append(line.strip())
                _flush_buf()

        return blocks

    def _split_oversized_code_block(self, code_block: str, max_len: int) -> List[str]:
        lines = code_block.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
            fence_open = lines[0]
            body_lines = lines[1:-1]
        else:
            fence_open = "```"
            body_lines = lines

        fragments: List[str] = []
        cur: List[str] = []
        cur_len = len(fence_open) + 6
        for ln in body_lines:
            if cur and cur_len + len(ln) + 1 > max_len:
                fragments.append(f"{fence_open}\n" + "\n".join(cur) + "\n```")
                cur = [ln]
                cur_len = len(fence_open) + len(ln) + 6
            else:
                cur.append(ln)
                cur_len += len(ln) + 1
        if cur:
            fragments.append(f"{fence_open}\n" + "\n".join(cur) + "\n```")
        return fragments or [code_block]

    def _split_long_paragraph(self, text: str, max_len: int) -> List[str]:
        """Découpe un long paragraphe par phrases puis par mots avec recouvrement réel."""
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        chunks: List[str] = []
        cur = ""

        for sent in sentences:
            candidate = f"{cur} {sent}".strip() if cur else sent
            if len(candidate) <= max_len:
                cur = candidate
                continue

            if cur:
                chunks.append(cur)
                seed = self._extract_overlap_tail(cur)
                cur = f"{seed} {sent}".strip() if seed and len(f"{seed} {sent}".strip()) <= max_len else sent
            else:
                cur = sent

            if len(cur) > max_len:
                words = cur.split(" ")
                sub = ""
                for w in words:
                    cand = f"{sub} {w}".strip() if sub else w
                    if len(cand) <= max_len:
                        sub = cand
                    else:
                        if sub:
                            chunks.append(sub)
                            seed_w = self._extract_overlap_tail(sub)
                            cand_after = f"{seed_w} {w}".strip() if seed_w else w
                            sub = cand_after if len(cand_after) <= max_len else w
                        else:
                            sub = w
                cur = sub

        if cur:
            chunks.append(cur)
        return chunks

    def chunk_document(
        self,
        text: str,
        title: str = "",
        source_type: str = "glpi_kb",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[SemanticChunk]:
        """Découpe sémantiquement un document HTML/Markdown avec métadonnées contextuelles."""
        structured = html_to_structured_text(text)
        if not structured:
            return []

        legacy_mode = source_type == "" and metadata is None
        op_meta = (
            {}
            if legacy_mode
            else extract_operational_metadata(
                title=title,
                text=structured,
                source_type=source_type or "glpi_kb",
                extra_metadata=metadata,
            )
        )

        blocks = self._parse_semantic_blocks(structured)
        entries: List[Dict[str, Any]] = []
        active_section: Optional[str] = None
        current_parts: List[str] = []
        current_has_code = False
        current_has_list = False
        current_section: Optional[str] = None

        def _prefix_len(sec: Optional[str]) -> int:
            return len(build_contextual_prefix(title, source_type, None if legacy_mode else op_meta, sec))

        def _current_effective_size() -> int:
            return max(80, self.chunk_size - _prefix_len(current_section))

        def _flush(carry_overlap: bool = False) -> str:
            nonlocal current_parts, current_has_code, current_has_list
            if not current_parts:
                return ""
            raw = "\n\n".join(current_parts).strip()
            entries.append(
                {
                    "raw_text": raw,
                    "section": current_section,
                    "has_code_block": current_has_code,
                    "has_list": current_has_list,
                }
            )
            overlap = self._extract_overlap_tail(raw) if (carry_overlap and not current_has_code) else ""
            current_parts = []
            current_has_code = False
            current_has_list = False
            return overlap

        for blk in blocks:
            btype = blk["type"]
            btext = blk["content"]

            if btype == "heading":
                _flush(carry_overlap=False)
                active_section = btext
                current_section = active_section
                continue

            if not current_parts:
                current_section = active_section
            eff_size = _current_effective_size()
            cur_len = sum(len(p) for p in current_parts) + max(0, len(current_parts) - 1) * 2

            if btype == "code_block":
                if current_parts and cur_len + len(btext) + 2 > eff_size:
                    _flush(carry_overlap=False)
                    current_section = active_section
                    eff_size = _current_effective_size()

                if len(btext) > int(eff_size * 1.4):
                    for frag in self._split_oversized_code_block(btext, eff_size):
                        entries.append(
                            {
                                "raw_text": frag,
                                "section": current_section,
                                "has_code_block": True,
                                "has_list": False,
                            }
                        )
                else:
                    current_parts.append(btext)
                    current_has_code = True
                continue

            if btype == "list_block":
                if current_parts and cur_len + len(btext) + 2 > eff_size:
                    _flush(carry_overlap=False)
                    current_section = active_section
                    eff_size = _current_effective_size()

                if len(btext) <= eff_size:
                    current_parts.append(btext)
                    current_has_list = True
                else:
                    for item_line in btext.splitlines():
                        c_len = sum(len(p) for p in current_parts) + max(0, len(current_parts) - 1) * 2
                        if current_parts and c_len + len(item_line) + 2 > eff_size:
                            _flush(carry_overlap=False)
                            current_section = active_section
                        current_parts.append(item_line)
                        current_has_list = True
                continue

            # btype == "paragraph"
            if len(btext) <= eff_size:
                if current_parts and cur_len + len(btext) + 2 <= eff_size:
                    current_parts.append(btext)
                else:
                    if current_parts:
                        seed = _flush(carry_overlap=True)
                        current_section = active_section
                        eff_size = _current_effective_size()
                        if seed and len(seed) + len(btext) + 2 <= eff_size:
                            current_parts = [seed, btext]
                        else:
                            current_parts = [btext]
                    else:
                        current_parts = [btext]
            else:
                if current_parts:
                    seed = _flush(carry_overlap=True)
                    current_section = active_section
                    eff_size = _current_effective_size()
                    combined = f"{seed} {btext}".strip() if seed else btext
                else:
                    combined = btext
                long_parts = self._split_long_paragraph(combined, eff_size)
                for lp in long_parts[:-1]:
                    entries.append(
                        {
                            "raw_text": lp,
                            "section": current_section,
                            "has_code_block": False,
                            "has_list": False,
                        }
                    )
                if long_parts:
                    current_parts = [long_parts[-1]]

        _flush(carry_overlap=False)

        overlap_ratio = round(self.chunk_overlap / self.chunk_size, 3)
        total = len(entries)
        result: List[SemanticChunk] = []
        for idx, entry in enumerate(entries):
            sec = entry["section"]
            prefix = build_contextual_prefix(
                title=title,
                source_type=source_type,
                meta=None if legacy_mode else op_meta,
                section=sec,
            )
            full_text = f"{prefix}{entry['raw_text']}".strip()
            chunk_meta = dict(op_meta)
            chunk_meta.update(
                {
                    "chunk_schema_version": 2,
                    "chunk_index": idx,
                    "total_chunks": total,
                    "section": sec,
                    "has_code_block": bool(entry["has_code_block"]),
                    "has_list": bool(entry["has_list"]),
                    "overlap_ratio": overlap_ratio,
                }
            )
            result.append(
                SemanticChunk(
                    chunk_index=idx,
                    text=full_text,
                    raw_text=entry["raw_text"],
                    section=sec,
                    has_code_block=bool(entry["has_code_block"]),
                    has_list=bool(entry["has_list"]),
                    metadata=chunk_meta,
                )
            )
        return result

    def split_text(
        self,
        text: str,
        title: str = "",
        source_type: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Point d'entrée compatible retournant les textes contextualisés des chunks."""
        return [
            sc.text
            for sc in self.chunk_document(
                text=text,
                title=title,
                source_type=source_type,
                metadata=metadata,
            )
        ]


text_chunker = TextChunker()
