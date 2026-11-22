"""Small text helpers shared by the pages."""

from __future__ import annotations


def md_escape(text) -> str:
    """Escape characters that Streamlit markdown would interpret in data-driven labels."""
    out = str(text)
    for ch in ("\\", "*", "_", "`", "[", "]", "$", "<", ">", ":", "#", "|", "~"):
        out = out.replace(ch, "\\" + ch)
    return out
