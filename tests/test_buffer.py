"""Characterization tests for the keystroke buffer."""

from frfix.buffer import EventType, TextBuffer


def feed(buffer: TextBuffer, text: str) -> list:
    return [buffer.feed_char(char) for char in text]


def test_plain_characters_accumulate_without_events():
    buf = TextBuffer()
    events = feed(buf, "bonjour")
    assert all(event.type is EventType.NONE for event in events)
    assert buf.current_word == "bonjour"
    assert buf.current_sentence == ""


def test_space_completes_a_word_and_moves_it_into_the_sentence():
    buf = TextBuffer()
    feed(buf, "bonjour")
    event = buf.feed_char(" ")
    assert event.type is EventType.WORD_COMPLETE
    assert event.word == "bonjour"
    assert buf.current_word == ""
    assert buf.current_sentence == "bonjour "


def test_word_boundary_punctuation_completes_a_word():
    buf = TextBuffer()
    feed(buf, "salut")
    event = buf.feed_char(",")
    assert event.type is EventType.WORD_COMPLETE
    assert event.word == "salut"
    assert buf.current_sentence == "salut,"


def test_repeated_separator_yields_no_event():
    buf = TextBuffer()
    buf.feed_char(" ")
    event = buf.feed_char(" ")
    assert event.type is EventType.NONE
    assert event.word == ""


def test_sentence_ending_reports_word_and_sentence_and_clears_both():
    buf = TextBuffer()
    feed(buf, "salut le monde")
    event = buf.feed_char(".")
    assert event.type is EventType.SENTENCE_COMPLETE
    assert event.word == "monde"
    assert event.sentence == "salut le monde."
    assert buf.current_word == ""
    assert buf.current_sentence == ""


def test_sentence_ending_right_after_a_separator_has_an_empty_word():
    buf = TextBuffer()
    feed(buf, "fini ")
    event = buf.feed_char("!")
    assert event.type is EventType.SENTENCE_COMPLETE
    assert event.word == ""
    assert event.sentence == "fini !"


def test_backspace_trims_the_current_word():
    buf = TextBuffer()
    feed(buf, "abc")
    buf.feed_backspace()
    assert buf.current_word == "ab"


def test_backspace_on_an_empty_word_pulls_the_previous_word_back():
    buf = TextBuffer()
    feed(buf, "un deux ")
    buf.feed_backspace()
    assert buf.current_word == "deux"
    assert buf.current_sentence == "un "


def test_backspace_on_a_single_word_sentence_empties_the_sentence():
    buf = TextBuffer()
    feed(buf, "seul ")
    buf.feed_backspace()
    assert buf.current_word == "seul"
    assert buf.current_sentence == ""


def test_backspace_on_an_empty_buffer_is_a_no_op():
    buf = TextBuffer()
    buf.feed_backspace()
    assert buf.current_word == ""
    assert buf.current_sentence == ""


def test_reset_clears_word_and_sentence():
    buf = TextBuffer()
    feed(buf, "quelque chose")
    buf.reset()
    assert buf.current_word == ""
    assert buf.current_sentence == ""


def test_pop_correction_returns_what_was_pushed():
    buf = TextBuffer()
    buf.push_correction("ca", "ça")
    assert buf.pop_correction() == ("ca", "ça")


def test_pop_correction_is_empty_with_nothing_pushed():
    buf = TextBuffer()
    assert buf.pop_correction() is None


def test_only_the_most_recent_correction_is_kept():
    buf = TextBuffer()
    buf.push_correction("ca", "ça")
    buf.push_correction("cest", "c'est")
    assert buf.pop_correction() == ("cest", "c'est")


def test_popping_consumes_the_correction():
    buf = TextBuffer()
    buf.push_correction("ca", "ça")
    buf.pop_correction()
    assert buf.pop_correction() is None


def test_reset_does_not_drop_the_undo_history():
    buf = TextBuffer()
    buf.push_correction("ca", "ça")
    buf.reset()
    assert buf.pop_correction() == ("ca", "ça")
