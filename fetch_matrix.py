# -*- coding: utf-8 -*-
"""抓取「新品 x 门店」矩阵：同一批新品在上海人民广场周边 5 家门店的分布与价格。

输出 data/matrix_<date>.json
"""
import argparse
import json
import os
import re
import subprocess
import sys

TOKEN_KEYS = ("MCD_MCP_TOKEN",)
MCP_URL = "https://mcp.mcd.cn"
NEW_KW = ("上新", "新升级", "新吃法", "回归", "新上市")
# 非食品关键词：上新标签里混着周边、玩具，必须剔除
NON_FOOD = ("丝巾", "帽", "按摩", "痒", "玩具", "徽章", "摆件", "玩偶", "手办",
            "公仔", "抱枕", "杯套", "贴", "挂件", "袋", "摆台", "钥匙扣",
            "单肩包", "背包", "挎包", "手包", "包袋", "耳机包")


def get_token():
    for k in TOKEN_KEYS:
        v = os.environ.get(k)
        if v:
            return v.strip()
    p = os.path.expanduser("~/.workbuddy/mcp.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
        for srv in (cfg.get("mcpServers") or {}).values():
            h = (srv.get("headers") or {}).get("Authorization")
            if h:
                return h.replace("Bearer", "").strip()
    sys.exit("未找到 MCD_MCP_TOKEN，请设置环境变量后重试")


def rpc(token, name, args, rid=1):
    body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                       "params": {"name": name, "arguments": args}}, ensure_ascii=False)
    cmd = ["curl", "-sS", "--max-time", "45", "-X", "POST", MCP_URL,
           "-H", "Content-Type: application/json",
           "-H", "Accept: application/json, text/event-stream",
           "-H", "Authorization: Bearer " + token,
           "-d", body]
    out = subprocess.run(cmd, capture_output=True)
    txt = out.stdout.decode("utf-8", "ignore")
    try:
        env = json.loads(txt)
    except Exception:
        return None
    if "error" in env:
        return None
    content = (env.get("result") or {}).get("content") or []
    t = "".join(x.get("text") or "" for x in content)
    i = t.find("## Original Response")
    blob = t[i:] if i > 0 else t
    m = re.search(r"\{[\s\S]*\}", blob)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def norm_name(s):
    return re.sub(r"[\s\u3000·•・—\-－_“”\"'’]", "", s or "")


def is_new(tags):
    return any(any(k in (tg or "") for k in NEW_KW) for tg in (tags or []))


def clean_cat(s):
    return re.sub(r"/{2,}", "/", (s or "").replace("\n", "")).strip("/ ")


def spec_group(name):
    """把「心形薯饼8块 / 心形薯饼5块」折叠成同一品"""
    m = re.match(r"^(.+?)[（(]?(\d+)\s*(块|个|件|只|杯)装?[)）]?$", name)
    return m.group(1) if m else name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="上海市")
    ap.add_argument("--keyword", default="人民广场")
    ap.add_argument("--limit", type=int, default=5, help="最多取几家门店")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    token = get_token()
    print("[1/4] 查询门店 ...")
    st = rpc(token, "query-nearby-stores",
             {"beType": 1, "searchType": 2, "city": a.city, "keyword": a.keyword})
    stores = (st or {}).get("data") or []
    stores = [s for s in stores if s.get("businessStatus")][: a.limit]
    if not stores:
        sys.exit("没有营业中的门店")
    for s in stores:
        print("   ", s["storeCode"], s["storeName"], s.get("distance"), "m")

    print("[2/4] 逐店拉菜单 ...")
    per_store = {}
    all_codes = {}
    for s in stores:
        code = s["storeCode"]
        o = rpc(token, "query-meals", {"storeCode": code, "orderType": 1, "beType": 1})
        cats = ((o or {}).get("data") or {}).get("categories") or []
        meals = [(clean_cat(c.get("name")), m) for c in cats for m in (c.get("meals") or [])]
        news = [(cn, m) for cn, m in meals if is_new(m.get("tags"))]
        per_store[code] = {"cats": len(cats), "total": len(meals), "news": news}
        for cn, m in news:
            all_codes.setdefault(m["code"], {"category": cn, "tags": m.get("tags") or []})
        print("    %s: %d 分类 / %d 品 / 上新 %d" % (code, len(cats), len(meals), len(news)))

    print("[3/4] 核价 + 取名称（%d 个候选 code）..." % len(all_codes))
    detail = {}
    for i, (code, meta) in enumerate(sorted(all_codes.items()), 1):
        o = rpc(token, "calculate-price", {
            "storeCode": stores[0]["storeCode"], "orderType": 1, "beType": 1,
            "items": [{"productCode": code, "quantity": 1}]}, rid=100 + i)
        name, price = None, None
        d = (o or {}).get("data") or {}
        plist = d.get("productList") or []
        if plist:
            it = plist[0]
            name = it.get("productName") or it.get("name")
            cents = it.get("subtotal") if it.get("subtotal") is not None else it.get("originalSubtotal")
            if isinstance(cents, (int, float)):
                price = round(cents / 100.0, 2)
        if name is None:
            od = rpc(token, "query-meal-detail", {"storeCode": stores[0]["storeCode"],
                                                  "orderType": 1, "beType": 1, "code": code}, rid=900 + i)
            name = ((od or {}).get("data") or {}).get("name")
        if not name:
            continue
        detail[code] = {"name": name, "price": price, "tags": meta["tags"], "category": meta["category"]}
        print("    %-3d %s  ¥%s" % (i, name, price))

    print("[4/4] 汇总 ...")
    # 食品过滤
    foods = {c: v for c, v in detail.items() if not any(k in v["name"] for k in NON_FOOD)}
    dropped = [v["name"] for c, v in detail.items() if c not in foods]
    # 折叠规格
    groups = {}
    for code, v in foods.items():
        key = norm_name(spec_group(v["name"]))
        groups.setdefault(key, []).append((code, v))

    items = []
    for key, lst in groups.items():
        lst.sort(key=lambda x: (x[1]["price"] is None, x[1]["price"] or 0))
        head = lst[0][1]
        price = head["price"]
        price_lo = min([v["price"] for _, v in lst if v["price"] is not None], default=None)
        price_hi = max([v["price"] for _, v in lst if v["price"] is not None], default=None)
        stores_have = []
        for s in stores:
            codes_here = {m["code"] for _, m in per_store[s["storeCode"]]["news"]}
            hit = [c for c, _ in lst if c in codes_here]
            if hit:
                stores_have.append({
                    "code": s["storeCode"], "name": s["storeName"],
                    "distance": s.get("distance"), "address": s.get("address"),
                    "productCode": hit[0],
                    "price": next((v["price"] for c, v in lst if c == hit[0]), price),
                })
        items.append({
            "name": head["name"],
            "price": price,
            "priceRange": [price_lo, price_hi] if price_lo != price_hi else None,
            "category": head["category"],
            "tags": head["tags"],
            "variants": [{"name": v["name"], "code": c, "price": v["price"]} for c, v in lst] if len(lst) > 1 else None,
            "stores": stores_have,
            "storeCount": len(stores_have),
        })

    items.sort(key=lambda x: (-x["storeCount"], x["price"] if x["price"] is not None else 999))
    out = {
        "meta": {
            "date": __import__("datetime").date.today().isoformat(),
            "city": a.city, "anchor": a.keyword,
            "generatedAt": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stores": [{"code": s["storeCode"], "name": s["storeName"],
                        "distance": s.get("distance"), "address": s.get("address")} for s in stores],
        },
        "stats": {"raw_new": len(detail), "dropped_nonfood": dropped, "items": len(items)},
        "items": items,
    }
    path = a.out or ("data/matrix_%s.json" % out["meta"]["date"])
    os.makedirs("data", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n写入", path)
    print("原上新 %d 条 → 剔除非食品 %d → 折叠规格后 %d 个新品" % (len(detail), len(dropped), len(items)))
    if dropped:
        print("已剔除：", "、".join(dropped))
    print("\n--- 分布（按覆盖门店数）---")
    for x in items:
        print("  %-2d店  ¥%-6s %s" % (x["storeCount"], x["price"], x["name"]))


if __name__ == "__main__":
    main()
