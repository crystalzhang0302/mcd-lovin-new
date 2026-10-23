#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_all.py — 按 cities.json 配置批量抓取全部城市

每城产出（存 data/cities/）：
    pool_<slug>.json     单店候选池（fetch_pool.py）
    matrix_<slug>.json   多门店矩阵（fetch_matrix.py）

单个城市失败不中断整体，最后打印汇总。手动补抓单个城市：
    python fetch_all.py --only chengdu
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CITIES_CFG = os.path.join(HERE, "cities.json")
OUT_DIR = os.path.join(HERE, "data", "cities")
PY = sys.executable


def load_cities():
    with open(CITIES_CFG, encoding="utf-8") as f:
        return json.load(f)["cities"]


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, cwd=HERE)
    ok = p.returncode == 0
    return ok, p.stdout.decode("utf-8", "ignore") + p.stderr.decode("utf-8", "ignore")


def fetch_city(city, limit):
    slug = city["slug"]
    pool_out = os.path.join(OUT_DIR, f"pool_{slug}.json")
    matrix_out = os.path.join(OUT_DIR, f"matrix_{slug}.json")
    base = ["--city", city["city"], "--keyword", city["keyword"]]

    print(f"\n=== [{city['name']}] {city['city']} · {city['keyword']} ===", flush=True)
    ok1, log1 = run([PY, "fetch_pool.py"] + base + ["--out", pool_out])
    print(log1.strip()[-500:], flush=True)
    if not ok1:
        return False, "pool 失败"

    ok2, log2 = run([PY, "fetch_matrix.py"] + base +
                    ["--limit", str(limit), "--out", matrix_out])
    print(log2.strip()[-500:], flush=True)
    if not ok2:
        return False, "matrix 失败"
    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只抓指定 slug 的城市")
    ap.add_argument("--limit", type=int, default=5, help="每城门店数")
    args = ap.parse_args()

    cities = load_cities()
    if args.only:
        cities = [c for c in cities if c["slug"] == args.only]
        if not cities:
            sys.exit(f"cities.json 中没有 slug={args.only}")

    os.makedirs(OUT_DIR, exist_ok=True)
    t0 = datetime.now()
    results = []
    for i, c in enumerate(cities, 1):
        print(f"\n>>> ({i}/{len(cities)}) {c['name']}", flush=True)
        try:
            ok, msg = fetch_city(c, args.limit)
        except Exception as e:
            ok, msg = False, repr(e)
        results.append((c["name"], ok, msg))

    print("\n" + "=" * 46)
    print(f"耗时 {datetime.now() - t0}")
    fails = 0
    for name, ok, msg in results:
        print(("  ✓ " if ok else "  ✗ ") + name + ("" if ok else "  ← " + msg))
        fails += 0 if ok else 1
    print(f"\n完成：{len(results) - fails}/{len(results)} 城成功")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
