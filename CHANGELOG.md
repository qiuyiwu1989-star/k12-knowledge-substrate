# Changelog

破坏性变更与弃用**必须逐条写在这里**，由 `scripts/version-diff.mjs` 核对。
版本号是给机器看的，这份文件是给人看的 —— 逐条写，是为了逼一个人真的去看每一条。

## v1.2 — 2026-08-27

### 新增（additive，704 条锚点）

【五、学业质量】章首次作为锚点来源（口径见 `DECISIONS.md`，邱懿武 2026-08-27 明示确认）。
此前 `gaozhong_commit.py` 只收「内容要求」，20 科里 17 科从没碰过那一章。

同批还含 `split_reqs` 状语抑制修复与 `GOOD_OPENER` 重写之后新过闸的 55 条内容要求锚点
（地理 31 · 思想政治 11 · 音乐 6 · 美术 5 · 德语 2 —— 地理那 31 条正对上
「87/120 个切点被抑制」的诊断）。

全部 `reviewStatus: llm-proposed`，**不计入可引用**（可用数仍是 2,589）。
242 条带课标自己标的素养，记在 `provenance.srcLiteracy`。

落库过程中被闸挡下、当场处理掉的：

- **3 条法语抽取残渣**删除（表头「阅读与朗读」粘上了列表项「（1）阅读基于至该级…」，
  「基于至该级」本身就是坏文本）。全新未发布，所以是删不是弃用。
- **美术 p50 三条被课标标了全部 5 个核心素养** —— 「标全部等于没标」正是我们那条规则的原话，
  只不过这次是课标自己这么标的。处理：`provenance.srcLiteracy` 忠实留下课标标了什么，
  锚点的 `literacy` 置空。两边都不撒谎。
- **`courseType` 词表按课标补全**：加「必修必学 / 必修选学」。那是体育与健康课标自己的划分（p18），
  那一科根本不用「必修/选择性必修」这套词 —— 原来的三值枚举是从别科归纳的，
  遇到第 21 份课标就不够用了。**词表要从课标来，不从我们的归纳来。**

### 弃用（deprecating，2 条）

- `ca_ud3aBAKs`（艺术）「能分析远古艺术的社会文化内涵引导学生分析远古艺术的表现形式传递了怎样的信息？」
  —— 主语是教师不是学生，且两句话糊在一起、句末是问号。
- `ca_j9AVkwsU`（艺术）「能理解、鉴赏作品教师以提问题的方式，引导学生分析和理解艺术作品」
  —— 同上。

两条都由 2026-08-27 新加的**主语闸**抓出：此前所有闸都问「有没有可观察动词」，
没有一条在问「这句话说的是谁」。而锚点的定义是「这个**孩子**会不会」，
主语是教师/教材/学校的句子根本不在这个空间里。

弃用不是删除：记录仍在文件里，已发布的引用仍解析得到（`no-shrink` 保证）。

## v1.3 — 2026-08-29

### 新增（additive，51 条边）

跨学科边 **11 → 37**（+26）：理科 8 · 文科 4 · 艺体技术 14。
另 25 条给原本孤立的锚点补的同学科边（覆盖 18 条）。

三组子 Agent 分学科并行跑 `gen_edges --cross`，命中率从提议的 5.4% 掉到
最终的 **0.51%** —— 因为这是这条路上**第一次真正施加判据**（见下）。

### 撤销一条 spec 承诺（specs/001）

原文：「不扩充跨学科边（现存 11 条保持不动，那个数是对的）」。

撤销的理由不是「想要更多边」，是**这条承诺的依据被证伪了**。子 Agent 去查历史：
2026-08-15 那次产出 63 条、现存 11 条，而 **52 条没活下来的全部是端点被
deprecated 掉的，没有一条是被判据或人工毙掉的**（「劳动：会使用简单的工具」
一条前置就占 18 条，那个锚点后来被判为不是学生能力而作废）。
**存活的 11 条从来没被独立判据验证过。**

由邱懿武明示（原话：「我觉得跨学科的连接点也是要深度的，要进行一下这个连接」）。

### 修复（三个 bug，其中一个能凭空造出复核记录）

- **`ai_review.py` 空对象静默升档**：回复里找不到 `{` 时 `obj = {}`，既无 error
  也无 issues，主循环当成「没挑出问题」→ **静默升成 ai-reviewed**。一次网络截断
  就伪造出一条「AI 看过」。现在没吐 JSON 一律记 error，并加硬条件：
  **「没挑出问题」必须来自一个有 issues 键的回答**。三个子 Agent 独立报了它。
- **`ai_review.py` 缓存钉死失败**：10 条 `{"error":"解析失败"}` 被永久缓存、
  每次重跑重放。和 `fix_fallback_evidence.py` 同一个病（8-25 修过一次，这处漏了）。
- **`OPEN_AT['艺术'] = (1,9)`**：《普通高中艺术课程标准》是真实存在的独立文档，
  库里 61 条 G10–G12。于是 34 条里 32 条被误判学段错，其中 `ca_TRZAHH2A` 的
  假异议已经进了裁决单，已撤销。改成 (1,12)。
- **`no-dup-defs` 扫进 git worktree**：TRUTH 白名单按相对路径写，worktree 里
  同一个文件路径不同，于是**副本里合法的定义被当成第二份**。任何人开 worktree
  都会中。SKIP_DIR 加 `.claude` / `worktrees`。

### 记一次我自己的错

第一次合并时我合错了文件：理科组的终稿叫 `-final`（8 条），另两组叫 `-accepted`，
我合了它的 `cross-理科.jsonl`（46 条，**人工复核之前**的）。

更糟的是接下来：validate 报「MATRIX 档不得有 hard 边」，我写脚本把所有
MATRIX+hard 降成 soft，**降了 133 条**。而规则往上数三行就写着豁免 ——
拆原子建出来的 component 边不在此列，它的证据是 set-containment，
**不是发明出来的依赖**。那 133 条里 125 条完全合法。

**读了报错就动手，没读规则本身。** 全部回滚重来，这一版是重合的。

教训写在这里：**批量"修复"之前先读那条规则的完整定义，包括它的豁免。**

## v1.4 — 2026-08-29

### 1,066 条从没被看过的锚点复核落库

两组子 Agent 各审 533 条。**三种处置，不是两种：**

| | 条数 | 含义 |
|---|---:|---|
| → `disputed` | 537 | 复核挑出了具体问题，已记进 `aiIssues` |
| → `ai-reviewed` | 277 | 断言过了，证据也是真的 |
| **卡在 `llm-proposed`** | **252** | 断言过了，但**证据是占位符** |

那 252 条不是被否掉，是「断言没问题，但我们说不出凭什么判他会」。
它们的 evidence 形如 `能在X课堂或作业情境中完成：<断言原文>` —— 复读断言，零信息。
**说不出怎么判，就不该被叫作可引用。** 用 schema 已有的
`fieldIssues: evidence-weak` 标，没有自己造词。

可用锚点 **2,589 → 2,866**。

### 为什么这次进版本，尽管 version-diff 说「没有变化」

指纹故意不含 `reviewStatus`（契约原话：「复核升档是纯增益，不该惊动任何人」）。
但这次可引用集合涨了 277 条 —— **一个 pin 在 v1.3 和一个 pin 在 v1.4 的调用方，
拿到的可引用集合不一样**。那对调用方是可见的，所以进 minor。

**顺带记一个契约的盲区**：按现在的指纹口径，可引用集合的变化对 version-diff
不可见。哪天有调用方缓存了这个集合，他不会收到任何信号。这条值得单独修。

### 两组独立得出的同一条结论

问题率**跟来源章节走，不跟学科走**：

- A 组：地理 32%（抽自「内容要求」单行条目） vs 小语种 92%（抽自「素养总述」长句）
- B 组：学业质量批 52% vs 其他来源 25%（排除工具 bug 后 51% vs 26%）

B 组把机制挖到了底，而且是不靠 AI 的机械统计：学业质量批 **79%** 的证据是占位符
（其他来源 31%）；占位证据的 disputed 率 **58%**，真实证据 **24%**。
逐字校验 533 条只有 3 条不满足 —— **取字是干净的，坏的是切分粒度和证据生成**。

所以该修的不是这 537 条，是三个上游：证据生成器、切分器在模块目标长句上的表现、
以及抽取入口在「素养/目标总述」段落上的系统性失效。那是下一轮。

## v1.5 — 2026-09-28

### 占位证据换成真证据，复审过的 234 条进可引用

v1.4 卡在 `llm-proposed` 的 252 条（断言过了、证据是占位模板），加上唯一异议是
`evidence-weak` 的 32 条 disputed，共 284 条。`tools/out/_evfix.py` 起草证据，
283 条过闸（至少两条、10–60 字、不复读断言、不回到兜底模板）。

**换了证据就等于换了被审的东西**，所以写回后用 `ai_review` 同一份提示词再审一遍
（`tools/evfix_commit.py`），审过才升档：

| | 条数 |
|---|---:|
| 原 held → `ai-reviewed` | 211 |
| 原 held → `disputed` | 41 |
| 原 disputed → `ai-reviewed`（异议记为 resolved） | 23 |
| 原 disputed → 仍 `disputed` | 8 |

复审新挑出的问题：evidence-weak 38 · not-a-capability 20 · undecidable 6 · truncated 1。
另有 39 条提了 stage，全部撤销 —— 学段由课标文档本身定（高中课标 / 正文印的学段），
模型的意见不能盖过课标（与 `resolve_disputed.py` 同一条规则）。

可用锚点 **2,866 → 3,100**。

**照实记一个弱点**：mimo 额度用完，起草和复审都用了火山方舟 DeepSeek V4.1 Flash ——
同一个模型审自己写的东西，比换模型审要宽。`reviewedBy` 单独记为
`ai:deepseek-v4-1-flash-2026-09-28`，要换模型重审时按它筛。

### 可引用集合的变化现在对 version-diff 可见

v1.4 记下的盲区修了：指纹新增 `cit`（只报告，不参与破坏性判定）。
v1.4 的指纹没有这一项，所以本版 version-diff 只能说「从下个版本起可比」—— 不假装比过了。

## v1.6 — 2026-09-28

### 证据第二轮：带着复核意见重写

对象 68 条（证据抄自课标原文的 curriculum-* 不在内 —— 课标自己写得弱，不归我们改写）：
A = 已可引用但挂着 `fieldIssues: evidence-weak` 的 36 条；B = 唯一未撤异议是 evidence-weak 的 disputed 32 条。
起草时把**旧证据和复核意见**一起交给模型，过闸后用 `ai_review` 的提示词复审（`tools/evfix_round2.py`）。

| | 条数 |
|---|---:|
| B 换了证据 → `ai-reviewed` | 23 |
| A 换了证据，摘掉 evidence-weak | 12 |
| 复审说新证据仍弱 → 不换（A 20 · B 8） | 28 |
| 模型说写不出（原文只有一句空话） | 1 |
| **A 复审对断言本身有异议 → 不动，留给人** | 4 |

最后一行是这一版的规矩：上一轮复核放行了断言，这一轮说不行，是两个判官冲突。
看过这 4 条，一条挑的其实是**前置**的毛病，一条把日语术语「こそあ」判成截断 ——
这种意见不该把可引用的降下去。待人判：`ca_5vjTCnv4` 数学 · `ca_BxbczZ63` 日语 ·
`ca_9cBjrFLv` 科学 · `ca_ARmxnb6Y` 科学。

「仍弱」那 28 条里有复审抓得准的：俄语证据写出了英语的 *more taller*、
俄语朗读证据写「听清每个字的读音」（俄语没有「字」）。所以不换是对的。

可用锚点 **3,100 → 3,123**。version-diff 第一次报出可引用集合的变化：+23 / −0。
起草与复审仍是同一个模型（DeepSeek V4.1 Flash），弱点同 v1.5。

## v1.7 — 2026-09-28

### 修订 4 条：信息科技「数据与编码」的学段按课标原件改正

`ca_04EZiCNZ` `ca_cqH4lRb2` `ca_dLBE5G3L` `ca_wpRWb8Vk` 原标 G1–G2，而信息科技三年级才开课。
`check-consts` 首跑抓出后只打了 `fieldIssues: stage`，没改 —— 当时课标原件不在手边，推断不能当事实写进学段字段。
现已翻到《义务教育信息科技课程标准（2022 年版）》原件：PDF 第 31 页（「数据与编码」内容要求）
和第 34 页（跨学科主题「数据编码探秘」）都在「第二学段（3～4 年级）」之下（第二学段标题在 PDF 第 27 页）。
改为 G3–G4，`provenance.srcStage` 记「第二学段」，标记摘掉。可引用集合不变。


## v1.8 — 2026-09-28

### 撤销误弃用 391 条（契约新增 reviving 一类，决策见 DECISIONS.md 同日条目）

映射基准标金标时撞见：「能根据具体问题中的数量关系列出方程」被判「不是学生能力」弃用，
而它在可判定性自测里是「通过」的正例。复查了弃用理由只凭一个模型一次判断的 821 条
（口号/教学建议 550 · 不是学生能力 189 · AI 裁决 82），门槛见 `tools/revive.py` 文件头：
可判定闸放行、断言忠于课标原句（实义字覆盖 ≥62%）、没有同句在用、证据是真的、
另一个模型（DeepSeek V4.1 Flash；当初判弃用的是 mimo）复审。

| 处置 | 条数 |
|---|---:|
| 撤销弃用 → 在用（复审没挑出问题；含随后证据重写升档的） | 140 |
| 撤销弃用 → disputed（复审只挑了学段 / 证据这类**字段**问题，挂着异议排队） | 251 |
| 维持弃用（闸拦 94 · 不忠于原句 11 · 已有同句 5（+1 条「能/会」之差，validate 去重签名闸抓出后退回）· 两个模型都说不是能力 / 不可判定 / 残句 319） | 430 |

**为什么只挑了字段问题的也撤销**：弃用说的是「这不是一条能力」。复审只说学段标宽了
（多是 G1–G9 占位）、证据不够好 —— 那是字段的毛病，不该让断言替它们背锅。
它们回到 disputed，不进可引用，等人判学段。

恢复出来的 15 条旧字段不合现行规矩（9 条问句缺 `{{name}}`、2 条可引用却没问句、4 条 verb 取了定语），
validate 当场拦下，已逐条修字段。

随后对「只差证据」的跑了一轮 `evfix_round2`：27 条换了证据升 ai-reviewed（已计入上表第一行），
6 条换证据后复审挑出断言问题留在 disputed。

可用锚点 **3,123 → 3,263**。
同一个弱点照记：起草、复审都是同一个模型；`reviewedBy` 记为 `ai:deepseek-v4-1-flash-2026-09-28`。

<details><summary>逐条：撤销弃用后在用（140）</summary>

**艺术**（38）

- `ca_Axagf9DD` 会演奏简单的锣鼓经片段或其他节奏型
- `ca_9427s3YS` 能用线条、色块、图形等表示所听到的音乐
- `ca_fEqPhPSL` 能遵守游戏规则，初步建立合作意识
- `ca_2Zht6qGd` 能选择合适的表现形式，根据一定的情境、主题或表演要求进行创编和表演
- `ca_cZG3n5vT` 能听辨常见音乐结构，并选用合适的方式表示出来
- `ca_PVsAj7ZW` 能分辨所听乐曲的音乐体裁、形式，简单描述其音乐特征和风格特点
- `ca_hVQ7GrtR` 能说出音乐表现特征与情感表达之间的联系
- `ca_LU6V9y5y` 能比较听觉艺术与视觉艺术的异同
- `ca_pwtwC3ug` 能根据音乐术语或记号，适切地表达歌曲的情感
- `ca_kBQPqU3X` 能用声势、语言、动作等模仿或表现包含简单和稍复杂节奏型的节奏谱（含多声部节奏）
- `ca_upzCRU68` 对歌曲有自己的见解和创意表达的想法，在演唱时能进行个性化的处理与表达
- `ca_zVt2sxaQ` 能运用乐器编创并演奏简单节奏和旋律
- `ca_sbzMBqLb` 能根据既定标准评价自己及他人的演奏，并根据评价反馈调整自己的演奏
- `ca_3T3ZyXBb` 能运用一定的演奏技巧提高演奏的表现力，较好地与他人合作演奏多声部音乐
- `ca_tQfZRxzX` 能运用乐器演奏欣赏曲的音乐主题或所学歌曲的旋律，表现音乐的各种要素
- `ca_DUguf4Pb` 能较全面、客观地评价自己及他人的演奏
- `ca_WXAqiRmy` 运用图形谱、乐谱或其他方式记录编创的作品
- `ca_ZQeaW4XK` 掌握主要舞蹈种类中的基本动作及动作组合，并能将其运用到表演中
- `ca_zBsvFKfe` 乐于参与多种题材的歌舞剧编创与表演，主动担当角色
- `ca_YMTUZUNb` 能根据需要选择合适的音乐作为舞蹈、戏剧（含戏曲）、曲艺的配乐
- `ca_srqGVdHz` 选择身边的材料，自制简易乐器，尝试演奏
- `ca_LUUjj2xc` 能用自制的打击乐器或简易音高乐器演奏简单的节奏与旋律，或为歌曲伴奏
- `ca_wqGzJN7Z` 能列举生活中的音乐现象、音乐活动和相关文化，并与人交流自己的看法
- `ca_bf3Pgm5W` 能参加家庭或社会的音乐活动，并根据需要选用合适的音乐和表演形式
- `ca_kYtLcAD9` 能用自制的打击乐器或简易音高乐器进行合奏或为其他表演伴奏
- `ca_KQL5Z6xL` 能分享与交流自己的作品
- `ca_A7UsVMPU` 能根据小组或班级活动的要求设计或创作作品
- `ca_xmZngVTr` 能根据班级、学校的环境特点和需求，绘制草图或制作模型
- `ca_7jYPBipp` 能借助数字媒体技术完成3分钟的、反映班级学习和生活的微电影作品
- `ca_Z9CYzGkw` 能借助数字媒体技术完成3~5分钟的、表现校园生活的微电影作品
- `ca_D644ve8R` 运用长镜头、特写镜头等表现手法进行拍摄
- `ca_8CaKBLQm` 能运用美术语言，辨析中外美术的主要流派，尊重并理解世界美术的多样性
- `ca_zuQyhCPT` 能捕捉舞蹈的动态特点和风格特征，并尝试进行表演
- `ca_hPfhY4Z7` 能与他人合作完成队列变化与造型配合
- `ca_AfVHUSP3` 掌握影视（含数字媒体艺术）制作软件的基本使用技巧
- `ca_ZdC4UWWp` 能根据当地的实际情况，提出保护非物质文化遗产的建设性意见，撰写300~500字的报告
- `ca_LrsLVHvz` 能与他人合作完成队列变化和造型配合
- `ca_rkUaTjKb` 能根据剧目的规定情境，遵循舞台表演的基本规则，进行角色的合作表演

**语文**（17）

- `ca_dzBy3RLd` 能就感兴趣的内容提出问题，结合其他学科的学习和生活经验交流讨论，尝试提出自己的看法
- `ca_TbfL76Pw` 理解词句的意思，体会课文中关键词句表达情意的作用
- `ca_YPNFeDDM` 能简单描述印象最深的场景、人物、细节
- `ca_sdP5RiWr` 参与讨论，敢于发表自己的意见，说清自己的观点
- `ca_N6kuHVHw` 能区分写实作品与虚构作品
- `ca_umwh88EP` 梳理学过的语言现象，欣赏优秀作品的语言表达技巧，初步探究语言文字的运用规律
- `ca_dvuntXU5` 能正确书写 800 个左右常用汉字
- `ca_ScEsYnJe` 喜欢积累优美的词句，并尝试在口头和书面表达中运用
- `ca_sfgXdLSr` 能根据具体语境辨析多音多义字的读音和字义，辨识、纠正常见的错别字
- `ca_wn42zV7E` 能结合关键词句解释作品中人物的行为，从某个角度分析和评价人物
- `ca_5VMPUPS4` 能复述读过的故事，概括文本内容，根据自己的阅读理解提出问题并与他人交流
- `ca_4QuHmnJb` 能参与简单的活动策划、组织工作
- `ca_k5uXb2rL` 能根据字形推断字音字义，并借助语境和工具书验证自己的推断
- `ca_fMUBhyHN` 能概括说明性文字的主要内容或简单的非连续性文本的关键信息，初步判断内容或信息的合理性
- `ca_2PSeTyQj` 运用文本主要信息解决现实生活中的简单问题
- `ca_gXUXxExK` 能用多种媒介方式表达交流
- `ca_6kLb5kYy` 能利用掌握的多种证据判断信息的真实性与可信度

**数学**（16）

- `ca_jQNhEhFZ` 能运用平面解析几何方法解决简单的数学问题和实际问题 ，感悟平面解析几何中蕴含的数学思想
- `ca_mvpNKgHp` 能判断两个量是否成正比例或反比例
- `ca_NCV9ekHR` 能解决按比例分配的问题
- `ca_5kRfQBre` 能解决按比例分配的简单问题
- `ca_tznPAsEp` 能恰当地选择单位估测一些物体的长度和面积
- `ca_iHG66utR` 会测量三角形、长方形和正方形的周长
- `ca_7xRaRndK` 能发现事物的特征并制订分类标准，依据标准对事物分类
- `ca_GRqYZnPH` 能用语言简单描述分类的过程
- `ca_icuzbLNf` 能用条形统计图合理表示数据，说明数据的现实意义
- `ca_HYTT36Nz` 能用平均数解决有关的简单实际问题（例42）
- `ca_ZFMFdbHN` 能说出钟表上的时间
- `ca_JJeLQ2v6` 能记录测量的结果
- `ca_V6rtkHan` 能根据具体问题中的数量关系列出方程
- `ca_gWn25FkK` 会计算正方形的周长
- `ca_fTBsnfR4` 能计算长方体的体积和表面积

**劳动**（11）

- `ca_7vvEhTiq` 能按照物品类别、形状等整齐摆放，初步建立及时整理与收纳的意识
- `ca_sFzYjVv8` 正确使用卫生工具，参与教室卫生打扫，将桌椅摆放整齐
- `ca_iLjBVDqD` 正确使用消毒纸巾、棉球和洗手液，在公共场所能自觉做好个人防护
- `ca_whjNht8G` 掌握居室、教室内物品整理与收纳的方法
- `ca_PkRHAF9S` 初步掌握家庭常用小电器的使用方法
- `ca_knhrhhZx` 能进行家庭餐食的设计和营养搭配，并掌握简单的烹饪方法
- `ca_XAGzF3NJ` 参与1~2项公益劳动与志愿服务劳动项目
- `ca_uWDqaJza` 灵活运用整理与收纳的方法，从整体上完成对家庭各居室和教室内部物品的整理与收纳
- `ca_MiSxnuRd` 独立完成外出远行的行李箱整理与收纳，依据行程安排、天气状况准备衣物和生活用品等
- `ca_yUpHmuia` 独立制作午餐或晚餐中的 3~4 道菜
- `ca_6tM3vU6e` ~9年级，可确定项目目标为"能够根据需求，识读并绘制简单木工工艺作品图样

**体育与健康**（9）

- `ca_TjGmqtCj` 与同伴合作完成体能学练，根据身体感受调整练习节奏，并乐在其中
- `ca_hvipihHz` 能列举体育活动和比赛中的安全注意事项，表现出主动规避运动伤害和危险的意识与行为
- `ca_yhsRhX5z` 能列举吸烟的危害，拒绝吸烟并抵制二手烟
- `ca_RXJCs4gs` 能识别近视症状，并运用科学的方法预防近视和矫正视力
- `ca_6B4R9vdx` 能说出促进人体生长发育的主要因素并在生活中加以运用
- `ca_UrHFDak5` 能描述所学球类运动项目的基本动作技术要领和基本规则
- `ca_GNcLkdih` 能描述所学体操类运动项目的动作技术要领、练习方法和比赛基本规则
- `ca_ufcpiAar` 掌握所学新兴体育类运动项目的完整动作技术，并合理运用所学动作技术开展班级内展示或比赛
- `ca_tvwLkQxn` 能与同伴融洽相处，善于沟通与合作，并运用情绪调控的方法缓解比赛中的紧张情绪

**科学**（9）

- `ca_xcvmCdHs` 会用简单工具测量距离、时间等
- `ca_uB5KTNRk` 能比较不同动物感知环境的器官
- `ca_fSfh7CUi` 举例说明重大的技术发明会给人类社会发展带来深远影响（如工业革命、信息技术革命）
- `ca_25wVqpmy` 能举例说出一些技术产品所涉及的科学概念或原理
- `ca_Ls2JZvp9` 能观察并描述与地球和太阳运动相关的自然现象
- `ca_TTN2XSdX` 能发现所制作模型的问题，并进行适当的改进
- `ca_QTsAksAs` 能运用创造性思维的基本方法，基于所学的科学原理提出有一定新颖性和合理性的观点
- `ca_52dnQ5vs` 能以事实为依据作出判断，面对有说服力的证据能调整自己的想法
- `ca_My7834Qm` 能完成与所学知识和方法相适应的、简单的探究报告，自觉地对探究过程和结果进行反思与评价

**化学**（7）

- `ca_EenXE976` 能查找资料并讲述我国化学家胸怀祖国、艰苦奋斗、勇于创新的故事
- `ca_wJfpqM2z` 能设计简单的实验方案或实践活动方案
- `ca_XD86MSjX` 能举例说明化学变化在自然界和生产生活中的重要应用价值，以及化学家利用化学反应造福人类的创造性贡献
- `ca_xqi4VSx9` 能利用化学反应及绿色环保理念设计实验方案，完成常见物质的制备、检验等任务
- `ca_QNpEeE4b` 能根据实验目的选择必要的试剂、常见的实验仪器和装置
- `ca_uNJBjPmz` 运用实验基本操作技能和条件控制的方法，安全、顺利地实施实验探究方案
- `ca_bd9bWNUk` 能设计简单实验，制备二氧化碳

**生物学**（6）

- `ca_xsLaLvtN` 运用示意图或模型等方式，展示和说明细胞各结构的功能及其相互关系
- `ca_d9ZKsu9v` 识别给定生物材料所属的结构层次，并阐明生物体在结构和功能上是一个有机整体
- `ca_hSdpDTNS` 能够设计简单的实验，探究有关人体生理与健康的问题
- `ca_me7FxGTf` 学会科学用眼和用耳，保护眼和耳的健康
- `ca_9L5Jvyif` 尝试提出可有效预防传染病的方法
- `ca_rUv6kbqP` 运用结构与功能观、生物与环境的关系等知识进行分析，推测产生特定病症的可能原因

**信息科技**（6）

- `ca_BBLPb5LA` 能使用生活中常见的数字设备帮助自己开展学习
- `ca_z3HgGbde` 能在分享他人数字作品时标注来源
- `ca_bscX5Wv3` 能合理选用数字化工具解决简单问题
- `ca_nWctPyqV` 能用数据记录并描述规律性发生的事件，简单地表达自己的想法或预测结果
- `ca_SybjARHA` 通过分析典型案例，对比计算机传统方法和人工智能方法处理同类问题的效果
- `ca_hNk7QCn3` 能列举人工智能的主要术语

**物理**（6）

- `ca_dDJ6wvxE` 能说出生活中常见的温度值
- `ca_Ux5zShLc` 能制订简单的实验方案
- `ca_TJrTsaHW` 能按实验方案操作，获得实验数据
- `ca_F3qxBYcX` 能基于证据说明操作的合理性
- `ca_hpePafys` 能根据实验目的，正确地选择实验器材
- `ca_FfTxJH2w` 运用控制变量法等制订比较合理的科学探究方案

**道德与法治**（5）

- `ca_dqZFZUUK` 能够理解"绿水青山就是金山银山"的道理，自觉保护自然环境（健全人格、责任意识）
- `ca_CxFwL94r` 能够用实例说明中华文化的源远流长与博大精深
- `ca_RxqvvSG2` 能够结合实例简要说明维护国家安全的重要性
- `ca_sn28fvcR` 能够举例说明世界文化的多样性
- `ca_KjFPLWjH` 能够完成学习和作息计划

**英语**（4）

- `ca_5uUx2BjP` 愿意参与课堂活动，与同伴一起通过模仿、表演等方式学习英语
- `ca_tczQedAx` 能正确使用大小写字母、标点符号进行书面表达，拼写基本正确
- `ca_aGHs4iAJ` 能参照范例仿写简单的贺卡、邀请卡等，语言基本准确
- `ca_xkGGKVxb` 能讲述具有代表性的中外杰出人物的故事，如科学家等为社会和世界作出贡献的人物，表达基本清楚

**西班牙语**（2）

- `ca_Ka9zKajT` 能够识别感叹句的语调
- `ca_acXRbbKT` 能够模仿范例，写出简单的贺卡

**通用技术**（2）

- `ca_pmv9fsUY` 能理解工程设计过程中的安全性
- `ca_s29CpcBb` 能将简单的设计方案用二维设计软件表现出来

**历史**（2）

- `ca_SnuChAnW` 能够利用并分析可信史料，初步理解近代世界政治、经济和思想文化之间的关系
- `ca_NZbDrgg9` 能够运用记录历史年代的基本方式

**地理**（1）

- `ca_4YLih2Re` 能够说出地球在宇宙环境中的位置、地球的大小，初步建立科学的宇宙观

</details>

<details><summary>逐条：撤销弃用后进 disputed（251）</summary>

**科学**（122）

- `ca_S28z8gNL` 能举例说出生活中常见物体和材料的外部特征　`stage`
- `ca_xzbECV7K` 能说出空气和水的形态特点　`evidence-weak·stage`
- `ca_mjB6Nvnh` 能说明某些材料的透光性、导电性等特性及其主要用途　`stage`
- `ca_7vTEQwWE` 能说出水有三种状态　`stage`
- `ca_FehCknHR` 能利用证据说明空气占据空间、充满各处的性质等　`evidence-weak·stage`
- `ca_ZqUMbs3B` 能观察、描述常见材料的某些性能　`stage`
- `ca_AsFbPWPv` 能利用控制变量的方法设计方案并操作，探究不同材料在水中的沉浮现象和导热性等　`evidence-weak·stage`
- `ca_bJaNTrqM` 能说明常见物质主要的物理性质和化学性质　`evidence-weak·stage`
- `ca_5CsGzZnU` 能用化学方程式表示常见单质、氧化物、酸（碱）之间的转化　`evidence-weak·stage`
- `ca_MKSBGfvk` 能初步从微观粒子的角度认识物质，并简单地解释生产生活及实验中的一些现象　`stage`
- `ca_YeVTuRRG` 会用天平测量物体的质量　`stage`
- `ca_PWMKrwKe` 会用排水法测量物体的体积　`stage`
- `ca_ut6arhj8` 能根据物质的性质设计实验，检验和区分氧气、二氧化碳及常见的酸和碱　`evidence-weak·stage`
- `ca_AA5BbNfT` 能操作简单的实验，观察和描述某些物质在水中的溶解现象　`stage`
- `ca_LX6HCZXc` 能说明影响物质溶解快慢的常见因素　`stage`
- `ca_Qbmqwq34` 能举例说明物质发生变化时有些产生了新物质，有些则没有　`stage`
- `ca_Psi4cLve` 能寻找证据解释和判断物体发生变化时，其构成物质是否改变　`stage`
- `ca_S6RkrkJX` 能设计方案，探究身边物体的变化　`evidence-weak·stage`
- `ca_HKJadshe` 能说出溶液的组成，从定性与定量的视角说明饱和溶液、溶解度及溶质质量分数的含义　`evidence-weak·stage`
- `ca_enXcAHpA` 能利用化学反应相关知识分析解释自然界、生产生活及实验中的现象　`evidence-weak·stage`
- `ca_irMGx4QN` 能从宏观和微观的视角说明物理变化与化学变化　`evidence-weak·stage`
- `ca_qPTTmyCm` 能用图像表示物态变化时物理量的变化规律，用观察和实验方法研究物质的三态及变化现象，并用物质的粒子模型作简要的微观解释　`evidence-weak·stage`
- `ca_jRe37vqz` 能选取实验证据说明、论证质量守恒定律，并能解释其微观本质　`evidence-weak·stage`
- `ca_sEzfUzvq` 能运用控制变量的方法设计实验，探究燃烧的条件　`evidence-weak·stage`
- `ca_KYjDwJBY` 能说明形成简单电路的基本条件及控制方法，区别导体和绝缘体　`stage`
- `ca_QU79zKsW` 能识别生活中的光源　`stage`
- `ca_VLxde2xQ` 能说明声音可以在不同物质中传播　`stage`
- `ca_DuqAamT2` 能解释物体振动与声音产生及其变化之间的关系　`evidence-weak·stage`
- `ca_cE4K98XN` 能用科学词汇、图示符号等表达物体运动的方式　`evidence-weak·stage`
- `ca_7cAC2xtU` 会用简单的元件连接简单电路　`stage`
- `ca_veuXDubK` 能举例说出光的反射现象　`stage`
- `ca_UwTUcuaz` 能通过观察和实验理解常见的力对物体运动的作用　`evidence-weak·stage`
- `ca_D3LyJyKB` 能设计制作简单的光学物品　`evidence-weak·stage`
- `ca_Afegj5rH` 能用力与运动的关系解释和解决生活中的简单力学问题　`evidence-weak·stage`
- `ca_BjKssewu` 能描述物体运动的快慢　`stage`
- `ca_V22BV3Yb` 能用压强与流速的关系解释相关现象　`stage`
- `ca_vHHnCiNZ` 能解释与声音的产生、传播有关的简单问题　`stage`
- `ca_MKHDQY9b` 能根据光线模型解释针孔成像、影子等现象　`evidence-weak·stage`
- `ca_qRu5AW3Z` 能连接简单的串联电路和并联电路　`stage`
- `ca_7BQtknDQ` 能用控制变量的方法探究电阻大小相关影响因素，探究电流与电压、电阻之间的关系　`evidence-weak·stage`
- `ca_hCNVD2rG` 能用欧姆定律解释常见的电学问题，求解简单的电路问题　`stage`
- `ca_szswjzhs` 能描述和建构通电直导线、通电螺线管周围的磁场模型　`evidence-weak·stage`
- `ca_brMwBV4K` 能用实验探究阿基米德原理　`evidence-weak·stage`
- `ca_2Ti6m4km` 能正确测量电路中的电流和电压　`evidence-weak·stage`
- `ca_6zcSxGZJ` 关注生产生活中的运动与相互作用的现象，并能解释交通运输、生产生活中的简单问题　`evidence-weak·stage`
- `ca_Y94bWpwh` 能用实例归纳概括物体的热胀冷缩性质　`stage`
- `ca_8Vzy8jTF` 能举例分析物体运动过程中有能的变化　`evidence-weak·stage`
- `ca_SL7QqUQC` 能利用科学词汇、图示符号等方式记录现象　`stage`
- `ca_FH6xeD86` 能对热传递的方式进行分析和推理　`evidence-weak·stage`
- `ca_JvCrGS6E` 能设计并实施调查活动，说明能的转化现象　`evidence-weak·stage`
- `ca_WDz8vXX7` 能用案例分析归纳改变内能的两种方式　`stage`
- `ca_CGxrihwV` 能探究简单机械的特点，解决简单机械的相关问题　`evidence-weak·stage`
- `ca_mm4MxSfL` 能设计与探究电流产生热量的影响因素　`stage`
- `ca_iU3r4vmU` 能收集数据计算家用电器的能耗问题　`evidence-weak·stage`
- `ca_H6jTEWa7` 关注个人、社区的能源使用问题　`stage`
- `ca_SkDeAfTK` 能概括动物的某些共同特征　`evidence-weak·stage`
- `ca_bK9tM4NC` 能使用显微镜观察动物细胞和植物细胞的形态　`evidence-weak·stage`
- `ca_U7gKe6Sf` 能运用生态系统的概念分析生产生活中的一些简单问题　`evidence-weak·stage`
- `ca_XTwQG8ia` 能选择适当的观察工具观察各类生物　`evidence-weak·stage`
- `ca_PZ4GewWM` 会制作简单的临时装片，并绘制简单的生物图　`stage`
- `ca_8jLVf8T4` 列举人体的主要内分泌腺及其功能，列举激素对生命活动的调节作用　`stage`
- `ca_FTqUf6GJ` 能分析不同植物生存和生长的条件　`stage`
- `ca_92ECC4SX` 能比较分析植物、动物生存需要的差异　`stage`
- `ca_u7LQkLvE` 能设计简单方案并实施操作，搜集植物和动物生存、生长所需条件的证据　`stage`
- `ca_Kv6nKGyM` 能收集人和动物以其他生物为食获得维持生命活动所需能量的信息，用多种方式表达调查过程与结果　`evidence-weak·stage`
- `ca_kKfvGtUH` 能建构光合作用、呼吸作用的概念或模型　`stage`
- `ca_UWZhaThx` 能分析人体体温调节的过程　`evidence-weak·stage`
- `ca_hqAZt5vF` 能设计方案，通过调查探讨疫苗的来源和作用机理　`evidence-weak·stage`
- `ca_aX94CAag` 举例说明生活中可能遇到的有毒物质和防御措施　`stage`
- `ca_VZEe3kfP` 能分析不同环境中植物的不同外部形态特点对维持其生存的作用　`evidence-weak·stage`
- `ca_sMYvzFrd` 能比较不同动物适应季节变化的方式对维持其生存的作用　`stage`
- `ca_LRmTiVQd` 能收集生活在不同环境中的植物外部形态特征的信息，调查动物适应季节变化的方式　`evidence-weak·stage`
- `ca_gyXHM7Gi` 能分析不同动物在气候、食物、空气和水源等环境变化时的行为　`stage`
- `ca_2UMmbQuj` 能分析影响合理膳食的因素　`evidence-weak·stage`
- `ca_svbwh2hU` 能归纳传染病的特点及防治措施　`stage`
- `ca_u4ff3yER` 能分析动植物生命周期不同阶段的相应特点　`stage`
- `ca_EPzCzHSz` 能记录、整理和描述常见植物和动物从生到死的生命过程　`stage`
- `ca_HhWgAvS8` 能举例说明生物的遗传、变异与环境因素的共同作用导致了生物的进化　`stage`
- `ca_HNQ5Ptvb` 能比较不同生物的生殖方式与发育过程　`evidence-weak·stage`
- `ca_WevZCMdn` 能从遗传学角度分析近亲结婚的危害　`stage`
- `ca_nBmFz4SC` 能收集和交流生物进化历程的资料，对生物进化的不同观点提出自己的见解　`evidence-weak·stage`
- `ca_hqpxzveM` 能描述太阳的位置变化和月亮的形状变化　`stage`
- `ca_5XrHemPQ` 能说出月球表面的概况　`stage`
- `ca_USTDPpGr` ~6年级能说出太阳系的基本结构　`evidence-weak·stage`
- `ca_Y8RhYJjy` 能运用太阳系的简单模型　`evidence-weak·stage`
- `ca_L6CdAZPu` 能借助动画演示或动手制作简单模型，模拟地球、月球和太阳的相互关系　`evidence-weak·stage`
- `ca_xqSiX5Yb` 能解释节气与地球公转的关系　`evidence-weak·stage`
- `ca_sU8bdSGL` 能说出地球表面海陆分布的概况和主要水体类型　`stage`
- `ca_hT4FqavQ` 能解释生活中常见的天气现象　`evidence-weak·stage`
- `ca_nCpAVCJJ` 能解释火山和地震的成因　`stage`
- `ca_CCKgJz6u` 能通过制作实物模型，模拟地球内部的圈层结构　`evidence-weak·stage`
- `ca_RErXcnLV` 能解释气候对生产生活的影响　`stage`
- `ca_N3KS6mpd` 能描述水循环的主要过程　`stage`
- `ca_fMk2GbSr` 能区别天气和气候的含义，用曲线图呈现气温随时间的变化，用柱状图呈现降水量随时间的变化　`stage`
- `ca_rrDF9uku` 能用图表解释水循环的主要过程　`stage`
- `ca_Y2JBxDAV` 能运用等高线地形图和实景图识别主要的地形类型　`stage`
- `ca_edw5vTN2` 能运用板块构造学说解释火山和地震的分布特点　`stage`
- `ca_nDWHTAzq` 能举例说出海洋为人类提供的多种资源　`stage`
- `ca_niKJ76zg` 根据特定问题或需求，尝试分析并阐明发明方案　`stage`
- `ca_yYxNaiBS` 列举科学原理转换为实用技术的案例，尝试制作把科学原理转化为技术的简单展示模型　`stage`
- `ca_QpsUd5Lu` 能描述常见简单科技产品的结构与功能　`stage`
- `ca_mg2PUJUB` 能举例说出常用的发明方法　`stage`
- `ca_tdvmbahN` 能说出一些工程中的主要系统和中国的一些大科学工程　`evidence-weak·stage`
- `ca_ECnnkK6x` 能简要说明技术与工程对科学发展的促进作用　`stage`
- `ca_pEqdERUH` 能从批判性思维的角度，基于证据讨论涉及伦理争议的技术与工程问题，并作出理性判断　`evidence-weak·stage`
- `ca_3qpKQqrs` 能举例说明科学对技术与工程具有指导意义　`stage`
- `ca_xQQjJuQf` 能制作把科学原理转化为技术产品的简单装置　`stage`
- `ca_XWx8pzJ6` 能提出满足一定限制条件的简单设计问题和多种设计方案　`stage`
- `ca_wehvTaw9` 能完成实物模型制作，发现实物模型的不足并进行改进　`stage`
- `ca_3Su46zVA` 能制作实物模型，并基于证据改进实物模型的设计和制作　`evidence-weak·stage`
- `ca_eTa9g9HX` 识别日常生活中各种形式的能　`evidence-weak·stage`
- `ca_KUdtaErK` 能正确讲述并反思自己的探究过程与结论，作出自我评价与调整　`stage`
- `ca_5zBfheNC` 能用二维方式表达三维空间的物体，并解决简单的实际问题　`evidence-weak·stage`
- `ca_42hAzseP` 说出日常生活中不同形式能之间的转化现象，举例说明生活中的热传递现象　`evidence-weak·stage`
- `ca_2ULTQc2F` 能使用显微镜等观察工具，从宏观与微观视角比较动物和植物的不同　`evidence-weak·stage`
- `ca_BwE9ihBy` 说出细胞是生物体结构的基本单位，总结生物体形态结构和功能的关系　`evidence-weak·stage`
- `ca_r8Q5WWfk` 能举例说明自然资源、自然灾害和自然过程对人类活动的影响　`stage`
- `ca_j9pFmPVS` 能利用生物的多样性与适应性的相关知识，综合分析生物的遗传、变异和环境因素　`evidence-weak`
- `ca_sHBihScw` 能根据研究问题的需要和讨论交流的情境，提出科学假设和观点　`stage`
- `ca_WTG95vRR` 能识别探究问题和研究变量　`stage`
- `ca_xPbFSvga` 能使用常见的工具和科学仪器，完成简单的、与所学知识相关的技术与工程任务的设计和实施　`evidence-weak·stage`
- `ca_jDYk7M5c` 运用测量工具获得数据并进行整理，得出有说服力的结论　`evidence-weak`

**体育与健康**（60）

- `ca_eUiRWbjL` 能说出生命孕育的过程、人体主要器官的名称及功能、男女生的生理差异　`evidence-weak`
- `ca_bf7DxpJJ` 运用预防运动损伤的简单方法　`evidence-weak`
- `ca_hKdfyRQB` 运用所学球类运动项目技战术参与班级内的教学比赛　`evidence-weak·stage`
- `ca_W5LufNPK` 能描述所学球类运动项目的相关原理和文化，在比赛中合理运用主要的比赛规则，承担班级内比赛的裁判工作　`evidence-weak·stage`
- `ca_Z5tL2sHQ` 每学期观看不少于8次所学球类运动项目的比赛，并能对某场高水平的比赛作出分析与评价　`evidence-weak·stage`
- `ca_HubheJmS` 能运用所学球类运动项目知识与技能制订并实施锻炼计划　`evidence-weak·stage`
- `ca_dMx47SVp` 掌握所学田径类运动项目主要的基本动作技术、组合动作技术和完整动作技术，并运用于多种游戏和比赛中　`evidence-weak·stage`
- `ca_F9jXDCaM` 能简单处理田径类运动中的轻度损伤　`stage`
- `ca_u8cBCJkk` 能描述所学田径类运动项目的基本原理和文化　`evidence-weak·stage`
- `ca_YFJew8pT` 能简单处理田径类运动中常见的运动损伤　`stage`
- `ca_Ve6Utyqe` 能基本判断动作的对错，并尝试进行打分　`evidence-weak·stage`
- `ca_PgjgqZr4` 在所学体操类运动项目的个人和小组练习中运用多种动作技术　`evidence-weak·stage`
- `ca_NN55FU9d` 参与小组间成套动作创编比赛　`stage`
- `ca_qnPi4k6K` 积极参与技巧运动成套动作展示，做到动作正确、规范和连贯　`evidence-weak·stage`
- `ca_2snVzyME` 能判断动作质量并正确执裁　`evidence-weak·stage`
- `ca_A7K6xQwm` 能描述所学体操类运动项目的基本原理和文化　`evidence-weak·stage`
- `ca_YRtJgbxq` 能运用简单方法处理运动损伤　`evidence-weak·stage`
- `ca_sx6cYcA2` 按照规则和要求参与所学水上或冰雪类运动项目的比赛　`evidence-weak·stage`
- `ca_VDYKAy4k` 在所学水上或冰雪类运动项目的比赛中正确运用基本动作技术、组合动作技术和完整动作技术　`evidence-weak·stage`
- `ca_rpamt8ih` 在所学水上或冰雪类运动项目学练和比赛中保持情绪稳定，表现出合作能力和团队精神，安全地参与该运动项目　`stage`
- `ca_tSrMbATG` 能描述所学中华传统体育类运动项目的基本动作技术要领和特点，以及比赛基本规则和裁判方法　`evidence-weak·stage`
- `ca_Srwrp9WX` 具有运用所学中华传统体育类运动项目进行体育锻炼的习惯　`evidence-weak·stage`
- `ca_rWJUVXLJ` 自信地参与所学新兴体育类运动项目的展示或比赛　`undecidable`
- `ca_eZHw7cjC` 合理运用所学新兴体育类运动项目的知识与技能分析、解决体育展示或比赛中遇到的问题　`stage`
- `ca_he8eS9xQ` 能描述所学新兴体育类运动项目的基本原理和文化，担任课内教学比赛的裁判　`evidence-weak·stage`
- `ca_SaM8AfMT` 能运用心率描述运动强度　`stage`
- `ca_c5u9HLQw` 描述体能发展的超负荷原则和个性化原则　`evidence-weak·stage`
- `ca_EdG7hDnJ` 能简单处理自己或他人的运动损伤　`evidence-weak·stage`
- `ca_tC4b9uzz` 能说出饮食卫生和食品安全知识，合理、安全地饮食　`evidence-weak·stage`
- `ca_hhHHNZNz` 能运用青春期的保健方法　`evidence-weak·stage`
- `ca_JjyBGaPp` 能描述视力不良对自身生活质量等的影响　`evidence-weak·stage`
- `ca_CfTgWZ7q` 能描述预防超重、肥胖、营养不良的方法　`evidence-weak·stage`
- `ca_unsWxQe4` 能描述视力不良对职业发展的影响，积极保护视力　`evidence-weak·stage`
- `ca_2fbmuK8E` 能说出与球类运动项目相关的动作术语　`evidence-weak·stage`
- `ca_YqhcFhWb` 能按照要求参与所学球类运动项目游戏和学练，在挑战自身身体极限且保证安全的情况下继续坚持　`evidence-weak·stage`
- `ca_uGnwxtTw` 能做到每周运用所学球类运动技能进行3次（每次至少0.5小时）课外体育锻炼　`evidence-weak·stage`
- `ca_NuyxDGrZ` 掌握所学球类运动项目主要的基本动作技术和组合动作技术，参与班级内较为正式的教学比赛，并运用简单的技战术配合　`evidence-weak·stage`
- `ca_MJZhjRTk` 能描述所学球类运动项目的动作技术要领和基本比赛规则　`evidence-weak·stage`
- `ca_n3wKn2tJ` 能在比赛中合理运用主要比赛规则，承担班级内比赛的裁判工作　`evidence-weak·stage`
- `ca_cAKrcn5C` 能与同伴交流交往，适应游戏和比赛环境的变化　`evidence-weak·stage`
- `ca_AvhnKQWG` 能及时处理跑、跳、投掷学练和比赛中易发生的安全问题　`stage`
- `ca_wvcpmLCj` 运用所学的3~4个动作技术组成组合动作技术参与展示或比赛　`evidence-weak·stage`
- `ca_tqN8Um4k` 水上或冰雪类运动- 能做出所学水上或冰雪类运动项目的基本动作和简单组合动作，并参与简化规则、降低要求的游戏和比赛　`evidence-weak·stage`
- `ca_Mug5ByA4` 能说出所学水上或冰雪类运动项目的相关动作术语　`stage`
- `ca_qh7HmucZ` 乐于参与所学水上或冰雪类运动，表现出稳定的情绪　`evidence-weak·stage`
- `ca_jH28dJV9` 能按照要求参与所学水上或冰雪类运动项目的学练和比赛，表现出敢于尝试、不怕失败的意志品质　`evidence-weak·stage`
- `ca_biaChcqn` 能做到每周运用所学水上或冰雪类运动技能进行 3 次（每次至少 0.5 小时）课外体育锻炼　`evidence-weak·stage`
- `ca_dnAe83m7` 掌握所学水上或冰雪类运动项目主要的基本动作技术和组合动作技术，并参与比赛　`evidence-weak·stage`
- `ca_NinXRJme` 能安全地进行所学水上或冰雪类运动，并运用简单的运动损伤处理方法　`evidence-weak·stage`
- `ca_bJmGczGc` 能做到每周运用所学水上或冰雪类运动技能进行 3 次（每次 1 小时左右）课外体育锻炼　`evidence-weak·stage`
- `ca_2nabAiUg` 能解释所学水上或冰雪类运动项目的历史文化、特点与价值　`evidence-weak·stage`
- `ca_dNuPHLY7` 能解释所学水上或冰雪类运动的安全知识，消除运动中的疲劳并进行身心恢复　`evidence-weak·stage`
- `ca_MCgnFGHd` 水平三·掌握所学中华传统体育类运动项目主要的基本动作技术和组合动作技术，并运用所学知识与技能参与对抗演练和半实战比赛　`evidence-weak·stage`
- `ca_9UMJJHMM` 能做到每周运用所学中华传统体育类运动技能进行3次（每次1小时左右）课外体育锻炼　`evidence-weak·stage`
- `ca_kxeeDvnq` 掌握所学中华传统体育类运动项目的完整动作技术，灵活运用所学知识与技能进行半实战、实战对抗练习和比赛　`evidence-weak·stage`
- `ca_jmNk2ZZP` 能描述所学中华传统体育类运动项目的起源、发展与文化的关系　`evidence-weak·stage`
- `ca_mfsRByrb` 能按照规则和要求参与所学新兴体育类运动项目的游戏和比赛　`evidence-weak·stage`
- `ca_3HCmdkGF` 掌握所学新兴体育类运动项目主要的基本动作技术和组合动作技术，并参与该运动项目的展示或比赛　`evidence-weak·stage`
- `ca_jx7DnhJd` 主动参与班级、学校或社区内新兴体育类运动项目的展示或比赛，并能遵守规则　`stage`
- `ca_mk2erS7Y` 能积极参与多种花样跳绳比赛，如《全国跳绳大众等级锻炼标准（花样跳绳）》二级动作配乐自编套路赛、规定4个动作计时/计数赛等　`evidence-weak·stage`

**艺术**（22）

- `ca_HfxxzuJM` 能对音乐在舞蹈、戏剧（含戏曲）、影视（含数字媒体艺术）等艺术形式中的特点和作用作出客观分析与评价　`stage`
- `ca_g6gnMdBZ` 能表达自己的观演感受，有兴趣进行模仿或表演　`stage`
- `ca_5WMXxXvQ` 学会简单的舞蹈基本动作，并能将所学舞蹈动作运用到表演唱及其他综合性艺术表演中　`stage`
- `ca_5n94PBsP` 观察生活中的音乐现象，参与生活中的音乐活动　`evidence-weak·stage`
- `ca_ugMpPh75` 能运用自然界和生活中声音的特点和规律，进行音乐编创与表演　`evidence-weak·stage`
- `ca_abyPrQMA` 会使用相关软件简单地编辑音乐　`stage`
- `ca_zudp9Jrm` 能提出各种构想，并尝试运用各种表现形式和方法，创作富有创意的美术作品　`evidence-weak·stage`
- `ca_rMDduP6H` 能针对不同问题，用美术与其他学科相结合的方式提出解决问题的思路和方案　`stage`
- `ca_Sg5DJac8` 能运用现代媒体艺术的工具和手段，创作动态、多维的美术作品　`stage`
- `ca_zF3qaSwZ` 掌握正确使用工具、材料和媒介的方法　`evidence-weak·stage`
- `ca_7vBE4cRq` 能围绕所居住地区的革命遗址、古建筑或古村落的历史与现实意义，撰写简短的图文相结合的调研报告或制作立体模型　`evidence-weak·stage`
- `ca_Ue6FL796` 能用传统工艺的制作方法制作工艺品　`evidence-weak·stage`
- `ca_3P38eEX7` 能安全使用工具和材料　`stage`
- `ca_2AzxVWAP` 能结合所学舞蹈动作与表现形式，探索、尝试新的舞蹈动作与表现形式　`stage`
- `ca_JZEsgKTW` 掌握对表现现实生活的影视（含数字媒体艺术）作品进行判断、评价的基本方法　`evidence-weak·stage`
- `ca_yVpcjsDP` 能用自己的话简单描述不同音乐的特色　`stage`
- `ca_JhymeDwJ` 运用乐谱进行音乐实践，对乐谱中符号、记号的辨识和表现准确度高　`evidence-weak·stage`
- `ca_tFy2gJGf` 随音乐即兴表演，表情及身体动作能体现音乐情绪和音乐特点　`stage`
- `ca_REF9Npra` 能根据音乐表现需要控制力度、速度和音色等，体现一定的创意　`evidence-weak·stage`
- `ca_TPHn5VhK` 对社会生活中的音乐现象和音乐文化能作出一定的合理分析与评价，在运用信息技术或其他方式选择和运用音乐方面有初步经验　`evidence-weak·stage`
- `ca_ycuSfqnu` 能表明并解释个人兴趣、知识、背景以及其他因素对音乐选择产生的影响　`evidence-weak·stage`
- `ca_cGU2qqAn` 能运用"教育剧场"的方法策划体现时代主题的戏剧活动　`stage`

**语文**（13）

- `ca_q9hNbyTA` 能利用图书馆、网络搜集自己需要的信息和资料，帮助阅读　`stage`
- `ca_JEJnDMSm` 学习运用细节描写等文学表现手法　`evidence-weak·stage`
- `ca_ybVrqvEj` 运用口头和图文结合的方式，表达自己的观点和思考　`stage`
- `ca_mcMv8ynW` 运用跨媒介形式分享研学成果　`evidence-weak·stage`
- `ca_wfwq5QCr` 运用多样形式丰富自己的语言表达，呈现与分享奇思妙想　`evidence-weak·stage`
- `ca_NZrRZvAs` 能尝试根据语文学习经验和生活经验解决日常生活中的问题　`evidence-weak`
- `ca_kbzQXaJB` 能主动梳理、记录可供借鉴的语言运用实例　`evidence-weak`
- `ca_ZdCHzjcQ` 能规范、端正、整洁地书写常用汉字　`not-a-capability`
- `ca_tBrj6hLx` 能使用常用的标点符号，准确地表情达意　`not-a-capability`
- `ca_FP8BngRb` 能从作品中找出值得借鉴的地方，对照他人的语言表达反思自己的语言实践　`evidence-weak·stage`
- `ca_sQszGrR4` 能概括文学作品中的典型形象特征和典型事件，并归纳总结出一些文化现象　`evidence-weak·stage`
- `ca_ipAFj2JC` 能运用实证性材料对相关问题作出合理的解释与推断　`evidence-weak·stage`
- `ca_zWTWJPum` 能通过梳理、分析材料提炼出自己的看法　`evidence-weak·stage`

**数学**（11）

- `ca_UkuuZKi6` 能进行简单小数和分数的四则运算和混合运算（不超过三步），并说明运算过程　`evidence-weak`
- `ca_Z3Qq9cZj` 能在具体情境中描述成正比的量 \(\frac{y}{x} = k (k \neq 0)\)　`not-a-capability`
- `ca_Ps3Uk6yB` 能表达具体情境中负数的实际意义　`stage`
- `ca_tV2fWetY` 能通过对多个事例的归纳、比较，感悟负数可以表达与正数相反意义的量　`evidence-weak·stage`
- `ca_euHBPae6` 能按校园的方位和场所的位置，依据绘图比例绘制简单的校园平面图　`evidence-weak·stage`
- `ca_zuvjgu93` 会用扇形统计图整理调查结果　`stage`
- `ca_9r989rnQ` 能根据问题的背景，通过对问题条件和预期结论的分析，构建数学模型　`evidence-weak·stage`
- `ca_vz9wYSMe` 能根据问题背景分析结论的意义，反思模型的合理性，最终得到符合问题背景的模型解答　`evidence-weak·stage`
- `ca_QYNai8DJ` 结合现实生活情境，尝试用数学语言描述生活中的实际问题　`stage`
- `ca_C2tLsEX7` 能绘制简单的数据统计表和统计图　`stage`
- `ca_VrU3gdX2` 能用字母表示数量关系和规律　`evidence-weak·stage`

**劳动**（10）

- `ca_DYVeXsYS` 能表达参与农业劳动后收获的快乐，初步具有关心、照顾身边常见动植物的责任心和农业生产安全意识　`evidence-weak·stage`
- `ca_FxakAyPG` 能简单表达自己的方案构想，并使用常用工具制作简单的传统工艺作品　`stage`
- `ca_ub5qsGEk` 参与社区环境维护，为他人创造更好的公共空间　`stage`
- `ca_8DQSrmYz` 能根据劳动需要设计与制作传统工艺作品　`stage`
- `ca_CTKuJ22A` 能根据需要，使用某项新技术设计制作简单的产品模型或原型，并独立完成产品的技术测试　`evidence-weak·stage`
- `ca_xfYzUpwt` 能说明现代服务业劳动的革新与发展趋势　`evidence-weak·stage`
- `ca_2AdH7Npu` 参与社区环境治理，进行社区公园环境优化、公共健身设施维护等　`evidence-weak·stage`
- `ca_mFpC6WRb` 参与社区公共卫生服务，进行疫情防控宣讲等　`stage`
- `ca_gqFzPR3v` 在简单的工艺制作劳动、农业劳动中，初步掌握简单的手工技能　`stage`
- `ca_XAaUhxPM` 会使用简单的工具　`stage`

**信息科技**（7）

- `ca_yE2iQxpz` 能在日常学习与生活中健康、安全地使用数字设备　`stage`
- `ca_VAJX6zGW` 能列举在线社会对学习与生活的影响　`stage`
- `ca_c5gAzcCL` 能进一步判断解决同一问题的不同算法在时间效率上的高低　`stage`
- `ca_A8CaTUKW` 能在实验系统中通过编程等手段验证过程与控制系统的设计　`evidence-weak·stage`
- `ca_yQezhwDP` 能分辨输入与输出环节中的数据是开关量还是连续量，并能运用逻辑和数值运算设计简单的处理环节　`evidence-weak·stage`
- `ca_TLGRsdrr` 能设计用计算机实现过程与控制的方案，并在实验系统中通过编程等手段加以验证　`stage`
- `ca_DmzZGSjw` 设计并搭建具有数据采集、实时传输和简单控制功能的简易物联网系统　`stage`

**英语**（3）

- `ca_EgierWdk` 初步具备比较和识别中外文化异同的能力　`stage`
- `ca_jTbZaU38` 能根据写作任务的要求，收集、整理和归纳相关语言和文化知识　`evidence-weak·stage`
- `ca_y3Mwbi8J` 能根据评价标准，对自己和同伴的写作进行评价和修改　`evidence-weak·stage`

**道德与法治**（2）

- `ca_wdYtN6pi` 能够讲述老一辈无产阶级革命家和我国著名英雄模范人物的事迹及其榜样示范作用　`stage`
- `ca_heVjNfyy` 能够结合生活中的实例讲述职业没有高低贵贱之分（政治认同、道德修养、法治观念）　`stage`

**生物学**（1）

- `ca_FWuz9u9P` 运用结构与功能相适应、生物与环境相适应的观点，阐明基因组成和环境共同决定生物的性状　`stage`

</details>


## v1.9 — 2026-09-28

### 学段按课标原件改正 407 条

430 条锚点的学段不可信：标成 G1–G9 的占位，或 disputed 里挂着 stage 异议。
原先按「页 → 学段标题」前向填充的做法（`stage_by_page.py`）对两种版式无能为力：
科学、体育的内容要求 / 学业要求是一张表，1～2 / 3～4 / 5～6 / 7～9 年级（体育是水平一～四）是**行**，
同一页四个学段都有；「第二学段（3～4年级）」这类横幅式标题，页索引没认出来。

这一版**逐条看了原件的扫描页**（`~/Downloads/2022全套新课标/`，11 份义教课标），判读这句话落在哪个学段的行或标题下，
每条带页码和依据（`reports/stage-judgments-2026-09-28.jsonl`）。只收高置信的 414 条；低置信 13 条、找不到 3 条不动。
落库见 `tools/apply_stage.py`：旧值记进 `provenance.stageFixedFrom`，恰好是一个学段的 `srcStage` 记「第X学段」
（艺术按它自己的 1-2／3-5／6-7／8-9）。

- 抽查：科学 PDF 第 31 页「会用排水法测量物体的体积」确在 7～9 年级行，判读正确
- 体育的专项运动技能、体能在原件里只对水平二～四（表 2），没有一条该从 G1 起
- 原先 disputed 里的 stage 异议，**复审给的年级也常常是错的**（如显微镜观察细胞，复审说 7–9，原件是 5～6）——
  学段一律以原件为准；异议记成 resolved 附页码
- stage 异议撤销后没有别的异议、且过可判定闸的升 ai-reviewed；还挂着证据异议的，随后 `evfix_round2` 重写证据，又升了一批

### 两类抽取残渣

**复述课程安排的伪断言**：「能说出 7~9 年级学生应观察动物取食、争斗等行为」「能说出第四学段的学习任务 1 是演出舞台剧目」。
孩子会不会说出课标给哪个年级排了什么，不是能力。它们其实是**原句层**：真正可判定的能力是由它们转写出来的子条
（「能描述至少两种所观察到的动物取食行为或争斗行为的具体表现」），当初套上「能说出…应…」是为了让原句层混过可判定闸。
处置（`tools/fix_restates_plan.py`）：拆掉框子、还原成原句说的那件事，旧句记进 `provenance.verbFixedFrom`；
还原后 13 条过不了闸（「观察…」是过程），进 disputed、挂 undecidable（源链不断，转写子条照旧可引用）；2 条过闸保持可引用；
2 条弃用：

- `ca_z3MvQNLP` 能说出 3~7 年级舞蹈学习任务中「小型歌舞剧表演」和「即兴表演」的名称 → supersededBy `ca_Go3P6uox`
- `ca_HitSfjqU` 能说出 3~7 年级影视的学习任务包括「领略蒙太奇」和「接触多媒体」—— 只是学习任务名，拆掉框子不剩可判定的能力

可判定闸新增 `RESTATES_PLAN`：在全部可引用锚点上跑，恰好命中这 17 条 + 1 条前缀残渣，零误伤。
第一版处置是全部弃用 —— validate 当场拦下：弃用源等于让 11 条转写成了孤证。

**断言开头粘着表格行标签**（4 条）：「~6年级能说出太阳系的基本结构」「水平三·掌握…」等，去掉前缀，
其余一字不动，剥掉的记进 `provenance.leadStripped`。

### 边

学段改正后有 28 条 soft 边学段倒挂（先修晚于被修）—— 它们是在错的 G1–G9 占位上建的，方向从来没有依据；
连同指向 2 条新弃用锚点的 8 条，共 36 条由 `retire_orphan_edges.py` 退休进 `retired/`（留档不删）。

### 还开着的

- 英语 p187 的 `ca_jTbZaU38` `ca_y3Mwbi8J`：判读时全书 OCR 搜不到这两句原文，疑似转述；两条本来就是 disputed，没动
- `ca_mJsmjWw3` `ca_YEtV9Zer` 放在义教文件里，原文其实出自高中课标 —— 并入「272 条高中锚点放错文件」那件事一起处理
- v1.8 恢复的锚点，弃用时退休的边没有跟着恢复（`retired/edges.jsonl` 里还躺着）

可用锚点 **3,263 → 3,444**。
