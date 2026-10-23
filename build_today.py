#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把抓取结果 pool_<date>.json 转成前端可直接加载的 data/today.js

用法：
    python build_today.py                 # 用 data/ 下最新的 pool 文件
    python build_today.py --date 2026-10-23

活动关联规则来自 campaign-calendar 的真实文案（2026-10-22 抓取），
按品名关键词匹配；匹配不到的标 null，并在终端列出，方便人工补录。
"""
import argparse
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

# 活动库：key 为匹配规则，value 为活动信息
# 依据：campaign-calendar 2026-10-22 抓取的官方文案
ACTIVITY_RULES = [
    (["龙焰", "芝士棒", "拉丝芝士条"], {
        "t": "麦当劳联动 G-DRAGON",
        "x": "韩式辣酱 × 青梅 × 黄油，三件套 26.9 元起 / 芝士棒版 29.9 元",
        "k": "联名",
    }),
    (["鸡薯双全"], {
        "t": "韩式蘸酱上新",
        "x": "15.9 元起，get GD 同款花式比心",
        "k": "联名",
    }),
    (["蘸酱"], {
        "t": "韩式风味蘸酱上新",
        "x": "韩式辣椒黄油 / 烟熏芝士双酱，11.9 元起",
        "k": "上新",
    }),
    (["蓝莓"], {
        "t": "蓝莓爆爆珠上新",
        "x": "真实蓝莓原浆 × 爆爆珠，颗颗爆汁",
        "k": "上新",
    }),
    (["灰焰"], {
        "t": "灰焰圆筒酷爽登场",
        "x": "香草味 × 酷灰脆筒，灰白撞色",
        "k": "上新",
    }),
    (["心形薯饼"], {
        "t": "限时特惠",
        "x": "8 块装 9.9 元，比 5 块装还便宜",
        "k": "限时",
    }),
    (["板烧"], {
        "t": "板烧「更多汁」升级",
        "x": "腌制工艺升级，不加价换更嫩的腿肉",
        "k": "升级",
    }),
    (["奶昔"], {
        "t": "经典回归",
        "x": "下架多年后重新上架，三味可选",
        "k": "回归",
    }),
    (["柠柠", "多汁柠"], {
        "t": "清爽上新",
        "x": "美汁源联名柠檬饮，解腻首选",
        "k": "上新",
    }),
]

# 通用连带（与具体新品无关，常驻展示）
CROSS = {
    "t": "PEACEMINUSONE 联名周边",
    "x": "任意餐品 +39.9 元换购棒球帽 / 徽章 / 丝巾 · 限定丝巾 10/22 首日开售",
}


def match_activity(name):
    for keys, act in ACTIVITY_RULES:
        if any(k in name for k in keys):
            return act
    return None


def norm(s):
    """名称归一化：去掉空格与各种分隔符，避免「A·B」与「A——B」匹配不上"""
    return re.sub(r"[\s·—–\-~〜/]+", "", s or "")


def load_copy():
    path = os.path.join(DATA, "copy.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        items = json.load(f).get("items", {})
    return {norm(k): v for k, v in items.items()}


def fallback_copy(it):
    tags = [t for t in (it.get("tags") or []) if t not in ("上新", "新升级", "套餐")]
    flavor = ("风味线索是「%s」。" % tags[0]) if tags else ""
    return {
        "s": "初来乍到，先尝为敬",
        "d": "今天新上的一款，%s文案还没补录——在 data/copy.json 里加一条就能换成本店专属的签文。" % flavor,
    }


def latest_pool(day=None):
    if day:
        path = os.path.join(DATA, "pool_%s.json" % day)
        if not os.path.exists(path):
            raise SystemExit("找不到 %s" % path)
        return path
    files = sorted(glob.glob(os.path.join(DATA, "pool_*.json")))
    if not files:
        raise SystemExit("data/ 下没有 pool_*.json，请先运行 fetch_pool.py")
    return files[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD")
    ap.add_argument("--out", default=os.path.join(DATA, "today.js"))
    args = ap.parse_args()

    path = latest_pool(args.date)
    with open(path, encoding="utf-8") as f:
        src = json.load(f)

    copy_map = load_copy()
    pool, unmatched, no_copy = [], [], []
    for it in src["pool"]:
        act = match_activity(it["name"])
        if act is None:
            unmatched.append(it["name"])
        cp = copy_map.get(norm(it["name"]))
        if cp is None:
            cp = fallback_copy(it)
            no_copy.append(it["name"])
        pool.append({
            "n": it["name"],
            "p": it["price_yuan"],
            "c": re.sub(r"/{2,}", "/", it.get("category") or ""),
            "s": cp.get("s", ""),
            "d": cp.get("d", ""),
            "a": act,
            **({"v": it["variants"]} if it.get("variants") else {}),
        })

    payload = {
        "meta": {
            "date": src["date"],
            "city": src["anchor"]["city"],
            "anchor": src["anchor"]["keyword"],
            "storeCode": src["store"]["storeCode"],
            "storeName": src["store"]["storeName"],
            "distance": src["store"]["distance_m"],
            "generatedAt": src.get("generated_at", ""),
        },
        "cross": CROSS,
        "pool": pool,
    }

    js = "/* 自动生成 by build_today.py · 数据日期 %s · 勿手改 */\n" % payload["meta"]["date"]
    js += "window.TODAY_DATA = " + json.dumps(payload, ensure_ascii=False, indent=1) + ";\n"
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(js)

    print("写出 %s · %d 个新品 · 日期 %s" % (args.out, len(pool), payload["meta"]["date"]))
    if no_copy:
        print("以下新品没有专属文案（已用模板兜底，建议补 data/copy.json）:")
        for n in no_copy:
            print("   -", n)
    if unmatched:
        print("以下新品未匹配到活动（已标 null，可补 ACTIVITY_RULES）:")
        for n in unmatched:
            print("   -", n)


if __name__ == "__main__":
    main()
