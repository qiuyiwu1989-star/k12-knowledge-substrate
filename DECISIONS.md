# Decisions

追加式记录，永不删除，只标记废弃。
格式：`- YYYY-MM-DD: <决策>。理由：<为什么>。备选：<被放弃的选项及原因>。Confidence.`

## 2026-08-20 交接包（邱懿武 → Claude Code）带来的决策

- 2026-08-20: 能力层（潜变量估计、能力雷达图、掌握度百分比）本期不做。理由：认知诊断模型（Q 矩阵 / IRT）的前提是存在大规模真实作答数据，本项目 L3 档案层为空、一条证据都没有，前提不成立。备选：先上一个简化能力雷达图 —— 会产出无数据支撑的数字，一旦印出就会被当事实引用。Confidence: high.
- 2026-08-20: 先修边分四类 —— component / instrument / semantic / convention。理由：「A 必须排在 B 之前」混装了四种关系，其中 convention 是文档结构混入。备选：只分 hard/soft 两档 —— 实测库里 3,066 soft / 3 hard，这个字段等于没用过，不足以支撑「可绕过」推理。Confidence: high.
- 2026-08-20: 边的判据定为「能否描述出不具备前置时的具体失败表现」。理由：与锚点判据「能否回答会/不会」同构，两者都要求落到可观测。Confidence: high.
- 2026-08-20: 重标管线两段式 —— 先让模型写 failureSignature（不告知有分类任务），再独立调用按 signature 分类。理由：一次性问「这是什么类型」，模型会先选标签再倒推理由，产出无法证伪的标签。这和 `tools/adversarial_verify.py` 「换的是信息流不是措辞」是同一个道理，在本项目已被证明有效。Confidence: medium→high.
- 2026-08-20: 禁止 difficulty / averageMasteryAge / peerPercentile 三字段，写进 schema 的 `forbidden` 关键字由验收器执行。理由：前两个在无真实作答数据前是编的，第三个是横向比较的入口，进来了拿不掉。Confidence: high.
- 2026-08-20: 空字段必须显示为「尚未定义」，禁止隐藏或折叠。理由：缺字段的可见性就是数据质量的可见性，与首页把「教师签字 0」放在最显眼处是同一操守。Confidence: high.
- 2026-08-20: 冗余边只输出建议清单，不自动删除。理由：删边不可逆且影响所有下游推理。Confidence: high.

## 本仓库对交接包的两处偏离（已与发起方确认）

- 2026-08-20: **不改 ID 与字段命名。** 保持 `ca_[A-Za-z0-9]{8}`、`statement`/`anchorId`/`prerequisiteId`，只新增 `type`/`failureSignature`/`inInferenceGraph`/`assessmentSpec` 等真正没有的字段；换算表见 `specs/000-naming.md`。理由：交接包红线第 5 条写着「不改动现有锚点 ID」，而它的 schema 用 `^A-[0-9a-f]{6}$`，两者矛盾；3,066 个 ID 已发布，DSH 插件、诗歌资产库与线上 `/data/` 都在引用。备选：双写别名层 —— 多一层要维护且两边迟早发散。Confidence: high.
- 2026-08-20: **验收器只保留一个**（`scripts/validate.mjs`），交接包的 `tools/validate.py` 不采纳为第二个，其 F001–F205 / W101–W104 规则原编号移植进来，反样本转成 `selftest.mjs` 的注入用例。理由：本轮修的全是「同一个概念两份定义」（重复的核心素养词表、没人跑的 schema、各自实现的去重签名），两个验收器是同一个病的最大号版本，而失配的表现是「本该拦的没拦」，不报错。Confidence: high.
- 2026-08-20: 新规则先以 **reporting 档**上线（`validate.mjs` 的 `ENFORCE`），不阻断 CI。理由：F001 在 3,069 条边上全部命中、F202 在 388 条可用锚点上全部命中 —— 现在就硬拦等于 CI 永久红，而红了就会有人把规则删掉。规则按最终形态写，只有 err/warn 的选择受档位控制；重标完成后改一行翻成 required。Confidence: high.
- 2026-08-20: `citable` / `credibility_tier` 不新增字段，由 `reviewStatus` 推出。理由：同一件事不存两份，否则两个字段迟早说法不一致。Confidence: high.

## 本轮实测得出的、交接包未覆盖的决策

- 2026-08-20: 去重签名从 `(学科, verb, object)` 改成 `(学科, verb, 整句去掉动词)`。理由：旧签名的 object 取「动词之后的文字」，分辨不出前置成分 —— 「会用线速度描述匀速圆周运动」和「会用周期描述匀速圆周运动」签名相同，三条真原子被判成互相重复。实测对 2,161 条零假阳性，并抓出 3 组旧签名漏掉的真重复。Confidence: high.
- 2026-08-20: 860 条兜底证据的 `evidenceSource` 从 `curriculum-content-gaozhong` 改成 `fallback`。理由：证据是「能在X课堂或作业情境中完成：<断言原文>」的模板复读，而该字段说的正是证据来源。断言确实来自课标（`provenance.method`/`srcText`/`srcPage` 都在），证据不是。Confidence: high.
