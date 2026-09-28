# 映射基准

「底座可以被映射」这句话要有数。这里是 100 道真题，每题标了它真正考的锚点，拿来量 `tools/mapper.py`
（也就是 MCP `search_anchors`）能不能把它们排到前面。结果见 [`reports/mapping-bench.md`](../reports/mapping-bench.md)。

```
python3 bench/fetch.py                  # 把题拉到 bench/.cache/（不进 git）
python3 bench/eval.py                   # 只量字面粗召回，不花钱
python3 bench/eval.py --expand --rerank # 再量查询改写 + 精排（要 LLM_BASE / LLM_KEY / LLM_MODEL）
```

| 文件 | 是什么 |
|---|---|
| `mapping-100.jsonl` | 100 题：来源、编号、题面哈希、金标锚点、`fit`（exact / partial / none）、备注 |
| `fetch.py` | 拉题。三个来源、三种许可，为什么原文不进仓库写在文件头 |
| `pick.py` | 固定种子分层抽题。**只跑过一次**，重抽等于换考卷 |
| `eval.py` | 打分，写 `reports/mapping-bench.md` |
| `check_gold.py` | 金标指向的锚点被弃用或降档时报错（进 `npm run check`） |

## 题从哪来

| 学段 | 来源 | 许可 | 题数 |
|---|---|---|---:|
| 小学 | CMATH（小学数学应用题，1–6 年级） | CC BY 4.0 | 30 |
| 初中 | C-Eval `middle_school_*` 验证集 | CC BY-NC-SA 4.0 | 35 |
| 高中 | GAOKAO-Bench（2010–2022 高考题） | Apache 2.0 | 35 |

排除了看不到图就答不了的题，和超过 500 字、一题考一串能力的题。

## 金标是谁标的

**AI 标的**（`labeledBy: ai:claude-opus-5-5-2026-09-28`），四个标注者各标 25 题，
**标注时禁止使用 mapper 和 MCP 检索**，只能自己 grep 锚点 —— 否则就是拿被测对象去出考卷。

所以现在的命中率意思是「和一个认真的 AI 标注者比」。老师复核金标之前，不要把它当准确率对外说。

`fit: none`（21 题）是**底座的覆盖缺口**，不是映射器的错：题目考的能力在可引用锚点里找不到。
