#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_pool.py — 抓取门店当日在售新品候选池

只用 Python 标准库。Token 读取顺序：
    1. 环境变量 MCD_MCP_TOKEN
    2. ~/.workbuddy/mcp.json 中 mcd-mcp 的 Authorization
这样仓库里永远不需要出现 Token。

用法：
    python fetch_pool.py --city 上海市 --keyword 人民广场
    python fetch_pool.py --store 1450713 --out data/pool.json
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

MCP_URL = "https://mcp.mcd.cn"
BE_TYPE_STORE = 1  # 到店自取
ORDER_TYPE_STORE = 1

# 「上新」语义标签：官方不一定只给 "上新" 两个字，还有 "韩式芝士风味酱上新""清爽上新" 等变体
NEW_TAG_KEYWORDS = ("上新", "新升级", "新吃法")

# 非食品（周边 / 玩具 / 联名物），必须在候选池里剔除
NON_FOOD_KEYWORDS = ("丝巾", "棒球帽", "帽", "徽章", "痒痒挠", "捶", "玩具", "周边", "手提袋", "杯", "摆件")

# 规格后缀，用于把同一餐品的不同规格折叠成一个「品」
SPEC_PATTERN = re.compile(r"(\d+\s*块|\d+\s*个|\d+\s*只|\d+\s*片|\d+\s*件|\d+\s*杯|大杯|中杯|小杯|大份|中份|小份)$")


def get_token():
    tok = os.environ.get("MCD_MCP_TOKEN")
    if tok:
        return tok.strip()
    cfg_path = os.path.join(os.path.expanduser("~"), ".workbuddy", "mcp.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        auth = cfg["mcpServers"]["mcd-mcp"]["headers"]["Authorization"]
        return auth.split("Bearer", 1)[-1].strip()
    except Exception:
        sys.exit(
            "未找到 MCP Token。请设置环境变量 MCD_MCP_TOKEN，"
            "或在 ~/.workbuddy/mcp.json 中配置 mcd-mcp。"
        )


def rpc(token, method, params, rid=1):
    payload = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        MCP_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + token,
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_data(env):
    """MCP 返回的 content[0].text 是「说明 + ## Original Response + JSON」的混合文本，
    需要用 raw_decode 从第一个 '{' 开始精确解析，不能简单正则截取。"""
    text = "".join(c.get("text", "") for c in env["result"]["content"])
    idx = text.find("## Original Response")
    blob = text[idx:] if idx >= 0 else text
    start = blob.find("{")
    if start < 0:
        raise ValueError("返回中未找到 JSON：\n" + text[:400])
    obj, _ = json.JSONDecoder().raw_decode(blob[start:])
    if obj.get("code") not in (200, None):
        raise ValueError(f'{obj.get("code")} {obj.get("message")}')
    return obj.get("data")


def call(token, name, args, rid=1):
    return extract_data(rpc(token, "tools/call", {"name": name, "arguments": args}, rid))


def pick_store(token, city, keyword, store_code=None):
    if store_code:
        return {"storeCode": store_code, "storeName": "(手动指定)", "distance": None}
    data = call(token, "query-nearby-stores",
                {"beType": BE_TYPE_STORE, "searchType": 2, "city": city, "keyword": keyword}, 100)
    stores = data or []
    if not stores:
        sys.exit("未查询到门店，请更换 city/keyword")
    # 按距离升序，取最近且在营业的
    stores.sort(key=lambda s: s.get("distance") or 1 << 30)
    open_stores = [s for s in stores if s.get("businessStatus")]
    return (open_stores or stores)[0]


def fold_specs(items):
    """同一餐品的不同规格折叠为一个「品」，抽中后再选规格。"""
    groups = {}
    for it in items:
        base = SPEC_PATTERN.sub("", it["name"]).strip() or it["name"]
        groups.setdefault(base, []).append(it)
    folded = []
    for base, members in groups.items():
        main = dict(members[0])
        main["name"] = base if len(members) > 1 else members[0]["name"]
        if len(members) > 1:
            main["variants"] = [m["name"] for m in members]
        folded.append(main)
    return folded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="上海市")
    ap.add_argument("--keyword", default="人民广场")
    ap.add_argument("--store", default=None, help="直接指定 storeCode，跳过门店搜索")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    token = get_token()
    stores = rpc(token, "initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "mcd-lovin-new", "version": "0.1"},
    }, 0)

    store = pick_store(token, args.city, args.keyword, args.store)
    sc = store["storeCode"]
    print(f"门店：{store['storeName']}  storeCode={sc}  距离={store.get('distance')}m")

    meals = call(token, "query-meals",
                 {"storeCode": sc, "orderType": ORDER_TYPE_STORE, "beType": BE_TYPE_STORE}, 101)
    cats = meals.get("categories") or []
    all_meals = []
    for c in cats:
        for m in (c.get("meals") or []):
            m = dict(m)
            m["category"] = re.sub(r"/{2,}", "/", (c.get("name") or "").replace("
", ""))
            all_meals.append(m)
    print(f"菜单：{len(cats)} 个分类 / {len(all_meals)} 个在售餐品")

    # 先按 tags 粗筛「上新」
    tagged = [m for m in all_meals
              if any(k in t for t in (m.get("tags") or []) for k in NEW_TAG_KEYWORDS)]
    print(f'带「上新」语义标签：{len(tagged)} 个')

    # 菜单里没有名称和价格，必须逐个核价获取（calculate-price 同时返回 productName）
    pool, dropped = [], []
    for i, m in enumerate(tagged, 1):
        try:
            price = call(token, "calculate-price", {
                "storeCode": sc, "orderType": ORDER_TYPE_STORE, "beType": BE_TYPE_STORE,
                "items": [{"productCode": m["code"], "quantity": 1}],
            }, 200 + i)
            name = (price.get("productList") or [{}])[0].get("productName") or m["code"]
            fen = price.get("price")
        except Exception as e:
            print(f"  ! {m['code']} 核价失败：{e}")
            continue
        item = {
            "code": m["code"],
            "name": name,
            "price_fen": fen,
            "price_yuan": round((fen or 0) / 100, 2),
            "category": m["category"],
            "tags": m.get("tags") or [],
        }
        if any(k in name for k in NON_FOOD_KEYWORDS):
            dropped.append(item)
        else:
            pool.append(item)
        print(f'  [{i}/{len(tagged)}] {name}  ¥{item["price_yuan"]}')

    folded = fold_specs(pool)
    result = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "anchor": {"city": args.city, "keyword": args.keyword},
        "store": {
            "storeCode": sc,
            "storeName": store.get("storeName"),
            "address": store.get("address"),
            "distance_m": store.get("distance"),
            "businessStartTime": store.get("businessStartTime"),
            "businessEndTime": store.get("businessEndTime"),
        },
        "stats": {
            "menu_total": len(all_meals),
            "tagged_new": len(tagged),
            "non_food_dropped": len(dropped),
            "food_new": len(pool),
            "after_fold": len(folded),
        },
        "dropped_non_food": [d["name"] for d in dropped],
        "pool": folded,
    }

    out = args.out or os.path.join("data", f'pool_{result["date"]}.json')
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n候选池：{len(pool)} 个食品新品 → 折叠规格后 {len(folded)} 个")
    print(f"剔除周边：{result['dropped_non_food']}")
    print(f"已保存：{out}")


if __name__ == "__main__":
    main()
