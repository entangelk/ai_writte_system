"""fan-out 병합이 전역 top-N 을 정확히 재현하는가 — 반증 시도.

검증 세션의 주장: 프로젝트별 상한 C 로 자른 뒤 합쳐도 **N ≤ C 이면** 전역 top-N 이 정확하다.
내(구현자) 브리프의 주장: 부정확할 수 있다.
둘 중 하나는 틀렸으므로 무작위로 깨뜨려 본다.
"""
import random

def trial(rng, n_projects, n_events, cap, n):
    # (at, project) 사건들. at 동률도 일부러 만든다.
    events = [(rng.randrange(0, 50), rng.randrange(n_projects)) for _ in range(n_events)]
    events = [(at, p, i) for i, (at, p) in enumerate(events)]      # i = tie-breaker

    key = lambda e: (-e[0], e[2])                                   # 최신순, 동률은 i
    true_top = sorted(events, key=key)[:n]

    merged = []
    for p in range(n_projects):
        per = sorted([e for e in events if e[1] == p], key=key)[:cap]  # 서버가 주는 것
        merged += per
    fanout_top = sorted(merged, key=key)[:n]
    return true_top == fanout_top

rng = random.Random(20260810)
CAP = 100
bad_within, bad_beyond = 0, 0
for _ in range(20000):
    n_projects = rng.randrange(1, 12)
    n_events = rng.randrange(0, 900)
    n_within = rng.randrange(1, CAP + 1)        # N ≤ cap
    if not trial(rng, n_projects, n_events, CAP, n_within):
        bad_within += 1
    n_beyond = rng.randrange(CAP + 1, CAP * 4)  # N > cap
    if not trial(rng, n_projects, n_events, CAP, n_beyond):
        bad_beyond += 1

print(f"N <= cap(100) 반례: {bad_within} / 20000")
print(f"N >  cap(100) 반례: {bad_beyond} / 20000")
