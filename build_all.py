#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_all.py — 按 cities.json 构建全部城市数据包

产出：
    data/cities/<slug>.js   每城一个数据包（window.NEW_DATA = {...}）
    data/cities/manifest.js 城市清单（window.CITY_MANIFEST = {...}），前端据此渲染切换器
    data/items.js           默认城市（上海）数据包，兜底 file:// 直开

构建后可用 build_qa.py 校验数据完整性。
"""
import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CITIES_CFG = os.path.join(HERE, "cities.json")
CITY_DIR = os.path.join(HERE, "data", "cities")
PY = sys.executable


def main():
    with open(CITIES_CFG, encoding="utf-8") as f:
        cities = json.load(f)["cities"]
    os.makedirs(CITY_DIR, exist_ok=True)

    built, failed = [], []
    for c in cities:
        slug = c["slug"]
        pool = os.path.join(CITY_DIR, f"pool_{slug}.json")
        matrix = os.path.join(CITY_DIR, f"matrix_{slug}.json")
        if not (os.path.exists(pool) and os.path.exists(matrix)):
            print(f"✗ {c['name']}：缺 {os.path.basename(pool) if not os.path.exists(pool) else os.path.basename(matrix)}，跳过（先跑 fetch_all.py）")
            failed.append(c["name"])
            continue
        out_js = os.path.join(CITY_DIR, f"{slug}.js")
        p = subprocess.run(
            [PY, "build_site.py", "--pool", pool, "--matrix", matrix, "--out", out_js],
            capture_output=True, cwd=HERE)
        log = p.stdout.decode("utf-8", "ignore") + p.stderr.decode("utf-8", "ignore")
        if p.returncode != 0:
            print(f"✗ {c['name']} 构建失败：\n{log[-400:]}")
            failed.append(c["name"])
            continue
        size_kb = os.path.getsize(out_js) // 1024
        print(f"✓ {c['name']} → cities/{slug}.js ({size_kb} KB)")
        built.append({"slug": slug, "name": c["name"], "size_kb": size_kb})

    manifest = {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "default": built[0]["slug"] if built else "shanghai",
        "cities": built,
    }
    with open(os.path.join(CITY_DIR, "manifest.js"), "w", encoding="utf-8") as f:
        f.write("window.CITY_MANIFEST = " + json.dumps(manifest, ensure_ascii=False, indent=1) + ";\n")
    print(f"\n清单：{len(built)} 城 → data/cities/manifest.js")
    if failed:
        print("缺数据/失败：", "、".join(failed))
    sys.exit(0 if built else 1)


if __name__ == "__main__":
    main()
