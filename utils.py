"""
Utility functions for Jenkins pipeline parsing and conversion
"""

import re
from typing import Tuple


def strip_comments(text: str) -> str:
    """Remove C-style and C++-style comments from text"""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*", "", text)
    return text


def find_block(text: str, start_pat: str) -> Tuple[int, int]:
    """
    Find a block starting with pattern and enclosed in braces
    Returns (start_index, end_index) of content within braces, or (-1, -1) if not found
    """
    m = re.search(start_pat, text)
    if not m:
        return -1, -1
    i = m.end()
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text) or text[i] != '{':
        return -1, -1
    depth = 0
    start = i + 1
    i += 1
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            if depth == 0:
                return start, i
            depth -= 1
        i += 1
    return -1, -1


def sanitize_name(name: str) -> str:
    """Sanitize names for file paths and action names"""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name.strip())


def gha_job_id(name: str) -> str:
    """Convert stage name to GitHub Actions job ID"""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-").lower()
    return slug or "job"


def multiline_to_commands(s: str) -> list[str]:
    """Convert multiline string to list of commands, filtering empty lines"""
    lines = [ln.strip() for ln in s.splitlines()]
    return [ln for ln in lines if ln]
