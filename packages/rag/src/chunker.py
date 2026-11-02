"""Nettoyage et découpage récursif des documents GLPI et procédures."""

import re
from typing import List


def clean_html(text: str) -> str:
    """Supprime les balises HTML et décode les entités basiques issues de GLPI."""
    if not text:
        return ""
    # Remplacement des sauts de ligne HTML
    cleaned = re.sub(r"<br\s*/?>|</p>|</div>", "\n", text, flags=re.IGNORECASE)
    # Suppression des balises HTML
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    # Remplacement des espaces multiples et entités
    cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\n\s*\n", "\n\n", cleaned).strip()


class TextChunker:
    """Découpe un texte en segments de taille cible avec recouvrement (overlap)."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 80):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        """Découpe le texte en respectant les paragraphes et phrases."""
        cleaned = clean_html(text)
        if not cleaned:
            return []
        if len(cleaned) <= self.chunk_size:
            return [cleaned]

        paragraphs = cleaned.split("\n\n")
        chunks: List[str] = []
        current_chunk = ""

        for p in paragraphs:
            p_strip = p.strip()
            if not p_strip:
                continue

            if len(current_chunk) + len(p_strip) + 2 <= self.chunk_size:
                current_chunk = f"{current_chunk}\n\n{p_strip}".strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(p_strip) > self.chunk_size:
                    # Découpage par phrases
                    words = p_strip.split(" ")
                    sub_chunk = ""
                    for w in words:
                        if len(sub_chunk) + len(w) + 1 <= self.chunk_size:
                            sub_chunk = f"{sub_chunk} {w}".strip()
                        else:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                            sub_chunk = w
                    if sub_chunk:
                        current_chunk = sub_chunk
                else:
                    current_chunk = p_strip

        if current_chunk:
            chunks.append(current_chunk)

        return chunks


text_chunker = TextChunker()
