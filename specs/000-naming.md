# 000: 交接包与仓库的命名换算

交接包（2026-08-20，邱懿武 → Claude Code）用的是一套新命名。**仓库不改名**，
理由是交接包自己的红线第 5 条就写着「不改动现有锚点 ID」，而它的 schema 里
`^A-[0-9a-f]{6}$` 与那条红线互相矛盾。3,066 个 `ca_` ID 已经发布，
DSH 插件、诗歌资产库和线上 `/data/` 都在引用。

**001–004 各 spec 里出现的字段名，一律按下表读。**

| 交接包 | 仓库 | 备注 |
|---|---|---|
| `A-[0-9a-f]{6}` | `ca_[A-Za-z0-9]{8}` | ID 无语义、永不复用，这一点两边一致 |
| `E-[0-9a-f]{6}` | 边无独立 ID，主键是 `(anchorId, prerequisiteId)` | 边可退休留档，不需要稳定 ID |
| `claim` | `statement` | |
| `from` / `to` | `prerequisiteId` / `anchorId` | **方向注意**：仓库的 `anchorId` 是被修方 |
| `subject` | `discipline` | |
| `stage` | `stageHint: {min, max}` | 仓库存区间，不存单值 |
| `status: active/deprecated` | `deprecated: bool` + `supersededBy` | |
| `status: split` | `provenance.splitFrom` | 见 tools/atomize.py |
| `citable` | 由 `reviewStatus` 推出：`auto-confirmed`／`expert-confirmed`／`ai-adjudicated` 三档为真 | 不新增冗余字段 |
| `credibility_tier` | `reviewStatus` | 同上，同一件事不存两份 |
| `is_our_assertion` | `evidenceSource === 'capability-rewrite'` | 已有 214 条 |
| `assertion_rationale` | `provenance.why` | |
| `cognitive_level` | `cognitive` | |
| `core_competency` | `literacy` | 学科核心素养，闭合词表 |
| `standard_quote` / `source_page` | `provenance.srcText` / `srcPage` | |
| `extraction_method` | `provenance.method` | |
| `assessment_spec` | **新增** `assessmentSpec` | 现在几乎全空，见 003 |
| `failure_signature` | **新增** `failureSignature` | 见 001 |
| `in_inference_graph` | **新增** `inInferenceGraph` | 见 001 |
| `type`（边） | **新增** `type` | component / instrument / semantic / convention |

新增字段一律用 camelCase —— 边和锚点现有字段就是 camelCase（`anchorId`、`reviewStatus`、
`crossDiscipline`），混两种风格会让消费方每个字段都得查一次。

## 验收器只有一个

交接包带了 `tools/validate.py`（Python，333 行）。**不采纳为第二个验收器**，
而是把 F001–F205 / W101–W104 的规则移植进 `scripts/validate.mjs`，
编号原样保留，反样本转成 `scripts/selftest.mjs` 的注入用例。

理由：这一整轮修的全是「同一个概念在仓库里有两份定义」——
重复的核心素养词表、没人跑的 schema、各自实现的去重签名。
两个验收器是同一个病的最大号版本，而且失配的表现是**「本该拦的没拦」，不报错**。

验收命令换算：

| 交接包 | 仓库 |
|---|---|
| `python3 tools/validate.py --edges … --anchors …` | `npm run validate` |
| `--report-redundant` | `npm run fw-report` |
| `--report-coverage` | `npm run fw-report` |
| 反样本退出码 1 | `npm run selftest`（逐条注入，证明每条规则真的会拦） |
