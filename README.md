# AccessGram

An accessible Telegram client for Linux, designed to work with screen readers like Orca.

## Features

- Full keyboard navigation and screen reader support
- Private chats, groups, and channels
- Send and receive text messages
- Voice message recording and playback
- File uploads and downloads
- Search for users, groups, and channels
- Mute/unmute chats
- Message reply support with context display
- Read receipts (sent/seen status)

## Installation

### System Dependencies

**Gentoo:**
```bash
emerge -av gtk:4 pygobject gst-plugins-base gst-plugins-good gst-plugins-bad
```

**Debian/Ubuntu:**
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
```

**Fedora:**
```bash
sudo dnf install python3-gobject gtk4 gstreamer1-plugins-base \
    gstreamer1-plugins-good gstreamer1-plugins-bad-free
```

**Arch:**
```bash
sudo pacman -S python-gobject gtk4 gst-plugins-base gst-plugins-good gst-plugins-bad
```

### Install AccessGram

```bash
pip install -e .
```

## Setup

1. Get API credentials from https://my.telegram.org
2. Run `python -m accessgram`
3. Enter your API credentials on first run

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | Search |
| `Ctrl+F` | Filter chat list |
| `Ctrl+Q` | Quit |
| `Escape` | Go back |
| `Enter` | Send message / activate |
| `Tab` | Navigate between areas |
| `Arrow Keys` | Navigate within lists |

## License

MIT
