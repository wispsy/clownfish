# Clownfish Keyboard & Mouse Shortcuts

This guide covers all key combinations and pointer interactions supported in Clownfish.

---

## Tabs & Session Management

| Shortcut (macOS) | Shortcut (Linux / Windows) | Action |
| :--- | :--- | :--- |
| `Cmd + T` | `Ctrl + Shift + T` | **New Tab**: Open a new terminal tab and switch to it. |
| `Cmd + W` | `Ctrl + Shift + W` | **Close**: Close active pane (or tab if single pane). |
| `Ctrl + Tab` | `Ctrl + Tab` | **Next Tab**: Cycle forward to next tab. |
| `Ctrl + Shift + Tab` | `Ctrl + Shift + Tab` | **Previous Tab**: Cycle backward to previous tab. |
| `Cmd + 1` .. `Cmd + 9` | `Alt + 1` .. `Alt + 9` | **Switch Tab**: Jump directly to tab N. |

---

## Split Panes

| Shortcut (macOS) | Shortcut (Linux / Windows) | Action |
| :--- | :--- | :--- |
| `Cmd + D` | `Ctrl + Shift + D` | **Split Vertical**: Split current pane top-and-bottom. |
| `Cmd + Shift + D` | `Ctrl + Shift + Alt + D` | **Split Horizontal**: Split current pane side-by-side. |

---

## In-Buffer Search

| Shortcut (macOS) | Shortcut (Linux / Windows) | Action |
| :--- | :--- | :--- |
| `Cmd + F` | `Ctrl + Shift + F` | **Find**: Open / toggle in-buffer search overlay. |
| `Enter` | `Enter` | Jump to next search match. |
| `Shift + Enter` | `Shift + Enter` | Jump to previous search match. |
| `Escape` | `Escape` | Dismiss search bar and clear match highlights. |

---

## Screen Management & Reset

| Shortcut (macOS) | Shortcut (Linux / Windows) | Action |
| :--- | :--- | :--- |
| `Cmd + K` | `Ctrl + Shift + K` | **Full Screen & Scrollback Clear**: Wipes visible screen and all 10,000 lines of scrollback buffer. |

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
