"""`:disabled` 겉모습 통일(부채 ④) — 네 자리의 실효 대비를 계산한다.

**값을 고르는 것이 아니라 계산해서 세운다** — 10.1 팔레트(`10_palette_contrast.py`)와
같은 자세다. `opacity` 는 요소 전체를 배경과 합성하므로, 비활성 버튼의 실제 겉모습은
**합성된 색**이고 그것을 그 자리의 배경과 견줘야 한다.

**★ 네 자리는 한 계열이 아니다.** 하나는 solid(파란 배경 + 흰 글자)이고 셋은
ghost(투명 배경 + 테두리)다. 같은 불투명도라도 ghost 는 배경이 비쳐 훨씬 옅어진다 —
그래서 "네 값을 한 값으로" 가 자동으로 정답이 아니다. 이 표가 그것을 수치로 낸다.

    python3 docs/plans/10_disabled_contrast.py
"""


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


def composite(fg, bg, alpha):
    """`opacity` 는 요소를 배경 위에 알파 합성한다 — 그 결과 색을 돌려준다."""
    out = []
    for i in (1, 3, 5):
        f, b = int(fg[i:i + 2], 16), int(bg[i:i + 2], 16)
        out.append(round(f * alpha + b * (1 - alpha)))
    return "#%02x%02x%02x" % tuple(out)


#: styles.css `:root` 에서 그대로 옮긴 값. 팔레트가 바뀌면 여기도 바뀐다.
TOKENS = {
    "--blue-600": "#006ebe",   # --action-primary
    "--blue-800": "#003e70",   # --action-primary-hover (admin ghost 글자가 같은 토큰을 쓴다)
    "--blue-900": "#042847",   # --text-body
    "--slate-0": "#ffffff",    # --surface-card / --text-on-accent
    "--slate-50": "#f6f9fc",   # --surface-raised
    "--slate-200": "#dbe2e9",  # --border-hairline
    "--slate-600": "#545f6a",  # --text-muted
}

#: 대상 네 자리. `(선택자군, 계열, 글자, 채움, 현행 alpha)`.
#: 배경은 그 버튼이 실제로 놓이는 표면이다(카드 위 = `--surface-card`).
SITES = [
    ("auth-submit 외 7선택자", "solid", "--slate-0", "--blue-600", 0.42),
    ("admin-create-form / admin-project-card", "ghost", "--blue-800", None, 0.45),
    ("order-controls", "ghost", "--blue-900", None, 0.35),
    ("version-list / export-actions / export-controls", "ghost", "--slate-600", None, 0.50),
]

SURFACE = "--slate-0"
CANDIDATES = (0.35, 0.42, 0.45, 0.50, 0.55, 0.60)


def _row(site, alpha, surface_hex):
    label, kind, text, fill, _ = site
    text_hex, = (TOKENS[text],)
    # solid 는 채움과 글자가 함께 합성되므로 "글자 대 채움" 이 실효 대비다.
    # ghost 는 채움이 없어 "글자 대 표면" 이 그대로 실효 대비다.
    if kind == "solid":
        fg = composite(text_hex, composite(TOKENS[fill], surface_hex, alpha), 1.0)
        bg = composite(TOKENS[fill], surface_hex, alpha)
    else:
        fg = composite(text_hex, surface_hex, alpha)
        bg = surface_hex
    return fg, bg, contrast(fg, bg)


def build():
    surface_hex = TOKENS[SURFACE]
    print(f"표면 = {SURFACE} {surface_hex}\n")
    print("현행 —")
    print(f"{'자리':52} {'계열':6} {'alpha':>6} {'합성 글자':>10} {'대비':>7}")
    for site in SITES:
        fg, bg, ratio = _row(site, site[4], surface_hex)
        print(f"{site[0]:52} {site[1]:6} {site[4]:6.2f} {fg:>10} {ratio:6.2f}:1")

    print("\n후보값별 실효 대비 —")
    header = "자리".ljust(52) + "".join(f"{a:>8.2f}" for a in CANDIDATES)
    print(header)
    for site in SITES:
        cells = "".join(
            f"{_row(site, a, surface_hex)[2]:7.2f} " for a in CANDIDATES
        )
        print(f"{site[0]:52}{cells}")

    print("\n읽는 법 — 비활성 컨트롤에는 WCAG 최소 대비 요건이 없다(1.4.3 예외).")
    print("그래서 이 표는 합격/불합격이 아니라 **네 자리가 서로 얼마나 다른가**를 잰다.")
    print("solid 는 채움이 함께 옅어져 글자 대비가 거의 안 변하고(파란 블록이 남는다),")
    print("ghost 는 alpha 가 그대로 글자 대비다 — 같은 값을 줘도 두 계열은 안 같아진다.")


if __name__ == "__main__":
    build()
