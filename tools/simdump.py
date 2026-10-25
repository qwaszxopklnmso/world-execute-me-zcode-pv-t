"""Render t0..t1 continuously (persistent scene state), dump the last frame."""
import sys
sys.path.insert(0, ".")
import world_execute_me as m

t0, t1 = float(sys.argv[1]), float(sys.argv[2])
rows = sys.argv[3] if len(sys.argv) > 3 else None
W, H = 100, 36
if len(sys.argv) > 4:
    H = int(sys.argv[4])
lines = m.load_lrc(m.LRC)
tl = m.load_timeline(m.TIMELINE)
buf = m.Buf(W, H)
st = {}
ls = [-1]
bs = [None, 0.0]
t = t0
while t < t1:
    m.render_frame(buf, t, lines, tl, st, ls, band_state=bs)
    t += 1.0 / 30
rng = range(H)
if rows:
    a, b = rows.split("-")
    rng = range(int(a), int(b) + 1)
for j in rng:
    print(f"{j:3d}|{''.join(buf.ch[j * W:(j + 1) * W]).rstrip()}|")
