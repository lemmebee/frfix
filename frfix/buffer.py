"""Keystroke buffer with word/sentence boundary detection."""

from dataclasses import dataclass, field
from enum import Enum, auto


class EventType(Enum):
    NONE = auto()
    WORD_COMPLETE = auto()
    SENTENCE_COMPLETE = auto()


@dataclass
class BufferEvent:
    type: EventType = EventType.NONE
    word: str = ""
    sentence: str = ""


# Characters that end a word (like space)
WORD_BOUNDARIES = set(",;:()[]{}\"'")

# Characters that end a sentence
SENTENCE_ENDINGS = set(".!?")


@dataclass
class TextBuffer:
    current_word: str = ""
    current_sentence: str = ""
    _last_corrections: list[tuple[str, str]] = field(default_factory=list)

    def feed_char(self, char: str) -> BufferEvent:
        """Feed a character and return any triggered event."""
        if char == " " or char in WORD_BOUNDARIES:
            word = self.current_word
            self.current_sentence += self.current_word + char
            self.current_word = ""
            if word:
                return BufferEvent(type=EventType.WORD_COMPLETE, word=word)
            return BufferEvent()

        if char in SENTENCE_ENDINGS:
            word = self.current_word
            sentence = self.current_sentence + self.current_word + char
            self.current_word = ""
            self.current_sentence = ""
            return BufferEvent(
                type=EventType.SENTENCE_COMPLETE,
                word=word,
                sentence=sentence,
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

    def replace_last_word(self, new_word: str) -> None:
        """Update sentence buffer after a word correction."""
        if self.current_sentence.endswith(" "):
            parts = self.current_sentence.rstrip().rsplit(" ", 1)
            if len(parts) == 2:
                self.current_sentence = parts[0] + " " + new_word + " "
            else:
                self.current_sentence = new_word + " "

    def push_correction(self, old: str, new: str) -> None:
        """Store a correction for undo."""
        self._last_corrections.append((old, new))
        if len(self._last_corrections) > 20:
            self._last_corrections.pop(0)

    def pop_correction(self) -> tuple[str, str] | None:
        """Pop last correction for undo."""
        if self._last_corrections:
            return self._last_corrections.pop()
        return None
