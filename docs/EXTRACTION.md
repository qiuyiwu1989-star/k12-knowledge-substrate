# 抽取流水线

官方课标 PDF **全部是 150 DPI 扫描图，零文字层**（1,594 页实测）。
所以入口只能是图像识读。这条流水线的全部设计目标是：**尽可能少地消耗老师的时间**。

```
课标 PDF（扫描图，1594 页）
   │
   ├─ Pass A  scan_standards.py   全页结构分类（110 DPI，1 次/页）
   │            → tools/out/page-index.jsonl
   │            圈定含【学业要求】的页，把 Pass B 的范围砍掉 ~90%
   │
   ├─ Pass B  extract_xueye.py    逐字转写【学业要求】（150 DPI，3 次投票）
   │            → tools/out/xueye-raw.jsonl
   │
   ├─ 切分    to_candidates.py    机械切分 + 过可判定性闸
   │            → tools/out/anchor-candidates.jsonl   （llm-proposed）
   │            → tools/out/candidates-rejected.jsonl （附拒绝理由）
   │
   └─ 复核    学科主编             llm-proposed → expert-confirmed
                → anchors/<学科>/<学段>.jsonl
```

附录类（字表、篇目）走另一条更短的线：`extract_pages.py` → `to_lists.py` → `lists/`。

## 铁律一：只转写，不判断

**VLM 绝不能一步出锚点。** 转写和切分必须是两道独立工序。

混在一起做，转写错误（看错字）和判断错误（切错能力边界）就分不开了——
出问题你不知道该修 prompt 还是修切分规则，也没法定位是哪一页出的错。

所以 Pass B 的产出是**忠实逐字转写**，`to_candidates.py` 才做切分，
而切分是纯机械规则（分号断句 + 砍口号尾巴），不调模型。

## 铁律二：过滤器只有一份实现

抽取流水线是 Python，可判定性闸门是 JS（`scripts/lib/decidability.mjs`）。
Python 侧**一律 shell 出来调 `scripts/decide.mjs`**，绝不重写一份。

两份实现必然漂移，那时会成批出现「入库时通过、CI 校验时被拒」的记录，
而且没人说得清哪一份才对。

## QA 分两类，成本差一个数量级

| 类型 | 内容 | 校验方式 | 人工成本 |
|---|---|---|---|
| **自验证** | 字表、篇目（**有官方连号**） | 抽完检查 1..N 无缺号无重号 → 100% 机械可验 | **0** |
| **无自验证** | 学业要求（散文，无连号） | N 次投票逐句比对，不一致的整句进复核队列 | 只核分歧 |

实测（语文附录 43 页，5 次投票）：

- 常用字表 3,500 字：编号 1–2500 / 1–1000 **全部无缺号**，3489/3500 全票一致
- 背诵篇目 135 篇：两个序列**无缺号**
- 基本字表 300 字：**无连号 → 只抽到 299，5 次跑全部一致**（稳定漏读，非随机误差）→ 进复核队列

**有编号和没编号的差别是决定性的。** 没编号的表连"少了一个"都发现不了，只能靠人。

## 实测的模型坑（mimo-v2.5，2026-08）

| 坑 | 表现 | 对策 |
|---|---|---|
| `mimo-v2.5-pro` 无视觉 | `404 No endpoints found that support image input` | 视觉只能用 `mimo-v2.5` |
| `reasoning_effort:"none"` 失效 | 直接 400 Bad Request（曾经可用） | 用 `thinking:{"type":"disabled"}` |
| `max_tokens` 陷阱 | 不关 thinking 时 reasoning 吃光配额，`content` 返回空串 | 用 `max_completion_tokens` **且**同时关 thinking |
| 关了 thinking 反而更啰嗦 | 视觉任务把思考写进 `content`（"用户希望我识别…"） | prompt 末句硬约束：「不解释不总结，第一个字符就是第一个编号」 |
| **按行读，不按列读** | 多栏表格的分组标题归属全错（实测 p76 证实） | 无编号表格不要落分组元数据，宁可空着 |
| 视觉并发天花板远低于文本 | `/v1` 约 24、`/anthropic` 约 16，超了 429 | 双端点轮询（两个独立限流池），合计 ~30 |
| 429 风暴 | 固定退避会被限流风暴烧光重试配额 | 退避 + 抖动 + 8 次重试；**429 不算任务级失败** |

## 缓存与续跑

每页每次调用的原始响应按 `sha256(图像 + prompt + 跑次)` 落盘：
`tools/.cache/`、`tools/.cache-scan/`、`tools/.cache-xueye/`。

改 prompt 会自然失效重跑，不改就零成本重跑。中断随时可续，不会重复烧 token。
