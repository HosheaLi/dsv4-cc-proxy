"""从 coverage.json 生成 SVG 覆盖率徽章。"""

import json
import sys

COLORS = {
    "brightgreen": 90,
    "yellow": 80,
    "orange": 70,
    "red": 0,
}


def main():
    with open("coverage.json") as f:
        data = json.load(f)

    pct = int(data["totals"]["percent_covered"])

    color = next(c for c, threshold in COLORS.items() if pct >= threshold)

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="110" height="20">'
        '<rect width="110" height="20" fill="#555" rx="3"/>'
        f'<rect x="60" width="50" height="20" fill="{color}" rx="3"/>'
        '<text x="30" y="14" fill="#fff" font-size="11" font-family="sans-serif" text-anchor="middle">coverage</text>'
        f'<text x="85" y="14" fill="#fff" font-size="11" font-family="sans-serif" text-anchor="middle">{pct}%</text>'
        "</svg>"
    )

    with open("coverage.svg", "w") as f:
        f.write(svg)

    print(f"Coverage badge: {pct}% ({color})")


if __name__ == "__main__":
    main()
