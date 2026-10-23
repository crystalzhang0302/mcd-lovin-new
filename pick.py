#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pick.py — 新品盲盒：抽出你今天的新品

机制：当日签序由 seed("日期|门店|用户") 洗牌生成，同一天同一人结果固定可复现。
重抽沿签序推进（无放回），最多 N 抽必中。全程离线，只读 data/pool_*.json。

用法：
    python pick.py                    # 抽第 1 抽（今日新品签）
    python pick.py --draw 3           # 抽到第 3 抽
    python pick.py --all              # 直接看完整签序
    python pick.py --html out/x.html  # 生成可截图的签卡
"""

import argparse
import glob
import json
import math
import os
import random
import re
from datetime import datetime

# 签文库：命中顺序即优先级，靠前的更具体
SIGN_TABLE = [
    (("龙焰", "辣"),            "火", "火气正旺，辣得其所", "宜痛快", "忌逞强"),
    (("芝士", "拉丝"),          "丝", "今日宜拉长，忌硬碰硬", "宜热食", "忌放凉"),
    (("蓝莓", "莓"),            "莓", "爆珠一响，好事成双", "宜惊喜", "忌将就"),
    (("咖喱",),                 "香", "香气引路，识味者来", "宜远行", "忌守旧"),
    (("奶昔", "回归"),          "旧", "旧味重逢，故人归位", "宜怀旧", "忌恋战"),
    (("扭扭薯", "薯饼", "薯"),  "金", "金黄满手，所愿皆圆", "宜分享", "忌独食"),
    (("柠",),                   "清", "酸里回甘，苦尽自有甜", "宜清爽", "忌上头"),
    (("心形", "比心"),          "心", "心之所向，一咬即中", "宜表白", "忌犹豫"),
    (("麦旋风", "旋"),          "旋", "旋开一步，天地自转", "宜破局", "忌原地"),
    (("圆筒",),                 "圆", "小小的圆，也是圆", "宜知足", "忌贪多"),
    (("炸鸡", "脆汁"),          "酥", "外壳够脆，心事不碎", "宜解压", "忌内耗"),
    (("三件套", "全盒", "四宫格", "盘"), "满", "满盘皆喜，一人也盛", "宜结伴", "忌剩下"),
]
SIGN_DEFAULT = ("新", "新到即缘，尝过便知", "宜尝鲜", "忌观望")


def make_sign(item):
    haystack = item["name"] + " " + " ".join(item.get("tags") or [])
    for keys, word, text, good, bad in SIGN_TABLE:
        if any(k in haystack for k in keys):
            return {"word": word, "text": text, "good": good, "bad": bad}
    return {"word": SIGN_DEFAULT[0], "text": SIGN_DEFAULT[1],
            "good": SIGN_DEFAULT[2], "bad": SIGN_DEFAULT[3]}


def rank(k, n):
    """按命中位置给运气评级。位置越靠前越幸运。用分位而非绝对次数，随池子大小自适应。"""
    pct = k / n
    if k == 1:
        return "欧皇", pct
    if k <= max(3, math.ceil(n * 0.18)):
        return "锦鲤", pct
    if k <= math.ceil(n * 0.5):
        return "平常心", pct
    if k <= math.ceil(n * 0.8):
        return "手气略背", pct
    return "非酋", pct


def load_pool(date=None, path=None):
    if path:
        files = [path]
    else:
        pattern = f"data/pool_{date}.json" if date else "data/pool_*.json"
        files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit("未找到候选池数据，请先运行 fetch_pool.py")
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def build_order(pool, seed, weights=None):
    """洗牌生成当日签序。加权抽样通过重复放入实现，仍保持可复现。"""
    items = pool[:]
    if weights:
        bag = []
        for it in items:
            w = weights(it)
            bag.extend([it] * max(1, int(round(w))))
        items = bag
    rng = random.Random(seed)
    rng.shuffle(items)
    # 加权后去重，保持首次出现顺序
    seen, ordered = set(), []
    for it in items:
        if it["code"] in seen:
            continue
        seen.add(it["code"])
        ordered.append(it)
    return ordered


def html_card(ctx, out_path):
    it, sign, rank_name, pct = ctx["item"], ctx["sign"], ctx["rank"], ctx["pct"]
    variants = it.get("variants")
    variant_html = ""
    if variants:
        variant_html = f'<div class="variant">两个规格：{" / ".join(variants)}（抽中后可自选）</div>'
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>今日新品签 · {it['name']}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#FFF6E5;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
       display:flex;justify-content:center;padding:32px 16px;color:#2B1B0E}}
  .card{{width:420px;background:#fff;border-radius:22px;overflow:hidden;
        box-shadow:0 18px 44px rgba(120,70,10,.18);position:relative}}
  .top{{background:linear-gradient(135deg,#DB0007,#8E000A);color:#FFD24A;padding:22px 24px 20px}}
  .top .kicker{{font-size:12px;letter-spacing:3px;opacity:.85;margin-bottom:10px}}
  .top h1{{font-size:26px;line-height:1.2;color:#fff;letter-spacing:1px}}
  .top .store{{margin-top:12px;font-size:12.5px;color:#FFE9B0;opacity:.95}}
  .badge{{position:absolute;right:20px;top:20px;background:#FFC72C;color:#7A1200;
         font-weight:800;font-size:13px;padding:7px 13px;border-radius:999px;
         box-shadow:0 6px 14px rgba(0,0,0,.18)}}
  .body{{padding:24px}}
  .signword{{font-size:56px;font-weight:900;color:#DB0007;line-height:1;
            letter-spacing:2px;float:left;margin:2px 16px 6px 0}}
  .signtext{{font-size:17px;font-weight:600;line-height:1.65;padding-top:6px}}
  .clear{{clear:both}}
  .divider{{height:1px;background:linear-gradient(90deg,#FFD24A,transparent);margin:20px 0 18px}}
  .prize{{font-size:15px;line-height:1.9}}
  .prize .name{{font-size:20px;font-weight:800;letter-spacing:.5px}}
  .price{{color:#DB0007;font-weight:800;font-size:26px;letter-spacing:-.5px}}
  .price small{{font-size:13px;font-weight:600;color:#8A6A3E;margin-left:6px}}
  .variant{{margin-top:8px;font-size:12.5px;color:#8A6A3E;background:#FFF8E7;
           padding:8px 12px;border-radius:9px}}
  .meta{{display:flex;gap:10px;margin-top:18px}}
  .meta div{{flex:1;background:#FFF8E7;border-radius:12px;padding:11px 12px;text-align:center}}
  .meta .v{{font-size:19px;font-weight:800;color:#DB0007}}
  .meta .l{{font-size:11px;color:#8A6A3E;margin-top:3px;letter-spacing:.5px}}
  .fortune{{margin-top:16px;font-size:13.5px;line-height:1.9;color:#5A4225;
           background:#FFFDF7;border-left:3px solid #FFC72C;padding:12px 14px;border-radius:0 8px 8px 0}}
  .foot{{padding:14px 24px 20px;font-size:11px;line-height:1.7;color:#9C8B72}}
</style></head><body>
<div class="card">
  <div class="top">
    <div class="badge">{rank_name}</div>
    <div class="kicker">今 日 新 品 签</div>
    <h1>我就爱吃新</h1>
    <div class="store">{ctx['date']} · {ctx['store_name']} · {ctx['distance']}m</div>
  </div>
  <div class="body">
    <div class="signword">{sign['word']}</div>
    <div class="signtext">{sign['text']}</div>
    <div class="clear"></div>
    <div class="divider"></div>
    <div class="prize">
      <div class="name">{it['name']}</div>
      <div><span class="price">¥{it['price_yuan']:.1f}</span><small>{it['category']}</small></div>
      {variant_html}
    </div>
    <div class="meta">
      <div><div class="v">第 {ctx['k']} 抽</div><div class="l">命中位置</div></div>
      <div><div class="v">前 {pct*100:.0f}%</div><div class="l">运气分位</div></div>
      <div><div class="v">{ctx['remain']}</div><div class="l">剩余未抽</div></div>
    </div>
    <div class="fortune">{sign['good']} · {sign['bad']}<br>共 {ctx['n']} 个在售新品，今天这一口，算是定了。</div>
  </div>
  <div class="foot">
    本工具为娱乐性新品推荐，随机结果不构成任何抽奖或兑奖，与麦当劳官方积分抽奖无关。<br>
    餐品、价格与供应状态以麦当劳官方渠道实时结果为准。非麦当劳官方产品。
  </div>
</div></body></html>"""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draw", type=int, default=1, help="抽到第几抽")
    ap.add_argument("--seed", default=None, help="覆盖默认 seed")
    ap.add_argument("--user", default="guest", help="用户标识，参与 seed 计算")
    ap.add_argument("--date", default=None, help="指定日期数据 yyyy-mm-dd")
    ap.add_argument("--data", default=None, help="直接指定 pool json 路径")
    ap.add_argument("--all", action="store_true", help="打印完整签序")
    ap.add_argument("--html", default=None, help="输出签卡 HTML 路径")
    args = ap.parse_args()

    data = load_pool(args.date, args.data)
    pool = data["pool"]
    n = len(pool)
    store = data["store"]
    date = data["date"]
    seed = args.seed or f"{date}|{store['storeCode']}|{args.user}"
    order = build_order(pool, seed)

    if args.all:
        print(f"门店：{store['storeName']}（{store.get('distance_m')}m）")
        print(f"日期：{date}　候选池：{n} 个　seed：{seed}\n")
        print("完整签序：")
        for i, it in enumerate(order, 1):
            mark = " ←" if i == 1 else ""
            print(f"  第{i:2d}抽  {it['name']:<28} ¥{it['price_yuan']:>5.1f}{mark}")
        return

    k = max(1, min(args.draw, n))
    it = order[k - 1]
    it["category"] = re.sub(r"/{2,}", "/", (it.get("category") or "").replace("\n", ""))
    sign = make_sign(it)
    rank_name, pct = rank(k, n)

    ctx = {
        "item": it, "sign": sign, "rank": rank_name, "pct": pct,
        "k": k, "n": n, "remain": n - k, "date": date,
        "store_name": store["storeName"], "distance": store.get("distance_m"),
    }

    print(f"\n{'=' * 46}")
    print(f"  今 日 新 品 签   {rank_name}")
    print(f"{'=' * 46}")
    print(f"  「{sign['word']}」{sign['text']}")
    print(f"{'-' * 46}")
    print(f"  {it['name']}")
    print(f"  ¥{it['price_yuan']:.1f}   {it['category']}")
    if it.get("variants"):
        print(f"  规格：{' / '.join(it['variants'])}（自选）")
    print(f"{'-' * 46}")
    print(f"  第 {k} 抽命中 · 全池 {n} 个 · 剩余 {n - k} 个未抽")
    print(f"  {sign['good']} · {sign['bad']}")
    print(f"  店：{store['storeName']}（{store.get('distance_m')}m）")
    print(f"{'=' * 46}\n")

    if args.html:
        p = html_card(ctx, args.html)
        print(f"签卡已生成：{p}")


if __name__ == "__main__":
    main()
