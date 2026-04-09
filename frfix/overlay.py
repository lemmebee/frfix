"""Correction overlay — shows brief tooltip near text caret."""

import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')

from gi.repository import Gtk, Gdk, GLib, Pango


class CorrectionOverlay:
    """Brief floating overlay showing corrections near the caret."""

    def __init__(self, duration_ms: int = 1500, bg_color: str = "#1a1a2e",
                 text_color: str = "#e0e0e0", highlight_color: str = "#4ecca3"):
        self._duration_ms = duration_ms
        self._bg_color = bg_color
        self._text_color = text_color
        self._highlight_color = highlight_color
        self._window: Gtk.Window | None = None
        self._hide_timer: int | None = None
        self._gtk_ready = False
        self._atspi_available = False

        # Try to init AT-SPI for caret position
        try:
            gi.require_version('Atspi', '2.0')
            from gi.repository import Atspi
            Atspi.init()
            self._atspi_available = True
        except Exception:
            pass

    def show_correction(self, old_text: str, new_text: str,
                        cursor_x: int = 0, cursor_y: int = 0) -> None:
        """Show correction overlay. Must be called from any thread — dispatches to GTK."""
        # Try to get caret position via AT-SPI
        caret_x, caret_y = self._get_caret_position()
        if caret_x is not None:
            cursor_x, cursor_y = caret_x, caret_y

        GLib.idle_add(self._show_on_gtk_thread, old_text, new_text, cursor_x, cursor_y)

    def _show_on_gtk_thread(self, old_text: str, new_text: str,
                            x: int, y: int) -> bool:
        """Create/update overlay window on GTK thread."""
        # Cancel previous hide timer
        if self._hide_timer is not None:
            GLib.source_remove(self._hide_timer)
            self._hide_timer = None

        # Destroy previous window
        if self._window is not None:
            self._window.destroy()

        # Create new window
        win = Gtk.Window(type=Gtk.WindowType.POPUP)
        win.set_decorated(False)
        win.set_accept_focus(False)
        win.set_keep_above(True)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)

        # Make it semi-transparent
        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            win.set_visual(visual)
        win.set_app_paintable(True)

        # Apply CSS styling
        css = f"""
        .correction-overlay {{
            background-color: {self._bg_color};
            border-radius: 6px;
            padding: 4px 10px;
        }}
        .old-text {{
            color: {self._text_color};
            text-decoration: line-through;
            font-size: 13px;
        }}
        .arrow {{
            color: {self._text_color};
            font-size: 13px;
        }}
        .new-text {{
            color: {self._highlight_color};
            font-weight: bold;
            font-size: 13px;
        }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Build content
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.get_style_context().add_class("correction-overlay")

        old_label = Gtk.Label(label=old_text)
        old_label.get_style_context().add_class("old-text")

        arrow_label = Gtk.Label(label="→")
        arrow_label.get_style_context().add_class("arrow")

        new_label = Gtk.Label(label=new_text)
        new_label.get_style_context().add_class("new-text")

        box.pack_start(old_label, False, False, 0)
        box.pack_start(arrow_label, False, False, 0)
        box.pack_start(new_label, False, False, 0)

        win.add(box)

        # Position slightly above the cursor
        win.move(x, y - 40)
        win.show_all()

        self._window = win

        # Auto-hide after duration
        self._hide_timer = GLib.timeout_add(self._duration_ms, self._hide)

        return False  # Don't repeat

    def _hide(self) -> bool:
        """Hide and destroy the overlay."""
        if self._window is not None:
            self._window.destroy()
            self._window = None
        self._hide_timer = None
        return False  # Don't repeat

    def _get_caret_position(self) -> tuple[int | None, int | None]:
        """Try to get text caret position via AT-SPI."""
        if not self._atspi_available:
            return None, None

        try:
            from gi.repository import Atspi

            desktop = Atspi.get_desktop(0)
            # Find the focused accessible object
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                if app is None:
                    continue
                focused = self._find_focused_text(app)
                if focused is not None:
                    try:
                        text_iface = focused.get_text_iface()
                        if text_iface:
                            offset = text_iface.get_caret_offset()
                            rect = text_iface.get_character_extents(
                                offset, Atspi.CoordType.SCREEN
                            )
                            if rect.x > 0 and rect.y > 0:
                                return rect.x, rect.y
                    except Exception:
                        pass
        except Exception:
            pass

        return None, None

    def _find_focused_text(self, obj) -> object | None:
        """Recursively find the focused text widget via AT-SPI."""
        from gi.repository import Atspi

        try:
            state_set = obj.get_state_set()
            if state_set.contains(Atspi.StateType.FOCUSED):
                # Check if it has text interface
                try:
                    text_iface = obj.get_text_iface()
                    if text_iface:
                        return obj
                except Exception:
                    pass

            for i in range(obj.get_child_count()):
                child = obj.get_child_at_index(i)
                if child is None:
                    continue
                result = self._find_focused_text(child)
                if result is not None:
                    return result
        except Exception:
            pass

        return None
