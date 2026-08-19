# 004: 课标对账单渲染器

## 要什么

输入一份创作记录 JSONL，输出一页 HTML 对账单。样张见 `samples/duizhangdan-sample.html`。

**三档状态，边界不可模糊：**

| 状态 | 含义 | 谁给 |
|---|---|---|
| `touched` 触达 | 创作过程中用到了 | 自动 |
| `evidenced` 有表现 | 留下了可核对的具体行为 | 自动 + 人工填证据 |
| `judged` 已判定 | 够格写进档案（L3） | **仅教师签字后**，本期恒为 0 |

**第四个状态 `avoided`（回避）是确定性计算出来的，不是模型判的：**

```
avoided(X) := X.stage == 当前学段
           && X.course_type == 必修
           && X 未出现在本次创作的 touched 集合
           && X 的全部硬前置（type in {component, semantic}, strength=hard）
              均在本次创作中达到 evidenced
```

这一栏是全单最有价值的部分——它区分"不会"和"能会但没做"，
而且**只有拥有前置图的人才算得出来**。

## 不做什么

- **不实现创作过程 → 锚点的自动 mapper。** 输入是人工或半自动填好的 JSONL。
  不要为了让对账单跑起来而造一个"看起来能用"的假 mapper（见 HANDOFF 缺口 1）。
- 不输出掌握度百分比、不输出分数、不输出任何横向比较。
- 不做学生身份信息，输入里只有学生代号。

## 实现约束

- 渲染器纯静态，输入 JSONL + 锚点数据，输出单文件 HTML（可打印）
- 课标出处与页码从锚点数据读取，**不由渲染器生成**
- "已判定 0"必须显式渲染为 0 并配文字说明，不可因为是 0 就省略

## 输入契约

```jsonc
{
  "student_ref": "S-0417",          // 代号，非真实身份
  "stage": "G6",
  "work_title": "班级图书借阅小程序",
  "sessions": 4,
  "items": [
    {
      "anchor_id": "A-7f3c91",
      "status": "touched|evidenced",
      "evidence": "为「逾期提醒」写了遍历借阅记录的循环，内含日期分支判断",
      "evidence_source": "code_diff|transcript|teacher_note",
      "by": "student|ai|unclear"   // 留字段，本期允许 unclear
    }
  ]
}
```

`by` 字段本期允许全为 `unclear`，但**字段必须存在**——它是下一期 mapper 的核心难题
（区分学生做的和 AI 做的），现在留好位置。

## 验收清单

- [ ] `python3 tools/render_duizhang.py samples/work.json > out.html` 成功产出
- [ ] "已判定"计数在无签字数据时渲染为 0，且带说明文字
- [ ] `avoided` 计算在一个构造用例上正确：前置全 evidenced + 自身未 touched + 必修 → 命中
- [ ] 反用例：前置只有一条 evidenced → 不命中 avoided
- [ ] 输出 HTML 不含任何百分比、分数、排名字样（grep 检查）
- [ ] 打印样式可用（A4，签字栏在页内）

## 状态
draft
