# Clownfish 🐟

[![CI](https://github.com/wispsy/clownfish/actions/workflows/ci.yml/badge.svg)](https://github.com/wispsy/clownfish/actions/workflows/ci.yml)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A lightweight, modern terminal emulator written in Python and Tkinter, featuring TrueColor rendering, full POSIX PTY bridge, mouse reporting, Unicode wide character support, device attribute queries, and shell integration.

---

## Features

- **Unicode Grapheme Clusters & Complex Emojis**: Support for Zero-Width Joiner (ZWJ, `\u200D`) connected emoji sequences (e.g. `👩‍💻`), Fitzpatrick skin tone modifiers, regional indicator flag pairs (`🇯🇵`), and extended emoji/symbol pictographs in monospace terminal grid math.
- **VT/xterm & Keyboard Conformance**: Full F1–F12 function key encoding, standard xterm modified navigation keys (`Ctrl/Alt/Shift + Arrows/Home/End/PageUp/PageDown`), DECOM Origin Mode (`?6h`/`?6l`), DECAWM Auto-wrap Mode (`?7h`/`?7l`), DECSCUSR cursor styles (block, underline, bar), and DEC Mode 2026 Synchronized Output for tear-free rendering.
- **Mouse Motion Reporting**: Button motion tracking (`?1002h`) and any-event motion tracking (`?1003h`) alongside standard press/release (`?1000h`) and SGR format (`?1006h`).
- **Interactive Login Shells & Job Control**: Launches native user shells (`/bin/zsh`, `/bin/bash`) as login interactive shells (`-l -i`) with controlling terminal allocation (`TIOCSCTTY`), pre-spawn window sizing (`TIOCSWINSZ`), and full POSIX job control (`Ctrl+C`, `Ctrl+Z`, `fg`, `bg`).
- **Non-Destructive Soft-Wrap Reflow**: Dynamic text reflow (`Row.is_wrapped`) when resizing terminal columns, preserving character buffers, styles, wide glyphs, and cursor positioning without data loss.
- **Screen-Editing VT Sequences**: Full support for Cursor Next/Previous Line (`CSI E`/`F`), Erase Characters (`CSI X`), Insert/Delete Lines (`CSI L`/`M`), Scroll Up/Down (`CSI S`/`T`), and ANSI Cursor Save/Restore (`CSI s`/`u`).
- **Prompt Preservation on Clear**: Complete terminal reset (`Cmd+K` / `Ctrl+K`) flushes scrollback while requesting interactive shell redraw (`Ctrl+L`), preserving partially typed command lines.
- **Dynamic Window & Tab Titles**: Shell `precmd` window and tab title sequences (`OSC 0` and `OSC 2`) update desktop tab headers in real time.
- **Multi-Tab Terminal Sessions**: Manage multiple independent terminal sessions with tab switching shortcuts (`Cmd+T`, `Cmd+W`, `Cmd+1..9`, `Ctrl+Tab`).
- **Split Panes**: Divide any tab vertically (`Cmd+D`) or horizontally (`Cmd+Shift+D`) with native resizable sash dividers.
- **In-Buffer Search**: Interactive search bar (`Cmd+F`) across active terminal screen and scrollback history with match highlighting and cycling.
- **User Preferences**: Persistent configuration in `~/.config/clownfish/config.json`.
- **TrueColor & 256-Color Support**: Full 24-bit RGB TrueColor escaping and standard ANSI 16/256 palette support.
- **Full Screen & Scrollback Clear**: Complete terminal reset with `Cmd+K` (macOS) or `Ctrl+K` (Linux/Windows) that flushes active screen and all 10,000 lines of scrollback buffer.
- **Unicode Wide Characters & Emojis**: Character classification via East Asian Width (`unicodedata.east_asian_width`) for 2-column CJK characters and emojis with sentinel spacer cells.
- **Device Attribute Queries**: Standard VT220 / xterm query responses for DA1 (`\x1b[c`), DA2 (`\x1b[>c`), DSR / CPR (`\x1b[6n`), and OSC 10/11 color queries, eliminating CLI boot delays.
- **Kitty Keyboard Protocol**: Protocol flag negotiation (`CSI ? u`, `CSI = u`, `CSI > u`, `CSI < u`) enabling disambiguation of modified keystrokes like `Shift+Enter`.
- **OSC 133 Semantic Prompts**: Shell integration tracking prompt start, command execution, and exit codes, enabling prompt-to-prompt jumping (`Cmd+Up` / `Cmd+Down`).
- **OSC 8 Hyperlinks**: Clickable URLs with browser launching via `Cmd+Click` or `Ctrl+Click`.
- **Mouse Tracking**: Normal tracking (`?1000h`) and SGR decimal tracking (`?1006h`) for interactive CLI programs like `vim`, `htop`, and `tmux`.
- **Primary & Alternate Screen Buffers**: Smooth transitions into and out of full-screen terminal programs without corrupting main scrollback.

---

## Installation & Running

Ensure you have Python 3.14+ and [uv](https://docs.astral.sh/uv/) installed.

### Clone the Repository
```bash
git clone https://github.com/wispsy/clownfish.git
cd clownfish
```

### Install Dependencies
```bash
uv sync --all-extras
```

### Run Clownfish
```bash
uv run clownfish
```

Or run directly with python:
```bash
uv run python -m clownfish
```

---

## Testing & Quality Assurance

Run the test suite:
```bash
uv run pytest
```

Run code formatting and linting:
```bash
uv run ruff check .
```

---

## Documentation

- [Architecture Guide](docs/architecture.md): Deep dive into screen buffer management, parser state machine, and render loop.
- [Modern Terminal Gap Analysis](docs/modern-terminal-gap-analysis.md): Technical analysis of the fundamental features required for modern terminal emulators.
- [Keyboard & Mouse Shortcuts](docs/shortcuts.md): Guide to shortcuts for clearing buffers, navigation, and clipboard operations.

---

## Project Structure

```text
clownfish/
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions CI workflow (Ubuntu & macOS)
├── docs/
│   ├── architecture.md            # Architecture overview & data flow
│   ├── modern-terminal-gap-analysis.md # Modern terminal specifications
│   └── shortcuts.md               # Keybinding reference
├── src/
│   └── clownfish/
│       ├── __init__.py            # Public API exports & launch function
│       ├── __main__.py            # Module entrypoint (python -m clownfish)
│       ├── config.py              # Configuration dataclasses (TerminalConfig)
│       ├── syntax.py              # Syntax highlighting integration
│       ├── core/                  # Core terminal engine
│       │   ├── models.py          # Data models (Cell, Style, Selection, PromptMarker)
│       │   ├── keyboard.py        # Keystroke encoding & Kitty keyboard protocol
│       │   ├── parser.py          # VT100 / ANSI / OSC escape sequence parser
│       │   ├── screen.py          # Screen buffer, dual grid, autowrap & scrollback
│       │   └── search.py          # In-buffer regex & plain text search engine
│       ├── session/               # Terminal session layer
│       │   ├── session.py         # TerminalSession lifecycle manager
│       │   └── transport.py       # Abstract Transport base class
│       ├── transports/            # Pluggable I/O transports
│       │   ├── pty.py             # POSIX PTYTransport with write buffering
│       │   └── ssh.py             # SSHTransport via OpenSSH PTY bridge
│       └── frontends/
│           └── tkinter/           # Tkinter desktop frontend
│               ├── app.py         # TkTerminalApp main window & menu shortcuts
│               ├── pane.py        # TerminalPane self-contained terminal widget
│               ├── split.py       # SplitView arbitrary nested split pane manager
│               ├── tabs.py        # TabbedTerminalView multi-tab session manager
│               ├── renderer.py    # Canvas text & selection renderer
│               └── input.py       # Pointer & keyboard event translator
├── tests/                         # Comprehensive unit & integration test suite
├── pyproject.toml                 # Project metadata & build settings
└── README.md
```

---

## Roadmap

- [x] Split-pane multiplexing and tabbed sessions.
- [x] In-buffer regex / plain text search with highlight overlay.
- [ ] GPU-accelerated texture atlas rendering via Metal/Vulkan.
- [ ] HarfBuzz typography shaping for developer font ligatures (`->`, `!=`, `===`).
- [ ] Kitty Graphics Protocol inline image streaming.
- [ ] Sixel bitmap rasterization protocol support.

---

## License

This project is licensed under the MIT License.
