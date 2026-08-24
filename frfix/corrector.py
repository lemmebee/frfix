"""French correction engine powered by grammalecte."""

import unicodedata
from dataclasses import dataclass

try:
    import grammalecte
except ImportError as exc:  # pragma: no cover - depends on install state
    raise ImportError(
        "The Grammalecte engine is missing. It is not on PyPI; pygrammalecte "
        "downloads it on first use. Run 'frfix-bootstrap' to install it."
    ) from exc


@dataclass
class Correction:
    """A single correction within a text."""
    start: int
    end: int
    original: str
    replacement: str


class FrenchCorrector:
    """French spell/grammar checker using grammalecte."""

    def __init__(self, user_words: set[str] | None = None):
        self._user_words = {w.lower() for w in (user_words or set())}
        self._gc = grammalecte.GrammarChecker('fr')
        self._sp = self._gc.getSpellChecker()

    def check_word(self, word: str) -> str | None:
        """Check a single word. Returns correction or None if correct."""
        if not word:
            return None

        clean = word.strip(".,;:!?\"\u2019'()[]{}«»")
        if not clean or (len(clean) <= 2 and clean.lower() != "ca"):
            return None
        if not any(c.isalpha() for c in clean):
            return None
        if clean.lower() in self._user_words:
            return None

        # "ca" → "ça" — extremely common 2-char accent fix
        if clean.lower() == "ca":
            return _preserve_case(clean, "ça")

        if self._sp.isValid(clean):
            return None

        # Try elision (cest→c'est, lhomme→l'homme, cetait→c'était)
        elision = self._try_elision(clean)
        if elision:
            return _normalize_apostrophe(_preserve_case(clean, elision))

        # Grammalecte suggestions — require 4+ chars to avoid ambiguity
        if len(clean) >= 4:
            raw = list(self._sp.suggest(clean))
            if raw:
                suggestions = raw[0] if isinstance(raw[0], list) else raw
                if suggestions:
                    best = _pick_best(clean, suggestions[:15])
                    if best:
                        return _normalize_apostrophe(_preserve_case(clean, best))

        return None

    # Elision prefixes
    _ELISION_PREFIXES = ("c", "d", "j", "l", "m", "n", "s", "qu", "jusqu", "lorsqu", "puisqu")
    _VOWELS = set("aeiouyàâäéèêëïîôùûüÿœæ")
    _VALID_SHORT_ELISIONS = {
        ("j", "ai"), ("j", "en"), ("j", "y"),
        ("l", "ai"), ("l", "on"), ("l", "un"),
        ("n", "ai"), ("n", "en"), ("n", "y"),
        ("s", "en"), ("s", "y"),
        ("d", "en"), ("d", "y"), ("d", "un"),
        ("c", "en"),
        ("qu", "il"), ("qu", "on"), ("qu", "en"), ("qu", "un"),
    }

    def _try_elision(self, word: str) -> str | None:
        """Try inserting apostrophe. Very conservative:
        - Rest must start with vowel/h
        - Rest must be valid AS-IS or be an accent-only fix of a valid word
        """
        lower = word.lower()
        for prefix in self._ELISION_PREFIXES:
            if not lower.startswith(prefix) or len(lower) < len(prefix) + 2:
                continue
            rest = lower[len(prefix):]

            if rest[0] not in self._VOWELS and rest[0] != 'h':
                continue

            # For short rest (2 chars), only allow known valid combinations
            if len(rest) <= 2 and (prefix, rest) not in self._VALID_SHORT_ELISIONS:
                continue

            # Rest is already a valid word
            if self._sp.isValid(rest):
                return f"{prefix}'{rest}"

            # Rest is an accent-only fix of a valid word
            rest_stripped = _strip_accents(rest)
            raw = list(self._sp.suggest(rest))
            if not raw:
                continue
            rest_sugg = raw[0] if isinstance(raw[0], list) else raw
            for rs in rest_sugg[:5]:
                # Only accept accent-only corrections (stripped forms must match exactly)
                if _strip_accents(rs.lower()) == rest_stripped and self._sp.isValid(rs):
                    return f"{prefix}'{rs}"

        return None

    def check_sentence(self, sentence: str) -> list[Correction]:
        """Check a full sentence for grammar errors."""
        corrections = []
        try:
            errs = self._gc.getParagraphErrors(sentence)
            if not errs:
                return []
            for err in errs:
                if isinstance(err, dict):
                    sugg = err.get("aSuggestions", [])
                    if len(sugg) == 1:
                        start = err.get("nStart", 0)
                        end = err.get("nEnd", 0)
                        corrections.append(Correction(
                            start=start, end=end,
                            original=sentence[start:end],
                            replacement=sugg[0],
                        ))
        except Exception:
            pass
        return corrections


def _pick_best(original: str, suggestions: list[str]) -> str | None:
    """Pick the best suggestion. Conservative: only accent fixes and distance-1 typos."""
    lower = original.lower()
    orig_stripped = _strip_accents(lower)

    best = None
    best_score = 999

    for s in suggestions:
        s_lower = s.lower()
        s_stripped = _strip_accents(s_lower)

        base_dist = _edit_distance(orig_stripped, s_stripped)
        full_dist = _edit_distance(lower, s_lower)

        # Tier 1: Accent-only fix (base forms identical) — always safe
        if base_dist == 0 and full_dist <= 4:
            score = full_dist
        # Tier 2: 1 real char diff + possible accents — only for 4+ char words
        elif base_dist == 1 and full_dist <= 4 and len(original) >= 4:
            score = 10 + full_dist
        # Skip everything else — too risky
        else:
            continue

        if score < best_score:
            best = s
            best_score = score

    return best


def _normalize_apostrophe(text: str) -> str:
    """Replace typographic apostrophe with ASCII for reliable key injection."""
    return text.replace("\u2019", "'").replace("\u2018", "'")


def _preserve_case(original: str, correction: str) -> str:
    """Preserve the case pattern of the original word."""
    if original.isupper() and len(original) > 1:
        return correction.upper()
    if original[0].isupper():
        return correction[0].upper() + correction[1:]
    return correction


def _strip_accents(text: str) -> str:
    """Remove French accents for comparison."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance."""
    if len(a) < len(b):
        return _edit_distance(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[len(b)]
