#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
World.execute(me);  —  a terminal music video (song by Mili)

A self-contained ANSI/truecolor renderer that plays song.mp3 through pygame
and draws a beat-synced, lyric-synced "MV" directly into your terminal.

  python world_execute_me.py            play with audio (song.mp3 required)
  python world_execute_me.py --no-audio visuals only
  python world_execute_me.py --help     all options

Fan-made visualizer. The song is "World.execute(me);" by Mili — support the
artist: https://music.163.com/#/song?id=435278010
"""
import argparse
import bisect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = Path(__file__).resolve().parent
SONG = ROOT / "song.mp3"
LRC = ROOT / "lyrics.lrc"
TIMELINE = ROOT / "assets" / "timeline.json"

TAU = math.tau
PI = math.pi

# ---------------------------------------------------------------- utilities

# Some console fonts (e.g. CJK bitmap fonts on Chinese Windows) render block
# and box-drawing glyphs double-width, which smears the whole frame.  We probe
# the terminal once at startup and, if needed, fall back to an all-ASCII
# palette through this map (checked in Buf.put / finish / render).
NARROW_MAP = {
    "\u2588": "#", "\u2593": "#", "\u2592": "+", "\u2591": ".",
    "\u00b7": ".", "\u2500": "-", "\u2501": "-", "\u2502": "|",
    "\u250c": "+", "\u2510": "+", "\u2514": "+", "\u2518": "+",
    "\u251c": "+", "\u2524": "+", "\u252c": "+", "\u2534": "+", "\u253c": "+",
    "\u2550": "=", "\u2551": "|", "\u2554": "+", "\u2557": "+",
    "\u255a": "+", "\u255d": "+",
}
ASCII_ONLY = False


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, k):
    return a + (b - a) * k


def rnd(seed):
    """Deterministic pseudo-random in [0,1); accepts int or float seed."""
    h = int(seed) & 0xFFFFFFFF
    h = (h * 0x9E3779B1) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    return (h & 0xFFFFFF) / 0x1000000


def mixc(a, b, k):
    """Mix two RGB tuples."""
    return (
        int(clamp(a[0] + (b[0] - a[0]) * k, 0, 255)),
        int(clamp(a[1] + (b[1] - a[1]) * k, 0, 255)),
        int(clamp(a[2] + (b[2] - a[2]) * k, 0, 255)),
    )


def scalec(c, g):
    if c is None or g >= 0.999:
        return c
    return (int(c[0] * g), int(c[1] * g), int(c[2] * g))


def fmt_time(t):
    t = max(0, int(t))
    return f"{t // 60:02d}:{t % 60:02d}"


# ------------------------------------------------------------------- fonts
# FONT5: 5x7  (titles / karaoke band)   FONT3: 3x5 (long lines / labels)

_F5_RAW = {
    "A": "01110 10001 10001 11111 10001 10001 10001",
    "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110",
    "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111",
    "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01111",
    "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "11111 00100 00100 00100 00100 00100 11111",
    "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001",
    "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001",
    "N": "10001 11001 10101 10011 10001 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110",
    "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101",
    "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110",
    "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110",
    "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 11011 10001",
    "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100",
    "Z": "11111 00001 00010 00100 01000 10000 11111",
    "0": "01110 10001 10011 10101 11001 10001 01110",
    "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00110 01000 10000 11111",
    "3": "11111 00010 00100 00010 00001 10001 01110",
    "4": "00010 00110 01010 10010 11111 00010 00010",
    "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110",
    "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110",
    "9": "01110 10001 10001 01111 00001 00010 01100",
    ".": "00000 00000 00000 00000 00000 01100 01100",
    ",": "00000 00000 00000 00000 00110 00110 01100",
    ":": "00000 01100 01100 00000 01100 01100 00000",
    ";": "00000 01100 01100 00000 00110 00110 01100",
    "!": "00100 00100 00100 00100 00100 00000 00100",
    "?": "01110 10001 00001 00110 00100 00000 00100",
    "'": "00100 00100 01000 00000 00000 00000 00000",
    '"': "01010 01010 00000 00000 00000 00000 00000",
    "-": "00000 00000 00000 01110 00000 00000 00000",
    "+": "00000 00100 00100 11111 00100 00100 00000",
    "=": "00000 00000 11111 00000 11111 00000 00000",
    "/": "00001 00010 00010 00100 01000 01000 10000",
    "(": "00010 00100 01000 01000 01000 00100 00010",
    ")": "01000 00100 00010 00010 00010 00100 01000",
    "<": "00010 00100 01000 10000 01000 00100 00010",
    ">": "01000 00100 00010 00001 00010 00100 01000",
    "*": "00000 10101 01110 11111 01110 10101 00000",
    "%": "11001 11010 00010 00100 01000 01011 10011",
    "#": "01010 11111 01010 01010 01010 11111 01010",
    "&": "01100 10010 10100 01000 10101 10010 01101",
    "_": "00000 00000 00000 00000 00000 00000 11111",
    "~": "00000 00000 01001 10110 00000 00000 00000",
}

_F3_RAW = {
    "A": "010 101 111 101 101", "B": "110 101 110 101 110",
    "C": "011 100 100 100 011", "D": "110 101 101 101 110",
    "E": "111 100 110 100 111", "F": "111 100 110 100 100",
    "G": "111 100 101 101 111", "H": "101 101 111 101 101",
    "I": "111 010 010 010 111", "J": "011 001 001 101 010",
    "K": "101 110 100 110 101", "L": "100 100 100 100 111",
    "M": "101 111 111 101 101", "N": "110 101 101 101 101",
    "O": "010 101 101 101 010", "P": "110 101 110 100 100",
    "Q": "111 101 101 111 001", "R": "110 101 110 101 101",
    "S": "011 100 010 001 110", "T": "111 010 010 010 010",
    "U": "101 101 101 101 111", "V": "101 101 101 101 010",
    "W": "101 101 111 111 101", "X": "101 101 010 101 101",
    "Y": "101 101 010 010 010", "Z": "111 001 010 100 111",
    "0": "111 101 101 101 111", "1": "010 110 010 010 111",
    "2": "110 001 010 100 111", "3": "110 001 010 001 110",
    "4": "101 101 111 001 001", "5": "111 100 110 001 110",
    "6": "011 100 111 101 111", "7": "111 001 001 010 010",
    "8": "111 101 111 101 111", "9": "111 101 111 001 110",
    ".": "000 000 000 000 010", ",": "000 000 000 010 100",
    ":": "000 010 000 010 000", ";": "000 010 000 010 100",
    "!": "010 010 010 000 010", "?": "110 001 010 000 010",
    "'": "010 100 000 000 000", '"': "101 101 000 000 000",
    "-": "000 000 111 000 000", "+": "000 010 111 010 000",
    "=": "000 111 000 111 000", "/": "001 001 010 100 100",
    "(": "010 100 100 100 010", ")": "010 001 001 001 010",
    "*": "000 101 010 101 000", "%": "101 001 010 100 101",
    "#": "101 111 101 111 101", "_": "000 000 000 000 111",
    "~": "000 010 101 000 000", "<": "001 010 100 010 001",
    ">": "100 010 001 010 100",
}


def _build_font(raw):
    out = {}
    for ch, spec in raw.items():
        rows = [int(w, 2) for w in spec.split()]
        out[ch] = (len(rows), 5 if len(rows) == 7 else 3, rows)
    return out


FONT5 = _build_font(_F5_RAW)
FONT3 = _build_font(_F3_RAW)


def font_width(text, font=FONT5, sc=1):
    _, gw, _ = next(iter(font.values()))
    step = (gw + 1) * sc
    return max(0, len(text) * step - sc)


def draw_font(buf, x, y, text, fg, font=FONT5, sc=1, slant=0, gain=1.0):
    _, gw, _ = next(iter(font.values()))
    rows_n = next(iter(f[0] for f in font.values()))
    step = (gw + 1) * sc
    col = scalec(fg, gain)
    if col is None:
        return
    for i, ch in enumerate(text):
        g = font.get(ch.upper())
        if g is None:
            continue
        _, _, rows = g
        for ry, row in enumerate(rows):
            ox = (rows_n - 1 - ry) // 2 * slant
            for rx in range(gw):
                if (row >> (gw - 1 - rx)) & 1:
                    px = x + i * step + rx * sc + ox
                    for a in range(sc):
                        for b in range(sc):
                            buf.put(px + a, y + ry * sc + b, "\u2588", col)


def wrap_font(text, max_cols, font=FONT3, sc=1):
    """Wrap a string so every line fits max_cols when drawn with font."""
    _, gw, _ = next(iter(font.values()))
    step = (gw + 1) * sc
    per_line = max(1, (max_cols + sc) // step)
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= per_line or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------------ buffer


class Buf:
    """A W x H character grid with truecolor fg/bg, ready for ANSI output."""

    def __init__(self, w, h):
        self.W, self.H = w, h
        n = w * h
        self.ch = [" "] * n
        self.fg = [None] * n
        self.bg = [None] * n

    def clear(self, bg=None):
        n = self.W * self.H
        self.ch[:] = [" "] * n
        self.fg[:] = [None] * n
        self.bg[:] = [bg] * n

    # -- primitives ---------------------------------------------------------
    def put(self, x, y, ch, fg=None, bg=None):
        x, y = int(x), int(y)
        if 0 <= x < self.W and 0 <= y < self.H:
            i = y * self.W + x
            self.ch[i] = NARROW_MAP.get(ch, ch) if ASCII_ONLY else ch
            if fg is not None:
                self.fg[i] = fg
            if bg is not None:
                self.bg[i] = bg

    def text(self, x, y, s, fg=None, bg=None):
        for i, c in enumerate(s):
            if c != " " or bg is not None:
                self.put(x + i, y, c, fg, bg)

    def textc(self, y, s, fg=None, bg=None):
        self.text((self.W - len(s)) // 2, y, s, fg, bg)

    def fill_bg(self, x0, y0, x1, y1, bg):
        for y in range(max(0, y0), min(self.H, y1 + 1)):
            for x in range(max(0, x0), min(self.W, x1 + 1)):
                i = y * self.W + x
                self.bg[i] = bg

    def clear_rect(self, x0, y0, x1, y1):
        for y in range(max(0, y0), min(self.H, y1 + 1)):
            for x in range(max(0, x0), min(self.W, x1 + 1)):
                i = y * self.W + x
                self.ch[i] = " "
                self.fg[i] = None
                self.bg[i] = None

    def hline(self, x0, x1, y, ch, fg=None, bg=None):
        if x1 < x0:
            x0, x1 = x1, x0
        for x in range(int(x0), int(x1) + 1):
            self.put(x, y, ch, fg, bg)

    def vline(self, x, y0, y1, ch, fg=None, bg=None):
        if y1 < y0:
            y0, y1 = y1, y0
        for y in range(int(y0), int(y1) + 1):
            self.put(x, y, ch, fg, bg)

    def line(self, x0, y0, x1, y1, ch, fg=None, bg=None):
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            self.put(x0, y0, ch, fg, bg)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def poly(self, pts, ch, fg=None, close=False):
        n = len(pts)
        for i in range(n - 1):
            self.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], ch, fg)
        if close and n > 2:
            self.line(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1], ch, fg)

    def ring(self, cx, cy, r, ch, fg=None, bg=None, a0=0.0, a1=TAU, squish=1.0):
        steps = max(12, int(2 * PI * r * 1.5))
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            self.put(cx + r * math.cos(a), cy + r * math.sin(a) * squish, ch, fg, bg)

    def disc(self, cx, cy, r, ch, fg=None, bg=None, squish=1.0):
        rr = int(r * squish)
        for dy in range(-rr, rr + 1):
            half = r * math.sqrt(max(0.0, 1 - (dy / (r * squish)) ** 2))
            self.hline(cx - half, cx + half, cy + dy, ch, fg, bg)

    def rect_border(self, x, y, w, h, fg, chs="\u250c\u2500\u2510\u2502\u2514\u2518"):
        if w < 2 or h < 2:
            return
        tl, hm, tr, vm, bl, br = chs
        self.put(x, y, tl, fg)
        self.put(x + w - 1, y, tr, fg)
        self.put(x, y + h - 1, bl, fg)
        self.put(x + w - 1, y + h - 1, br, fg)
        self.hline(x + 1, x + w - 2, y, hm, fg)
        self.hline(x + 1, x + w - 2, y + h - 1, hm, fg)
        self.vline(x, y + 1, y + h - 2, vm, fg)
        self.vline(x + w - 1, y + 1, y + h - 2, vm, fg)

    def sine(self, x0, x1, cy, amp, wavelength, phase, fg, ch="~", gain=1.0):
        col = scalec(fg, gain)
        for x in range(max(0, int(x0)), min(self.W, int(x1) + 1)):
            y = cy + amp * math.sin((x / wavelength + phase) * TAU)
            self.put(x, y, ch, col)

    # -- post fx ------------------------------------------------------------
    def shift(self, dx=0, dy=0):
        if dx == 0 and dy == 0:
            return
        W, H = self.W, self.H
        ch, fg, bg = [" "] * (W * H), [None] * (W * H), [None] * (W * H)
        for y in range(H):
            sy = y - dy
            if 0 <= sy < H:
                ro, so = y * W, sy * W
                for x in range(W):
                    sx = x - dx
                    if 0 <= sx < W:
                        ch[ro + x] = self.ch[so + sx]
                        fg[ro + x] = self.fg[so + sx]
                        bg[ro + x] = self.bg[so + sx]
        self.ch, self.fg, self.bg = ch, fg, bg

    def wobble(self, amp, t, freq=6.0):
        W, H = self.W, self.H
        for y in range(H):
            self.shift(int(round(amp * math.sin(y * 0.55 + t * freq))), 0)

    def glitch(self, amount, seed, ca=(255, 60, 60), cb=(60, 220, 255)):
        if amount <= 0:
            return
        W, H = self.W, self.H
        for y in range(H):
            if rnd(seed * 131 + y * 17) < amount * 0.9:
                dx = int((rnd(seed * 7 + y) - 0.5) * 14 * amount)
                ro = y * W
                if dx:
                    row = [self.ch[ro + (x - dx if 0 <= x - dx < W else x)] for x in range(W)]
                    self.ch[ro:ro + W] = row
                x0 = int(rnd(seed * 31 + y) * (W - 10))
                ln = 3 + int(rnd(seed * 41 + y) * 14 * amount)
                col = ca if rnd(seed * 53 + y) < 0.5 else cb
                for x in range(x0, min(W, x0 + ln)):
                    self.fg[ro + x] = col

    def flash(self, col, a):
        if a <= 0:
            return
        tgt = mixc((0, 0, 0), col, a)
        n = self.W * self.H
        for i in range(n):
            self.bg[i] = tgt
            if self.fg[i] is not None:
                self.fg[i] = mixc(self.fg[i], col, a * 0.4)

    def finish(self, vig=0.35, grain=0.04, scan=0.10, seed=0, gain=1.0):
        """Apply vignette + scanlines + grain + master gain in one pass."""
        seed = int(seed)
        W, H = self.W, self.H
        cx, cy = (W - 1) / 2, (H - 1) / 2
        rmax = math.hypot(cx, cy)
        for y in range(H):
            dy = y - cy
            scanrow = scan > 0 and (y % 3 == 0)
            for x in range(W):
                i = y * W + x
                f, b = self.fg[i], self.bg[i]
                if f is None and b is None:
                    continue
                g = gain
                if vig > 0:
                    dx = x - cx
                    d2 = (dx * dx + dy * dy) / (rmax * rmax)
                    g *= 1.0 - vig * d2
                if scanrow:
                    g *= 1.0 - scan
                if g < 0.999:
                    if f is not None:
                        self.fg[i] = scalec(f, g)
                    if b is not None:
                        self.bg[i] = scalec(b, g)
        if grain > 0:
            n = int(W * H * grain)
            dot = "." if ASCII_ONLY else "\u00b7"
            for k in range(n):
                i = int(rnd(seed * 977 + k) * W * H) % (W * H)
                if self.ch[i] == " " and self.bg[i] is None:
                    self.ch[i] = dot
                    self.fg[i] = (70, 70, 80)

    # -- output -------------------------------------------------------------
    def render(self):
        out = ["\x1b[0m"]
        W = self.W
        for y in range(self.H):
            out.append(f"\x1b[{y + 1};1H")
            last_f = last_b = "reset"
            row_start = y * W
            for x in range(W):
                i = row_start + x
                c, f, b = self.ch[i], self.fg[i], self.bg[i]
                if c == " " and f is None and b is None:
                    continue
                kf = "d" if f is None else f
                kb = "d" if b is None else b
                if kf != last_f:
                    if f is None:
                        out.append("\x1b[39m")
                    else:
                        out.append(f"\x1b[38;2;{f[0]};{f[1]};{f[2]}m")
                    last_f = kf
                if kb != last_b:
                    if b is None:
                        out.append("\x1b[49m")
                    else:
                        out.append(f"\x1b[48;2;{b[0]};{b[1]};{b[2]}m")
                    last_b = kb
                out.append(c)
        out.append("\x1b[0m")
        return "".join(out)

    def html(self):
        import html as _h
        rows = []
        for y in range(self.H):
            parts, cur_col, run = [], None, []
            for x in range(self.W):
                i = y * self.W + x
                c, f = self.ch[i], self.fg[i]
                col = "#%02x%02x%02x" % (f or (190, 190, 190))
                if col != cur_col:
                    if run:
                        parts.append(f'<span style="color:{cur_col}">{_h.escape("".join(run))}</span>')
                    run, cur_col = [], col
                run.append(c)
            if run:
                parts.append(f'<span style="color:{cur_col}">{_h.escape("".join(run))}</span>')
            rows.append("".join(parts))
        return "\n".join(rows)


# ------------------------------------------------------------- data loading


def load_lrc(path):
    import re
    events = []
    for ln in path.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"\[(\d+):(\d+\.?\d*)\](.*)", ln)
        if m:
            events.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip()))
    events.sort(key=lambda e: e[0])
    return events


def load_timeline(path):
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    return d


# --------------------------------------------------------------------- ctx


class Ctx:
    def __init__(self, buf, t, lines, tl):
        self.buf = buf
        self.W, self.H = buf.W, buf.H
        self.t = t
        self.lines = lines
        self.tl = tl
        self.state = {}
        # lyric line
        idx = bisect.bisect_right([e[0] for e in lines], t) - 1
        self.li = idx
        self.lt = t - lines[idx][0] if idx >= 0 else 0.0
        self.line_text = lines[idx][1] if idx >= 0 else ""
        # beats
        self.bpi = 60.0 / (tl["bpm"] if tl else 108.0)
        beats = tl["beats"] if tl else []
        bi = bisect.bisect_right(beats, t) - 1
        self.bi = bi
        self.bt = t - beats[bi] if bi >= 0 else 0.0
        self.pulse = math.exp(-4.0 * self.bt / max(self.bpi, 0.2))
        # energy / onset envelopes
        self.energy = self._env(t, "energy", 0.2)
        self.onset = self._env(t, "onset", 0.0)
        self.frame = int(t * 30)
        self.band_top = self.H - 2
        self.cy_canvas = (self.band_top - 1) / 2

    def _env(self, t, key, default):
        tl = self.tl
        if not tl:
            return default
        arr = tl[key]
        hop = tl["hop_ms"] / 1000.0
        x = clamp(t / hop, 0, len(arr) - 1.001)
        i = int(x)
        return lerp(arr[i], arr[i + 1], x - i)

    def rstate(self):
        """Fresh per-line state slot (resets when the lyric line changes)."""
        return self.state.setdefault(f"line{self.li}", {})


# ------------------------------------------------------------- draw helpers


def draw_stars(buf, t, n, seed, dim=(90, 100, 130), hot=(230, 240, 255), drift=0.0, y0=0, y1=None):
    y1 = buf.H if y1 is None else y1
    for i in range(n):
        x = (rnd(seed + i) * (buf.W + 20) + t * drift * (0.3 + rnd(seed + i * 3))) % buf.W
        y = y0 + rnd(seed + i * 7) * (y1 - y0)
        tw = 0.5 + 0.5 * math.sin(t * (1.5 + rnd(seed + i * 11) * 2) + i)
        col = mixc(dim, hot, tw)
        ch = "*" if tw > 0.8 else "."
        buf.put(x, y, ch, col)


def draw_persp(buf, horizon, t, col, gain=1.0):
    W, H = buf.W, buf.H
    g = gain
    vp = W / 2
    for i in range(-9, 10):
        x_bot = vp + i * W * 0.14
        buf.line(vp + i * 3, horizon, x_bot, H - 1, "\u00b7", scalec(col, g * 0.55))
    n = 12
    u = (t * 0.55) % (1.0 / n)
    for k in range(-1, n + 1):
        f = (k + u) / n
        if f <= 0:
            continue
        y = horizon + (H - 1 - horizon) * (f ** 2.1)
        buf.hline(0, W - 1, y, "\u00b7", scalec(col, g * lerp(0.3, 0.9, f)))


def draw_globe(buf, cx, cy, r, rot, col, back=None, continents=None, tilt=0.38, gain=1.0, dim=0.55):
    if r < 1.5:
        return
    fg = scalec(col, gain)
    bk = scalec(back if back else mixc(col, (0, 0, 0), 0.65), gain)
    tilt_s, tilt_c = math.sin(tilt), math.cos(tilt)
    for lat in (-60, -30, 0, 30, 60):
        phi = math.radians(lat)
        rr, yy = r * math.cos(phi), r * math.sin(phi)
        steps = max(10, int(rr * 2.2))
        for i in range(steps):
            th = TAU * i / steps
            X, Z = rr * math.cos(th), rr * math.sin(th)
            sy = cy + yy * tilt_c - Z * tilt_s
            ch = "\u2500" if abs(yy) < r * 0.1 else "\u00b7"
            buf.put(cx + X, sy, ch, fg if Z > 0 else bk)
    for m in range(6):
        psi = m * PI / 6 + rot
        steps = max(8, int(r * 1.6))
        for i in range(steps + 1):
            phi = -PI / 2 + PI * i / steps
            X = r * math.cos(phi) * math.cos(psi)
            Y = r * math.sin(phi)
            Z = r * math.cos(phi) * math.sin(psi)
            sy = cy + Y * tilt_c - Z * tilt_s
            buf.put(cx + X, sy, "\u2502" if abs(X) < r * 0.18 else "\u00b7",
                    fg if Z > 0 else bk)
    if continents:
        for j, (ux, uy, uz) in enumerate(continents):
            X = ux * math.cos(rot) + uz * math.sin(rot)
            Z = -ux * math.sin(rot) + uz * math.cos(rot)
            Y = uy
            if Z > 0:
                sy = cy + (Y * tilt_c - Z * tilt_s) * r
                buf.put(cx + X * r, sy, "*", scalec(col, gain))


def make_continents(n=26, seed=7):
    pts = []
    for i in range(n):
        z = rnd(seed + i) * 2 - 1
        a = rnd(seed + i * 3) * TAU
        rr = math.sqrt(1 - z * z)
        pts.append((rr * math.cos(a), z, rr * math.sin(a)))
    return pts


def heart_points(s):
    pts = []
    for i in range(97):
        th = TAU * i / 96
        x = 16 * math.sin(th) ** 3
        y = 13 * math.cos(th) - 5 * math.cos(2 * th) - 2 * math.cos(3 * th) - math.cos(4 * th)
        pts.append((x * s / 17.0, -y * s / 17.0))
    return pts


def draw_heart(buf, cx, cy, s, col, fill=False, progress=1.0, gain=1.0, ch="\u2588"):
    pts = heart_points(s)
    n = max(2, int(len(pts) * clamp(progress, 0, 1)))
    fg = scalec(col, gain)
    for i in range(n):
        buf.put(cx + pts[i][0], cy + pts[i][1], ch, fg)
    if fill and progress >= 0.999:
        cols = {}
        for (x, y) in pts:
            xi = int(round(x))
            cols.setdefault(xi, [1e9, -1e9])
            cols[xi][0] = min(cols[xi][0], y)
            cols[xi][1] = max(cols[xi][1], y)
        inner = scalec(mixc(col, (0, 0, 0), 0.35), gain)
        for xi, (y0, y1) in cols.items():
            for y in range(int(y0) + 1, int(y1)):
                buf.put(cx + xi, cy + y, ch, inner)


def draw_person(buf, cx, feet_y, h, col, keep=1.0, seed=0, gain=1.0, ch="\u2588"):
    fg = scalec(col, gain)
    cells = []
    hr = max(1, h * 0.14)
    hy = feet_y - h * 0.86
    for dy in range(-int(hr) - 1, int(hr) + 2):
        half = math.sqrt(max(0.0, hr * hr - dy * dy))
        for dx in range(-int(half) - 1, int(half) + 2):
            if dx * dx + dy * dy <= hr * hr:
                cells.append((cx + dx, hy + dy))
    cells += [(cx, feet_y - h * 0.66), (cx, feet_y - h * 0.5), (cx, feet_y - h * 0.36)]
    cells += [(cx - 1, feet_y - h * 0.56), (cx + 1, feet_y - h * 0.56)]
    cells += [(cx - 2, feet_y - h * 0.46), (cx + 2, feet_y - h * 0.46)]
    cells += [(cx - 1, feet_y - h * 0.24), (cx + 1, feet_y - h * 0.24),
              (cx - 1, feet_y - h * 0.12), (cx + 1, feet_y - h * 0.12),
              (cx - 2, feet_y), (cx + 2, feet_y)]
    for i, (x, y) in enumerate(cells):
        if keep >= 1.0 or rnd(seed * 131 + i * 17) < keep:
            buf.put(x, y, ch, fg)


def draw_eggplant(buf, cx, cy, s, t, gain=1.0):
    body = scalec((122, 58, 168), gain)
    hi = scalec((168, 105, 214), gain)
    leaf = scalec((70, 180, 90), gain)
    ang = math.radians(24)
    ca, sa = math.cos(ang), math.sin(ang)
    for dy in range(-int(s), int(s) + 1):
        k = dy / s
        half = s * 0.42 * math.sqrt(max(0.0, 1 - k * k)) * (1 + 0.15 * k)
        for dx in range(-int(half) - 1, int(half) + 2):
            if dx * dx / (half * half + 0.01) <= 1.0:
                X = cx + dx * ca - dy * sa * 0.6
                Y = cy + dy + dx * sa * 0.4
                col = hi if dx < -half * 0.45 else body
                buf.put(X, Y, "\u2588", col)
    for i in (-2, 0, 2):
        buf.line(cx + i, cy - s * 0.92, cx + i * 1.8, cy - s * 1.25, "\u2588", leaf)
    buf.vline(cx, cy - s * 1.28, cy - s * 1.5, "\u2502", leaf)


def draw_tomato(buf, cx, cy, s, t, gain=1.0):
    red = scalec((226, 68, 60), gain)
    dk = scalec((160, 40, 40), gain)
    leaf = scalec((80, 175, 80), gain)
    buf.disc(cx, cy + s * 0.06, s * 0.72, "\u2588", red, squish=0.85)
    for dy in range(int(s * 0.2), int(s * 0.75)):
        half = s * 0.72 * math.sqrt(max(0.0, 1 - (dy / (s * 0.72 * 0.85)) ** 2)) * 0.55
        buf.hline(cx - half, cx + half, cy + s * 0.06 + dy, "\u2588", dk)
    for a in (-2.4, -1.2, 0, 1.2, 2.4):
        buf.line(cx, cy - s * 0.55, cx + math.sin(a) * s * 0.42,
                 cy - s * 0.55 - math.cos(a) * s * 0.3, "\u2588", leaf)
    buf.put(cx, cy - s * 0.72, "\u2502", leaf)


def draw_cat(buf, cx, cy, s, t, gain=1.0):
    fur = scalec((235, 190, 120), gain)
    stripe = scalec((160, 110, 60), gain)
    pink = scalec((255, 150, 170), gain)
    dark = scalec((40, 30, 25), gain)
    purr = 1 + 0.05 * math.sin(t * TAU * 2.2)
    r = s * 0.5 * purr
    buf.disc(cx, cy, r, "\u2588", fur)
    for ex in (-1, 1):
        buf.line(cx + ex * r * 0.55, cy - r * 0.55, cx + ex * r * 0.9, cy - r * 1.25, "\u2588", fur)
        buf.line(cx + ex * r * 0.75, cy - r * 0.85, cx + ex * r * 0.85, cy - r * 1.05, "\u2588", pink)
    blink = (t % 2.6) < 0.18
    for ex in (-1, 1):
        if blink:
            buf.hline(cx + ex * r * 0.35 - 1, cx + ex * r * 0.35 + 1, cy - r * 0.1, "\u2588", dark)
        else:
            buf.put(cx + ex * r * 0.35, cy - r * 0.1, "\u2588", dark)
    buf.put(cx, cy + r * 0.28, "v", dark)
    for i in (-1, 0, 1):
        buf.vline(cx + i * r * 0.4, cy - r * 0.95, cy - r * 0.55, "\u2588", stripe)
    for ex in (-1, 1):
        for dy in (-0.15, 0.15):
            buf.hline(cx + ex * r * 1.05, cx + ex * r * 1.7, cy + dy * r, "\u2500", fur)
    buf.disc(cx, cy + r * 1.5, r * 0.95, "\u2588", fur, squish=0.7)
    tail = math.sin(t * 2.0) * s * 0.3
    buf.line(cx - r * 0.9, cy + r * 1.5, cx - r * 1.9, cy + r * 1.1 + tail, "\u2588", fur)


def draw_god(buf, cx, cy, s, t, col, gain=1.0):
    fg = scalec(col, gain)
    top = (cx, cy - s)
    bl, br = (cx - s * 0.9, cy + s * 0.75), (cx + s * 0.9, cy + s * 0.75)
    buf.line(*top, *bl, "\u2588", fg)
    buf.line(*top, *br, "\u2588", fg)
    buf.hline(bl[0], br[0], bl[1], "\u2588", fg)
    buf.ring(cx, cy, s * 0.22, "\u2588", fg, squish=0.7)
    buf.disc(cx, cy, s * 0.07, "\u2588", fg)
    for i in range(10):
        a = TAU * i / 10 + t * 0.8
        r0, r1 = s * 1.05, s * (1.25 + 0.12 * math.sin(t * 3 + i))
        buf.line(cx + math.cos(a) * r0, cy + math.sin(a) * r0 * 0.7,
                 cx + math.cos(a) * r1, cy + math.sin(a) * r1 * 0.7, "\u00b7", fg)
    buf.ring(cx, cy - s * 1.35, s * 0.3, "\u2500", fg, squish=0.4)


def draw_toggle(buf, cx, cy, w, state, col_a, col_b, gain=1.0):
    """A two-way switch: active side bright, inactive side dimmed."""
    track = scalec(mixc(col_a, col_b, 0.45), gain)
    buf.hline(cx - w, cx + w, cy, "\u2500", track)
    buf.put(cx - w, cy, "[", track)
    buf.put(cx + w, cy, "]", track)
    knob = col_a if state == 0 else col_b
    kx = cx - w + 3 if state == 0 else cx + w - 3
    buf.put(kx - 1, cy, "\u2588", scalec(mixc(knob, (255, 255, 255), 0.4), gain))
    buf.put(kx, cy, "\u2588", scalec(knob, gain))
    act_a = mixc(col_a, (255, 255, 255), 0.35) if state == 0 else scalec(col_a, 0.3)
    act_b = mixc(col_b, (255, 255, 255), 0.35) if state == 1 else scalec(col_b, 0.3)
    draw_font(buf, cx - w - 4, cy - 6, "F", scalec(act_a, gain), FONT3)
    draw_font(buf, cx + w + 2, cy - 6, "M", scalec(act_b, gain), FONT3)


def draw_clock(buf, cx, cy, r, t, dayness, gain=1.0):
    fg = scalec((220, 220, 230), gain)
    buf.ring(cx, cy, r, "\u2500", fg)
    buf.ring(cx, cy, r * 0.4, "\u2500", scalec((120, 120, 130), gain))
    a_min = t * 1.2
    a_hr = t * 0.1
    buf.line(cx, cy, cx + math.cos(a_hr) * r * 0.55, cy + math.sin(a_hr) * r * 0.55, "\u2588", fg)
    buf.line(cx, cy, cx + math.cos(a_min) * r * 0.85, cy + math.sin(a_min) * r * 0.85, "\u2502", fg)
    if dayness > 0.5:
        sun = scalec((255, 210, 90), gain)
        sx, sy = cx + r * 1.6, cy
        buf.disc(sx, sy, r * 0.28, "\u2588", sun)
        for i in range(8):
            a = TAU * i / 8 + t
            buf.line(sx + math.cos(a) * r * 0.4, sy + math.sin(a) * r * 0.4,
                     sx + math.cos(a) * r * 0.55, sy + math.sin(a) * r * 0.55, "\u00b7", sun)
    else:
        moon = scalec((190, 200, 255), gain)
        mx, my = cx + r * 1.6, cy
        buf.disc(mx, my, r * 0.28, "\u2588", moon)
        buf.disc(mx - r * 0.12, my - r * 0.06, r * 0.22, " ", scalec((10, 8, 20), gain))


def draw_shield(buf, cx, cy, s, progress, col, gain=1.0):
    fg = scalec(col, gain)
    n = 6
    full = n * 2
    done = int(clamp(progress, 0, 1) * full)
    for i in range(done):
        seg = i // 2
        a0 = TAU * seg / n + (0 if i % 2 == 0 else TAU / n / 2)
        a1 = a0 + TAU / n / 2
        buf.ring(cx, cy, s, "\u2588", fg, a0=a0 - PI / 2, a1=a1 - PI / 2, squish=1.15)
    if progress >= 1:
        buf.put(cx, cy, "*", fg)


def draw_lemny(buf, cx, cy, s, progress, col, gain=1.0):
    fg = scalec(col, gain)
    n = int(120 * clamp(progress, 0, 1))
    for i in range(n):
        th = TAU * i / 120
        d = 1 + math.sin(th) ** 2
        x = s * math.cos(th) / d
        y = s * math.sin(th) * math.cos(th) / d * 1.6
        buf.put(cx + x, cy + y, "\u2588", fg)


def draw_spiral(buf, cx, cy, t, col, gain=1.0, arms=2):
    fg = scalec(col, gain)
    for arm in range(arms):
        for i in range(46):
            th = i * 0.16 + t * 2.2 + arm * PI
            r = 1.2 + i * 0.55
            buf.put(cx + math.cos(th) * r, cy + math.sin(th) * r * 0.55, "\u2588", fg)


def draw_window(buf, x, y, w, h, title, col, body=None, gain=1.0, shadow=True):
    fg = scalec(col, gain)
    dim = scalec(mixc(col, (0, 0, 0), 0.55), gain)
    if shadow:
        for k in range(1, 3):
            buf.hline(x + 2, x + w + 1, y + h + k - 1 + 0, "\u2591", scalec((60, 60, 70), gain))
        buf.vline(x + w + 1, y + 2, y + h, "\u2591", scalec((60, 60, 70), gain))
    buf.fill_bg(x + 1, y + 1, x + w - 2, y + h - 2, scalec((8, 8, 14), gain))
    buf.rect_border(x, y, w, h, fg, "\u250c\u2500\u2510\u2502\u2514\u2518")
    if title:
        buf.fill_bg(x + 2, y, x + 2 + len(title) + 1, y, fg)
        buf.text(x + 2, y, title, scalec((10, 10, 16), gain))
    if body:
        for i, ln in enumerate(body):
            if y + 2 + i < y + h - 1:
                buf.text(x + 2, y + 2 + i, ln[:w - 4], dim)


def draw_ecg(buf, x0, x1, y, t, amp, col, flat=0.0, gain=1.0):
    fg = scalec(col, gain)
    period = 26
    for x in range(int(x0), int(x1)):
        ph = ((x / period) - t * 0.9) % 1.0
        v = 0.0
        if ph < 0.06:
            v = -0.15
        elif ph < 0.12:
            v = 1.0
        elif ph < 0.17:
            v = -0.45
        elif ph < 0.24:
            v = 0.0
        elif ph < 0.42:
            v = 0.22
        elif ph < 0.62:
            v = -0.12 * math.sin((ph - 0.42) / 0.2 * PI)
        yy = y - v * amp * (1 - flat)
        buf.put(x, yy, "\u2588", fg if ph < 0.3 else scalec(fg, 0.55))


def draw_bird(buf, x, y, t, col, gain=1.0, s=1.0):
    fg = scalec(col, gain)
    flap = math.sin(t * 9)
    buf.line(x - 2 * s, y - flap * 1.6, x, y, "\u2588", fg)
    buf.line(x, y, x + 2 * s, y - flap * 1.6, "\u2588", fg)


def draw_rain(buf, rstate, W, H, t, dt, head, tail, charset, density=0.6, seed=3):
    if "cols" not in rstate:
        rstate["cols"] = []
        n = int(W * density)
        for i in range(n):
            rstate["cols"].append({
                "x": int(rnd(seed + i) * W),
                "y": rnd(seed + i * 3) * H,
                "spd": 5 + rnd(seed + i * 7) * 16,
                "ln": 4 + int(rnd(seed + i * 11) * 9),
            })
    for c in rstate["cols"]:
        c["y"] += c["spd"] * dt
        if c["y"] - c["ln"] > H:
            c["y"] = -rnd(t * 100 + c["x"]) * 4
        for k in range(c["ln"]):
            y = int(c["y"]) - k
            if 0 <= y < H:
                ch = charset[int(rnd(c["x"] * 131 + y * 17 + int(t * 8)) * len(charset)) % len(charset)]
                g = 1.0 if k == 0 else max(0.15, 1 - k / c["ln"])
                buf.put(c["x"], y, ch, scalec(head if k == 0 else tail, g))


def draw_hexdump(buf, x0, x1, y0, y1, t, col, seed=5):
    chs = "0123456789ABCDEF"
    for y in range(y0, y1 + 1):
        row = []
        for x in range(x0, min(x1, buf.W), 2):
            h = int(rnd(seed * 31 + y * 7 + x * 13 + int(t * 6) * 101) * 4096)
            row.append(chs[h % 16] + chs[(h >> 4) % 16])
        buf.text(x0, y, " ".join(row)[:x1 - x0], scalec(col, 0.5))


def spawn_particles(rstate, x, y, n, col, spread=22, up=30, g=90, life=1.2, ch="\u2588"):
    ps = rstate.setdefault("parts", [])
    for i in range(n):
        a = rnd(int(x * 7 + y * 13 + i * 31 + len(ps))) * TAU
        ps.append({
            "x": x, "y": y,
            "vx": math.cos(a) * spread * rnd(i * 7 + x) ,
            "vy": math.sin(a) * spread * rnd(i * 13 + y) - up,
            "life": life * (0.5 + rnd(i * 3) * 0.5),
            "age": 0.0, "col": col, "ch": ch, "g": g,
        })


def update_particles(buf, rstate, dt, gain=1.0):
    ps = rstate.get("parts", [])
    alive = []
    for p in ps:
        p["age"] += dt
        if p["age"] < p["life"]:
            p["vy"] += p["g"] * dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            alive.append(p)
            k = 1 - p["age"] / p["life"]
            buf.put(p["x"], p["y"], p["ch"], scalec(p["col"], k * gain))
    rstate["parts"] = alive


# ------------------------------------------------------------------ scenes
# Every scene: sc(buf, c) -> post-params dict.  Lyric band + HUD are drawn
# by the frame orchestrator afterwards.  Scenes key their per-line visuals
# off c.li (lyric line index) and c.lt (seconds into the line).


def sc_creation(buf, c):
    t, k = c.t, c.lt
    li = c.li
    W, H = buf.W, buf.H
    bg = (2, 8, 5)
    buf.clear(bg)
    green = (90, 255, 150)
    green_d = scalec(green, 0.45)
    cx, cy = W / 2, c.cy_canvas

    # persistent boot log (top-left)
    log = c.state.setdefault("log", [])
    texts = {0: "> power.line = ON", 1: "> protection.enable()  [OK]",
             2: "> laying pieces ...", 3: "> new World(me, you)",
             4: "> data.parameters fill", 5: "> initialization ...",
             6: "> world.setup()", 7: "> simulation.begin()"}
    if li in texts and (not log or log[-1][0] != li):
        log.append((li, texts[li]))
    for i, (_, s) in enumerate(log[:12]):
        buf.text(2, 2 + i, s, scalec(green_d, 0.8))

    # power line during the boot phase only (it would cross the globe later)
    if 0 <= li <= 2:
        py = int(H * 0.18)
        buf.hline(0, W - 1, py, "\u2500", green_d)
        sx = (t * 30) % W
        for j in range(4):
            buf.put(sx - j, py, "\u2588", scalec(green, 1 - j * 0.2))
        buf.put(3, py, "\u2588", green)
        buf.put(4, py, "\u2588", green)

    if li <= 1:
        if li == 1:
            draw_shield(buf, cx, cy, 6.5, min(1, k / 0.8), green)
            if k > 0.9:
                buf.textc(max(2, int(cy) - 8), "PROTECTION: ENABLED", green_d)
        else:
            buf.textc(int(cy), "POWER: ON", green)
            if k < 0.4:
                buf.flash((40, 120, 60), 0.5 * (1 - k / 0.4))
    elif li == 2:
        fy = int(H * 0.62)
        buf.hline(6, W - 7, fy, "\u2500", green_d)
        shapes = [((0, 0), (1, 0), (0, 1), (1, 1)), ((0, 0), (1, 0), (2, 0), (2, 1)),
                  ((0, 0), (0, 1), (1, 1), (2, 1))]
        starts = [2, -6, 3]
        tgtx = [int(W * 0.30), int(W * 0.48), int(W * 0.64)]
        for i, sh in enumerate(shapes):
            drop = clamp((k - i * 0.35) * 2.2, 0, 1)
            bx = lerp(starts[i], tgtx[i], min(1, drop * 3))
            by = lerp(4, fy - 2 - (2 if i == 0 else 0), drop)
            for (ox, oy) in sh:
                buf.put(bx + ox * 2, by - oy, "\u2588", green)
    elif li == 3:
        s = 7
        verts = [(1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1),
                 (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)]
        edges = [(0, 1), (0, 2), (1, 3), (2, 3), (4, 5), (4, 6), (5, 7), (6, 7),
                 (0, 4), (1, 5), (2, 6), (3, 7)]
        rot = t * 0.9
        proj = []
        for (vx, vy, vz) in verts:
            X = vx * math.cos(rot) - vz * math.sin(rot)
            Z = vx * math.sin(rot) + vz * math.cos(rot)
            proj.append((cx + X * s * 1.6, cy + vy * s * 0.8 - Z * s * 0.35))
        ne = min(len(edges), int(k / 0.12))
        for e in range(ne):
            a, b = edges[e]
            buf.line(*proj[a], *proj[b], "\u2588", green)
        buf.textc(int(cy + s * 1.4), "new World( me, you )", green_d)
        if k < 0.5:
            spawn_particles(c.state, cx, cy, 6, green, up=12, g=30, life=0.5)
            update_particles(buf, c.state, 0.016)
    elif li == 4:
        wx, wy = int(W * 0.24), int(cy - 5)
        fields = [("name", '"world"'), ("gravity", "9.8"), ("physics", "ON"),
                  ("you", "REQUIRED"), ("love", "NaN")]
        buf.rect_border(wx - 2, wy - 1, 30, len(fields) + 3, green_d)
        n = int(k * 26)
        cnt = 0
        for i, (key, val) in enumerate(fields):
            line = f"  {key:9}= "
            take = clamp(n - cnt, 0, len(val))
            line += val[:take]
            cnt += len(val)
            buf.text(wx, wy + i + 1, line, green if take < len(val) else green_d)
        if int(t * 2) % 2 == 0:
            i = min(len(fields) - 1, cnt // 5)
            buf.put(wx + 10 + take, wy + i + 1, "\u2588", green)
    elif li == 5:
        pct = clamp(k / 1.15, 0, 1)
        bw = 34
        bx = int(cx - bw / 2)
        by = int(cy)
        buf.rect_border(bx - 2, by - 2, bw + 4, 5, green_d)
        buf.hline(bx, bx + int(bw * pct) - 1, by, "\u2588", green)
        buf.textc(by + 2, f"INITIALIZING {int(pct * 100):3d}%", green)
        draw_hexdump(buf, 2, 20, by - 8, by + 6, t, green_d)
        draw_hexdump(buf, W - 20, W - 2, by - 8, by + 6, t, green_d)
    else:
        conts = c.state.setdefault("conts", make_continents(24))
        # fixed cap so the globe never shrinks when the next line wraps
        r = clamp(3 + (t - 10.9) * 2.2, 3, min(W * 0.14, 8.5))
        rot = t * 0.7 if li >= 7 else 0.4
        draw_globe(buf, cx, cy, r, rot, green, continents=conts)
        if li >= 7:
            horizon = int(min(cy + r * 0.8, c.band_top - 5))
            draw_persp(buf, horizon, t, green_d, gain=clamp((t - 12.4) * 0.8, 0, 1))
            if int(t * 2) % 2 == 0:
                buf.textc(max(2, int(cy - r) - 2), "SIMULATION RUNNING", scalec(green, 0.85))
            if c.pulse > 0.8:
                buf.ring(cx, cy, r + (1 - c.pulse) * 6, "\u00b7", scalec(green, c.pulse))
    return {"vig": 0.3, "grain": 0.05, "scan": 0.13}


def sc_title(buf, c):
    t = c.t
    W, H = buf.W, buf.H
    buf.clear((3, 4, 12))
    draw_stars(buf, t, 90, 11, dim=(70, 80, 120), drift=0.6)
    cy = (H - 4) / 2 + 3
    draw_persp(buf, int(cy + 6), t, (80, 110, 220))
    conts = c.state.setdefault("conts", make_continents(30))
    r = min(W * 0.13, (H - 4) * 0.36)
    draw_globe(buf, W / 2, cy - 2, r, t * 0.5, (110, 160, 255), continents=conts)
    if c.pulse > 0.75:
        buf.ring(W / 2, cy - 2, r + (1 - c.pulse) * 8, "\u00b7",
                 scalec((120, 170, 255), c.pulse))
    # title block
    title = "WORLD.EXECUTE(ME);"
    if font_width(title, FONT5) <= W - 4:
        rows = [title]
    else:
        rows = ["WORLD.", "EXECUTE(ME);"]
    ty = 3
    flick = 1.0 if (t % 0.4) > 0.05 else 0.75
    for i, ln in enumerate(rows):
        draw_font(buf, (W - font_width(ln, FONT5)) // 2, ty + i * 9, ln,
                  scalec((210, 230, 255), flick), FONT5)
    sub = "A TERMINAL MUSIC VIDEO  -  SONG BY MILI"
    buf.textc(ty + len(rows) * 9 - 1, sub, scalec((120, 140, 190), 0.9))
    return {"vig": 0.4, "grain": 0.04, "scan": 0.12}


def sc_math(buf, c):
    t, k, li = c.t, c.lt, c.li
    W, H = buf.W, buf.H
    buf.clear((3, 6, 16))
    cyan = (100, 220, 255)
    white = (225, 240, 255)
    pink = (255, 130, 190)
    cy = c.cy_canvas
    cx = W / 2
    fade = min(1.0, k / 0.35)
    g = c.pulse * 0.3 + 0.7

    if li in (9, 10):
        st = c.state
        if "pts" not in st:
            st["pts"] = [(6 + rnd(40 + i) * (W - 12), 3 + rnd(41 + i) * (H - 12))
                         for i in range(40)]
        pts = st["pts"]
        if li == 9:
            n = int(clamp(k / 0.1, 0, 40))
            for i in range(n):
                buf.put(*pts[i], "*", scalec(cyan, g))
        else:
            for p in pts:
                buf.put(*p, "\u00b7", scalec(cyan, 0.4))
            s = 6
            verts = [(1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1),
                     (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)]
            edges = [(0, 1), (0, 2), (1, 3), (2, 3), (4, 5), (4, 6), (5, 7), (6, 7),
                     (0, 4), (1, 5), (2, 6), (3, 7)]
            rot = t * 0.8
            proj = []
            for (vx, vy, vz) in verts:
                X = vx * math.cos(rot) - vz * math.sin(rot)
                Z = vx * math.sin(rot) + vz * math.cos(rot)
                proj.append((cx + X * s * 2.0, cy + vy * s * 0.9 - Z * s * 0.4))
            for a, b in edges:
                buf.line(*proj[a], *proj[b], "\u2500" if abs(proj[a][1] - proj[b][1]) < 1 else "\u2502",
                         scalec(white, g))
            buf.textc(2, "dimension: 3D  [granted]", scalec(cyan, 0.9))
    elif li in (11, 12):
        r = min(9, max(4, int(cy) - 3))
        if li == 11:
            prog = clamp(k / 1.1, 0, 1)
            buf.ring(cx, cy, r, "\u2588", scalec(cyan, g), a0=-PI / 2, a1=-PI / 2 + TAU * prog)
            buf.line(cx, cy, cx + math.cos(-PI / 2 + TAU * prog) * r,
                     cy + math.sin(-PI / 2 + TAU * prog) * r, "\u00b7", scalec(white, 0.7))
            buf.put(cx, cy, "+", white)
        else:
            buf.ring(cx, cy, r, "\u2588", scalec(cyan, g))
            a = t * 1.6
            for j in range(6):
                aa = a - j * 0.18
                buf.put(cx + math.cos(aa) * r, cy + math.sin(aa) * r,
                        "\u2588", scalec(white, g * (1 - j / 6)))
            buf.line(cx, cy, cx + r * 0.7, cy + r * 0.7 * 0.5, "\u2502", scalec(white, 0.8))
            buf.text(cx + r * 0.35, cy + r * 0.42, "r", white)
            buf.textc(int(cy - r - 3), f"C = 2 x PI x r = {2 * PI * r:.2f}", scalec(cyan, 0.9))
    elif li in (13, 14):
        amp = 5 + c.pulse * 2
        buf.sine(0, W - 1, cy, amp, 16, t * 0.9, scalec(cyan, g), ch="\u2588")
        if li == 14:
            for j in range(3):
                px = (t * 14 + j * (W / 3)) % (W - 8) + 4
                slope = math.cos((px / 16 + t * 0.9) * TAU) * TAU * amp / 16
                y0 = cy + amp * math.sin((px / 16 + t * 0.9) * TAU)
                L = 7
                buf.line(px - L, y0 - slope * L, px + L, y0 + slope * L, "\u2500", scalec(pink, 0.85))
                buf.put(px, y0, "o", white)
    elif li in (15, 16):
        buf.hline(4, W - 5, int(cy - 6), "\u2500", scalec(white, 0.4))
        buf.hline(4, W - 5, int(cy + 6), "\u2500", scalec(white, 0.4))
        if li == 15:
            draw_lemny(buf, cx, cy, 8, k / 1.2, scalec(cyan, g))
        else:
            draw_lemny(buf, cx, cy, 8, 1.0, scalec(cyan, 0.8))
            for yy in (cy - 6, cy + 6):
                for x in range(int(cx - 14), int(cx + 14), 3):
                    buf.put(x, yy, "\u2591", white)
            buf.text(int(cx) + 10, int(cy - 8), "lim -> inf", scalec(white, 0.7))
    elif li in (17, 18):
        if li == 17:
            sw = clamp(k / 0.45, 0, 1)
            bx, by = int(cx - 4), int(cy + 2)
            buf.hline(bx - 6, bx + 6, by, "\u2500", scalec(white, g))
            buf.vline(bx - 6, by - 2, by, "\u2502", white)
            buf.put(bx - 6, by - 3, "\u2588", white)
            a = lerp(-1.1, 0.0, sw)
            buf.line(bx, by, bx + math.sin(a) * -7, by - math.cos(a) * 7, "\u2588",
                     scalec((255, 230, 120), g))
            buf.put(bx + 6, by, "\u2588", white)
            if 0.85 < sw < 1.0:
                buf.text(bx + 6, by - 3, "*", scalec((255, 255, 160), g))
        else:
            m = clamp(k / 1.4, 0, 1)
            m2 = clamp((k - 1.2) / 1.0, 0, 1)
            for x in range(4, W - 4):
                ph = x / 7.0 - t * 1.2
                v = math.sin(ph * TAU)
                if m2 > 0:
                    v = lerp(v, 0.06 * math.sin(ph * 6 * TAU), m2)
                elif m > 0.4:
                    v = lerp(v, abs(v), (m - 0.4) / 0.6)
                y = cy - v * 6
                buf.put(x, y, "\u2588", scalec(cyan, g))
            buf.text(4, 3, "AC", scalec((255, 170, 90), 1.0 if m < 0.5 else 0.4))
            buf.text(W - 8, 3, "DC", scalec((120, 255, 160), 1.0 if m2 > 0.4 else 0.4))
    elif li in (19, 20):
        if li == 19:
            n = clamp(k / 1.4, 0, 1)
            buf.ring(cx, cy, 4 + n * 12, "\u2591", scalec((200, 200, 220), 0.5 * (1 - n * 0.3)))
            buf.disc(cx, cy, 3 + n * 11, "\u2591", scalec((30, 30, 40), 0.9))
            for ex in (-1, 1):
                exx = cx + ex * 6
                close = clamp(k / 1.0, 0, 1)
                buf.line(exx - 3, cy - 2 + close * 3, exx - 1, cy - 2 + close * 3, "\u2588", white)
                buf.line(exx + 1, cy - 2 + close * 3, exx + 3, cy - 2 + close * 3, "\u2588", white)
        else:
            draw_spiral(buf, cx, cy, t * 1.4, scalec(cyan, g), arms=2)
            draw_spiral(buf, cx + 3, cy - 2, t * 1.4 + 2, scalec(pink, g * 0.7), arms=2)
            buf.wobble(2.0, t, 7)
    elif li in (21, 22):
        ty = int(cy + 4)
        if li == 21:
            buf.hline(2, W - 3, ty, "\u2500", scalec(white, 0.35))
            for i in range(0, W - 6, 6):
                buf.put(2 + i, ty, "\u00b7", white)
            px = 4 + (t * 12) % (W - 14)
            for j in range(5):
                buf.put(px - j * 1.5, ty, "\u2588" if j == 0 else "\u00b7",
                        scalec(cyan, 1 - j * 0.18))
            draw_stars(buf, t, 40, 77, drift=3.0, y0=2, y1=int(cy + 2))
        else:
            zero = W / 2 - (t * 8) % (W * 0.6)
            buf.hline(2, W - 3, ty, "\u2500", scalec(white, 0.35))
            buf.put(zero, ty - 1, "\u2588", white)
            buf.text(zero - 1, ty + 1, "0", white)
            yr = int(2026 - k * 900)
            for i in range(-4, 5):
                xx = zero + i * 10
                if 2 < xx < W - 4:
                    buf.put(xx, ty - 1, "\u2502", scalec(white, 0.6))
                    lab = f"{abs(yr + i * 225)}{'AD' if yr + i * 225 >= 0 else 'BC'}"
                    buf.text(xx - 2, ty + 1, lab[:5], scalec(cyan, 0.8))
    else:  # 23, 24 unite
        pr = clamp(k / 1.3, 0, 1)
        sep = (1 - pr) * W * 0.4
        buf.line(cx - sep, cy, cx + sep, cy, "\u2500", scalec(white, 0.25))
        buf.disc(cx - sep, cy, 1.6, "\u2588", cyan)
        buf.disc(cx + sep, cy, 1.6, "\u2588", pink)
        if pr >= 1:
            buf.disc(cx, cy, 1.6, "\u2588", white)
            for j in range(3):
                ph = (t * 0.7 + j / 3) % 1.0
                buf.ring(cx, cy, 2 + ph * 14, "\u00b7", scalec(mixc(cyan, pink, j / 2), (1 - ph)))
            buf.sine(0, W - 1, cy + 8, 2.5, 9, t, scalec(cyan, 0.4))
    return {"vig": 0.42, "grain": 0.035, "scan": 0.11}


def _chorus_core(buf, c, tint, spawn_rate, stamp_mode=False):
    """Shared chorus visual: a growing wall of simulation windows."""
    t, W, H = c.t, buf.W, buf.H
    buf.clear((5, 5, 14))
    st = c.state
    if "wins" not in st:
        st["wins"] = []
        st["next_slot"] = 0
    slots = []
    gw, gh = 19, 8
    for ry in range(3):
        for rx in range(4):
            slots.append((int(W * 0.06 + rx * (W * 0.23)), int(2 + ry * max(6, (c.band_top - 12) / 2))))
    # spawn on beats
    if "last_bi" not in st:
        st["last_bi"] = c.bi
    if c.bi > st["last_bi"] or not st["wins"]:
        st["last_bi"] = c.bi
        for _ in range(spawn_rate):
            if len(st["wins"]) < len(slots):
                kind = ["globe", "wave", "heart", "stars"][st["next_slot"] % 4]
                st["wins"].append({"slot": st["next_slot"],
                                   "t0": t - 0.45 - rnd(c.bi * 7 + st["next_slot"]) * 0.3,
                                   "kind": kind})
                st["next_slot"] += 1
    kinds_colors = {"globe": (110, 190, 255), "wave": (120, 255, 190),
                    "heart": (255, 120, 170), "stars": (240, 220, 140)}
    for w in st["wins"]:
        x, y = slots[w["slot"] % len(slots)]
        age = t - w["t0"]
        if age < 0.12:
            continue
        col = kinds_colors[w["kind"]]
        wob = 0.0
        if stamp_mode:
            w.setdefault("dead", age > 2.2)
            wob = math.sin(t * 20 + w["slot"]) * 0.7
        draw_window(buf, x + int(wob), y + int(wob * 0.5), gw, gh,
                    f"sim_{w['slot']:03d}.exe", scalec(col, 0.9))
        mx, my = x + 2, y + 2
        mw, mh = gw - 4, gh - 4
        if w["kind"] == "globe":
            buf.ring(mx + mw / 2, my + mh / 2, 2.2, "\u2500", col)
            buf.ring(mx + mw / 2, my + mh / 2, 1.2, "\u2502", scalec(col, 0.7))
        elif w["kind"] == "wave":
            buf.sine(mx, mx + mw, my + mh / 2, 1.6, 5, t + w["slot"], col, ch="\u2588")
        elif w["kind"] == "heart":
            draw_heart(buf, mx + mw / 2, my + mh / 2 - 1, 4.2, col,
                       fill=w["slot"] % 2 == 0)
        else:
            for i in range(6):
                buf.put(mx + rnd(w["slot"] * 9 + i) * mw, my + rnd(w["slot"] * 7 + i) * mh,
                        "*", scalec(col, 0.4 + 0.6 * math.sin(t * 3 + i) ** 2))
        if c.pulse > 0.85:
            buf.rect_border(x - 1, y - 1, gw + 2, gh + 2, scalec(col, c.pulse * 0.7))
    return st["wins"]


def sc_chorus(buf, c):
    t, k, li = c.t, c.lt, c.li
    W, H = buf.W, buf.H
    wins = _chorus_core(buf, c, (140, 170, 255), spawn_rate=2 if li in (26, 84) else 1)
    white = (235, 240, 255)
    cyan = (120, 220, 255)
    cx, cy = W / 2, H * 0.14
    if li in (29,):
        buf.ring(cx, cy, 3.5, "\u2500", scalec((255, 220, 90), 0.9))
        buf.line(cx - 2.5, cy - 1, cx - 1.5, cy - 2.4, "\u2588", (255, 220, 90))
        buf.line(cx + 1.5, cy - 2.4, cx + 2.5, cy - 1, "\u2588", (255, 220, 90))
        buf.ring(cx, cy + 1.2, 2.2, "\u2588", (255, 220, 90), a0=0.25, a1=PI - 0.25, squish=0.9)
        buf.textc(int(cy + 6), "happiness.exe", scalec((255, 220, 90), 0.8))
    if li in (30, 88):
        wx, wy = int(W * 0.30), int(H * 0.40)
        prog = clamp(k / 1.6, 0, 1)
        draw_window(buf, wx, wy, 40, 8, "world.exe", cyan,
                    body=["> run world.exe", "> executing" + "." * (int(t * 3) % 4)])
        buf.hline(wx + 2, wx + 2 + int(36 * prog), wy + 6, "\u2588", (120, 255, 160))
        if c.pulse > 0.6:
            buf.flash((90, 130, 255), (c.pulse - 0.6) * 0.25)
    if li in (31, 89):
        bx, by = int(W * 0.38), int(H * 0.30)
        bw, bh = int(W * 0.24), int(H * 0.38)
        buf.rect_border(bx, by, bw, bh, scalec((150, 150, 170), 0.9))
        for x in range(bx + 3, bx + bw - 2, 4):
            buf.vline(x, by + 1, by + bh - 2, "\u2502", scalec((150, 150, 170), 0.5))
        draw_person(buf, bx + bw * 0.35, by + bh - 2, bh * 0.6, (255, 160, 200))
        draw_person(buf, bx + bw * 0.65, by + bh - 2, bh * 0.6, (130, 210, 240), keep=1.0 if li == 31 else 0.35)
    if li == 32:
        draw_rain(buf, c.state, W, max(4, int(H * 0.6)), t, 0.016, cyan,
                  scalec(cyan, 0.5), "01{}[]<>=+*", density=0.4)
        buf.glitch(0.25, int(t * 8))
    return {"vig": 0.35, "grain": 0.04, "scan": 0.10}


def sc_quirky(buf, c):
    t, k, li = c.t, c.lt, c.li
    W, H = buf.W, buf.H
    buf.clear((16, 8, 20))
    warm = (255, 190, 120)
    magenta = (255, 110, 199)
    white = (240, 240, 255)
    cy = c.cy_canvas - 1
    cx = W / 2
    st = c.state

    pairs = {34: 33, 36: 35, 38: 37, 40: 39, 42: 41, 44: 43, 46: 45, 48: 47}
    base = pairs.get(li, li)

    if base in (33, 35):
        s = 6.5
        bob = math.sin(t * 2.2) * 1.5
        if base == 33:
            draw_eggplant(buf, cx, cy + bob, s, t)
            if li == 34 and k > 0.3:
                if rnd(int(t * 12)) < 0.5:
                    spawn_particles(st, cx + rnd(int(t * 30)) * 8 - 4, cy - s * 0.5, 2,
                                    (170, 255, 170), spread=6, up=10, g=20, life=0.9, ch="+")
                update_particles(buf, st, 0.016)
        else:
            draw_tomato(buf, cx, cy + bob, s, t)
            if li == 36 and k > 0.3:
                if rnd(int(t * 12)) < 0.5:
                    spawn_particles(st, cx + rnd(int(t * 30)) * 10 - 5, cy, 2,
                                    (170, 255, 170), spread=8, up=12, g=25, life=0.9, ch="*")
                update_particles(buf, st, 0.016)
        label_y = int(cy - s * 1.9)
        if label_y < 2:
            label_y = 2
        buf.textc(label_y, ["EGGPLANT.EXE", "TOMATO.EXE"][base == 35],
                  scalec(magenta, 0.8))
    elif base == 37:
        s = 9 + c.pulse * 1.2
        draw_cat(buf, cx, cy, s, t)
        for j in range(2):
            ph = (t * 0.5 + j * 0.5) % 1.0
            buf.text(cx + 8 + ph * 10, cy - 6 - ph * 4, "~purr~",
                     scalec(magenta, 1 - ph))
        if li == 38:
            buf.sine(cx - 20, cx + 20, cy + s * 1.3, 1.5, 5, t, scalec(magenta, 0.6))
    elif base == 39:
        draw_god(buf, cx, cy - 1, 6.5, t, warm)
        draw_person(buf, cx, cy + 8.5, 7, scalec(white, 0.5 + c.pulse * 0.5))
        buf.ring(cx, cy + 3, 3 + (1 - c.pulse) * 3, "\u00b7", scalec(warm, c.pulse))
        if li == 40:
            buf.textc(2, "existence: PROOF OF YOU FOUND", scalec(warm, 0.85))
    elif base == 41:
        fem, masc = (255, 110, 185), (110, 185, 255)
        state = 0 if (int(t * 1.4) % 2 == 0) else 1
        cur = fem if state == 0 else masc
        buf.flash(cur, 0.12 + c.pulse * 0.06)
        draw_font(buf, int(cx) - 3, max(2, int(cy) - 9), "F" if state == 0 else "M",
                  mixc(cur, (255, 255, 255), 0.4), FONT5)
        draw_toggle(buf, cx, cy, 8, state, fem, masc)
        buf.textc(int(min(cy + 4, c.band_top - 2)), "gender.swap()",
                  scalec(white, 0.6))
    elif base == 43:
        day = 0.5 + 0.5 * math.sin(t * 0.9)
        draw_clock(buf, cx, cy, 7, t, 1 if day > 0.5 else 0)
        buf.textc(int(cy + 10), "AM  <->  PM", scalec(white, 0.7))
        buf.flash((255, 200, 120) if day > 0.5 else (60, 60, 140), abs(day - 0.5) * 0.25)
    elif base == 45:
        swap = int(t * 1.6) % 2
        sky = (120, 200, 255)
        for i, lab in enumerate(["S", "M"]):
            px = cx + (-7 if (i == 0) != swap else 7) - 3
            draw_window(buf, int(px), int(cy - 3), 8, 6, None,
                        magenta if i == 0 else sky)
            draw_font(buf, int(px) + 2, int(cy - 1), lab, white, FONT5)
        buf.textc(int(cy + 5), "role.swap()", scalec(white, 0.6))
    else:  # 47/48 trance
        draw_spiral(buf, cx, cy, t * 0.9, scalec(magenta, 0.8), arms=3)
        draw_spiral(buf, cx, cy, t * 0.9 + PI, scalec((120, 200, 255), 0.6), arms=3)
        buf.flash(magenta, 0.06 + c.pulse * 0.12)
        if li == 48:
            buf.wobble(1.6, t, 4)
    # spotlight floor
    buf.hline(int(cx - 9), int(cx + 9), int(min(cy + 11, c.band_top - 2)), "\u2500", scalec(warm, 0.35))
    return {"vig": 0.45, "grain": 0.05, "scan": 0.12}


def sc_chorus2(buf, c):
    t, li = c.t, c.li
    W, H = buf.W, buf.H
    _chorus_core(buf, c, (150, 150, 230), spawn_rate=1)
    cx, cy = W / 2, H * 0.3
    if li in (50,):
        for j in range(3):
            ph = (t * 0.9 + j / 3) % 1.0
            buf.ring(cx, cy, 3 + ph * (W * 0.45), "\u00b7",
                     scalec((160, 220, 255), (1 - ph) * 0.8), squish=0.45)
    if li == 52:
        prog = clamp((t - 108.69) / 1.6, 0, 1)
        buf.ring(cx, cy, 9, "\u2500", scalec((120, 120, 140), 0.6))
        buf.ring(cx, cy, 9, "\u2588", (140, 255, 170), a0=-PI / 2,
                 a1=-PI / 2 + TAU * prog)
        if prog >= 1:
            draw_font(buf, int(cx - 20), int(cy - 3), "100%", (140, 255, 170), FONT3, sc=1)
            jag = [(int(cx - 12 + i * 3), int(cy + math.sin(i * 2.1) * 4)) for i in range(9)]
            buf.poly(jag, "\u2588", (255, 120, 90))
    return {"vig": 0.38, "grain": 0.04, "scan": 0.10}


def sc_breakup(buf, c):
    t, k, li = c.t, c.lt, c.li
    W, H = buf.W, buf.H
    # palette drains as "you have left" repeats
    drain_map = {53: 0.0, 54: 0.25, 55: 0.45, 56: 0.65, 57: 0.85}
    drain = drain_map.get(li, 1.0)
    base_bg = mixc((14, 12, 26), (8, 8, 10), drain)
    buf.clear(base_bg)
    grey = mixc((140, 150, 200), (110, 110, 120), drain)
    pink = mixc((255, 160, 200), (150, 140, 150), drain)
    cyanc = mixc((130, 215, 240), (120, 130, 140), drain)
    cy = c.cy_canvas
    cx = W / 2
    conts = c.state.setdefault("conts", make_continents(20))
    draw_globe(buf, cx, cy - 6, min(W * 0.16, 11), t * 0.25, scalec(grey, 0.5),
               continents=conts, dim=0.8)
    draw_stars(buf, t, 40, 21, dim=(70, 70, 90), drift=0.2, y1=int(cy - 12))
    floor = int(cy + 8)
    buf.hline(int(cx - 22), int(cx + 22), floor, "\u2500", scalec(grey, 0.6))
    # cracks on the globe (drawn first, figures go on top)
    for i in range(int(drain * 5)):
        a = rnd(50 + i) * TAU
        x0, y0 = cx + math.cos(a) * 4, cy - 6 + math.sin(a) * 4
        pts = [(x0, y0)]
        for j in range(4):
            pts.append((pts[-1][0] + (rnd(60 + i * 9 + j) - 0.5) * 8,
                        pts[-1][1] + (rnd(61 + i * 9 + j) - 0.3) * 5))
        buf.poly(pts, "\u2588", scalec((255, 90, 90), 0.55))

    me_x, you_x = cx - 8, cx + 8
    draw_person(buf, me_x, floor, 9, pink)
    if li == 53:
        flick = 0.6 + 0.4 * math.sin(t * 9)
        draw_person(buf, you_x, floor, 9, scalec(cyanc, flick))
    elif 54 <= li <= 57:
        keep = 1.0 - (li - 53) * 0.27
        draw_person(buf, you_x, floor, 9, cyanc, keep=max(0.05, keep), seed=li)
        if k < 0.4:
            spawn_particles(c.state, you_x, floor - 4, 5, cyanc, spread=6, up=14, g=80, life=1.0)
        update_particles(buf, c.state, 0.016)
    else:
        # isolation: me alone in a box, spotlight
        draw_person(buf, me_x, floor, 9, scalec(pink, 0.85))
        bx, bw, bh = int(me_x - 6), 13, 13
        buf.rect_border(bx, floor - bh, bw, bh, scalec(grey, 0.9))
        for x in range(bx + 2, bx + bw - 1, 3):
            buf.vline(x, floor - bh + 1, floor - 1, "\u2502", scalec(grey, 0.4))
        spot = scalec((255, 240, 210), 0.14 + c.pulse * 0.06)
        for dy in range(bh - 1):
            half = 1 + dy * 0.55
            buf.hline(me_x - half, me_x + half, floor - bh + dy + 1, "\u2591", spot)
    return {"vig": 0.5 + drain * 0.15, "grain": 0.06, "scan": 0.12}


def sc_erase(buf, c):
    t, k, li = c.t, c.lt, c.li
    W, H = buf.W, buf.H
    buf.clear((10, 8, 12))
    red = (255, 90, 90)
    grey = (150, 150, 165)
    rose = (255, 150, 170)
    cx, cy = W / 2, c.cy_canvas

    if li in (59, 60, 61, 62):
        floor = int(cy + 8)
        buf.hline(int(cx - 18), int(cx + 18), floor, "\u2500", scalec(grey, 0.5))
        draw_person(buf, cx, floor, 9, rose)
        if li == 59:
            buf.ring(cx, floor - 9, 2 + k * 3, "\u00b7", scalec((255, 220, 180), max(0, 0.8 - k)))
        elif li == 60:
            st = c.state
            if "debris" not in st:
                st["debris"] = [(rnd(200 + i) * W, 3 + rnd(201 + i) * (floor - 4),
                                 "01<>{};=#*"[int(rnd(202 + i) * 10)])
                                for i in range(70)]
            sweep = k / 1.8 * W
            for (x, y, ch) in st["debris"]:
                if x > sweep:
                    buf.put(x, y, ch, scalec(grey, 0.6))
            buf.vline(sweep, 2, floor, "\u2588", scalec((255, 255, 220), 0.9))
            buf.vline(sweep + 2, 3, floor, "\u2591", scalec((255, 255, 220), 0.4))
            if rnd(int(t * 20)) < 0.6:
                spawn_particles(st, sweep, rnd(int(t * 50)) * floor, 2, grey, spread=8, up=8, g=40, life=0.6)
            update_particles(buf, st, 0.016)
        elif li == 61:
            buf.flash((255, 200, 140), 0.10 + 0.06 * math.sin(t * 5))
            draw_font(buf, int(cx - font_width("MAYBE", FONT3) / 2), int(cy - 2),
                      "MAYBE", scalec((255, 210, 160), 0.5 + 0.5 * math.sin(t * 6)), FONT3, sc=1)
        else:
            draw_heart(buf, cx, cy, 8, rose, fill=False)
            draw_heart(buf, cx + 1.5, cy, 7.4, scalec((10, 8, 12), 1.0))
            jag = [(cx - 2 + i * 1.5, cy - 4 + abs(math.sin(i * 1.7)) * 6) for i in range(6)]
            buf.poly(jag, "\u2588", scalec((60, 40, 50), 1.0))
    elif li == 63:
        gx, gy = cx, 4
        draw_god(buf, gx, gy, 5.5, t, (255, 230, 160))
        # stairs
        for i in range(5):
            sx = cx - 12 + i * 5
            sy = cy + 9 - i * 2.5
            buf.hline(sx, sx + 4, sy, "\u2588", scalec(grey, 0.7))
            buf.vline(sx + 4, sy - 2, sy, "\u2502", scalec(grey, 0.5))
        climber = clamp(k / 3.0, 0, 1)
        px = cx - 12 + climber * 20
        py = cy + 9 - climber * 10
        draw_person(buf, px, py, 5, rose)
        if c.pulse > 0.75:
            bolt = [(cx + (rnd(int(t * 30) + j) - 0.5) * 14, gy + 3 + j * 3.4) for j in range(8)]
            buf.poly(bolt, "\u2588", scalec((255, 255, 180), c.pulse))
            buf.flash((255, 240, 200), (c.pulse - 0.75) * 0.6)
    else:  # 64, 65 illegal arguments
        st = c.state
        if "errs" not in st:
            st["errs"] = []
        msgs = ["TypeError: illegal arguments",
                "World.run() crashed",
                "AssertionError: god != null",
                "ValueError: you not in scope",
                "RuntimeError: heart overflow",
                "you.exe is not responding",
                "ERROR: proof of existence failed",
                "Segmentation fault (core dumped)"]
        if (c.bi != st.get("last_ebi") or not st["errs"]) and li >= 64:
            st["last_ebi"] = c.bi
            st["errs"].append({"t0": t, "x": rnd(int(t * 100) + len(st["errs"])) * (W - 42) + 2,
                               "y": 3 + (len(st["errs"]) % 5) * 4.2,
                               "msg": msgs[len(st["errs"]) % len(msgs)]})
        for e in st["errs"][-6:]:
            draw_window(buf, int(e["x"]), int(e["y"]), 44, 5, "FATAL", red,
                        body=[e["msg"]])
        buf.rect_border(0, 0, W, H - 2, scalec(red, 0.4 + c.pulse * 0.5))
        if li == 65:
            draw_font(buf, int(cx - font_width("ILLEGAL", FONT5) / 2), int(cy - 4),
                      "ILLEGAL", scalec(red, 0.6 + c.pulse * 0.4), FONT5)
            draw_font(buf, int(cx - font_width("ARGUMENTS", FONT5) / 2), int(cy + 4),
                      "ARGUMENTS", scalec(red, 0.6 + c.pulse * 0.4), FONT5)
            buf.glitch(0.2, int(t * 9))
        else:
            draw_font(buf, int(cx - font_width("ERROR", FONT5) / 2), int(cy - 3),
                      "ERROR", scalec(red, 0.5 + c.pulse * 0.5), FONT5)
    return {"vig": 0.45, "grain": 0.05, "scan": 0.12}


def sc_darksim(buf, c):
    t, W, H = c.t, buf.W, buf.H
    buf.clear((8, 2, 2))
    draw_rain(buf, c.state, W, H, t, 0.016, (255, 120, 80), (200, 60, 50),
              "01<>{};=#ERROKILLX/\\|", density=0.7)
    draw_heart(buf, W / 2, c.cy_canvas, min(W * 0.055, H * 0.14),
               scalec((120, 30, 40), 0.9))
    if c.onset > 0.75:
        buf.glitch(0.3, int(t * 11))
    if t > 145.6:
        word = "EXECUTION"
        n = clamp((t - 145.6) / 1.6, 0, 1)
        shown = word[:int(n * len(word))]
        draw_font(buf, (W - font_width(shown, FONT5)) // 2, int(c.cy_canvas) - 3,
                  shown, scalec((255, 240, 240), 0.9), FONT5)
    return {"vig": 0.5, "grain": 0.08, "scan": 0.14}


FEED = ["> taskkill /PID 435278010 /F",
        "SUCCESS: SIGTERM sent to world.exe",
        "> kill -9 $(pgrep -f love)",
        "ERROR: process <you> not found",
        "> rm -rf ./memories/",
        "WARNING: cannot delete: in use",
        "> git reset --hard you^",
        "FATAL: detached HEAD",
        "> sudo shutdown -h now",
        "broadcast: goodbye, world",
        "> :(){ :|:& };:",
        "segmentation fault (core dumped)"]


def sc_execution(buf, c):
    t, k, li = c.t, c.lt, c.li
    W, H = buf.W, buf.H
    buf.clear((6, 0, 0))
    red = (255, 45, 45)
    white = (255, 245, 245)
    cx, cy = W / 2, c.cy_canvas
    st = c.state

    if 67 <= li <= 78:
        idx = li - 67
        draw_hexdump(buf, 0, W, 2, H - 4, t, scalec(red, 0.4), seed=idx)
        # stamp
        imp = clamp(k / 0.12, 0, 1)
        col = white if idx % 2 == 0 else red
        word = "EXECUTION"
        w = font_width(word, FONT5, sc=1)
        buf.clear_rect(int(cx - w / 2) - 4, int(cy - 6), int(cx + w / 2) + 3, int(cy + 8))
        draw_font(buf, int(cx - w / 2), int(cy - 3), word, scalec(col, 1.0),
                  FONT5, sc=1, slant=1)
        # border box around stamp
        buf.rect_border(int(cx - w / 2) - 3, int(cy - 5), w + 6, 13,
                        scalec(col, 0.9))
        buf.text(4, 2, f"PROCESS TERMINATION #{idx + 1:02d}", scalec(red, 0.8))
        feed = st.setdefault("feed", [])
        if not feed or feed[-1][0] != li:
            feed.append((li, FEED[idx % len(FEED)]))
        for i, (_, s) in enumerate(feed[-5:]):
            buf.text(3, int(H * 0.55) + i, s, scalec((255, 130, 130), 0.75))
        buf.flash((255, 255, 255), max(0.0, 0.55 - k * 4.5))
        buf.shift(int((rnd(int(t * 60)) - 0.5) * 5 * (1 - imp)),
                  int((rnd(int(t * 60) + 1) - 0.5) * 3 * (1 - imp)))
        if imp >= 1 and k < 0.5 and c.pulse > 0.9:
            buf.flash(red, 0.12)
    elif 79 <= li <= 81:
        pairs = {79: [("EIN", "1"), ("DOS", "2")], 80: [("TRIOS", "3"), ("NE", "4")],
                 81: [("FEM", "5"), ("LIU", "6")]}
        draw_hexdump(buf, 0, W, 2, H - 4, t, scalec(red, 0.4), seed=79)
        words = [(word, num, j) for j, (word, num) in enumerate(pairs[li])
                 if k >= j * 0.43]
        if words:
            buf.clear_rect(int(cx - 30), int(cy - 6), int(cx + 30), int(cy + 8))
        for word, num, j in words:
            w0 = j * 0.43
            kk = k - w0
            imp = clamp(kk / 0.1, 0, 1)
            col = white if j == 0 else red
            fw = font_width(word, FONT5, sc=1)
            px = int(cx - fw / 2) + (j - 0.5) * int(W * 0.24)
            draw_font(buf, px, int(cy - 3), word, scalec(col, 0.95), FONT5, sc=1)
            draw_font(buf, px + fw + 2, int(cy - 3), num, scalec(col, 0.7), FONT5, sc=1)
            buf.shift(int((rnd(int(t * 70) + j) - 0.5) * 4 * (1 - imp)), 0)
            buf.flash(col, max(0.0, 0.35 - kk * 3))
    else:  # 82 final execute button
        draw_hexdump(buf, 0, W, 2, H - 4, t, scalec(red, 0.35), seed=82)
        press = clamp(k / 0.55, 0, 1)
        bw, bh = 31, 8
        bx, by = int(cx - bw / 2), int(cy - bh / 2)
        col = red if press < 1 else white
        buf.clear_rect(bx + 1, by + 1, bx + bw - 2, by + bh - 2)
        buf.fill_bg(bx + 1, by + 1, bx + bw - 2, by + bh - 2, scalec((30, 0, 0), 1.0))
        buf.rect_border(bx, by, bw, bh, col, "\u2554\u2550\u2557\u2551\u255a\u255d")
        draw_font(buf, bx + 2, by + 2, "EXECUTE", col, FONT3, sc=1)
        # cursor arrow approaching
        ax = lerp(W - 6, cx, min(1, press * 1.4))
        ay = lerp(H - 3, cy, min(1, press * 1.4))
        buf.put(ax, ay, ">", white)
        if press >= 1:
            buf.flash((255, 255, 255), clamp(1.6 - k, 0, 1) * 0.9)
            if k > 0.55:
                n = int((k - 0.55) * 60)
                for i in range(n):
                    a = rnd(i * 13 + 1) * TAU
                    r = (k - 0.55) * W * 1.2 * rnd(i * 7)
                    buf.put(cx + math.cos(a) * r, cy + math.sin(a) * r * 0.55,
                            "\u2588", scalec(white, 1 - (k - 0.55)))
                buf.glitch(0.5, int(t * 20))
    return {"vig": 0.55, "grain": 0.06, "scan": 0.12}


def sc_exec_chorus(buf, c):
    t, k, li = c.t, c.lt, c.li
    W, H = buf.W, buf.H
    cx, cy = W / 2, c.cy_canvas
    if li in (83, 84, 85, 86):
        wins = _chorus_core(buf, c, (255, 120, 120), spawn_rate=1, stamp_mode=True)
        st = c.state
        stamped = st.get("stamped", 0)
        if c.bi > st.get("last_sbi", -1):
            st["last_sbi"] = c.bi
            st["stamped"] = stamped + 1
            st["stamp_t"] = t
        st["stamped"] = min(st["stamped"], len(wins))
        for i, w in enumerate(wins):
            if i < st["stamped"]:
                slots_x = int(W * 0.06 + (w["slot"] % 4) * (W * 0.23))
                slots_y = int(H * 0.16 + (w["slot"] // 4) * (H * 0.24))
                if t - st.get("stamp_t", 0) < 0.2 and i == st["stamped"] - 1:
                    buf.flash((255, 60, 60), 0.3)
                draw_font(buf, slots_x + 6, slots_y + 2, "X", (255, 60, 60), FONT3, sc=1)
        if li == 86:
            draw_font(buf, int(W * 0.40), c.band_top - 8, "ALONE.EXE",
                      (255, 150, 150), FONT3)
    elif li in (87, 88):
        warm = (255, 200, 140)
        prog = clamp(k / 1.2, 0, 1)
        conts = c.state.setdefault("conts", make_continents(24))
        r = prog * min(W * 0.16, (H - 4) * 0.4)
        draw_globe(buf, cx, cy, max(2, r), t * 1.2, warm, continents=conts)
        buf.flash(warm, 0.05 + c.pulse * 0.08)
        if rnd(int(t * 6)) < 0.3:
            buf.glitch(0.35, int(t * 13))
        if li == 88 and k > 0.6:
            buf.textc(max(2, int(cy - r - 4)), f"restore: {int(prog * 37)}% ... failing",
                      scalec((255, 120, 120), 0.85))
    else:  # 89, 90 trapped
        buf.clear((10, 4, 8))
        grey = (140, 140, 150)
        bx, by = int(W * 0.34), int(H * 0.22)
        bw, bh = int(W * 0.32), int(H * 0.6)
        buf.rect_border(bx, by, bw, bh, scalec(grey, 0.8))
        for x in range(bx + 3, bx + bw - 2, 4):
            buf.vline(x, by + 1, by + bh - 2, "\u2502", scalec(grey, 0.4))
        floor = by + bh - 2
        draw_person(buf, bx + bw * 0.38, floor, bh * 0.62, (255, 160, 200))
        draw_person(buf, bx + bw * 0.62, floor, bh * 0.62, grey, keep=0.3, seed=99)
        buf.flash((255, 60, 60), c.pulse * 0.10)
        if li == 90 and k > 1.0:
            buf.wobble(1.2, t, 3)
    return {"vig": 0.5, "grain": 0.06, "scan": 0.12}


def sc_love(buf, c):
    t, k, li = c.t, c.lt, c.li
    W, H = buf.W, buf.H
    buf.clear((16, 8, 14))
    rose = (255, 160, 180)
    gold = (255, 210, 120)
    white = (250, 230, 235)
    cx, cy = W / 2, c.cy_canvas
    draw_stars(buf, t, 40, 31, dim=(120, 80, 100), drift=0.15, y1=H - 6)

    if li in (91, 92):
        st = c.state
        if "syms" not in st:
            syms = []
            for i in range(26):
                syms.append({"tx": rnd(300 + i) * W, "ty": 3 + rnd(301 + i) * (H - 10),
                             "s": "d/dx E=mc2 a2+b2=c2 sin cos SUM int you+me"[i % 40:][:1],
                             "ph": rnd(302 + i) * TAU})
            st["syms"] = syms
        for s in st["syms"]:
            x = s["tx"] + math.sin(t * 0.7 + s["ph"]) * 3
            y = s["ty"] + math.cos(t * 0.5 + s["ph"]) * 2
            buf.put(x, y, s["s"], scalec(gold, 0.5 + 0.3 * math.sin(t + s["ph"])))
        prog = clamp((t - 178.79) / 3.0, 0, 1) if li >= 92 else 0.0
        if prog > 0:
            draw_heart(buf, cx, cy, 9, rose, fill=False, progress=prog)
            if prog >= 1:
                draw_heart(buf, cx, cy, 9, mixc(rose, gold, 0.3 + 0.2 * math.sin(t * 2)),
                           fill=True)
    elif li in (93, 94):
        qs = ["Q: what is love?", "Q: how much?", "Q: why me?"]
        ans = ["A: you", "A: infinity", "A: always you"]
        for j in range(2):
            if k > j * 0.8:
                x = int(W * 0.14 + j * (W * 0.42))
                y = int(H * 0.2 + j * (H * 0.3))
                draw_window(buf, x, y, 30, 6, "query", gold,
                            body=[qs[(li - 93 + j) % 3], ans[(li - 93 + j) % 3]])
                buf.put(x + 26, y + 4, "v", (140, 255, 160))
    elif li == 95:
        eq = "LOVE = SUM( you * me )dt"
        draw_font(buf, (W - font_width(eq, FONT3, 1)) // 2, 2, eq, gold, FONT3)
        prog = clamp(k / 2.4, 0, 1)
        draw_heart(buf, cx, c.band_top - 6, min(6.0, c.band_top - 9), rose,
                   fill=prog >= 1, progress=prog)
        buf.flash(rose, 0.04 + c.pulse * 0.06)
    else:  # 96, 97, 98 free vs trapped
        # bird flies away (you are free)
        bx = W * 0.2 + (t - 187.97) * 5.5
        by = H * 0.30 - (t - 187.97) * 1.1
        if bx < W + 4:
            draw_bird(buf, bx, by, t, white)
            draw_bird(buf, bx - 5, by + 2, t + 0.4, scalec(white, 0.5))
        draw_stars(buf, t, 30, 33, dim=(150, 120, 140), drift=0.3, y1=int(H * 0.4))
        # heart-shaped cage with me inside
        st = c.state
        s = min(W * 0.075, max(4.0, cy - 2))
        pts = heart_points(s)
        colscale = {}
        for (x, y) in pts:
            xi = int(round(x))
            colscale.setdefault(xi, [1e9, -1e9])
            colscale[xi][0] = min(colscale[xi][0], y)
            colscale[xi][1] = max(colscale[xi][1], y)
        barcol = scalec(gold, 0.75 + c.pulse * 0.25)
        for xi, (y0, y1) in colscale.items():
            xx = int(cx + xi)
            for y in range(int(cy + y0) + 1, int(cy + y1)):
                if (xx + int(cy)) % 2 == 0:
                    buf.put(xx, y, "\u2502", barcol)
        draw_heart(buf, cx, cy, s, scalec(gold, 0.9))
        draw_person(buf, cx, cy + s * 0.55, s * 1.1, rose)
        draw_ecg(buf, 4, W - 5, c.band_top - 3, t, 3.5, scalec(rose, 0.9), flat=0.0)
    return {"vig": 0.42, "grain": 0.045, "scan": 0.11}


def sc_cage(buf, c):
    t, W, H = c.t, buf.W, buf.H
    buf.clear((9, 7, 12))
    rose = (255, 160, 180)
    gold = (255, 210, 120)
    cx, cy = W / 2, c.cy_canvas - 1
    draw_stars(buf, t, 60, 41, dim=(100, 90, 120), drift=0.25)
    s = min(W * 0.075, max(4.0, cy + 1))
    pts = heart_points(s)
    colscale = {}
    for (x, y) in pts:
        xi = int(round(x))
        colscale.setdefault(xi, [1e9, -1e9])
        colscale[xi][0] = min(colscale[xi][0], y)
        colscale[xi][1] = max(colscale[xi][1], y)
    for xi, (y0, y1) in colscale.items():
        xx = int(cx + xi)
        for y in range(int(cy + y0) + 1, int(cy + y1)):
            if (xx + int(cy)) % 2 == 0:
                buf.put(xx, y, "\u2502", scalec(gold, 0.35 + c.pulse * 0.3))
    draw_heart(buf, cx, cy, s, scalec(gold, 0.5))
    draw_person(buf, cx, cy + s * 0.55, s * 0.9, scalec(rose, 0.7))
    # ecg slowing toward flatline
    flat = clamp((t - 196.0) / 8.0, 0, 0.88)
    spike = 0.0
    if (t % 2.6) < 0.10 and flat < 0.8:
        spike = 0.5
    draw_ecg(buf, 4, W - 5, c.band_top - 3, t, 3.0, scalec(rose, 0.7), flat=flat - spike * 0.4)
    return {"vig": 0.5 + clamp((t - 196) / 10, 0, 0.25), "grain": 0.05, "scan": 0.13}


def sc_end(buf, c):
    t, k, W, H = c.t, c.lt, buf.W, buf.H
    buf.clear((0, 0, 0))
    cx = W / 2
    # CRT power-off: content collapses to a line, then a dot
    if t < 208.2:
        ph = clamp((t - 206.0) / 2.0, 0, 1)
        gh = (1 - ph) * H
        gw = W * (1 - ph ** 3)
        if ph < 0.85:
            for y in range(int((H - gh) / 2), int((H + gh) / 2)):
                buf.hline((W - gw) / 2, (W + gw) / 2, y, "\u2591",
                          scalec((120, 200, 255), 0.5 * (1 - ph)))
        if ph > 0.8:
            dot = clamp((ph - 0.8) / 0.2, 0, 1)
            buf.disc(cx, H / 2, 2 * (1 - dot) + 0.5, "\u2588",
                     scalec((180, 220, 255), 1 - dot))
        return {"vig": 0.0, "grain": 0.02, "scan": 0.0}
    # end card
    fade = clamp((t - 208.4) / 1.6, 0, 1)
    g = fade
    title_rows = ["WORLD.EXECUTE(ME);"]
    if font_width(title_rows[0], FONT5) > W - 4:
        title_rows = ["WORLD.", "EXECUTE(ME);"]
    text_rows = [
        ("SONG : MILI", (150, 155, 170)),
        ("MUSIC.163.COM #435278010", (150, 155, 170)),
        ("THANKS - EXIT CODE 0", (255, 160, 180)),
    ]
    h = 8 * len(title_rows) + 2 + 6 * len(text_rows)
    y = max(1, (H - 2 - h) // 2)
    for tr in title_rows:
        w = font_width(tr, FONT5)
        draw_font(buf, int(cx - w / 2), y, tr, scalec((200, 215, 235), g), FONT5)
        y += 8
    y += 2
    for s, col in text_rows:
        w = font_width(s, FONT3)
        draw_font(buf, int(cx - w / 2), y, s, scalec(col, g), FONT3)
        y += 6
    return {"vig": 0.0, "grain": 0.02, "scan": 0.0}


SCENES = [
    (0.0, 16.04, sc_creation, "I. creation"),
    (16.04, 29.28, sc_title, "II. title"),
    (29.28, 58.65, sc_math, "III. mathematics"),
    (58.65, 73.53, sc_chorus, "IV. simulations"),
    (73.53, 103.03, sc_quirky, "V. disguises"),
    (103.03, 110.40, sc_chorus2, "VI. vibrations"),
    (110.40, 117.95, sc_breakup, "VII. isolation"),
    (117.95, 134.38, sc_erase, "VIII. illegal arguments"),
    (134.38, 147.52, sc_darksim, "IX. darkness"),
    (147.52, 162.23, sc_execution, "X. execution"),
    (162.23, 176.96, sc_exec_chorus, "XI. reprise"),
    (176.96, 193.46, sc_love, "XII. love"),
    (193.46, 205.56, sc_cage, "XIII. alone"),
    (205.56, 9999.0, sc_end, "XIV. end"),
]

LYRIC_COLOR_RANGES = [
    (0, 8, (130, 255, 170)), (9, 24, (120, 225, 255)), (25, 32, (240, 245, 255)),
    (33, 48, (255, 200, 120)), (49, 52, (240, 245, 255)), (53, 58, (190, 190, 200)),
    (59, 65, (255, 120, 120)), (67, 90, (255, 235, 235)), (91, 98, (255, 170, 190)),
    (100, 100, (240, 240, 245)),
]


def lyric_color(li):
    for a, b, col in LYRIC_COLOR_RANGES:
        if a <= li <= b:
            return col
    return (220, 220, 230)


# ------------------------------------------------------- band / HUD chrome


def band_layout(text, W):
    """Return (font_lines, band_h) for the karaoke band of one lyric line."""
    text = (text or "").strip()
    if not text:
        return [], 0
    if font_width(text, FONT5) <= W - 4:
        return [(text, FONT5)], 9
    if font_width(text, FONT3) <= W - 4:
        return [(text, FONT3)], 7
    wrapped = wrap_font(text, W - 4, FONT3)
    return ([(s, FONT3) for s in wrapped],
            5 * len(wrapped) + (len(wrapped) - 1) + 4)


def draw_chrome(buf, c, act_name):
    W, H = buf.W, buf.H
    t = c.t
    # lyric band (band_top already smoothed by the orchestrator)
    font_lines, band_h = band_layout(c.line_text, W)
    if font_lines:
        band_top = c.band_top
        buf.clear_rect(0, band_top, W - 1, H - 2)
        buf.fill_bg(0, band_top, W - 1, H - 2, (2, 2, 4))
        col = scalec(lyric_color(c.li), 0.9 + c.pulse * 0.1)
        total_h = sum((7 if f is FONT5 else 5) for _, f in font_lines) \
            + (len(font_lines) - 1) * 2
        y = H - 2 - total_h
        for s, fnt in font_lines:
            w = font_width(s, fnt)
            draw_font(buf, (W - w) // 2, y, s, col, fnt)
            y += (7 if fnt is FONT5 else 5) + 2
    # top HUD
    buf.clear_rect(0, 0, W - 1, 0)
    hud = scalec((110, 110, 125), 0.9)
    buf.text(1, 0, "WORLD.EXECUTE(ME);", hud)
    buf.text(21, 0, "| " + act_name, scalec(hud, 0.75))
    right = f"[{fmt_time(t)}/{fmt_time(211.9)}]  BPM 107.7  "
    buf.text(W - len(right) - 3, 0, right, hud)
    beat_col = mixc((90, 90, 100), (255, 240, 200), c.pulse)
    buf.put(W - 3, 0, "o", beat_col)
    # progress bar
    buf.clear_rect(0, H - 1, W - 1, H - 1)
    pw = W - 16
    filled = int(clamp(t / 211.9, 0, 1) * pw)
    buf.put(0, H - 1, "[", hud)
    if filled >= 1:
        buf.hline(1, filled, H - 1, "\u2501", scalec((200, 205, 220), 0.8))
    if filled + 1 <= pw:
        buf.hline(filled + 1, pw, H - 1, "\u2501", scalec((60, 60, 70), 0.8))
    buf.put(pw + 1, H - 1, "]", hud)
    buf.text(pw + 3, H - 1, fmt_time(t) + "/" + fmt_time(211.9), scalec(hud, 0.8))


# -------------------------------------------------------------- orchestration


def render_frame(buf, t, lines, tl, scene_state_box, last_scene_idx,
                 band_state=None):
    idx = 0
    for i, (t0, t1, fn, name) in enumerate(SCENES):
        if t0 <= t < t1:
            idx = i
            break
    else:
        idx = len(SCENES) - 1
    t0, t1, fn, name = SCENES[idx]
    if idx != last_scene_idx[0]:
        scene_state_box.clear()
        last_scene_idx[0] = idx
    c = Ctx(buf, t, lines, tl)
    c.state = scene_state_box
    # karaoke band: ease band_top toward its target so scenes glide
    # instead of jumping when consecutive lines wrap differently
    _, band_h = band_layout(c.line_text, buf.W)
    target = buf.H - 2 - band_h if band_h else buf.H - 2
    if band_state is not None:
        prev, pt = band_state
        if prev is None or t < pt or t - pt > 0.5:
            band_state[0] = target
        else:
            k = min(1.0, (t - pt) * 9.0)
            band_state[0] = prev + (target - prev) * k
        band_state[1] = t
        c.band_top = int(round(band_state[0]))
    else:
        c.band_top = target
    c.cy_canvas = (c.band_top - 1) / 2
    params = {"vig": 0.4, "grain": 0.04, "scan": 0.12}
    try:
        p = fn(buf, c)
        if p:
            params.update(p)
    except Exception as e:  # never let one scene kill the show
        import traceback
        traceback.print_exc()
        buf.textc(buf.H // 2, f"[scene error: {e}]", (255, 80, 80))
    draw_chrome(buf, c, name)
    params["seed"] = int(t * 30)
    return c, params


# ------------------------------------------------------------------ preview


def render_still(t, W, H, lines, tl):
    buf = Buf(W, H)
    box = {}
    last = [-1]
    c, params = render_frame(buf, t, lines, tl, box, last)
    buf.finish(vig=params["vig"], grain=params["grain"], scan=params["scan"],
               seed=params["seed"], gain=1.0)
    return buf, c


def write_preview(path, times, W, H, lines, tl):
    frames = []
    for t in times:
        buf, c = render_still(t, W, H, lines, tl)
        act = next((n for (a, b, f, n) in SCENES if a <= t < b), "?")
        frames.append((t, act, buf.html()))
    page = ["<!doctype html><meta charset='utf-8'><title>PV preview</title>",
            "<body style='background:#000;margin:16px'>",
            "<style>pre{font:12px/12px 'Cascadia Mono','Consolas',monospace;"
            "letter-spacing:0;margin:4px 0 28px 0;color:#ccc}</style>"]
    for t, act, html in frames:
        page.append(f"<h3 style='color:#8f8;font-family:monospace'>t={t:.2f}s  [{act}]</h3>")
        page.append(f"<pre>{html}</pre>")
    page.append("</body>")
    Path(path).write_text("\n".join(page), encoding="utf-8")
    print(f"wrote {path} ({len(times)} frames)")


# -------------------------------------------------------------------- main


def enable_vt():
    if os.name == "nt":
        os.system("")
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if k32.GetConsoleMode(h, ctypes.byref(mode)):
                k32.SetConsoleMode(h, mode.value | 0x0004)
        except Exception:
            pass


def enter_screen():
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    sys.stdout.flush()


def leave_screen():
    sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
    sys.stdout.flush()


def probe_wide_chars():
    """True if the terminal renders U+2588 double-width (CJK console fonts).

    Prints one full-block at the home position, then asks the terminal for
    the cursor position via DSR 6n: a reported column of 3 means the glyph
    consumed two cells, so we switch the whole show to ASCII glyphs.
    """
    global ASCII_ONLY
    try:
        sys.stdout.write("\x1b[1;1H\u2588\x1b[6n")
        sys.stdout.flush()
        resp = ""
        deadline = time.time() + 0.4
        if os.name == "nt":
            import msvcrt
            while time.time() < deadline and "R" not in resp:
                if msvcrt.kbhit():
                    resp += msvcrt.getwch()
                else:
                    time.sleep(0.01)
        else:
            import select
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            try:
                while time.time() < deadline and "R" not in resp:
                    r, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if r:
                        resp += os.read(fd, 16).decode("utf-8", "ignore")
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\x1b[1;1H \x1b[1;1H")
        sys.stdout.flush()
        m = re.search(r"\x1b\[(\d+);(\d+)R", resp)
        if m:
            wide = int(m.group(2)) >= 3
            if wide:
                print("note: terminal font renders blocks double-width; "
                      "using ASCII glyphs", file=sys.stderr)
            return wide
    except Exception:
        pass
    return False


class KeyPoller:
    """Best-effort non-blocking key reads (q/esc quit, space pause)."""

    def __init__(self):
        self.impl = None
        try:
            if os.name == "nt":
                import msvcrt
                self.impl = ("nt", msvcrt)
            else:
                import select
                import termios
                import tty
                tty.setcbreak(0)
                self.impl = ("posix", select, termios)
        except Exception:
            pass

    def poll(self):
        if not self.impl:
            return None
        if self.impl[0] == "nt":
            msvcrt = self.impl[1]
            if msvcrt.kbhit():
                return msvcrt.getwch()
            return None
        sel, termios = self.impl[1], self.impl[2]
        import select as _s
        r, _, _ = _s.select([sys.stdin], [], [], 0)
        if r:
            return sys.stdin.read(1)
        return None


def run(args):
    lines = load_lrc(LRC)
    tl = load_timeline(TIMELINE)
    duration = tl["duration"] if tl else 211.9

    W = args.size_w or shutil.get_terminal_size((100, 36)).columns
    H = args.size_h or shutil.get_terminal_size((100, 36)).lines
    if W < 72 or H < 24:
        print(f"warning: terminal {W}x{H} is small; 100x36+ recommended", file=sys.stderr)

    enable_vt()
    enter_screen()
    global ASCII_ONLY
    if args.ascii:
        ASCII_ONLY = True
    else:
        ASCII_ONLY = probe_wide_chars()
        sys.stdout.write("\x1b[2J")
        sys.stdout.flush()

    music_ok = False
    if not args.no_audio:
        try:
            import pygame
            pygame.mixer.init(frequency=44100)
            pygame.mixer.music.load(str(SONG))
            pygame.mixer.music.set_volume(args.volume)
            if args.start > 0:
                pygame.mixer.music.play(start=args.start)
            else:
                pygame.mixer.music.play()
            music_ok = True
        except Exception as e:
            print(f"audio unavailable ({e}); running silent", file=sys.stderr)

    buf = Buf(W, H)
    keys = KeyPoller()
    scene_box = {}
    last_scene = [-1]
    band_state = [None, 0.0]
    frame_errs = 0
    fps = args.fps
    frame_budget = 1.0 / fps
    paused = False
    pause_off = 0.0
    frozen_t = args.start
    start_wall = time.perf_counter()
    end_hold = None
    try:
        while True:
            wall = time.perf_counter() - start_wall + pause_off
            if music_ok:
                import pygame
                pos = pygame.mixer.music.get_pos() / 1000.0
                if not pygame.mixer.music.get_busy() and not paused:
                    if end_hold is None:
                        end_hold = wall
                    pos = duration - args.start
                t = pos + args.start + args.av_offset
            else:
                t = wall + args.start
                if paused:
                    t = frozen_t
            if end_hold is not None and wall - end_hold > 4.0:
                break
            if t > duration + 3.4:
                break

            key = keys.poll()
            if key in ("q", "Q", "\x1b"):
                break
            if key == " ":
                paused = not paused
                if music_ok:
                    import pygame
                    if paused:
                        pygame.mixer.music.pause()
                    else:
                        pygame.mixer.music.unpause()
                else:
                    frozen_t = t
                    if not paused:
                        start_wall = time.perf_counter()
                        pause_off = 0.0
                        args.start = frozen_t

            render_t = t
            try:
                buf.clear()
                c, params = render_frame(buf, max(0.0, render_t), lines, tl,
                                         scene_box, last_scene, band_state)
                gain = 1.0
                if render_t < 0.6:
                    gain = clamp(render_t / 0.6, 0, 1)
                if render_t > duration + 1.4:
                    gain = clamp((duration + 3.4 - render_t) / 2.0, 0, 1)
                buf.finish(vig=params["vig"], grain=params["grain"],
                           scan=params["scan"], seed=params["seed"], gain=gain)
                sys.stdout.write(buf.render())
                sys.stdout.flush()
            except Exception:
                # a glitchy frame should never kill the whole show
                frame_errs += 1
                if frame_errs <= 5:
                    import traceback
                    traceback.print_exc()
            # pacing
            now = time.perf_counter()
            target = start_wall + (wall + frame_budget) - pause_off
            sleep = target - now
            if sleep > 0:
                time.sleep(sleep)
    except KeyboardInterrupt:
        pass
    finally:
        if music_ok:
            try:
                import pygame
                pygame.mixer.music.fadeout(600)
                pygame.mixer.quit()
            except Exception:
                pass
        leave_screen()
    print("World.execute(me); — thanks for watching.")
    print("listen: https://music.163.com/#/song?id=435278010")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="World.execute(me); — terminal MV")
    ap.add_argument("--no-audio", action="store_true", help="render visuals only")
    ap.add_argument("--start", type=float, default=0.0, help="begin N seconds in")
    ap.add_argument("--av-offset", type=float, default=0.0,
                    help="shift visuals vs audio (seconds, + = visuals later)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--volume", type=float, default=0.9)
    ap.add_argument("--size-w", type=int, default=None)
    ap.add_argument("--size-h", type=int, default=None)
    ap.add_argument("--ascii", action="store_true",
                    help="force ASCII glyphs (skip the double-width probe)")
    ap.add_argument("--still", type=str, default=None,
                    help="comma list of times; write preview.html and exit")
    ap.add_argument("--out", type=str, default="preview.html")
    args = ap.parse_args()

    if args.still:
        global ASCII_ONLY
        ASCII_ONLY = args.ascii
        lines = load_lrc(LRC)
        tl = load_timeline(TIMELINE)
        times = [float(x) for x in args.still.split(",")]
        W = args.size_w or 100
        H = args.size_h or 36
        write_preview(args.out, times, W, H, lines, tl)
        return
    run(args)


if __name__ == "__main__":
    main()
