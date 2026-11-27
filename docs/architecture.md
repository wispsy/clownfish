# Clownfish Architecture

Clownfish is a modular terminal emulator written in Python. This document describes the internal subsystems, data flow, concurrency model, and session architecture.

```mermaid
flowchart TD
    subgraph Host / Remote
        Shell["Interactive Shell / Subprocess (/bin/zsh, bash, OpenSSH)"]
    end

    subgraph Transport Layer
        Transport["Transport (ABC)"]
        PTY["PTYTransport (Lossless Outgoing Queue + Nonblocking Reader Thread)"]
        SSH["SSHTransport (Interactive OpenSSH Bridge)"]
        Transport --> PTY
        Transport --> SSH
    end

    subgraph Session Layer
        Session["TerminalSession (Thread-Safe Event Queue + Lifecyle Manager)"]
        UTF8["UTF-8 Incremental Decoder"]
        Session --> UTF8
    end

    subgraph Core Engine
        Parser["VT100Parser (State Machine, OSC 133, Kitty KB)"]
        Screen["ScreenBuffer (Primary + Alt Grids, Scrollback deque)"]
        Keyboard["Keyboard Encoder (Standard CSI + Kitty Protocol)"]
        Models["Data Models (Cell, Style, Selection, PromptMarker)"]
    end

    subgraph Frontend - Tkinter
        App["TkTerminalApp (Window & Session Controller)"]
        Renderer["TkCanvasRenderer (60 FPS Canvas Batching)"]
        InputHandler["TkInputHandler (Pointer & Key Translation)"]
    end

    Shell <--> PTY
    PTY -->|Raw Bytes via Thread-Safe Event Queue| Session
    Session --> Parser
    Parser --> Screen
    Parser -->|Response stream| PTY
    App -->|Main Thread Drain & Render| Renderer
    Renderer --> Screen
    InputHandler -->|Keystrokes / Clicks| Session
    Session -->|Enqueued Writes| PTY
```

---

## Subsystems

### 1. Core Engine (`clownfish.core`)
- **`models.py`**:
  - `Style`: 24-bit RGB TrueColor fg/bg tuples, plus attributes (`bold`, `italic`, `underline`, `reverse`).
  - `Cell`: Individual grid cell (`char`, `style`, `url`, `width`). Supports East Asian Wide characters (width=2) with continuation spacers (width=0).
  - `GraphicImage`: Stored graphic data in memory (`image_id`, `format`, `data`, `base64_data`, `pixel_width`, `pixel_height`, `version`).
  - `GraphicPlacement`: Inline graphic placement record (`image_id`, `placement_id`, `col`, `row`, `abs_row`, `cols`, `rows`, `cursor_advance`).
  - `Selection`: Normalized character cell coordinates for active mouse selection.
  - `PromptMarker`: Semantic prompt tracking for OSC 133 shell integration.
- **`keyboard.py`**:
  - Keystroke translation to standard ANSI/xterm sequences and Kitty keyboard protocol (`CSI u` and modified cursor navigation).
- **`ligatures.py`**:
  - Ligature-aware monospace text segmentation engine (`find_ligatures`, `segment_row_cells`). Groups contiguous same-styled cells into operator runs (`!=`, `->`, `=>`, `===`, `::=`, etc.) for developer fonts while locking segment start coordinates to the monospace column grid (`start_col * cell_width`). Default disabled (`enable_ligatures=False`).
- **`screen.py`**:
  - `ScreenBuffer`: Dual-grid architecture (`primary_grid` and `alt_grid`), pending autowrap delay (`wrap_pending`), dirty row tracking, prompt marker preservation, and high-performance scrollback (`collections.deque`).
- **`parser.py`**:
  - `VT100Parser`: Fast state machine parser handling ANSI colors, colon-delimited SGR subparameters, OSC 8 hyperlinks, OSC 133 shell integration, device attributes (DA1, DA2, DSR, color queries), and bounded payloads with robust ST (`ESC \`) termination detection.

### 2. Session Layer (`clownfish.session`)
- **`TerminalSession`**:
  - Owns `ScreenBuffer`, `VT100Parser`, input encoding, and `Transport`.
  - Independent of any GUI or platform: can be run headless, in test environments, in background automations, or attached to desktop frontends.
  - Thread-Safe Event Queue: Background transport threads deliver incoming byte chunks and disconnect notifications into a safe `queue.Queue`. The UI event loop drains these on the main thread, guaranteeing that screen buffer mutations and widget operations are strictly thread-safe.
  - Default Transport Factory: Decoupled via `set_default_transport_factory` / `get_default_transport` so embedded and non-POSIX environments can load sessions without requiring desktop POSIX PTY modules.

### 3. Transport Layer (`clownfish.transports`)
- **`Transport` (ABC)**:
  - Base interface defining `start()`, `write()`, `resize()`, `close()`, `is_alive()`, and callback registration.
- **`PTYTransport`**:
  - Local pseudo-terminal transport using `pty.fork()` and `termios.TIOCSWINSZ`.
  - Lossless outgoing write queue: Asynchronously drains unwritten bytes when the PTY file descriptor becomes writable without blocking caller threads or dropping bytes on `EAGAIN`.
  - Background reader thread multiplexes incoming PTY reads and outgoing write queue flushes via `select.select()`.
- **`SSHTransport`**:
  - Interactive OpenSSH client transport allocating a remote pseudo-terminal (`ssh -tt`).

### 4. Desktop Frontend (`clownfish.frontends.tkinter`)
- **`TkTerminalApp`**: Root application controller coordinating multi-tab views, window resizing, global shortcuts (`Cmd+T`, `Cmd+W`, `Cmd+K`, `Cmd+D`, `Cmd+Shift+O`, etc.), active job close confirmations, safe multiline paste prompts, and session layout persistence.
- **`TabbedTerminalView`**: Manages independent terminal tabs with custom tab bar, tab switching, SSH indicators (`🌐`), and recursive split layout restoration.
- **`SplitView`**: Manages arbitrary nested horizontal and vertical panes with resizable sash dividers, split cycling (`Cmd+[` / `Cmd+]` or `Alt+[` / `Alt+]`), split equalization (`Cmd+=` / `Ctrl+=`), active pane border highlights (`#4a90e2`), and recursive split-tree serialization.
- **`TerminalPane`**: Embeds a `TerminalSession`, `TkCanvasRenderer`, `TkInputHandler`, and search overlay bar. Features adaptive render ticks (1ms bursts, 16ms interactive, 100ms idle/hidden tabs) and DECSET 1004 focus reporting.
- **`TkCanvasRenderer`**: Canvas rendering pipeline with font metrics, dirty row caching, scanline background run batching (merging identical adjacent background cells into single canvas rectangles), ligature-aware text run rendering, inline Kitty graphics photo-image rendering with aspect-ratio-preserving cell scaling, and z-ordered selection/search highlighting behind legible text.
- **`TkInputHandler`**: Translates mouse selection (single, double word, triple line), hyperlink clicks, mouse wheel scrolling, and keyboard events into session actions.

### 5. Headless Frontend & Session Persistence (`clownfish.frontends.headless`, `clownfish.session.persistence`)
- **`HeadlessTerminal`**: Pure Python terminal interface without GUI or display server requirements. Provides full VT100 emulation, programmatic input dispatch (`send_input()`, `send_key()`), screen scraping (`get_text()`, `get_line()`), and polling/waiters (`wait_for_text()`, `wait_for_prompt()`) for automation, AI agents, and CI.
- **`SessionState`**: Hierarchical dataclass structure (`SessionState` -> `TabState` -> `SplitNodeState` -> `PaneState`) serializing nested split trees, working directories, and remote SSH connection parameters into `~/.config/clownfish/session_state.json`. Automatic save on window close and restoration on startup.

---

## Security & Protocol Conformance

- **OSC 52 Clipboard Isolation**: Reading the host clipboard via OSC 52 query is disabled by default (`allow_clipboard_read = False`) to protect sensitive user credentials from unauthorized remote reads (e.g. over SSH). Writing to clipboard remains permitted by default and configurable (`allow_clipboard_write`).
- **OSC 7 Working Directory Validation**: OSC 7 URI hostnames are strictly validated against local hostnames (`localhost`, `127.0.0.1`, local nodename), and directory paths must exist locally before being accepted. Invalid or remote directories automatically fall back to the user's home directory.
- **Kitty Graphics Protocol Security**: APC sequence strings are bounded at 10 MB (`MAX_GRAPHIC_STRING_LENGTH`). Direct inline Base64 streaming (`t=d` or default) is the only permitted transmission medium. File-backed transmissions (`t=f`, `t=t`) and shared memory (`t=s`) are strictly rejected with `EBADF` to protect host filesystem integrity from unauthorized remote reads or deletions. Total graphics storage is budgeted to 32 MB with automatic oldest-unreferenced image eviction.
- **Defensive Parser Bounds**: CSI parameters are bounded to 32 digits, 64 parameter groups, and 16 subparameters. OSC and DCS strings are bounded to 8,192 bytes to defend against memory exhaustion and integer conversion denial-of-service.
- **PTY Backpressure & Packaging Trampoline**: Both incoming event queues (4,096 items) and outgoing write queues (1,000 chunks) have bounded limits. The PTY launcher includes a `--pty-trampoline` entrypoint compatible with PyInstaller-frozen `.app` bundles where `sys.executable` is not a Python interpreter.
- **Job Control & Safe Teardown**: Active foreground jobs are detected via `os.tcgetpgrp(master_fd)` to prompt for user confirmation before terminating running processes during tab or window close. Safe multiline paste protects against accidental execution of newline-separated shell commands.

---

## Packaging & Distribution Architecture

Clownfish v0.5.0 introduces automated multi-channel distribution:

### 1. Standalone macOS Application Bundle (`Clownfish.app`)
- **PyInstaller Specification (`Clownfish.spec`)**: Compiles Python source files, bytecode, Tk/Tcl libraries, dynamic dylibs, and bundled resources (`clownfish.png`) into a standalone macOS `--windowed` bundle with bundle ID `tech.wispsy.clownfish`.
- **Icon Assets (`assets/Clownfish.icns`)**: Generated from the high-resolution vector/raster asset into multi-resolution icons (16x16 through 1024x1024 @2x retina).
- **PTY Trampoline Launcher**: Frozen executables on macOS cannot invoke arbitrary Python code via `sys.executable -c`. Clownfish bypasses this via `clownfish --pty-trampoline <command>`, configuring controlling terminals and invoking target shells directly.
- **Info.plist Customization & Ad-Hoc Signing**: Automatically sets `CFBundleDisplayName`, `CFBundleShortVersionString`, `NSHighResolutionCapable`, and `NSRequiresAquaSystemAppearance`, followed by strict deep ad-hoc code signing (`codesign --force --deep -s -`) to satisfy macOS security requirements.

### 2. PyPI Trusted Publishing
- Uses GitHub Actions OpenID Connect (OIDC) token exchange with PyPI (`environment: pypi`, `id-token: write`).
- Pure standard-library runtime design ensures zero external dependencies and frictionless wheel installations across all platforms (`pip install clownfish`, `uv tool install clownfish`).

### 3. Homebrew Tap Distribution (`wispsy/homebrew-tap`)
- **Formula (`Formula/clownfish.rb`)**: Distributes the pure CLI application using `Language::Python::Virtualenv` in an isolated virtual environment.
- **Cask (`Casks/clownfish.rb`)**: Distributes the prebuilt standalone macOS `.app` bundle directly from GitHub releases to `/Applications/Clownfish.app` with a symlinked `/usr/local/bin/clownfish` or `HOMEBREW_PREFIX/bin/clownfish` binary.
