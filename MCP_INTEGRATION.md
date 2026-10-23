# MCP_INTEGRATION.md —— 麦当劳 MCP 接入说明

本项目通过麦当劳官方 MCP Server（`https://mcp.mcd.cn`，Streamable HTTP，当前版本 v1.0.x）完成全部真实数据获取。本文说明实际使用的 Server / Tool、调用流程与业务价值。

## 一、接入方式

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer YOUR_MCP_TOKEN" }
    }
  }
}
```

脚本侧读取 Token 的顺序：环境变量 `MCD_MCP_TOKEN` → 本地 `~/.workbuddy/mcp.json`。**仓库内不存放任何 Token**。

## 二、使用的工具清单

| Tool | 用途 | 调用位置 |
|---|---|---|
| `query-nearby-stores` | 按「城市 + 关键词」查附近门店（含 `distance`、`businessStatus`、`storeCode`） | `fetch_pool.py` / `fetch_matrix.py` |
| `query-meals` | 拉取门店完整菜单，按 `tags` 中的「上新 / 新升级 / 新吃法 / 回归」标记筛选候选新品 | 同上 |
| `calculate-price` | 对候选新品逐个单件核价，返回 `productList[].productName` 与 `subtotal`（分） | 同上 |
| `campaign-calendar` | 拉取当月官方活动日历，建立「新品 → 连带活动」（联名 / 限时 / 回归）映射 | `build_today.py` |

> 服务端实际开放 35 个工具，本项目按最小必要原则使用其中 4 个。

## 三、调用流程

```text
① query-nearby-stores(city, keyword)
      → 附近门店列表（取前 5 家，过滤 businessStatus）

② 对每家门店：query-meals(storeCode, orderType=1, beType=1)
      → categories[].meals[].{code, tags}
      → tags 命中「上新/新升级/新吃法/回归」且非周边（剔除丝巾/帽子/玩具等）

③ 对每个候选 code：calculate-price(storeCode, items=[{productCode, quantity:1}])
      → 名称 + 实测价格（分 → 元）
      —— 一次调用同时拿名称和价格，省去逐个 query-meal-detail

④ campaign-calendar()
      → 当月活动日历 → 关键词规则匹配出「新品 → 连带活动」
      → 联名活动（如 G-DRAGON × 龙焰系列）标记为高价值卖点

⑤ 本地合并：候选池 × 门店矩阵 × 文案资产 → data/items.js → H5 货架
```

### 采样纪律（工程要点）

菜单随时段变化（实测同一门店 21:52 为 134 品、23:03 为 126 品，早餐时段正餐新品不上架）。因此：

- 抓取脚本记录数据时间戳，页面展示数据日期；
- 未经当餐时段实测的「门店 × 新品」组合标注 `fresh=false`，前端显示「时段校验」，不冒充实测。

## 四、实测验证记录

| 验证项 | 结果 |
|---|---|
| 上新信号 | 官方 `tags` 提供结构化「上新」标记，单店 122 品中 20 个命中 |
| 周边污染 | 「上新」标签混有非食品（丝巾 / 棒球帽 / 按摩捶），已做品类过滤 |
| 区域差异 | 沪 / 蓉 / 穗三城实测：三城共有 16 品，上海独有 6 品（含奶昔回归），成都独有 6 品（含三文鱼月堡）——约 70% 全国同步 + 30% 门店/区域差异 |
| 价格精度 | `calculate-price` 单件核价精确到分，与门店实售价一致 |
| 限流 | 单 Token 600 次/分钟；本项目单次全量抓取约 30 次调用，余量充足 |

## 五、业务价值

1. **把官方没整合的信息整合了**：「上新」标记埋在菜单接口里、活动散在日历里、价格要单独核价、门店各有差异——四个来源没有任何一个官方页面同时呈现。
2. **发现并诚实处理了官方数据缺口**：营养接口是静态清单不覆盖新品、无下架时间字段——本项目选择不展示这些维度，而不是编造数据。
3. **区域差异即信息差**：「你这家店有、别家没有」是货架的核心卖点，这一结论本身来自 MCP 三城实测。
4. **签能落地**：每个新品卡片最终都能走到「真实可执行的 `create-order` 凭证」， discovery → action 闭环，抽中即可吃。
