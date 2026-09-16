"""Characterization tests for the French correction engine."""

import pytest

from frfix.corrector import (
    FrenchCorrector,
    _edit_distance,
    _normalize_apostrophe,
    _pick_best,
    _preserve_case,
    _strip_accents,
)


@pytest.fixture(scope="module")
def corrector():
    return FrenchCorrector()


@pytest.mark.parametrize(
    "word, expected",
    [
        ("francais", "français"),
        ("tres", "très"),
        ("etre", "être"),
        ("deja", "déjà"),
        ("ecole", "école"),
        ("probleme", "problème"),
        ("pere", "père"),
    ],
)
def test_missing_accents_are_restored(corrector, word, expected):
    assert corrector.check_word(word) == expected


def test_single_character_typo_is_fixed(corrector):
    assert corrector.check_word("bonjor") == "bonjour"


@pytest.mark.parametrize(
    "word, expected",
    [
        ("cest", "c'est"),
        ("lhomme", "l'homme"),
        ("cetait", "c'était"),
        ("jai", "j'ai"),
        ("quil", "qu'il"),
        ("dun", "d'un"),
    ],
)
def test_elisions_get_their_apostrophe(corrector, word, expected):
    assert corrector.check_word(word) == expected


@pytest.mark.parametrize("word", ["ca", "Ca"])
def test_ca_is_the_one_short_word_that_is_corrected(corrector, word):
    assert corrector.check_word(word) == ("ça" if word == "ca" else "Ça")


@pytest.mark.parametrize("word", ["bonjour", "mais", "oui", "tache"])
def test_valid_words_are_left_alone(corrector, word):
    assert corrector.check_word(word) is None


@pytest.mark.parametrize("word", ["", "a", "le", "ou", "ete"])
def test_short_words_are_never_touched(corrector, word):
    assert corrector.check_word(word) is None


def test_an_unrecognisable_word_is_left_alone(corrector):
    assert corrector.check_word("xyzzy") is None


@pytest.mark.parametrize("word", ["123", "!!!", "42."])
def test_words_without_letters_are_ignored(corrector, word):
    assert corrector.check_word(word) is None


def test_user_dictionary_words_are_never_corrected():
    corrector = FrenchCorrector(user_words={"francais"})
    assert corrector.check_word("francais") is None


def test_user_dictionary_matching_ignores_case():
    corrector = FrenchCorrector(user_words={"FRANCAIS"})
    assert corrector.check_word("francais") is None


def test_surrounding_punctuation_does_not_block_a_correction(corrector):
    assert corrector.check_word('"francais"') == "français"


def test_a_correction_never_contains_a_typographic_apostrophe(corrector):
    assert "\u2019" not in (corrector.check_word("cest") or "")


def test_check_sentence_returns_a_list(corrector):
    assert isinstance(corrector.check_sentence("Ceci est un test."), list)


def test_check_sentence_survives_empty_input(corrector):
    assert corrector.check_sentence("") == []


def test_an_agreement_error_yields_a_real_correction(corrector):
    assert [(c.start, c.end, c.replacement) for c in corrector.check_sentence(
        "Les chien sont dehors."
    )] == [(4, 9, "chiens")]


def test_a_real_error_survives_while_typography_is_dropped(corrector):
    # Default options would also suggest "\xa0:" (non-breaking space) here.
    assert [(c.start, c.end, c.replacement) for c in corrector.check_sentence(
        "Les chien sont dehors : ok."
    )] == [(4, 9, "chiens")]


def test_plural_notation_is_never_rewritten_with_a_middle_dot(corrector):
    # An always-on rule (no option group) suggests "auteur\u00b7s" here.
    assert corrector.check_sentence("Les auteur(s) du livre.") == []
    assert corrector.check_sentence("Les client.s sont contents.") == []


def test_unit_spacing_never_injects_a_non_breaking_space(corrector):
    # Default options would suggest "5\xa0km" (unit group) here.
    assert [(c.start, c.end, c.replacement) for c in corrector.check_sentence(
        "Elle a 5 km a faire."
    )] == [(12, 13, "à")]


def test_thousands_grouping_never_injects_a_non_breaking_space(corrector):
    # The still-enabled "num" group suggests "1\xa0000" here.
    assert corrector.check_sentence("1000 km parcourus.") == []


def test_letter_o_for_zero_is_still_corrected(corrector):
    # Same "num" group as above; these are real typo fixes and must survive the guard.
    assert [c.replacement for c in corrector.check_sentence("Il y a 1OO personnes.")] == ["100"]
    assert [c.replacement for c in corrector.check_sentence("J'ai 3O ans.")] == ["30"]


def test_a_sentence_correction_never_contains_a_typographic_apostrophe(corrector):
    # grammalecte suggests "qu\u2019" for this elision error.
    corrections = corrector.check_sentence("Je pense que il viendra.")
    assert [c.replacement for c in corrections] == ["qu'"]


@pytest.mark.parametrize(
    "original, correction, expected",
    [
        ("bonjour", "bonjour", "bonjour"),
        ("Bonjour", "bonjour", "Bonjour"),
        ("BONJOUR", "bonjour", "BONJOUR"),
        ("A", "a", "A"),
    ],
)
def test_preserve_case(original, correction, expected):
    assert _preserve_case(original, correction) == expected


@pytest.mark.parametrize(
    "text, expected",
    [("français", "francais"), ("élève", "eleve"), ("abc", "abc")],
)
def test_strip_accents(text, expected):
    assert _strip_accents(text) == expected


@pytest.mark.parametrize(
    "a, b, expected",
    [("", "", 0), ("abc", "abc", 0), ("abc", "abd", 1), ("abc", "", 3), ("", "ab", 2)],
)
def test_edit_distance(a, b, expected):
    assert _edit_distance(a, b) == expected


def test_normalize_apostrophe_rewrites_both_curly_forms():
    assert _normalize_apostrophe("c\u2019est l\u2018un") == "c'est l'un"


def test_pick_best_prefers_an_accent_only_fix():
    assert _pick_best("francais", ["francaise", "français"]) == "français"


def test_pick_best_rejects_a_suggestion_that_is_too_far_away():
    assert _pick_best("francais", ["bonjour"]) is None


def test_pick_best_allows_one_real_character_difference():
    assert _pick_best("bonjor", ["bonjour"]) == "bonjour"


def test_pick_best_refuses_a_character_difference_on_short_words():
    assert _pick_best("abc", ["abd"]) is None


def test_pick_best_returns_none_without_suggestions():
    assert _pick_best("francais", []) is None
