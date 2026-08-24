"""frfix — main daemon entry point."""

import asyncio
import signal
import sys

from .buffer import TextBuffer, EventType
from .capture import KeystrokeCapture, KeyAction
from .config import load_config
from .corrector import FrenchCorrector
from .injector import TextInjector
from .xchar import KeyTranslator


LAYOUT_CHECK_INTERVAL = 2.0


class FrfixDaemon:
    """Main daemon orchestrating all components."""

    def __init__(self, skip_layout_check: bool = False, debug: bool = False,
                 force_layout: str | None = None, switch_layout: bool | None = None):
        self.config = load_config()
        self.buffer = TextBuffer()
        self.corrector = FrenchCorrector(user_words=self.config.user_words)
        self.injector = TextInjector()
        self.capture = KeystrokeCapture()
        self.translator = KeyTranslator(force_layout=force_layout)

        self._skip_layout_check = skip_layout_check
        self._debug = debug
        self._switch_layout = (
            self.config.auto_switch_layout if switch_layout is None else switch_layout
        )
        self._is_french = skip_layout_check
        self._original_layout_idx: int | None = None

    def _switch_to_french(self) -> None:
        """Put the session on a French layout, remembering what to restore."""
        self._original_layout_idx = self.translator.switch_to("fr")

    def _restore_layout(self) -> None:
        if self._original_layout_idx is not None:
            self.translator.restore(self._original_layout_idx)
            self._original_layout_idx = None

    def _print_banner(self) -> None:
        layouts = self.translator.layouts()
        print(
            f"frfix started.\n"
            f"  layout backend : {self.translator.backend_name} "
            f"({', '.join(layouts) if layouts else 'none detected'})\n"
            f"  keymap source  : {self.translator.source}\n"
            f"  injection      : {self.injector.backend_name}\n"
            f"  active layout  : {self.translator.active_layout() or 'unknown'} "
            f"(French: {self._is_french})"
        )
        print("Press Ctrl+C to stop.")

    async def run(self) -> None:
        """Main event loop."""
        if self._switch_layout and not self.translator.is_french():
            self._switch_to_french()

        if not self._skip_layout_check:
            self._is_french = self.translator.is_french()
            layout_task = asyncio.create_task(self._layout_checker())
        else:
            self._is_french = True
            layout_task = None

        self._print_banner()

        # systemd stops the service with SIGTERM, which by default kills the
        # process outright and skips the cleanup below, leaving the keyboard on
        # whatever layout the daemon switched it to. Handle it explicitly.
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):
                pass

        consumer = asyncio.create_task(self._consume_events())
        stopper = asyncio.create_task(stop.wait())
        try:
            await asyncio.wait({consumer, stopper}, return_when=asyncio.FIRST_COMPLETED)
            if consumer.done():
                consumer.result()  # surface capture errors instead of exiting silently
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            for task in (consumer, stopper, layout_task):
                if task:
                    task.cancel()
            self._restore_layout()
            self.translator.close()
            self.injector.close()
            print("frfix stopped.")

    async def _consume_events(self) -> None:
        """Feed captured keystrokes into the correction pipeline."""
        async for key_event in self.capture.events():
            if not self._is_french:
                self.buffer.reset()
                continue
            await self._handle_key(key_event)

    async def _handle_key(self, key_event) -> None:
        if key_event.action == KeyAction.UNDO:
            self._handle_undo()
            return

        if key_event.action in (KeyAction.ARROW, KeyAction.TAB,
                                KeyAction.ESCAPE, KeyAction.ENTER,
                                KeyAction.MODIFIER):
            self.buffer.reset()
            return

        if key_event.action == KeyAction.BACKSPACE:
            self.buffer.feed_backspace()
            return

        if key_event.action == KeyAction.SPACE:
            event = self.buffer.feed_char(" ")
            if event.type == EventType.WORD_COMPLETE:
                self._correct_word(event.word, extra_bs=1)
            return

        if key_event.action == KeyAction.CHAR:
            char = self.translator.translate(
                key_event.evdev_keycode,
                shift=key_event.shift,
                altgr=key_event.altgr,
            )
            if self._debug:
                print(f"  [char] {repr(char)} (keycode={key_event.evdev_keycode}, "
                      f"shift={key_event.shift}) | word={self.buffer.current_word!r}")
            if char:
                event = self.buffer.feed_char(char)
                if event.type == EventType.WORD_COMPLETE:
                    self._correct_word(event.word, extra_bs=1)
                elif event.type == EventType.SENTENCE_COMPLETE:
                    if event.word:
                        self._correct_word(event.word, extra_bs=1)
                    if self.config.grammar:
                        self._correct_sentence(event.sentence)

    def _correct_word(self, word: str, extra_bs: int = 1) -> None:
        """Check and correct a single word."""
        if not self.config.spelling:
            return

        if self._debug:
            print(f"  [check] word={word!r}")

        correction = self.corrector.check_word(word)
        if self._debug:
            print(f"  [result] {word!r} -> {correction!r}")

        if correction and correction != word:
            self.injector.replace_word(word, correction, extra_backspaces=extra_bs)
            self.buffer.push_correction(word, correction)
            self.buffer.reset()

            if self._debug:
                print(f"  [corrected] {word!r} -> {correction!r}")

    def _correct_sentence(self, sentence: str) -> None:
        """Check and correct grammar in a sentence."""
        corrections = self.corrector.check_sentence(sentence)
        if not corrections:
            return

        # Apply corrections right-to-left
        corrections.sort(key=lambda c: c.start, reverse=True)
        corrected = sentence
        for corr in corrections:
            corrected = corrected[:corr.start] + corr.replacement + corrected[corr.end:]

        if corrected == sentence:
            return

        if self._debug:
            print(f"  [grammar] {sentence!r} -> {corrected!r}")

        self.injector.send_backspaces(len(sentence))
        self.injector.send_string(corrected)

    def _handle_undo(self) -> None:
        """Undo last correction."""
        last = self.buffer.pop_correction()
        if last:
            old_word, corrected_word = last
            self.injector.replace_word(corrected_word, old_word, extra_backspaces=0)
            self.buffer.reset()

    async def _layout_checker(self) -> None:
        while True:
            await asyncio.sleep(LAYOUT_CHECK_INTERVAL)
            was_french = self._is_french
            self._is_french = self.translator.is_french()
            if was_french != self._is_french:
                if self._is_french:
                    print("French layout detected — corrections enabled")
                else:
                    print("Non-French layout — corrections paused")
                    self.buffer.reset()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="frfix — French autocorrect daemon")
    parser.add_argument("--no-layout-check", action="store_true",
                        help="Skip keyboard layout detection, always correct")
    parser.add_argument("--debug", action="store_true",
                        help="Print debug info (keystrokes, corrections)")
    parser.add_argument("--force-layout", type=str, default=None,
                        help="Force a specific layout (e.g., 'fr')")
    parser.add_argument("--switch-layout", action="store_true", default=None,
                        help="Switch the keyboard to French on startup "
                             "(overrides general.auto_switch_layout)")
    args = parser.parse_args()

    try:
        daemon = FrfixDaemon(
            skip_layout_check=args.no_layout_check,
            debug=args.debug,
            force_layout=args.force_layout,
            switch_layout=args.switch_layout,
        )
    except RuntimeError as exc:
        # Missing injection backend or unreadable input devices: both are
        # setup problems, and a traceback tells the user nothing useful.
        print(f"frfix: {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        asyncio.run(daemon.run())
    except RuntimeError as exc:
        print(f"frfix: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
