"""OKLCH -> sRGB hex + WCAG contrast, 의존성 없이.

블루 파스텔 팔레트를 '고르는' 것이 아니라 '계산해서' 세운다.
- 램프는 OKLCH 에서 hue/chroma 고정 + L 등간격 (지각 균등)
- 모든 전경/배경 짝을 WCAG 2.2 로 검산
"""
import math

# ---------- OKLCH -> sRGB ----------
def _srgb_gamma(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055

def oklch_to_hex(L, C, H):
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bl = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    out = []
    clipped = False
    for v in (r, g, bl):
        v = _srgb_gamma(v)
        if v < -0.001 or v > 1.001:
            clipped = True
        out.append(max(0.0, min(1.0, v)))
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in out), clipped

# ---------- WCAG ----------
def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def luminance(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

def contrast(fg, bg):
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)

# ---------- 팔레트 정의 ----------
# 주 색상(hue): 서늘한 잉크블루. 250 = 파랑에 살짝 보라가 도는 쪽,
# 회색과 섞였을 때 탁해지지 않는 구간.
HUE = 250
# 중립도 살짝 파랗게 — 순회색이면 파스텔 표면과 안 붙는다.
NEUTRAL_HUE = 250

RAMP = {  # (L, C)
    "blue-50":  (0.975, 0.012),
    "blue-100": (0.945, 0.028),
    "blue-200": (0.900, 0.048),
    "blue-300": (0.830, 0.072),
    "blue-400": (0.720, 0.105),
    "blue-500": (0.620, 0.140),
    "blue-600": (0.530, 0.150),
    "blue-700": (0.450, 0.135),
    "blue-800": (0.360, 0.105),
    "blue-900": (0.270, 0.070),
}
NEUTRAL = {
    "slate-0":   (1.000, 0.000),
    "slate-50":  (0.980, 0.005),
    "slate-100": (0.955, 0.008),
    "slate-200": (0.910, 0.012),
    "slate-300": (0.850, 0.016),
    # ★ 10.1 구현이 푼 값 둘. 브리프 초판은 카드(가장 밝은 면)만 보고 정했는데
    # 실제 최악 조건은 **페이지(`blue-50`)** 다 — 거기서 재니 둘 다 미달이었다
    # (테두리 2.95 / placeholder 3.97). 감으로 조정하지 않고 **최악 배경에서 목표
    # 대비를 내는 가장 밝은 L** 을 이분 탐색으로 풀었다(둘 다 여유 없이 딱 맞는
    # 값이라 더 밝게 하면 즉시 미달한다).
    "slate-400": (0.650, 0.020),   # border-control — page 에서 3.03:1
    "slate-450": (0.545, 0.020),   # placeholder    — page 에서 4.58:1
    # ★ 이분 탐색이 낸 0.552 는 실수 공간에서 정확히 4.50 이었으나 **hex 로
    # 8비트 양자화되며 4.49 로 떨어졌다.** 경계값은 양자화 뒤에 다시 재고
    # 여유를 둔다 — 검산이 실수값이 아니라 **실제 렌더될 hex** 를 보기 때문이다.
    "slate-500": (0.580, 0.020),
    "slate-600": (0.480, 0.022),
    "slate-700": (0.390, 0.022),
    "slate-900": (0.255, 0.020),
}
STATES = {  # 파스텔 톤과 같은 L 대역에 맞춘 상태색
    "danger-100": (0.930, 0.040, 25),
    "danger-600": (0.520, 0.170, 25),
    "danger-700": (0.440, 0.155, 25),
    "warn-100":   (0.940, 0.045, 75),
    "warn-700":   (0.470, 0.110, 75),
    "ok-100":     (0.940, 0.040, 155),
    "ok-700":     (0.460, 0.090, 155),
}

def fit_gamut(L, C, H):
    """색역을 벗어나면 **명도(L)는 유지한 채 채도만** 줄여 들여놓는다.

    L 을 건드리면 지각 균등 램프가 무너지고 대비 계산이 어긋난다. 채도는
    줄여도 '같은 밝기의 조금 덜 선명한 파랑'이라 램프의 성질이 유지된다.
    """
    hex_, clipped = oklch_to_hex(L, C, H)
    if not clipped:
        return hex_, C, False
    lo, hi = 0.0, C
    for _ in range(40):
        mid = (lo + hi) / 2
        _, over = oklch_to_hex(L, mid, H)
        if over:
            hi = mid
        else:
            lo = mid
    hex_, _ = oklch_to_hex(L, lo, H)
    return hex_, lo, True


def build():
    out = {}
    for name, (L, C) in RAMP.items():
        out[name] = fit_gamut(L, C, HUE)
    for name, (L, C) in NEUTRAL.items():
        out[name] = fit_gamut(L, C, NEUTRAL_HUE)
    for name, (L, C, H) in STATES.items():
        out[name] = fit_gamut(L, C, H)
    return out

_B = build()
P = {k: v[0] for k, v in _B.items()}
CLIPPED = {k: round(v[1], 4) for k, v in _B.items() if v[2]}

# ---------- 검산 대상: 실제로 화면에 나올 짝 ----------
SURFACES = {
    "page (blue-50)":    P["blue-50"],
    "card (slate-0)":    P["slate-0"],
    "sunken (blue-100)": P["blue-100"],
    "accent soft (blue-100)": P["blue-100"],
}
PAIRS = [
    # (전경, 배경, 최소요구, 용도)
    ("blue-900", "blue-50",  4.5, "본문 잉크 / 페이지"),
    ("blue-900", "slate-0",  4.5, "본문 잉크 / 카드"),
    ("blue-900", "blue-100", 4.5, "본문 잉크 / 침강면"),
    ("slate-600", "blue-50", 4.5, "보조 문구 / 페이지"),
    ("slate-600", "slate-0", 4.5, "보조 문구 / 카드"),
    ("blue-700", "blue-50",  4.5, "링크 / 페이지"),
    ("blue-700", "slate-0",  4.5, "링크 / 카드"),
    ("blue-700", "blue-100", 4.5, "링크 / 침강면"),
    ("slate-0",  "blue-600", 4.5, "주 버튼 라벨"),
    ("slate-0",  "blue-700", 4.5, "주 버튼 라벨(hover)"),
    ("slate-0",  "danger-600", 4.5, "파괴 버튼 라벨"),
    ("danger-700", "danger-100", 4.5, "오류 문구 / 오류면"),
    ("danger-700", "blue-50", 4.5, "오류 문구 / 페이지"),
    ("warn-700", "warn-100", 4.5, "경고 문구 / 경고면"),
    ("ok-700",  "ok-100",   4.5, "성공 문구 / 성공면"),
    # ★ 10.1 구현이 추가한 짝 — 실제 CSS 가 쓰는 표면 계층이 브리프 가정과 달랐다.
    # 이 앱에는 침강면보다 **융기면**이 많다(page 보다 밝은 카드/패널). 그 tier 를
    # `slate-50` 으로 놓으면서 그 위의 모든 전경을 다시 잰다.
    ("blue-900", "slate-50",  4.5, "본문 잉크 / 융기면"),
    ("slate-600", "slate-50", 4.5, "보조 문구 / 융기면"),
    ("blue-700", "slate-50",  4.5, "링크 / 융기면"),
    ("slate-450", "slate-0",  4.5, "placeholder / 카드"),
    ("slate-450", "slate-50", 4.5, "placeholder / 융기면"),
    ("slate-450", "blue-50",  4.5, "placeholder / 페이지"),
    ("danger-700", "slate-0", 4.5, "오류 문구 / 카드"),
    # 비텍스트(테두리·포커스·아이콘) = 3:1
    ("slate-400", "slate-0", 3.0, "입력 테두리 / 카드"),
    ("slate-400", "slate-50", 3.0, "입력 테두리 / 융기면"),
    ("slate-400", "blue-50", 3.0, "입력 테두리 / 페이지"),
    ("blue-600", "slate-50", 3.0, "포커스 링 / 융기면"),
    ("blue-600",  "blue-50", 3.0, "포커스 링 / 페이지"),
    ("blue-600",  "slate-0", 3.0, "포커스 링 / 카드"),
]

if __name__ == "__main__":
    print("=== 색역 이탈(clip) ===", CLIPPED or "없음")
    print("\n=== 램프 ===")
    for k in list(RAMP) + list(NEUTRAL) + list(STATES):
        print(f"  --{k:<12} {P[k]}")

    print("\n=== WCAG 2.2 검산 ===")
    fails = []
    for fg, bg, need, use in PAIRS:
        r = contrast(P[fg], P[bg])
        ok = r >= need
        aaa = r >= 7.0 and need == 4.5
        mark = "OK " if ok else "FAIL"
        if not ok:
            fails.append((fg, bg, r, need, use))
        print(f"  [{mark}] {r:5.2f}:1 (>={need}) {fg:>11} on {bg:<11} {use}"
              + ("  ← AAA" if aaa else ""))
    print(f"\n실패 {len(fails)}건")
    for f in fails:
        print("   ", f)
