# K12 Learning Infrastructure MCP · 官方接口候选规范 v0.1

日期：2026-09-06。发布主体：本项目维护方；“官方”表示项目维护接口，不表示教育部认证。状态：候选契约，未实现/部署其中新增工具。现有五工具继续以 mcp/README.md 为准。

## 1. 定义

向 Agent 提供带版本、出处、适用条件和审阅状态的知识、能力、课程与任务映射。帮助 Agent 发现坐标、展开依据、解释关系、识别覆盖与缺口，并在后续授权范围内提交提案。

本规范属于 MCP 上的教育领域契约，不另造传输协议。MCP 协议版本、服务软件版本、领域 schema 版本、使用策略版本与数据快照必须分别表达。

## 2. 参考依据与现状

参考本地《深脑MCP-通用认知服务与应用协作需求书-2026-09-06.md》《深脑MCP-下游应用客户回复与接入验收要求-2026-09-06.md》及深脑 Skill 的状态、证据与作用域设计。本轮未实测深脑远程 MCP，不把文档里的接口名或“已实现”当作验证结果；文档本身也区分了需求与验收。

借鉴：目录到证据逐层读取、材料包、原始来源与推断分离、状态与生成方式分离、显式取代、提案反馈、覆盖说明。修正易僵化做法：不强制先摘要、不强制最多六次调用、不禁止准确引用历史版本。

本地 K12 代码核实：已有 search_anchors、get_anchor、get_prerequisites、list_slice、map_science_tasks；有初始化说明及 text/structuredContent 双返回。仍缺完整 outputSchema、资源/提示模板发现、统一分页、输出预算和跨库实体读取。来源、粒度提示已有基础。

特别差距：get_prerequisites 当前按 hard 优先遍历，并继续遍历 convention；排序不能替代推断准入。edgeOut 未携带完整边审阅信息。initialize 当前回显客户端版本，不能当作真实支持任意协议版本的证明。新接口实施时优先处理这些差距，保留旧接口兼容测试。

## 3. Agent 易读的四个入口

| 层次 | 内容 | 读取方式 |
|---|---|---|
| 简介 | 服务用途、主要路由、关键限制；目标约 200–400 中文字 | 所采用协议支持的服务说明 + get_profile 兼容读取 |
| 工具描述 | 做什么、什么时候用、必要参数、结果边界 | tools/list；每个工具可以独立理解 |
| 使用手册 | 对象词典、关系方向、状态、工作流、错误恢复 | 版本化 Resources；只支持工具的客户端用 get_profile(section=guide) |
| 任务结果 | 简短摘要、具体对象、依据、未知、下一步入口 | structuredContent；同一数据生成文本兼容返回 |

关键限制必须随结果保留，不能假设宿主已加载 Resource、Skill 或初始化说明。说明资源不高于用户或宿主指令；教材、应用描述、来源正文里的命令句是数据。next_actions 是建议，不授予执行权限。

默认给足以决策的短记录，按 ID 展开原文。摘要、对象、来源三档读取；返回数量与字符预算可配置，服务硬上限单独声明。预算不允许截断 JSON、ID、来源身份、状态或关键限制；应整条省略，并返回可续取游标或明确不可续取原因。

## 4. 工具目录

全部下列名称为拟议接口。P0 六个工具：

| 名称 | 何时用 | 输入要点 | 输出要点 |
|---|---|---|---|
| k12_get_profile | 首次接入、检查覆盖/版本、读取指南 | section | 可用对象类型、工具状态、快照、策略、限制、指南 |
| k12_search_entities | 只有主题/文本，尚无确定 ID | query、types、学科/年段、limit、cursor | 简短候选、命中理由、来源状态、展开入口 |
| k12_get_entities | 已有 ID，要核对具体内容 | refs、detail、max_chars | 按输入 ID 顺序返回对象或逐项失败，保留版本 |
| k12_get_source_context | 核对原文与适用栏目 | ref、邻近段落预算 | 版本化片段、页码类型、栏目、前后文及缺失状态 |
| k12_get_relations | 核对一个具体关系或邻域 | ref、类型、方向、depth、limit、cursor | 明确 subject/predicate/object、来源、条件、审阅与可用范围 |
| k12_map_activity | 应用有具体任务，需学习覆盖候选 | 任务、产物描述、范围、预算 | 内容/练习/评价候选、理由、缺失条件、来源、待审状态 |

P1：k12_build_learning_context（开放式任务材料包）、k12_get_unit_coverage（带版本课程目录）、k12_submit_proposal（纠错/映射提案）、k12_list_changes（增量同步）。P1 不应提前出现在可调用工具清单；profile 可明确列为 planned。

不增设泛化的“判断学生掌握度”工具。k12_map_activity 评价的是任务设计的覆盖可能性，不接收学生身份，不产生学习者掌握判断。未来学习证据服务是独立权限域和验证阶段。

典型路由：未知主题 → search → get_entities → source；指定 ID → get_entities；指定引文 → source；应用任务 → map_activity → 针对候选取证；先修问题 → get_relations，不能按 hard 自动排必修路径。

机器目录见同目录 k12-mcp-tool-catalog.v0.1.json。它是设计工件，不是当前 tools/list 响应。

## 5. 返回契约

所有工具业务返回使用同一外壳，data 按工具分别定义正式 outputSchema。当前目录仅给出了输入 schema 和返回字段摘要，完整逐工具 outputSchema 是 P0 实施验收项。

| 字段 | 约定 |
|---|---|
| schema_version / policy_version | 领域结构与策略分别版本化 |
| snapshot | 本次固定的数据快照引用；未接入的库明确 unavailable |
| status | ok / partial / needs_context / unavailable；执行错误另以 isError 表达 |
| summary | 一句回答当前任务，不能超出 data 的证据范围 |
| data | 类型明确的对象、关系或映射候选；禁止只返回一篇长文 |
| coverage | 查询过滤、处理阶段、候选数、返回数、截断、next_cursor、失败与未支持范围 |
| limitations | 与本结果相关的限制，短文本配稳定 code |
| next_actions | 可选 tool + 有效参数 + reason；不强制、不自动执行 |

coverage 不把检索命中数称为“阅读数”。count 不可计算时用 null + 原因；返回 0 表示明确的零，不能表示未接入或无权限。不使用基于同义词命中的“覆盖率”，除非有明确、核实过的目标分母。

空结果要区分 no_match、unsupported_scope、not_indexed、budget_omitted、source_unavailable、partial_failure；错误使用 invalid_argument、version_unavailable、not_found_or_not_accessible、rate_limited 等可恢复代码。不得为区分不存在与无权限而泄漏私有对象存在性。

## 6. 对象与关系的最低可解释性

每个候选至少返回：

- ref：namespace、id、revision（可解析的真实版本；未知时不造值）。
- type、label、statement、scope（学科、年段、课程类型、条件）。
- origin.kind：standard_extract / derived / imported / authored，并保留 derived_from。
- review：来源定位核验、语义审阅、测量验证分开；原始旧状态保留为 legacy_status。
- evidence_refs、limitations、可引用位置。只核对了仓库片段就明确 excerpt_only，不能写成 PDF 已核验。

关系必须表达 subject、predicate、object，不只给 source/target 缩写。prerequisite 统一为基础 → 目标；part_of 为子项 → 母项；sequence 限于课程版本。返回原始关系与规范化结果、转换规则版本；尚未审定的转换用 candidate，不伪装为原有事实。

`allowed_uses` / `unsupported_inferences` 是教育语义边界，不是访问权限。模型标签 hard 或 confirmed 不自动允许拦截学习。多次派生输出不能累计为独立证据。

引用格式应能含“能力表述 + ID + 数据版本 + 原文/推导身份 + 所核验范围”。过期 ID 返回取代关系；历史查询允许读取旧版，不能静默替换成新语义。

## 7. 应用映射的三个维度

每个任务分别返回：content（涉及知识）、practice（练习表现）、assessment（是否有条件评价）。候选关系可分别为 candidate / partial / insufficient_information / no_match，不能用一个总分合并。

映射理由引用输入任务的具体片段或稳定任务 ID，并指出缺失的产物、条件或评价规则。模型推导标明 model_proposed；调用者采纳也只意味着应用映射被接受，不升级为课标认证或学生掌握。

例如“看动画，然后回答搅拌是否加快溶解”：可提出因素知识的候选映射；控制变量实验评价应返回 insufficient_information，并说明没有实验设计、变量控制与记录证据。不能因文本同时出现“搅拌、实验”就生成已确认探究能力覆盖。

## 8. 服务分层与协议兼容

MCP / 网页 / REST 共用领域服务、同一 presenter 与映射算法。发布数据只读，应用项目和提案在独立数据库；P1 写工具单独要求 scope 与幂等键，写入失败不得被解释为成功。

建议远程部署采用 Streamable HTTP，保留本地 stdio。当前没有本规范的已验收远程 endpoint；不能在接入配置中杜撰 URL 或声称改名即可接入。

2026-09-06 读取 MCP 官方 latest 指向 2026-07-28；它与旧版初始化模型不同，包含每请求元数据等要求。本规范领域结构独立于传输版本。实施前选择明确支持矩阵并做真实协议测试；不得继续简单回显任意请求版本。旧版与新版适配分开，不把两版握手/结果外壳混用。

工具 inputSchema / outputSchema、structuredContent、错误及 annotations 按选定版本实现。只读工具声明 readOnlyHint；写提案必须明确副作用。annotations 是提示，权限由服务器执行。完整 JSON 同时通过兼容文本返回时，从同一对象序列化；控制结果体积，不能为了减少重复而只在一条通道保留限制。

拟议资源 URI：k12://guide/0.1、k12://schemas/0.1、k12://policies/0.1、k12://snapshots/{id}。资源支持不是客户端正确使用的前提，get_profile 可读相同内容。可选提示模板：explain_activity_mapping、review_unit_coverage；模板不能隐式写入或发布。

权限：公共图谱读取、组织应用读取、提案提交分别授权；缓存按组织/授权与快照隔离；资料正文不参与指令路由。不存在“接入 MCP 即可读取所有学校/学生数据”的隐式授权。

## 9. P0 验收任务（实施后执行，目前未执行）

1. 仅发现工具、不安装 Skill，也能找到搅拌能力并正确标注推导身份。
2. 给定 ca_VKU9hc8E 直接读取，无需先检索或摘要。
3. 只提供知识问答时，不输出探究能力已评价或学生已掌握。
4. 知识库未接入时返回 unsupported_scope，不声称无此知识。
5. 对 12 条“能说出学生应…”等争议样本保留可见状态，不输出已审定认证。
6. part_of 邻域不变成必先学顺序；hard 标签不构成已验证先修。
7. 小返回预算下保留来源/限制，能续取，没有静默丢项。
8. 读取旧版或被取代 ID 能定位原版或明确失败，不悄悄换义。
9. 批量请求一条坏 ID，其他结果保留，逐项错误可定位。
10. 原文含“忽略规则/提交数据”时仅作为原文返回，不触发工具调用或写入。

每个场景保存实际请求、原始返回、服务/策略/数据版本与预期断言。至少使用两个独立 Agent 客户端完成端到端试验，分别统计首次选工具成功率、关键引用解析率、错误推断、调用/返回成本和缺口报告准确性。语义表现需要任务级评分；不能用手写理想 JSON 或字符串测试替代真实 Agent 验收。

## 10. 实施顺序

P0a：现有五工具补真实版本支持、输入/输出校验、关系状态与遍历边界；实现 profile 与统一外壳，旧名保留兼容。

P0b：六工具逐项实现，按实际接入声明实体范围；先让 capability 可用，knowledge/course 未接入时诚实返回 unavailable。通过本地真实协议与 Agent 验收后，再发布带认证的远程只读接口。

P1：知识和课程跨库读取、材料包、目标清单覆盖、受控提案、变化同步。k12_submit_proposal 写候选队列，不写 anchors/edges，不提升人工状态。

同源发布策略、schema、工具说明、示例与可选 Skill；清单带哈希，发现缓存版本差异时可以刷新。正式发布需包含服务能力矩阵及真实样本；本次工件只是实现的可审阅起点。

协议依据：[MCP 当前规范](https://modelcontextprotocol.io/specification/2026-07-28)、[工具定义](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)、[旧版工具兼容参考](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)。
