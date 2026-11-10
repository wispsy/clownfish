# Clownfish Keyboard & Mouse Shortcuts

This guide covers all key combinations and pointer interactions supported in Clownfish.

---

## Screen Management & Reset

| Shortcut (macOS) | Shortcut (Linux / Windows) | Action |
| :--- | :--- | :--- |
| `Cmd + K` | `Ctrl + K` | **Full Screen & Scrollback Clear**: Wipes the visible screen, purges the entire 10,000-line scrollback history, resets scroll offset to 0, moves cursor home, and forces a shell prompt redraw (`\x1b[2J\x1b[H`). |

---

## Clipboard & Selection

| Shortcut (macOS) | Shortcut (Linux / Windows) | Action |
| :--- | :--- | :--- |
| `Cmd + C` | `Ctrl + Shift + C` | Copy current selection to system clipboard. |
| `Cmd + V` | `Ctrl + Shift + V` | Paste system clipboard contents into shell (supports bracketed paste mode). |
| Middle Mouse Button | Middle Mouse Button | Paste from clipboard. |
| `Escape` | `Escape` | Cancel active text selection. |

---

## Navigation & Scrolling

| Shortcut (macOS) | Shortcut (Linux / Windows) | Action |
| :--- | :--- | :--- |
| `Shift + PageUp` | `Shift + PageUp` | Scroll upward half a screen. |
| `Shift + PageDown` | `Shift + PageDown` | Scroll downward half a screen. |
| `Mouse Wheel Up` | `Mouse Wheel Up` | Scroll view upward (or send mouse button events in full-screen apps). |
| `Mouse Wheel Down` | `Mouse Wheel Down` | Scroll view downward (or send mouse button events in full-screen apps). |
| `Cmd + Up` | `Ctrl + Up` | Jump backward to previous semantic prompt marker (OSC 133). |
| `Cmd + Down` | `Ctrl + Down` | Jump forward to next semantic prompt marker (OSC 133). |

---

## Mouse Selection Actions

- **Single Click + Drag**: Select arbitrary rectangular / linear character ranges.
- **Double Click**: Expand selection to current word bounded by whitespace and delimiters (`()[\]{}"':;,=`).
- **Triple Click**: Select the entire current line.
- **Cmd + Click** (macOS) / **Ctrl + Click** (Linux): Open clicked OSC 8 hyperlink in default web browser.
