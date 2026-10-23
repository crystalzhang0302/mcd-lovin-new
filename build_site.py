# -*- coding: utf-8 -*-
"""构建站点数据：完整新品池 x 门店分布 x 人工文案 -> data/items.js

- 新品池：取 data/pool_*.json 中最新一份（正餐时段的完整上新集）
- 门店分布：取 data/matrix_*.json 中最新一份（多门店实测）
- 文案：data/copy.json —— 关键词按名称归一化匹配，缺文案用模板兜底并在终端提示

设计取舍：正餐新品在早餐时段不上架，早间抓取会漏掉大半。因此以「完整新品池」
为主体内容，门店分布用最新实测覆盖；实测未命中的门店回退到最近一次验证过的门店，
并在数据里标 fresh=false，前端据此显示「时段校验」而非假装实时。
"""
import argparse
import glob
import json
import os
import re

DATA = "data"
# 活动规则：来自 campaign-calendar 10/22 实抓，按名称关键词匹配
ACTIVITY_RULES = [
    (["龙焰", "芝士棒", "拉丝芝士条"],
     {"t": "麦当劳联动 G-DRAGON", "x": "韩式辣酱 × 青梅 × 黄油，三件套 26.9 元起 / 芝士棒版 29.9 元", "k": "联名"}),
    (["鸡薯双全"], {"t": "韩式蘸酱上新", "x": "15.9 元起，get GD 同款花式比心", "k": "联名"}),
    (["蘸酱"], {"t": "韩式风味蘸酱上新", "x": "韩式辣椒黄油 / 烟熏芝士双酱，11.9 元起", "k": "上新"}),
    (["蓝莓"], {"t": "蓝莓爆爆珠上新", "x": "真实蓝莓原浆 × 爆爆珠，颗颗爆汁", "k": "上新"}),
    (["灰焰"], {"t": "灰焰圆筒酷爽登场", "x": "香草味 × 酷灰脆筒，灰白撞色", "k": "上新"}),
    (["心形薯饼"], {"t": "限时特惠", "x": "8 块装 9.9 元，比 5 块装还便宜", "k": "限时"}),
    (["板烧"], {"t": "板烧「更多汁」升级", "x": "腌制工艺升级，不加价换更嫩的腿肉", "k": "升级"}),
    (["奶昔"], {"t": "经典回归", "x": "下架多年后重新上架，三味可选", "k": "回归"}),
    (["柠柠", "多汁柠"], {"t": "清爽上新", "x": "美汁源联名柠檬饮，解腻首选", "k": "上新"}),
    (["扭扭薯", "相思"], {"t": "秋日限定", "x": "月下相思扭扭薯，秋季档期限定", "k": "限时"}),
    (["咖喱"], {"t": None, "x": "暂无关联活动，静默上新", "k": "静默"}),
]
CROSS = {"t": "PEACEMINUSONE 联名周边",
         "x": "任意餐品 +39.9 元换购棒球帽 / 徽章 / 丝巾，限定丝巾 10/22 首日开售"}


def norm(s):
    return re.sub(r"[\s·—–\-~〜/・“”\"'’]+", "", s or "")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def latest(pattern):
    files = sorted(glob.glob(os.path.join(DATA, pattern)))
    return files[-1] if files else None


def load_copy():
    p = os.path.join(DATA, "copy.json")
    if not os.path.exists(p):
        return {}
    return {norm(k): v for k, v in load_json(p).get("items", {}).items()}


def match_activity(name):
    for keys, act in ACTIVITY_RULES:
        if any(k in name for k in keys):
            return act
    return None


def fallback_copy(it):
    tags = [t for t in (it.get("tags") or []) if t not in ("上新", "新升级", "套餐")]
    flavor = ("风味线索是「%s」。" % tags[0]) if tags else ""
    return {"s": "初来乍到，先尝为敬",
            "d": "今天新上的一款。%s文案还没补录——在 data/copy.json 里加一条就能换成专属签文。" % flavor}


def short_name(full):
    n = full or ""
    n = n.replace("麦当劳", "", 1)
    n = re.sub(r"^(上海|北京|广州|深圳|成都|杭州|南京)", "", n)
    return n.replace("餐厅", "").replace("店", "") or full


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default=None, help="指定 pool json 路径")
    ap.add_argument("--matrix", default=None, help="指定 matrix json 路径")
    a = ap.parse_args()

    pool_path = a.pool or latest("pool_*.json")
    matrix_path = a.matrix or latest("matrix_*.json")
    if not pool_path:
        raise SystemExit("找不到 pool_*.json，请先运行 fetch_pool.py")
    pool = load_json(pool_path)["pool"]
    matrix = load_json(matrix_path) if matrix_path else {"meta": {}, "items": []}

    # 门店元信息
    store_meta = {s["code"]: s for s in (matrix.get("meta", {}).get("stores") or [])}
    # code -> 门店命中：(store, 该店productCode, 价格)
    code_hits = {}
    for it in matrix.get("items") or []:
        for st in it.get("stores") or []:
            pc = st.get("productCode")
            if pc:
                code_hits.setdefault(pc, []).append(st)
        for v in it.get("variants") or []:
            if v.get("code") in code_hits:
                pass

    copy_map = load_copy()
    items, no_copy, no_store = [], [], []
    fallback_store = None
    for meta in (matrix.get("meta", {}).get("stores") or [])[:1]:
        fallback_store = meta

    for it in pool:
        code = str(it["code"])
        cp = copy_map.get(norm(it["name"])) or fallback_copy(it)
        if norm(it["name"]) not in copy_map:
            no_copy.append(it["name"])

        hits = code_hits.get(code) or []
        stores = []
        for st in hits:
            sm = store_meta.get(st["code"], {})
            stores.append({
                "c": st["code"],
                "n": short_name(st.get("name") or sm.get("name", "")),
                "d": st.get("distance") if st.get("distance") is not None else sm.get("distance"),
                "addr": st.get("address") or sm.get("address") or "",
                "pc": st.get("productCode") or code,
                "p": st.get("price") if st.get("price") is not None else it.get("price_yuan"),
                "fresh": True,
            })
        stores.sort(key=lambda x: x["d"] if x["d"] is not None else 9999)
        if not stores:
            no_store.append(it["name"])
            if fallback_store:
                stores.append({
                    "c": fallback_store["code"],
                    "n": short_name(fallback_store["name"]),
                    "d": fallback_store.get("distance"),
                    "addr": fallback_store.get("address") or "",
                    "pc": code,
                    "p": it.get("price_yuan"),
                    "fresh": False,
                })

        items.append({
            "id": code,
            "n": it["name"],
            "p": it.get("price_yuan"),
            "c": re.sub(r"/{2,}", "/", (it.get("category") or "").replace("\n", "")).strip("/ "),
            "g": (it.get("tags") or [])[:3],
            "v": cp.get("s", ""),
            "d": cp.get("d", ""),
            "a": match_activity(it["name"]),
            "s": stores,
        })

    items.sort(key=lambda x: (-len(x["s"]), x["p"] if x["p"] is not None else 999))
    out = {
        "meta": {
            "date": __import__("datetime").date.today().isoformat(),
            "city": matrix.get("meta", {}).get("city") or "上海市",
            "anchor": matrix.get("meta", {}).get("anchor") or "人民广场",
            "poolAt": os.path.basename(pool_path).replace("pool_", "").replace(".json", ""),
            "matrixAt": matrix.get("meta", {}).get("generatedAt") if matrix_path else None,
            "generatedAt": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stores": [{"code": s["code"], "name": short_name(s["name"]),
                        "distance": s.get("distance"), "address": s.get("address")}
                       for s in (matrix.get("meta", {}).get("stores") or [])],
            "cross": CROSS,
        },
        "items": items,
    }
    os.makedirs(DATA, exist_ok=True)
    js = "window.NEW_DATA = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n"
    with open(os.path.join(DATA, "items.js"), "w", encoding="utf-8") as f:
        f.write(js)

    print("写入 data/items.js")
    print("新品 %d 个（%s 池 + %s 门店快照）" % (
        len(items), out["meta"]["poolAt"], out["meta"]["matrixAt"] or "无"))
    if no_copy:
        print("缺文案（已模板兜底）:", "、".join(no_copy))
    if no_store:
        print("无当日在架门店（回退最近验证门店）:", "、".join(no_store))
    print()
    for x in items:
        act = (x["a"] or {}).get("t") or "-"
        print("  %-2d店 ¥%-6s %-24s %s" % (len(x["s"]), x["p"], x["n"], act))


if __name__ == "__main__":
    main()
