"""
grammar_checker.py — Basic grammar analysis for PDF test script text.

Checks:
- Duplicate words
- Spelling mistakes (pyspellchecker)
- Punctuation issues
- Tense inconsistency (heuristic regex)
- Sentence fragments (heuristic: no verb detected)
"""

import re
from typing import List, Dict, Any, Optional

try:
    from spellchecker import SpellChecker
    _spell = SpellChecker()
    SPELL_AVAILABLE = True
except ImportError:
    SPELL_AVAILABLE = False

# ─── Domain whitelist ─────────────────────────────────────────────────────────
# Technical and domain-specific terms that are valid but absent from the
# standard English dictionary used by pyspellchecker.

DOMAIN_WHITELIST: set = {
    # Veeva / pharma / SaaS
    "veeva", "vault", "vaultid", "assure", "vassure",
    "pts", "uat", "oos", "alm", "sdlc", "gamp",
    # UI / UX terms
    "dropdown", "dropdowns", "checkbox", "checkboxes",
    "navbar", "sidebar", "tooltip", "tooltips", "modal", "modals",
    "popup", "popups", "submenu", "submenus", "stepper", "steppers",
    "multiselect", "multiselects", "clickable", "scrollable", "resizable",
    # Auth / user management
    "login", "logout", "signin", "signout", "signup",
    "username", "usernames", "passcode", "passphrase",
    # Dev / data terms
    "pdf", "csv", "xlsx", "xml", "json", "api", "url", "uri",
    "backend", "frontend", "middleware", "workflow", "workflows",
    "timestamp", "timestamps", "deactivate", "reactivate",
    "reactivated", "deactivated", "subtype", "subtypes",
    # Common abbreviations used in scripts
    "usd", "eur", "gbp", "na", "tbd", "tbc", "pre", "pos",
    # Short valid domain words that pyspellchecker may flag
    "btn", "nav", "div",
}


def _should_skip_spell(raw_word: str) -> bool:
    """Return True if this word should be excluded from spell-checking."""
    word = raw_word.strip(".,;:!?\"'()[]{}/\\-_")
    w = word.lower()

    if len(w) <= 3:
        return True
    if word == word.upper() and len(word) > 1:   # ALL-CAPS abbreviation
        return True
    if any(c.isdigit() for c in word):            # contains a digit
        return True
    if w in DOMAIN_WHITELIST:
        return True
    if word[0].isupper():                          # capitalised → likely proper noun
        return True
    if "-" in word or "/" in raw_word:             # hyphenated / slash compound
        return True

    return False


def _make_error(
    error_type: str,
    message: str,
    context: str,
    word: str = "",
    suggestion: str = "",
    source: str = "unknown",
    step_type: str = "unknown",
    step_number: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "error_type": error_type,
        "message": message,
        "context": context[:200],
        "word": word,
        "suggestion": suggestion,
        "source": source,
        "step_type": step_type,
        "step_number": step_number,
    }


def _context_around(text: str, start: int, window: int = 50) -> str:
    s = max(0, start - window)
    e = min(len(text), start + window)
    prefix = "…" if s > 0 else ""
    suffix = "…" if e < len(text) else ""
    return prefix + text[s:e] + suffix


# ─── Check 1: Duplicate words ─────────────────────────────────────────────────

def _check_duplicate_words(
    text: str, source: str, step_type: str, step_number: Optional[int]
) -> List[Dict]:
    errors = []
    # Match the same word (≥2 chars) appearing consecutively, case-insensitive
    pattern = re.compile(r"\b(\w{2,})\s+\1\b", re.IGNORECASE)
    for m in pattern.finditer(text):
        word = m.group(1)
        errors.append(_make_error(
            error_type="duplicate_word",
            message=f"Duplicate word: '{word} {word}'",
            context=_context_around(text, m.start()),
            word=word.lower(),
            suggestion=f"Remove one instance of '{word}'",
            source=source,
            step_type=step_type,
            step_number=step_number,
        ))
    return errors


# ─── Check 2: Spelling ────────────────────────────────────────────────────────

def _check_spelling(
    text: str, source: str, step_type: str, step_number: Optional[int]
) -> List[Dict]:
    if not SPELL_AVAILABLE:
        return []

    raw_words = re.findall(r"\S+", text)
    to_check = [
        re.sub(r"[^a-zA-Z]", "", w).lower()
        for w in raw_words
        if not _should_skip_spell(w)
    ]
    to_check = [w for w in to_check if len(w) > 3]
    if not to_check:
        return []

    misspelled = _spell.unknown(to_check)
    errors = []
    seen: set = set()

    for word in misspelled:
        if word in seen or word in DOMAIN_WHITELIST:
            continue
        seen.add(word)

        match = re.search(r"\b" + re.escape(word) + r"\b", text, re.IGNORECASE)
        pos = match.start() if match else 0
        suggestion = _spell.correction(word) or ""

        errors.append(_make_error(
            error_type="spelling",
            message=f"Possible spelling error: '{word}'",
            context=_context_around(text, pos),
            word=word,
            suggestion=(
                f"Did you mean '{suggestion}'?"
                if suggestion and suggestion != word else ""
            ),
            source=source,
            step_type=step_type,
            step_number=step_number,
        ))

    return errors


# ─── Check 3: Punctuation ─────────────────────────────────────────────────────

_PUNCT_RULES = [
    (r"[,;:][a-zA-Z]",  "Missing space after punctuation mark"),
    (r"[.!?]{2,}",      "Multiple consecutive sentence-ending punctuation"),
    (r" [,;]",          "Unexpected space before punctuation mark"),
]


def _check_punctuation(
    text: str, source: str, step_type: str, step_number: Optional[int]
) -> List[Dict]:
    errors = []
    for pattern, message in _PUNCT_RULES:
        for m in re.finditer(pattern, text):
            match_str = m.group()
            # Skip decimal numbers (e.g. "3.14") and URL patterns
            surrounding = text[max(0, m.start() - 2) : m.end() + 2]
            if re.search(r"\d[.]\d", surrounding):
                continue
            if any(
                proto in text[max(0, m.start() - 10) : m.start()]
                for proto in ("http", "https", "ftp")
            ):
                continue

            errors.append(_make_error(
                error_type="punctuation",
                message=message,
                context=_context_around(text, m.start()),
                word=match_str.strip(),
                suggestion="",
                source=source,
                step_type=step_type,
                step_number=step_number,
            ))
    return errors


# ─── Check 4: Tense inconsistency ─────────────────────────────────────────────

_PAST_RE = re.compile(
    r"\b(was|were|had|did|went|came|saw|knew|took|gave|found|told|thought|made"
    r"|appeared|returned|showed|verified|clicked|navigated|selected|entered"
    r"|confirmed|logged|saved|deleted|updated|created|opened|closed)\b",
    re.IGNORECASE,
)
_PRESENT_RE = re.compile(
    r"\b(is|are|has|have|does|navigate|click|select|verify|ensure|enter|confirm"
    r"|check|validate|display|show|appear|return|provide|create|delete|update"
    r"|save|close|open|login|logout|go|come|see|know|take|give|find|tell"
    r"|think|make|contains|includes|displays)\b",
    re.IGNORECASE,
)


def _check_tense_consistency(
    text: str, source: str, step_type: str, step_number: Optional[int]
) -> List[Dict]:
    past_found = _PAST_RE.findall(text)
    present_found = _PRESENT_RE.findall(text)

    # Only flag when both tenses are clearly present
    if len(past_found) >= 2 and len(present_found) >= 2:
        past_ex = ", ".join(
            f"'{w}'" for w in sorted({w.lower() for w in past_found})[:3]
        )
        pres_ex = ", ".join(
            f"'{w}'" for w in sorted({w.lower() for w in present_found})[:3]
        )
        return [_make_error(
            error_type="tense_inconsistency",
            message=(
                f"Mixed tenses detected — past ({past_ex}) and "
                f"present ({pres_ex}) used in the same text"
            ),
            context=text[:200],
            word="",
            suggestion=(
                "Use consistent tense throughout; test scripts "
                "typically use present/imperative tense"
            ),
            source=source,
            step_type=step_type,
            step_number=step_number,
        )]
    return []


# ─── Check 5: Sentence fragments ──────────────────────────────────────────────

_VERB_RE = re.compile(
    r"\b(is|are|was|were|has|have|had|do|does|did|will|would|should|could"
    r"|may|might|shall|be|been|being"
    # common past tense
    r"|went|came|got|put|set|ran|saw|gave|took|made|told|found|knew|left"
    r"|showed|appeared|returned|verified|clicked|navigated|selected|entered"
    r"|confirmed|logged|saved|deleted|updated|created|opened|closed"
    r"|displayed|included|contained|provided|checked|validated|ensured"
    # imperative/present
    r"|navigate|click|select|verify|ensure|enter|confirm|check|validate"
    r"|display|show|appear|return|provide|create|delete|update|save|close"
    r"|open|login|logout|contains|includes|displays|verifies|shows)\b",
    re.IGNORECASE,
)


def _check_sentence_fragments(
    text: str, source: str, step_type: str, step_number: Optional[int]
) -> List[Dict]:
    errors = []
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        words = sent.split()
        if len(words) < 4:
            continue
        if re.match(r"^[-•*\d#]", sent):   # bullet / numbered item — skip
            continue
        if not any(c.isalpha() for c in sent):
            continue

        if not _VERB_RE.search(sent):
            errors.append(_make_error(
                error_type="sentence_fragment",
                message="Possible sentence fragment (no verb detected)",
                context=sent[:150],
                word="",
                suggestion="Add a verb to complete the sentence",
                source=source,
                step_type=step_type,
                step_number=step_number,
            ))

    return errors


# ─── Public API ───────────────────────────────────────────────────────────────

def check_grammar(
    text: str,
    source: str,
    step_type: str,
    step_number: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Run all grammar checks on a piece of text.

    Args:
        text:        The text to analyse.
        source:      'client' or 'executed'.
        step_type:   'setup' | 'execution' | 'metadata'.
        step_number: Step number for context (optional).

    Returns:
        List of grammar-error dicts.
    """
    if not text or len(text.strip()) < 10:
        return []

    errors: List[Dict[str, Any]] = []
    errors.extend(_check_duplicate_words(text, source, step_type, step_number))
    errors.extend(_check_spelling(text, source, step_type, step_number))
    errors.extend(_check_punctuation(text, source, step_type, step_number))
    errors.extend(_check_tense_consistency(text, source, step_type, step_number))
    errors.extend(_check_sentence_fragments(text, source, step_type, step_number))
    return errors
