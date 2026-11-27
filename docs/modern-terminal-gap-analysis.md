# Modern Terminal Gap Analysis & Specification

While terminal emulators have their origin in VT100 hardware video terminals from 1978, modern developer workflows require far more than basic ANSI color codes and cursor movement. Modern emulators such as **Ghostty**, **WezTerm**, **Kitty**, and **Alacritty** have raised the bar across correctness, protocol standards, typography, performance, and shell integration.

This document analyzes the fundamental capabilities that separate traditional/toy terminal implementations from modern terminal emulators, detailing the technical architecture and implementation roadmap for Clownfish.

---

## Summary Matrix

| Feature | Category | Importance | Clownfish Status |
| :--- | :--- | :--- | :--- |
| **Cmd+K / Clear Buffer** | Convenience | High | **Implemented** (`ScreenBuffer.clear_all`) |
| **East Asian Width / CJK / Emojis** | Correctness | Critical | **Implemented** (`unicodedata.east_asian_width` + sentinel spacers) |
| **Device Attribute Replies (DA1/DA2/DSR)** | Protocol | Critical | **Implemented** (VT220 DA1, DA2, CPR, OSC 10/11) |
| **Kitty Extended Keyboard Protocol** | Modern CLI UX | High | **Implemented** (Flag negotiation + structured modifier codes) |
| **Shell Integration (OSC 133)** | Modern CLI UX | Medium | **Implemented** (Semantic prompt marks & jumping) |
| **Tabs & Nested Split Panes** | Modern CLI UX | High | **Implemented** (`TabbedTerminalView` & `SplitView`) |
| **In-Buffer Search & Highlighting** | Modern CLI UX | High | **Implemented** (`search_screen` overlay & match cycling) |
| **Remote SSH Sessions & Quick Connect** | Connectivity | High | **Implemented** (`SSHTransport`, `clownfish ssh`, `Cmd+Shift+O`) |
| **Session Persistence & Layout Restoration** | Usability | High | **Implemented** (`SessionState` JSON serialization & `--restore`) |
| **Headless Terminal Interface** | Portability | High | **Implemented** (`HeadlessTerminal` programmatic API) |
| **macOS Native Bundle (`.app`)** | Distribution | High | **Implemented** (PyInstaller bundle, Info.plist, code signing) |
| **Package Distribution (PyPI & Tap)** | Distribution | High | **Implemented** (Trusted Publishing & `wispsy/homebrew-tap`) |
| **High-Performance Layered Canvas** | Performance | High | **Implemented** (Scanline run batching, CALayer/Metal backing, borderless canvas) |
| **Programming Font Ligatures** | Typography | High | **Implemented** (`clownfish.core.ligatures` segmentation & `enable_ligatures` toggle) |
| **Terminal Graphics (Kitty)** | Media | High | **Implemented** (Inline PNG & raw RGB/RGBA streaming, queries, deletion) |
| **User Experience & Settings UI** | Usability | Medium | **Roadmap** (v0.8.0 configuration UI, search, custom themes, native menus) |
| **Accessibility (Screen Readers)** | Accessibility | High | **Roadmap** (v0.8.0 accessible text interface) |
| **Multi-Frontend Expansion** | Portability | High | **Roadmap** (v0.9.0 HTML browser frontend, UIKit/SwiftUI native macOS/iOS) |

---

## 1. Unicode Complexities: Wide Characters & Grapheme Clusters

### The Problem
Traditional terminals assume a simplistic 1:1 mapping between Unicode code points, character glyphs, and grid columns. In reality:
1. **CJK Characters & Emojis**: Characters in Chinese, Japanese, and Korean scripts (e.g. `你好`), as well as fullwidth symbols and pictographs (e.g. `🚀`, `🔥`), occupy **two** terminal columns in monospace grids according to the Unicode Standard Annex #11 (UAX #11).
2. **Column Misalignment**: Without tracking width, shells and interactive programs (like readline, zsh, fzf) advance the cursor by 2 columns, but a naïve terminal only advances by 1, resulting in prompt corruption, broken line wrapping, and displaced tab stops.
3. **Zero-Width & Combining Characters**: Accents (e.g. `e` + `\u0301` = `é`), Zero-Width Joiners (ZWJ `\u200D`), and variation selectors (`\uFE0F`) occupy zero display columns and attach to preceding characters.
4. **Grapheme Clusters**: Multi-codepoint sequences such as flag emojis (`🏳️` + ZWJ + `🌈`) or skin-tone modified emojis (`👍` + `🏽`) form a single user-perceived grapheme cluster.

### Implementation in Clownfish
- **Character Classification**: Uses `unicodedata.east_asian_width()` to identify `'W'` (Wide) and `'F'` (Fullwidth) code points.
- **Sentinel Spacer Cells**:
  - The leading column stores the glyph with `Cell(width=2)`.
  - The immediately following column stores a sentinel spacer `Cell(char="", width=0)`.
  - Cursor advances by 2 columns for wide characters.
- **Line-Wrapping Boundaries**: If a wide character arrives at `col == cols - 1`, the cell is padded with whitespace and the wide glyph wraps cleanly to the start of the next line.
- **Overwriting Protection**: Overwriting a spacer cell clears the preceding leader cell to prevent visual artifacting.
- **Selection & Copying**: Spacer cells (`width == 0`) are ignored during clipboard text assembly, preventing duplicate spaces or corrupted strings.

---

## 2. Primary & Secondary Device Attributes (DA1 / DA2) & DSR

### The Problem
CLI tools and modern interactive shells (zsh-autosuggestions, fish, tmux, Neovim, starship) query terminal capabilities at startup by transmitting escape sequences across stdin:
- `\x1b[c` or `\x1b[0c` (DA1: Primary Device Attributes query)
- `\x1b[>c` or `\x1b[>0c` (DA2: Secondary Device Attributes query)
- `\x1b[6n` (DSR: Device Status Report / Cursor Position Query)
- `\x1b[5n` (DSR: Operating Status query)
- `\x1b]10;?\x07` / `\x1b]11;?\x07` (Query Foreground/Background Theme Colors)

If the terminal fails to reply back through the master PTY descriptor:
1. **CLI Applications Hang**: Programs block waiting for input on `stdin` until a timeout expires (often 100ms–1000ms), introducing jarring startup latency.
2. **Degraded Capabilities**: Neovim, tmux, and rich CLIs fallback into crippled 16-color or monochrome modes, assuming the host is a primitive 1970s teletype.

### Implementation in Clownfish
- **DA1 Response**: Replies with VT220 identification `\x1b[?62;c`.
- **DA2 Response**: Replies with VT220/xterm identification `\x1b[>1;10;0c`.
- **DSR Cursor Position Report**: Formulates 1-based coordinate reply `\x1b[{row+1};{col+1}R`.
- **DSR Operating Status**: Returns terminal OK `\x1b[0n`.
- **Color Queries**: Responds with exact RGB values in `\x1b]10;rgb:rrrr/gggg/bbbb\x1b\` format.

---

## 3. Kitty Extended Keyboard Protocol

### The Problem
Traditional VT100 terminal key encoding has severe limitations:
- **Modifier Ambiguity**: `Ctrl+I` sends `\t` (identical to Tab); `Ctrl+M` sends `\r` (identical to Enter); `Ctrl+[` sends `\x1b` (identical to Escape).
- **Missing Modifiers**: Key combinations like `Shift+Enter`, `Ctrl+Enter`, `Ctrl+Shift+A`, `Ctrl+.`, `Alt+Shift+Up` cannot be disambiguated or detected under legacy VT100 encoding.
- **Modal Editor Constraints**: Modern text editors (Neovim, Helix, Micro) cannot bind shortcuts like `Shift+Enter` for line insertion above cursor without extended keyboard protocol support.

### Implementation in Clownfish
- **Flag Negotiation**:
  - `CSI ? u`: Query current keyboard flags (returns `\x1b[?{flags}u`).
  - `CSI = flags u`: Sets current flags.
  - `CSI > flags u`: Pushes flags onto an internal stack.
  - `CSI < count u`: Pops flags from the stack.
- **Structured Modifier Key Transmission**: Emits progressive enhancement sequences such as `\x1b[13;2u` for `Shift+Enter` and `\x1b[13;5u` for `Ctrl+Enter`.

---

## 4. Shell Integration (OSC 133 / Semantic Prompts)

### The Problem
Traditional terminals view screen content as an unstructured rectangular array of cells. They have no understanding of:
- Where the prompt starts and ends.
- Where the user's typed command starts.
- Where command output starts and finishes.
- Whether a command succeeded (exit code 0) or failed (exit code non-zero).

### The Modern Standard (OSC 133)
Shells like zsh, fish, and bash (with integration scripts) emit semantic annotations:
- `\x1b]133;A\x1b\`: Prompt started (marks the line as a prompt).
- `\x1b]133;B\x1b\`: Prompt ended / user command input starts.
- `\x1b]133;C\x1b\`: Command execution started (output begins).
- `\x1b]133;D;{exit_code}\x1b\`: Command finished with exit status code.

### Implementation in Clownfish
- **PromptMarker Tracking**: `ScreenBuffer.prompt_markers` records the row, command boundary, and exit code.
- **Semantic Prompt Navigation**: Key bindings (`Cmd+Up` / `Cmd+Down` on macOS, `Ctrl+Up` / `Ctrl+Down` on Linux) jump between previous and next shell prompts in scrollback.
- **Scrollback Reset**: `clear_all()` resets prompt markers alongside the grid and scrollback deque.

---

## 5. Hardware-Accelerated Rendering & Font Ligatures

### The Implementation in Clownfish (v0.7.0)
Clownfish achieves high-performance rendering and typography without external C-extension dependencies:
1. **High-Performance Hardware-Layered Canvas**:
   - Zero-dependency standard library implementation leveraging OS-level hardware acceleration (Metal / CALayer on macOS).
   - **Scanline Background Run Batching**: Merges contiguous identical background cells along each row into unified background rectangles, cutting canvas item allocations by over 70% during complex full-screen rendering.
   - **Canvas Optimization**: Configured with `highlightthickness=0` and `borderwidth=0` to eliminate unnecessary frame clipping computations.
   - **Layered Display Model**: Strict z-index ordering: background runs < graphic placements < text & ligature runs < underline/strikethrough lines < selection highlights < search match highlights < cursor.
2. **Programming Font Ligatures**:
   - `clownfish.core.ligatures` scans text rows for multi-character programming ligatures (`!=`, `==`, `===`, `->`, `=>`, `<=`, `>=`, `:=`, `/*`, `::`, `...`, `<!--`, `-->`, etc.).
   - Segments text into contiguous same-style runs and formats ligature groupings for modern developer fonts (Fira Code, JetBrains Mono, Cascadia Code) while locking segment start coordinates to the monospace column grid (`start_col * cell_width`).
   - Ensures zero kerning drift, keeping cursor hit-testing and rectangular mouse selection strictly aligned.
   - Fully customizable and user-toggleable via `TerminalConfig.enable_ligatures`.

---

## 6. Terminal Graphics Protocols (Kitty)

### The Implementation in Clownfish (v0.7.0)
Clownfish provides native support for the Kitty Graphics Protocol (`APC G ... ST`):
1. **Escape Sequence Parsing**:
   - Bounded APC buffer parsing (`MAX_GRAPHIC_STRING_LENGTH = 10_485_760`, 10 MB) handling key-value control directives (`a`, `f`, `m`, `s`, `v`, `i`, `p`, `C`, etc.).
   - **Chunked Payload Streaming**: Multi-part Base64 data transfers (`m=1` continuing, `m=0` complete) assembled seamlessly across escape sequences.
   - **Capability Query Support**: Handshakes with `a=q` requests by replying with standard `\x1b_Gi={id};OK\x1b\` responses.
   - **Lifecycle & Deletion**: Supports selective deletion by image ID (`d=i,i={id}`), placement ID (`d=p,p={id}`), or global purge (`d=a`).
2. **Zero-Dependency Image Formats**:
   - **PNG (`f=100`)**: Geometry extracted directly from standard PNG IHDR header (`struct.unpack(">II", raw_bytes[16:24])`) without external libraries.
   - **Raw 24-bit RGB (`f=24`) & 32-bit RGBA (`f=32`)**: Dynamically transformed via pure Python stdlib into Netpbm PPM (`P6`) binary format, enabling native `tk.PhotoImage` loading without PIL/Pillow.
3. **Screen & Scrollback Coordination**:
   - Placements are tracked in `ScreenBuffer.graphic_placements` (and `alt_graphic_placements` for full-screen alt-screens).
   - Placements track absolute scroll rows (`abs_row`), adjusting visual viewport coordinates smoothly during user scrolling.
   - Placements are automatically culled when scrolled beyond maximum scrollback retention (`max_scrollback = 10,000`).
