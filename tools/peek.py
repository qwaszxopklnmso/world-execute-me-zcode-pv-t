"""Dump a rendered frame as a numbered text grid (QA tool)."""
import sys
sys.path.insert(0, ".")
import world_execute_me as m


def main():
    t = float(sys.argv[1])
    rows = sys.argv[2] if len(sys.argv) > 2 else None  # "a-b" or None for all
    W, H = 100, 36
    if len(sys.argv) > 3:
        H = int(sys.argv[3])
    if len(sys.argv) > 4:
        W = int(sys.argv[4])
    lines = m.load_lrc(m.LRC)
    tl = m.load_timeline(m.TIMELINE)
    buf = m.Buf(W, H)
    st = {}
    m.render_frame(buf, t, lines, tl, st, [-1], band_state=[None, 0.0])
    rng = range(H)
    if rows:
        a, b = rows.split("-")
        rng = range(int(a), int(b) + 1)
    for j in rng:
        txt = "".join(buf.ch[j * W:(j + 1) * W]).rstrip()
        print(f"{j:3d}|{txt}|")


main()
