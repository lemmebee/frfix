"""Keystroke buffer with word/sentence boundary detection."""

from dataclasses import dataclass
from enum import Enum, auto


class EventType(Enum):
    NONE = auto()
    WORD_COMPLETE = auto()
    SENTENCE_COMPLETE = auto()


@dataclass
class BufferEvent:
    type: EventType = EventType.NONE
    word: str = ""
    separator: str = ""  # the character that completed the word


# Characters that end a word (like space)
WORD_BOUNDARIES = set(",;:()[]{}\"'")

# Characters that end a sentence
SENTENCE_ENDINGS = set(".!?")


@dataclass
class TextBuffer:
    current_word: str = ""
    current_sentence: str = ""
    _last_correction: tuple[str, str] | None = None

    def feed_char(self, char: str) -> BufferEvent:
        """Feed a character and return any triggered event."""
        if char == " " or char in WORD_BOUNDARIES:
            word = self.current_word
            self.current_sentence += self.current_word + char
            self.current_word = ""
            if word:
                return BufferEvent(type=EventType.WORD_COMPLETE, word=word, separator=char)
            return BufferEvent()

        if char in SENTENCE_ENDINGS:
            word = self.current_word
            self.current_sentence += self.current_word + char
            self.current_word = ""
            # The sentence stays in the buffer so a word correction made now
            # can patch it; the daemon resets once it has run the grammar check.
            return BufferEvent(
                type=EventType.SENTENCE_COMPLETE,
                word=word,
                separator=char,
            )

        self.current_word += char
        return BufferEvent()

    def feed_backspace(self) -> None:
        """Handle backspace — remove last character."""
        if self.current_word:
            self.current_word = self.current_word[:-1]
        elif self.current_sentence:
            self.current_sentence = self.current_sentence.rstrip()
            if self.current_sentence:
                parts = self.current_sentence.rsplit(" ", 1)
                if len(parts) == 2:
                    self.current_sentence = parts[0] + " "
                    self.current_word = parts[1]
                else:
                    self.current_word = parts[0]
                    self.current_sentence = ""

    def reset(self) -> None:
        """Reset buffer — called on cursor movement, focus change, etc."""
        self.current_word = ""
        self.current_sentence = ""

    def push_correction(self, old: str, new: str) -> None:
        """Remember the last correction, for a single level of undo, and
        patch the sentence so it keeps mirroring the screen.

        Only the most recent one: undo backspaces at the *current* caret,
        which is only correct for the correction just made. Keeping a
        deeper history would let undo eat text typed since an older
        correction, so a ring buffer here would be a bug, not a feature.
        """
        self._last_correction = (old, new)
        head = self.current_sentence[: len(self.current_sentence) - len(old)]
        self.current_sentence = head + new

    def drop_correction(self) -> None:
        """Forget the last correction: the caret has moved, so undo would
        backspace over the wrong text."""
        self._last_correction = None

    def pop_correction(self) -> tuple[str, str] | None:
        """Consume the last correction for undo."""
        last = self._last_correction
        self._last_correction = None
        return last
