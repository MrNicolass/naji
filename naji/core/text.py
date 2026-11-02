"""Sanitização da resposta do modelo para exibição e fala.

O modelo às vezes responde com markdown, listas, links, HTML ou emojis mesmo
com o prompt em contrário. A barra e o TTS trabalham com texto puro, então a
resposta final passa por este filtro antes de ser exibida, falada e guardada
no histórico.
"""

from __future__ import annotations

import re

_CODE_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BOLD_DOUBLE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_UNDERLINE = re.compile(r"__(.+?)__", re.DOTALL)
_STRIKE = re.compile(r"~~(.+?)~~", re.DOTALL)
_ITALIC_STAR = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_ITALIC_UNDERLINE = re.compile(r"(?<![\w_])_([^_\n]+)_(?![\w_])")
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_BARE_URL = re.compile(r"\bhttps?://\S+")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u2190-\u21FF]"
)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_TABLE_SEPARATOR = re.compile(r"^\|?[\s:|-]+\|[\s:|-]*$")


def clean_spoken_text(text: str) -> str:
    """Return plain, single-spaced text suitable for the bar and TTS."""
    if not text:
        return ""
    cleaned = text.replace("\r\n", "\n")
    cleaned = _CODE_FENCE.sub(r"\1", cleaned)
    cleaned = _IMAGE.sub(" ", cleaned)
    cleaned = _LINK.sub(r"\1", cleaned)
    cleaned = _INLINE_CODE.sub(r"\1", cleaned)
    cleaned = _BOLD_DOUBLE.sub(r"\1", cleaned)
    cleaned = _BOLD_UNDERLINE.sub(r"\1", cleaned)
    cleaned = _STRIKE.sub(r"\1", cleaned)
    cleaned = _ITALIC_STAR.sub(r"\1", cleaned)
    cleaned = _ITALIC_UNDERLINE.sub(r"\1", cleaned)
    cleaned = _HEADING.sub("", cleaned)
    cleaned = _BLOCKQUOTE.sub("", cleaned)
    lines: list[str] = []
    for line in cleaned.split("\n"):
        stripped = line.strip()
        if "|" in stripped and _TABLE_SEPARATOR.match(stripped):
            continue
        if "|" in line:
            inner = line.strip().strip("|")
            line = ", ".join(part.strip() for part in inner.split("|") if part.strip())
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = _BULLET.sub("", cleaned)
    cleaned = _NUMBERED.sub("", cleaned)
    cleaned = _HTML_TAG.sub(" ", cleaned)
    cleaned = _BARE_URL.sub(" ", cleaned)
    cleaned = _EMOJI.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\s*\n\s*", " ", cleaned)
    return cleaned.strip()
