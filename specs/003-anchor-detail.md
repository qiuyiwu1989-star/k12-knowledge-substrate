# 003: 锚点详情页

## 要什么

每条锚点一个详情页，`/anchor/<id>/`。**同一份 JSON，四个视图切页**：

| 视图 | 读者 | 主要字段 |
|---|---|---|
| 引用 | 开发者 | id / status / successor_ids / citable / api_endpoint / license_note |
| 判定 | 教师 | claim / non_examples / assessment_* / failure_modes / pass_criterion |
| 成长 | 家长 | plain_zh / unlocks / 生活中的表现举例 |
| 溯源 | 研究者 | standard_quote / source_doc+page / extraction_method / credibility / objections |

九组字段的完整定义见 `schema/anchor.schema.json`。

**三条硬规则：**

1. **空字段显示为空，注明"尚未定义"，禁止隐藏或折叠。**
   缺字段的可见性就是数据质量的可见性。允许折叠，页面会自动美化成"看起来都齐了"。
2. **`citable` 是页面顶部的红绿灯**，不可引用时必须同时显示不可引用的理由。
3. **禁止字段**：`difficulty`、`average_mastery_age`、`peer_percentile`。
   schema 里列为 forbidden，验收器 F201 拦截。这三个的缺席是设计结论，要在方法论页写明理由。

其他要点：
- 四套认知标签并列展示，页面上写明"这些是标签不是层，互不排斥"
- `is_our_assertion=true`（那 217 条）必须醒目标注 + 显示我们为什么加这一条 + 一个可单独撤销的入口
- `prerequisites` 每条显示 type / strength / failure_signature；`cross_links` 显式标注"不是先修"
- 只画局部子图（前置 1 跳 + 后继 1 跳），不放全图
- 一键异议按钮 + 异议计数公开可见
- `attached_list_items` 显示条数，不铺开（3,500 个字不展开）

## 不做什么

- 不做后端异议工作流（只落库，谁处理、怎么处理待定）
- 不撰写 `license_note` 内容（等法律意见，字段留空）
- 不批量生成 `assessment_spec`（会污染底座且不可追溯）
- 不做登录、不做学生状态展示（家长视图里"孩子当前状态"显示为"需接入档案"）

## 验收清单

- [ ] `validate.py --anchors data/anchors/*.jsonl` 退出码 0
- [ ] F201（出现禁止字段）计数为 0
- [ ] F202（citable=true 但 assessment_type 为空）计数为 0
- [ ] F203（is_our_assertion=true 但 assertion_rationale 为空）计数为 0
- [ ] 随机抽 20 个页面，人工确认：所有空字段都显示为"尚未定义"，无一被隐藏
- [ ] 反样本自测：`validate.py --anchors samples/anchors.bad.jsonl` 退出码 1
- [ ] 四视图在移动端可切换，键盘可达，focus 可见

## 状态
draft
