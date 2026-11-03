"""
Length limits each marketplace enforces on listing text, shared by the AI prompt and the rule engine.
Amazon: titles of 75 characters since 27 July 2026 and backend search terms under 200 bytes on
Amazon.in (spec §3.1). Flipkart and Meesho titles: 120 and 100 characters.
"""
from typing import Dict

TITLE_CHAR_LIMITS: Dict[str, int] = {"amazon": 75, "flipkart": 120, "meesho": 100}
# Counted in UTF-8 bytes; Flipkart and Meesho publish no limit, so they keep the earlier 250
KEYWORD_BYTE_LIMITS: Dict[str, int] = {"amazon": 200, "flipkart": 250, "meesho": 250}

# The prompt asks for this share of each limit; the rest is buffer, so generated text rarely
# overflows and has to be regenerated
PROMPT_LIMIT_RATIO = 0.9


def title_limit(marketplace: str) -> int:
    return TITLE_CHAR_LIMITS.get((marketplace or "amazon").lower(), TITLE_CHAR_LIMITS["amazon"])


def keyword_byte_limit(marketplace: str) -> int:
    return KEYWORD_BYTE_LIMITS.get((marketplace or "amazon").lower(), KEYWORD_BYTE_LIMITS["amazon"])


def prompt_target(limit: int) -> int:
    """The length the prompt asks for: PROMPT_LIMIT_RATIO of the marketplace's limit."""
    return int(limit * PROMPT_LIMIT_RATIO)
