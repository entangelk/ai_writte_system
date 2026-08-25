#!/usr/bin/env python3
"""docs/img 스크린샷 정규화 — 오너 결정 2026-08-25.

원본 5장은 서로 다른 창 크기로 찍혀 비율이 1.25~1.82로 퍼져 있다(측정 기록:
daily_logs/2026-08-25/work_log.md). 문서에 나란히 놓을 수 있게 아래 규칙으로 통일한다.

  1. 배경색(가장자리 최다색으로 측정, 다섯 장 모두 #f1f8ff)과 같은 색의 여백을
     24px만 남기고 잘라낸다 — 죽은 여백 제거 + 콘텐츠 중앙 배치.
  2. 3:2 캔버스에 같은 배경색으로 패딩해 콘텐츠를 중앙에 놓는다.
     패딩색 = 페이지 배경색이므로 이음새가 없다(검은 레터박스를 쓰지 않는 이유).
  3. 1200x800으로 리샘플(Lanczos)해 폭을 통일한다.

출력은 <이름>_3x2.png — 원본은 건드리지 않는다. 재실행 가능(멱등).
의존: Python3 + Pillow. 사용: python3 docs/img/normalize.py
"""

import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

TARGET_RATIO = 3 / 2       # 대상 가로세로비 (3:2 — 후보 중 패딩 총량 최소)
OUT_SIZE = (1200, 800)     # 최종 출력 치수 (README 본문폭보다 넉넉 → 레티나에서 선명)
MARGIN = 24                # 오토크롭 후 콘텐츠 주변에 남기는 여백(px)
SUM_THRESHOLD = 30         # 배경색과의 채널 편차 합이 이 값 이하면 여백으로 본다
BG_UNIFORMITY_WARN = 0.90  # 가장자리 최다색 점유율이 이 미만이면 경고(크롬 섞임 의심)

RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def measure_background(im):
    """가장자리 2px의 최다색 = 페이지 배경색. (점유율, 색) 반환."""
    w, h = im.size
    px = im.load()
    border = [px[x, y][:3] for y in (0, 1, h - 2, h - 1) for x in range(w)]
    border += [px[x, y][:3] for x in (0, 1, w - 2, w - 1) for y in range(h)]
    color, count = Counter(border).most_common(1)[0]
    return color, count / len(border)


def content_bbox(im, bg):
    """배경색과 다른 픽셀의 경계 상자. 채널 편차의 **합**이 임계를 넘으면 콘텐츠로 본다.

    채널별 최댓값 기준으로 잡으면 그림자·안티앨리어싱의 옅은 꼬리(합 ~20)까지 콘텐츠로
    분류돼 bbox가 화면 전체로 뛴다(2026-08-25 실측). 흰 카드 내부는 배경(#f1f8ff)과
    편차 합이 ~21이라 못 잡을 수 있으나, 카드의 테두리·그림자가 잡히므로 bbox 용도에는
    충분하다.
    """
    diff = ImageChops.difference(im, Image.new("RGB", im.size, bg))
    total = ImageChops.add(
        ImageChops.add(diff.getchannel(0), diff.getchannel(1)), diff.getchannel(2)
    )
    mask = total.point(lambda v: v > SUM_THRESHOLD and 255)
    return mask.getbbox() or (0, 0, im.width, im.height)


def normalize(path):
    im = Image.open(path).convert("RGB")
    bg, uniformity = measure_background(im)
    if uniformity < BG_UNIFORMITY_WARN:
        print(f"  ★ 경고: 가장자리 단색 점유율 {uniformity:.1%} — 브라우저 크롬이 섞였는지 확인")

    x0, y0, x1, y1 = content_bbox(im, bg)
    x0, y0 = max(0, x0 - MARGIN), max(0, y0 - MARGIN)
    x1, y1 = min(im.width, x1 + MARGIN), min(im.height, y1 + MARGIN)
    content = im.crop((x0, y0, x1, y1))

    # 3:2 캔버스 — 부족한 방향을 배경색으로 채우고 중앙 배치
    cw, ch = content.size
    if cw / ch < TARGET_RATIO:
        canvas_w, canvas_h = round(ch * TARGET_RATIO), ch
    else:
        canvas_w, canvas_h = cw, round(cw / TARGET_RATIO)
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg)
    canvas.paste(content, ((canvas_w - cw) // 2, (canvas_h - ch) // 2))

    out = canvas.resize(OUT_SIZE, RESAMPLE)
    out_path = path.with_name(f"{path.stem}_3x2.png")
    out.save(out_path, optimize=True)

    scale = OUT_SIZE[0] / canvas_w
    print(
        f"  {im.width}x{im.height} → trim({x0},{y0},{x1},{y1}) {cw}x{ch}"
        f" → canvas {canvas_w}x{canvas_h} → {OUT_SIZE[0]}x{OUT_SIZE[1]}"
        f" (리샘플 x{scale:.2f}, 배경 #{bg[0]:02x}{bg[1]:02x}{bg[2]:02x} {uniformity:.1%})"
    )
    assert out.size == OUT_SIZE
    return out_path


def main():
    img_dir = Path(__file__).resolve().parent
    files = sorted(p for p in img_dir.glob("*.png") if not p.stem.endswith("_3x2"))
    if not files:
        sys.exit(f"원본 png가 없음: {img_dir}")
    for p in files:
        print(f"{p.name}:")
        normalize(p)
    print(f"\n{len(files)}장 완료 — 출력: <이름>_3x2.png (원본 보존)")


if __name__ == "__main__":
    main()
