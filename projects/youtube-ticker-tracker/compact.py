#!/usr/bin/env python3
"""Print transcript(s) merged into ~60s chunks for faster analysis. Usage: compact.py <id>..."""
import sys, glob, re
for vid in sys.argv[1:]:
    f = glob.glob(f"transcripts/*/{vid}.txt")[0]
    chunks = {}
    for line in open(f):
        m = re.match(r"\[(\d+):(\d+)\] (.*)", line.strip())
        if not m: continue
        k = int(m[1]); chunks.setdefault(k, []).append(m[3].replace(">> ", ""))
    print(f"=== {vid}")
    for k, v in chunks.items(): print(f"[{k}m] " + " ".join(v))
