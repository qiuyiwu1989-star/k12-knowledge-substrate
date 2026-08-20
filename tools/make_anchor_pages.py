#!/usr/bin/env python3
"""
make_anchor_pages.py — 每条存活锚点一个详情页 /a/<id>/。

    python3 tools/make_anchor_pages.py          # → anchor-pages/

## 这个页面为什么存在

/list 能翻，图谱能看结构，但**都答不了「这一条到底能不能用」**。
底座对外的承诺是「L4 的应用不得自己定义知识点，只能引用 L0 的 ID」，
那么每一个 ID 就得有一个地方，一眼回答：能不能引、凭什么、缺什么、谁说的、错了找谁。
详情页就是这个地方 —— 它不是「把字段铺开」，是**把这条锚点的可信度摊开给人看**。

## 三条硬规则（specs/003-anchor-detail.md）在代码里的落点

1. **空字段显示为空并注明「尚未定义」，禁止隐藏或折叠。**
   实现上只有一个入口 `row()`，而且它**没有**「空就不渲染」这条分支，也不许加。
   空值渲染成 `<i data-k=xxx></i>`，靠共享 CSS 的 `i[data-k]:empty::after` 打出「尚未定义」。
   这不是防御性编程，是防自己 —— 一旦允许 `if not v: return ''`，
   页面半年后会自动美化成「看起来都齐了」，而这个底座 2,158 条里
   assessmentSpec 是 0 条、objections 是 0 条、边的 type/failureSignature 是 0 条。
   **那些 0 才是这一页最重要的信息。**

2. **citable 是页面顶部的红绿灯。** 仓库没有 `citable` 字段（specs/000-naming.md），
   由 `reviewStatus ∈ {auto-confirmed, expert-confirmed, ai-adjudicated}` 现推。
   不新增冗余字段的理由和 README 一致：同一件事不存两份，否则必然对不上。
   红灯时**理由与红灯同级、同为静态 HTML**（当前档位 + 该档位的含义），
   不进 CSS、不进 JS、不折叠 ——「不能用」和「为什么不能用」分开显示等于没说。

3. **difficulty / averageMasteryAge / peerPercentile 在 2,158 个页面里一次都不出现。**
   （可以 `grep -r` 验，计数是 0。）这三个在 schema 里标着 `forbidden`，验收器 F201 拦。
   它们的缺席是设计结论，不是没来得及做，所以页脚方法论必须主动声明 ——
   不声明的话，看的人只会以为是漏了。声明文本在共享 a.js 里存一份。

## 命名换算

spec 用交接包命名，仓库用另一套，对照表见 specs/000-naming.md。
换算集中在 `CITABLE / STATUS_CN / SRC_CN / LBL` 和 `panel_*()`：
claim→statement，is_our_assertion→evidenceSource=='capability-rewrite'，
assertion_rationale→provenance.why，standard_quote→provenance.srcText，
credibility_tier→reviewStatus，cross_links→crosscutting/practice（横切，不是先修边）。

## 四个视图是切页不是四份数据

引用（开发者）／判定（教师）／成长（家长）／溯源（研究者）。
**用 radio + CSS `:checked ~` 实现，零 JavaScript。** 三条理由，都不是洁癖：
  · 原生 radio group 天生就是 ARIA tabs 的键盘行为（左右箭头切换、Tab 进出、focus 可见），
    自己用 JS 写一遍只会写出一个更差的；
  · 没有 JS 也能切视图 —— 一个「必须跑 JS 才能看见字段」的透明度页面是自相矛盾的；
  · 2,158 个页面，每页省下的每一行都要乘以 2,158。

**关系、四套标签、清单条目、异议不进任何一个视图**，放在视图下方常显：
四类读者都要看，塞进每个 panel 就是同一份 HTML 出现四遍 —— 页面大四倍，
而且四份迟早会改歪一份。

## 体积：第一版 32MB，重做成 15MB 的那次

整站现在 12MB。第一版每页把字段名、「为什么空」的解释、方法论都写进 HTML，
平均 15.4KB/页 × 2,158 = **32MB**，整站直接翻近四倍。拆开看，
15KB 里有 8KB 是**每一页都一模一样的字段名和说明文字**。

所以分工改成：
  · **每页 HTML 只放这一条锚点自己的数据**，加上红绿灯理由（规则 2 要求静态）
    和「这一条的空字段有哪些」这个结构本身（规则 1 要求静态：
    `<i data-k=mastery></i>` 出现在 HTML 里，就是这一页在说「我缺 mastery」）；
  · **字段名 + 「尚未定义」四个字由共享 `_assets/a.css` 打出**
    （`i[data-k=x]::before` 给名字、`i[data-k]:empty::after` 给标记）。
    2,158 份同样的字段名 = 11MB，一份 = 5KB。改完平均 7.1KB/页，合计 15MB。
    代价有两个，都认：字段名复制不走（浏览器渲染出来了，但选中复制带不走）；a.css 没加载时字段名和「尚未定义」一起消失。
    第二个能接受，是因为它**对空字段和有值字段一视同仁** —— 掉了 CSS 就是所有字段名
    全没有，不会出现「空的那些看起来像被省略了、有值的那些看起来齐了」这种偏向性失真。
    页面在任何一种状态下都不会撒谎，这是选这条路的底线；
  · **常量长句（每个空字段「为什么空」、页脚方法论、全库统计）在共享 `a.js` 的 W 表**，
    由 JS 插在 `<i>` 后面（**不是插进去** —— 插进去 `:empty` 就不成立，
    「尚未定义」会当场消失，这个坑踩过一次）。

CSS/JS 走相对路径 `../_assets/`，anchor-pages/ 整个搬到 dist/ 任何位置都不用改路径，
直接 file:// 打开单页抽查也不会白板。

统计数字全部从 `anchors/*.jsonl`、`edges/*.jsonl`、`lists/*/*.jsonl` 现算，
manifest.json 只取版本号和日期。**没有一个手打的数** —— 手打的数字半年后一定是假的。

## 局部子图只画一跳

前置 1 跳 + 后继 1 跳，不放全图（全图在 / 和 /2d）。SVG 手写，节点是 `<a>`，键盘可达。
每侧最多画 6 个，文字列表给全量（后继超过 12 条时列前 12 并报总数）——
最大的一条有 39 个后继，全画出来是一团黑线，看不出任何东西。

## 两处最容易让人误会的，页面上都写明了

  · **边的 type / failureSignature 现在 100% 是空的**（重标还没跑，specs/001）。
    照规则 1 显示「尚未定义」，不因为全空就把这一块删掉 —— 删掉就看不出这块没做。
  · **evidenceSource == 'capability-rewrite' 那 214 条不是课标转述**，是我们自己的教育判断。
    横幅醒目标注 + 显示 provenance.why + 一个「这条应该撤掉」的入口。
    入口只落 localStorage 并给出可复制文本，**没有后端**（spec 明写不做工作流）。

## 不做

  · 不批量生成 assessmentSpec、不编课标引文 —— 缺就是缺，编了就污染底座且不可追溯。
  · 不写 license_note 的内容 —— 留位置、留空，等法律意见。自行撰写的法律表述是负资产。
  · 不做后端异议工作流、不做登录、不显示任何学生状态
    （家长视图里显示「需接入档案」，L3 永不进仓库）。
  · 不写 dist/ —— 主进程统一并入，本工具只产 anchor-pages/。
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
from citable import CITABLE as CITABLE_SET   # noqa: E402
import collections, html, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'anchor-pages'
REPO = 'https://github.com/qiuyiwu1989-star/k12-knowledge-substrate'

# 交接包的 citable 在仓库里没有对应字段，由 reviewStatus 现推（specs/000-naming.md）
CITABLE = CITABLE_SET   # 定义见 mappings/citable.json，不在这里写第二遍

STATUS_CN = {
    'auto-confirmed':   ('机械可判定', '判定客观（写对／读对／数得清），根本不需要人复核'),
    'ai-adjudicated':   ('AI 裁定，待人工异议',
                         'AI 带全部材料做过裁定，计入可用，但人还没签字——'
                         '它成立的前提是「没人反对」，不是「有人认可」'),
    'expert-confirmed': ('学科主编签字', '有具体的人对这条负责，签字记录在 endorsements'),
    'ai-reviewed':      ('只过了 AI 学科审查', 'AI 审查是筛子不是合格证，没有人看过这一条'),
    'disputed':         ('有争议，已挂起', '机械闸与 AI 判断冲突，或原句本身有问题'),
    'llm-proposed':     ('模型提议，无人看过', '没有经过任何复核'),
}
SRC_CN = {
    'curriculum-content':          '义务教育课标正文',
    'curriculum-content-gaozhong': '高中课标正文（零模型调用，不改一个字）',
    'curriculum-appendix':         '课标附录（字表／词表／背诵篇目）',
    'curriculum-example':          '课标示例',
    'capability-rewrite':          '能力转写——不是课标转述，是我们自己的教育判断',
    'repaired-from-source':        '按课标原文回修',
    'llm-draft':                   '模型起草',
    'fallback':                    '兜底模板（把断言又说了一遍，见 docs/disputed.md）',
}
TRACK_CN = {'DAG': '强先修（数理化）', 'LIST': '清单／覆盖（字表词表篇目）',
            'MATRIX': '能力维度 × 主题（史地生政科）'}
TYPE_CN = {'CONCEPTUAL': '概念性', 'KNOWLEDGE': '知识性（「知道 X」，本身不是能力）',
           'LANGUAGE': '语言性', 'META': '元认知', 'PROCEDURAL': '程序性',
           'REPRESENTATIONAL': '表征性'}
STAGE_CN = {'G1': '一二年级', 'G2': '一二年级', 'G3': '三四年级', 'G4': '三四年级',
            'G5': '五六年级', 'G6': '五六年级', 'G7': '初中', 'G8': '初中', 'G9': '初中',
            'G10': '高中', 'G11': '高中', 'G12': '高中'}
EV_KIND_CN = {'cooccurrence': '错题共现统计', 'edition-order': '多版本教材编排共识',
              'expert': '老师判断', 'llm': '模型提议（仅兜底）',
              'set-containment': '集合包含实测', 'standard-hierarchy': '课标内在层级'}

# ── 字段名与「为什么空」的唯一定义处 ────────────────────────────────────────
# key -> (页面上显示的字段名, 补充说明)。名字进共享 CSS，说明进共享 JS。
# 说明里的 {live}/{edges}/… 由现算的全库统计填。**这里一个手打的数都没有。**
LBL = {
    # 引用 · 开发者
    'id':    ('锚点 ID（id）', '无语义、永不复用。禁止编入学科／年级／单元——那些都会变。'),
    'sv':    ('schemaVersion', ''),
    'st':    ('状态（deprecated）', ''),
    'sup':   ('后继 ID（supersededBy）', '弃用时才有：档案里的引用不能悬空，所以锚点只弃用不删除。'),
    'drop':  ('弃用原因（dropReason）', '与 supersededBy 二选一必填。存活的锚点两个都空。'),
    'cit':   ('能否被 L3 档案引用（citable）',
              '仓库里没有 citable 字段，它由 reviewStatus 现推：'
              'auto-confirmed／expert-confirmed／ai-adjudicated 三档为真。'
              '同一件事不存两份，否则必然对不上。'),
    'trk':   ('结构档位（track）', '决定这条锚点允许存在什么边，校验器强制执行。'),
    'typ':   ('知识类型（type）', '这六个值是我们自造的，外部没法对齐；'
                                'Anderson & Krathwohl 四类知识维度的映射还没建。'),
    'file':  ('数据文件', ''),
    'grep':  ('取这一条', ''),
    'api':   ('逐条 API（api_endpoint）',
              '没有逐条 API。全量 JSONL 直取 /data/anchors/ ——'
              '整站没有后端，{live:,} 条锚点全部是静态文件。'),
    'lic':   ('许可说明（license_note）',
              '内容留空，等法律意见。课标引文的权利归教育部，'
              '可用 scripts/strip-srctext.mjs 一键剥离（见 PROVENANCE.md）。'
              '这里不自行撰写任何法律表述。'),
    'objn':  ('公开异议数（objections）',
              '异议只落库，不做工作流（谁看、怎么处理待定）。'
              '全库现有 {obj} 条锚点带公开异议。'),
    'pmeth': ('溯源方法（provenance.method）', ''),
    # 判定 · 教师
    'claim': ('能力断言（statement）', '判据只有一个：能不能对一个具体孩子在某一时刻回答「会／不会」。'),
    'before': ('改写前原句（statementBefore）', '改写过的锚点必须留下原句，否则无从判断改写对不对。'),
    'vo':    ('行为动词 ／ 作用对象（verb / object）', '两者构成去重签名。'),
    'cog':   ('认知层级（cognitive）',
              '课标自己的行为动词分级（了解／理解／掌握／运用）。这是国内官方表述，'
              '不是 Bloom —— 两套并存、互不覆盖。'),
    'ev':    ('掌握证据（evidence）',
              '每条都必须是可观察的行为，不是感受。全库有 {fallback} 条的 evidence 是兜底模板，'
              '把断言又说了一遍 —— 那些不构成证据。'),
    'ask':   ('检核问句（assessment）', '机械生成：实词不得超出断言与证据。它是问法，不是判据。'),
    'spect': ('判定方式（assessmentSpec.type）',
              '全库 {live:,} 条存活锚点里，有 assessmentSpec 的是 {spec} 条。'
              '空着是对的：用模型批量编样题会污染底座且无法追溯。'),
    'spec':  ('判定细则（assessmentSpec.spec）', '同上，不批量生成。'),
    'pass':  ('通过判据（assessmentSpec.passCriterion）',
              '要说清做对几道算会。说不清的，等于把判断又推回给人。'),
    'decay': ('保持期（assessmentSpec.decayHint）', '隔多久不练就不算会。没有真实作答数据之前编不出来。'),
    'mastery': ('掌握判据（mastery）',
                '要同时写明次数、条件、保持期，三者缺一不可（掌握学习，Bloom 1968）。'
                '字段还没建 —— 它会引入我们自己的教育判断，必须走 capability-rewrite 那一层的待遇：'
                '单独标来源、单独统计、能被单独撤掉、永远够不到 auto-confirmed。'),
    'vari':  ('变式空间（variations）',
              '同一能力的题目变式边界决定「会」的边界。至少两个变式，'
              '且能说明哪一个变式一旦不会就算不会。字段还没建。'),
    'misc':  ('典型错误（misconceptions）',
              '判「会」看行为，判「不会」看错法。「计算 300-198 时竖式退位出错」'
              '和「不知道可以凑整」是两种完全不同的不会。字段还没建。'),
    'nonex': ('反例：什么表现算不会（non_examples）', '字段还没建。'),
    'aiis':  ('AI 复核挑出的问题（aiIssues）',
              'AI 复核不是教师复核，它最高只能把这条抬到 ai-reviewed。'),
    'tri':   ('机械分诊桶（triageBucket）', '分诊不是复核。'),
    # 成长 · 家长
    'plain': ('这一条说的是什么（大白话 plain_zh）',
              '给家长看的说法，字段还没建。页面上现在给的是课标的措辞。'),
    'ask2':  ('家长可以这样问', '这是问法，不是判据 —— 孩子答上来不等于「会」。'),
    'cog2':  ('学到什么程度', '课标的行为动词分级：了解／理解／掌握／运用。'),
    'stage': ('大概哪个学段（stageHint）',
              '学段提示，非权威。真正的年级来自 L2 编排层（教材版本 × 年级），'
              '同一条能力在不同教材落在不同年级。'),
    'unlk':  ('会了之后能开始学什么（unlocks）',
              '这些先修关系全部来自模型提议，还没有被真实作答数据检验过。'),
    'life':  ('生活中的表现举例',
              '字段还没建。编一个出来很容易，但那不是从课标来的，也没人核过。'),
    'kid':   ('孩子当前状态',
              '这里永远不会显示你孩子的状态。掌握记录属于 L3 档案层，'
              '只存在使用方自己的设备或系统里，永不进这个仓库。'),
    'forbid': ('难度分 ／ 平均掌握年龄 ／ 同龄百分位', ''),   # ← 特判，见 CSS 与 W['forbid']
    # 溯源 · 研究者
    'quote': ('课标原文（provenance.srcText）', '句子级引文。溯源、接地校验、模型污染闸全靠它承重。'),
    'src':   ('出处学科 ／ 页码 ／ 学段', '页码指课标 PDF 的页码。'),
    'course': ('课程 ／ 编号（srcCourse / srcCode）', ''),
    'meth':  ('抽取方法（provenance.method）', '转写是机器做的，必须留痕。'),
    'agree': ('多次投票一致度（srcAgree）', '注意：温度 0 的重复投票不算独立证据。'),
    'esrc':  ('证据来源层（evidenceSource）',
              '全库 {rewrite} 条属于 capability-rewrite —— 那一层不是课标转述，'
              '是我们自己的教育判断，validate 对它有六条专门的闸。'),
    'derv':  ('转写自哪条知识锚点（provenance.derivedFrom）', 'capability-rewrite 专用，强制同学科。'),
    'why':   ('我们为什么加这一条（provenance.why）',
              '只有 capability-rewrite 层才有：我们凭什么在课标之上另立这条断言。'),
    'tier':  ('可信度档位（reviewStatus）',
              '全库 {live:,} 条存活锚点里，可被档案引用的有 {usable} 条，'
              '教师签过字的有 {expert} 条。锚点数不重要，可用锚点数才重要。'),
    'acb':   ('auto-confirmed 的依据（autoConfirmBasis）',
              '这一档的含义是「判定客观、根本不需要人」（字表词表这类数得清的东西），'
              '不是「AI 觉得没问题」。'),
    'by':    ('复核人（reviewedBy）', '老师的复核痕迹累积起来就是他自己的教学序列。'),
    'end':   ('教师签字（endorsements）',
              'expert-confirmed 的凭据：谁、什么时候、说了什么。全库现有 {expert} 条。'),
    'disp':  ('复核异议记录（disputes）',
              '不删条目、只降级 ——「谁在什么时候说它不对」必须查得到。'),
    'adj':   ('AI 裁定（adjudication）', 'pendingObjection 标明这条是「待人工异议」，不是定论。'),
    'ick':   ('对抗验证（independentCheck）',
              '模型看不到断言、只读原文自己抽事实，再机械比对。换的是信息流不是措辞 ——'
              '让它「再审一遍」只会确认自己。'),
    'rep':   ('回修记录（repair）', ''),
    'objl':  ('公开异议（objections）', ''),
    # 边
    'et':    ('关系类别（type）',
              'component／instrument／semantic／convention（specs/001）。'
              '全库 {edges:,} 条边里有 {etype} 条标了这个字段 —— 重标还没跑。'
              '判据只有一条：说得出不具备前置的孩子在后继上具体怎么失败，说不出的一律是 convention。'),
    'es':    ('强度（strength）', 'hard = 没有它就学不了。hard 边必须有至少一条非 llm 证据，校验器强制。'),
    'ef':    ('失败表现（failureSignature）',
              '不具备前置时后继上的具体失败表现 —— 这是边的判据本身。'
              '全库 {edges:,} 条边里有 {efail} 条写了。空泛词（基础不牢／能力不足）一律拒绝：'
              '说不出具体失败，就是说不出这条边。'),
    'eg':    ('进推理图（inInferenceGraph）',
              'convention 边恒为 false —— 它是教材编排顺序，不是能力依赖。'),
    'er':    ('理由（reason）', ''),
    'ek':    ('证据类型（evidence.kind）', ''),
    'erv':   ('边的复核档位（reviewStatus）', '三源一致的边可直接 auto-confirmed，不占老师的复核时间。'),
    'ec':    ('反例计数（counterEvidenceCount）',
              '大量孩子没掌握前置却掌握了后继，这条边就是错的。要等 L3 聚合回流，现在恒为 0 或缺省。'),
    # 四套标签
    'tcog':  ('课标行为动词分级（cognitive）', ''),
    'tlit':  ('学科核心素养（literacy）', '取值必须在该学科课标印的闭合清单内。'),
    'tcc':   ('跨学科通用概念（crosscutting）',
              'NGSS 七个通用概念，闭合词表。文科一律留空 —— 词表不适用，宁可空着。'),
    'tpr':   ('科学与工程实践（practice）', 'NGSS 八项实践，闭合词表。与 crosscutting 正交。'),
    'tccw':  ('打这组横切标签的理由（crosscuttingWhy）', ''),
    'tak':   ('Bloom / A&K 知识维度映射',
              '还没建。要建也只能建成一次性的、逐条可查的映射表，不是让模型现场判断。'),
    # 清单
    'li':    ('清单条目数（attached_list_items）',
              '清单条目本身不是锚点：「会写「人」字」是锚点，「人」是清单条目。'
              '全库 {items:,} 条清单条目挂在 {item_anchors} 条锚点上。'
              '这里只给条数 —— 3,500 个字铺开，页面没法看。'),
    'lt':    ('分学段累计目标（stageTargets）', '数量目标，不是字表切分 —— 课标不说哪些字属于哪个学段。'),
}

# 不挂在字段上的整段说明，同样只存一份
NOTES = {
    'iso':  '全库 {live:,} 条里有 {iso} 条既无前置也无后继。'
            '这不是「孤立点」的美学问题，是这条锚点还没被接进任何结构 —— 照实显示。',
    'reldir': '上排是前置（学这一条之前要先会的），下排是后继（会了之后能开始学的）。'
              '只画一跳，全图在首页。跨学科的联系主要不在这里 —— 它在下面的横切标签上。',
    'tags': '这四套是标签，不是层，互不排斥：一条锚点可以同时带四套里的值，也可以一套都不带。'
            '不要拿其中任何一套当分类主键。',
    'listitems': '清单条目只给条数，不铺开。',
    'objway': '异议只记在你这台设备上，没有后端。要让它被看见，请把记下来的文字提到 GitHub issue。',
    'objtip': '这条记录只在你这台设备上。要让它被看见，请提到 ' + REPO + '/issues',
    'rwtip':  '这条记录只在你这台设备上。要让它被看见，请提到 ' + REPO + '/issues',
    'rw':   '它属于 capability-rewrite 层 —— 全库 {rewrite} 条，是唯一一层由我们自己下的教育判断，'
            '在课标的「知道 X」之上另立了一条可判定断言。它永远够不到 auto-confirmed。',
    'forbid': '这三个字段在 schema 里标着 forbidden，验收器 F201 拦截。'
              '没有真实作答数据时它们全是编的；而横向比较的入口一旦开了就再也关不上。',
    'm1':   '空字段在这一页显示为「尚未定义」，不折叠、不隐藏。'
            '缺字段的可见性就是数据质量的可见性 —— 允许折叠，页面就会自动美化成「看起来都齐了」。',
    'm2':   '这一页没有难度分（difficulty）、没有平均掌握年龄（averageMasteryAge）、'
            '没有同龄百分位（peerPercentile）。这三个字段在 schema 里标着 forbidden，'
            '验收器 F201 拦截。没有真实作答数据时它们全是编的；'
            '而横向比较的入口一旦开了就再也关不上。它们的缺席是设计结论，不是没来得及做。',
    'm3':   '页面上每一个数都是从 anchors/、edges/、lists/ 现算的，没有一个是写死的。'
            '本次生成：{live:,} 条存活锚点、{edges:,} 条边、{items:,} 条清单条目、{disc} 个学科；'
            '其中可被档案引用 {usable} 条，教师签过字 {expert} 条。',
}


def esc(x):
    return html.escape('' if x is None else str(x), quote=True)


def empty(v):
    return v is None or v == '' or v == [] or v == {}


def row(k, val, raw=False):
    """字段的唯一渲染入口。

    ★ 这里**没有**「空就不渲染」的分支，而且不许加（见文件头规则 1）。
      空 → `<i data-k=xxx></i>`，字段名和「尚未定义」由共享 CSS 打出。
      非空 → 同一个壳，里面塞值。壳一样，才不会出现「空的那些长得像被省略了」。
    """
    if empty(val):
        return f'<i data-k={k}></i>'
    if raw:
        body = val
    elif isinstance(val, (list, tuple)):
        body = '<ul>' + ''.join(f'<li>{esc(x)}</li>' for x in val) + '</ul>'
    else:
        body = esc(val)
    return f'<i data-k={k}>{body}</i>'


def cut(s, n):
    s = str(s)
    return s if len(s) <= n else s[:n] + '…'


# ── 局部子图（前置 1 跳 + 后继 1 跳）────────────────────────────────────────
GW, NH, MAXG = 720, 34, 6


def _band(items, y, kind):
    if not items:
        return '', []
    n = len(items)
    slot = (GW - 20) / n
    rw = min(150, slot - 10)
    frag, xs = [], []
    for aid, st, dep in items:
        cx = 10 + slot * (len(xs) + .5)
        xs.append(cx)
        inner = (f'<rect class="n {kind}{" dep" if dep else ""}" x="{cx - rw / 2:.0f}" y="{y}" '
                 f'width="{rw:.0f}" height="{NH}" rx=8 />'
                 f'<text x="{cx:.0f}" y="{y + 21}" text-anchor=middle>'
                 f'{esc(cut(st, max(3, int(rw / 12) - 1)))}</text>')
        frag.append(inner if dep else f'<a href="../{aid}/">{inner}</a>')
    return ''.join(frag), xs


def subgraph(pres, sucs, me):
    """只画一跳。全图在 / 和 /2d，这里再画一次全图等于什么都没画。

    「另有 N 条」不画进 SVG —— 画在 y=7 会被顶边裁掉，画在右边会和最右一个节点撞上。
    图外的话就用图外的 HTML 说。
    """
    y0, y1, y2 = 8, 96, 184
    fp, xp = _band(pres[:MAXG], y0, 'pre')
    fs, xs = _band(sucs[:MAXG], y2, 'suc')
    fm, xm = _band([(me, '本条', False)], y1, 'me')
    cx = xm[0]
    ln = ''.join(f'<line x1="{x:.0f}" y1={y0 + NH} x2="{cx:.0f}" y2={y1} />' for x in xp)
    ln += ''.join(f'<line x1="{cx:.0f}" y1={y1 + NH} x2="{x:.0f}" y2={y2} />' for x in xs)
    # 方向标放在两排之间的左侧空档：那里只有向中心汇聚的连线，不会和节点撞。
    lab = (f'<text class=lb x=10 y={(y0 + NH + y1) // 2 + 4}>↑ 前置</text>'
           f'<text class=lb x=10 y={(y1 + NH + y2) // 2 + 4}>↓ 后继</text>') if (xp or xs) else ''
    return (f'<svg class=g viewBox="0 0 {GW} 240" role=img '
            f'aria-label="局部子图：{len(pres)} 条前置在上，{len(sucs)} 条后继在下">'
            f'{ln}{fp}{fm}{fs}{lab}</svg>')


# ── 四个视图 ───────────────────────────────────────────────────────────────
def panel_cite(a, src_file, cit, objn):
    """引用（开发者）：id / status / successor_ids / citable / api_endpoint / license_note"""
    p, aid = a.get('provenance') or {}, a['id']
    return ''.join([
        row('id', f'<code>{esc(aid)}</code>', raw=True),
        row('sv', a.get('schemaVersion')),
        row('st', '存活（deprecated: false）' if not a.get('deprecated') else '已弃用（deprecated: true）'),
        row('sup', a.get('supersededBy')),
        row('drop', a.get('dropReason')),
        row('cit', ('可以' if cit else '不可以') + f'（由 reviewStatus = {a["reviewStatus"]} 推出）'),
        row('trk', f'{a["track"]} · {TRACK_CN.get(a["track"], "")}'),
        row('typ', f'{a["type"]} · {TYPE_CN.get(a["type"], "")}'),
        row('file', f'<a href="/data/anchors/{esc(src_file)}">anchors/{esc(src_file)}</a>', raw=True),
        row('grep', f'<code>grep \'"{esc(aid)}"\' anchors/{esc(src_file)}</code>', raw=True),
        row('api', None),
        row('lic', None),
        row('objn', f'{objn} 条'),
        row('pmeth', p.get('method')),
    ])


def panel_judge(a):
    """判定（教师）：claim / non_examples / assessment_* / failure_modes / pass_criterion"""
    spec = a.get('assessmentSpec') or {}
    ev = a.get('evidence') or []
    if ev and a.get('evidenceSource') == 'fallback':
        ev_html = ('<p class=warn>这几条是<b>兜底模板</b>——把断言又说了一遍，不构成证据。</p>'
                   '<ul>' + ''.join(f'<li>{esc(x)}</li>' for x in ev) + '</ul>')
    else:
        ev_html = ('<ul>' + ''.join(f'<li>{esc(x)}</li>' for x in ev) + '</ul>') if ev else None
    ai = a.get('aiIssues') or []
    return ''.join([
        row('claim', a['statement']),
        row('before', a.get('statementBefore')),
        row('vo', f'{a["verb"]} ／ {a["object"]}'),
        row('cog', a['cognitive']),
        row('ev', ev_html, raw=bool(ev)),
        row('ask', (a.get('assessment') or '').replace('{{name}}', '孩子') or None),
        row('spect', spec.get('type')),
        row('spec', spec.get('spec')),
        row('pass', spec.get('passCriterion')),
        row('decay', spec.get('decayHint')),
        row('mastery', None),
        row('vari', None),
        row('misc', None),
        row('nonex', None),
        row('aiis', [f'{x.get("type")}：{x.get("detail") or ""}' for x in ai] or None),
        row('tri', a.get('triageBucket')),
    ])


def panel_grow(a, sucs):
    """成长（家长）：plain_zh / unlocks / 生活中的表现举例 / 孩子当前状态"""
    sh = a.get('stageHint') or {}
    stage = (f'{STAGE_CN.get(sh.get("min"), "")}—{STAGE_CN.get(sh.get("max"), "")}'
             f'（{sh.get("min")}–{sh.get("max")}）') if sh else None
    if sucs:
        unlock = '<ul>' + ''.join(
            f'<li><a href="../{i}/">{esc(cut(s, 40))}</a></li>' for i, s, _ in sucs[:8]) + '</ul>'
        if len(sucs) > 8:
            unlock += f'<p class=mo>另有 {len(sucs) - 8} 条，见下方「关系」。</p>'
    else:
        unlock = None
    return ''.join([
        row('plain', None),
        row('ask2', (a.get('assessment') or '').replace('{{name}}', '孩子') or None),
        row('cog2', a['cognitive']),
        row('stage', stage),
        row('unlk', unlock, raw=bool(sucs)),
        row('life', None),
        row('kid', '需接入档案'),
        # ★ 规则 3：这三个不是「尚未定义」，是「永远不做」。
        #   用 row() 渲染成「尚未定义」等于承诺以后会补，那是反着说了；
        #   所以字段名和结论都由 CSS 的 i[data-k=forbid] 特判打出，
        #   字段的英文名一次都不进 2,158 个页面（grep 可验）。
        '<i data-k=forbid></i>',
    ])


def panel_trace(a, objs):
    """溯源（研究者）：standard_quote / source_doc+page / extraction_method / credibility / objections"""
    p = a.get('provenance') or {}
    stt = a['reviewStatus']
    short, mean = STATUS_CN.get(stt, (stt, ''))
    src = p.get('srcText')
    q = None
    if src:
        q = f'<blockquote>{esc(src)}</blockquote>'
        if p.get('srcTextFullLen'):
            q += (f'<p class=mo>原整段 {p["srcTextFullLen"]} 字，'
                  f'已被 fix_srctext.py 换成句子级引文。</p>')
    page = p.get('srcPageRange') or p.get('srcPage')
    ck = a.get('independentCheck') or {}
    adj = a.get('adjudication') or {}
    rep = a.get('repair') or {}
    return ''.join([
        row('quote', q, raw=bool(src)),
        row('src', ' · '.join(str(x) for x in [p.get('srcSubject') or a['discipline'],
                                               f'第 {page} 页' if page else None,
                                               p.get('srcStage')] if x) or None),
        row('course', ' · '.join(str(x) for x in [p.get('srcCourse'), p.get('srcCode')] if x) or None),
        row('meth', p.get('method')),
        row('agree', p.get('srcAgree')),
        row('esrc', f'{a.get("evidenceSource")} · {SRC_CN.get(a.get("evidenceSource"), "")}'),
        row('derv', f'<a href="../{esc(p["derivedFrom"])}/">{esc(p["derivedFrom"])}</a>'
            if p.get('derivedFrom') else None, raw=bool(p.get('derivedFrom'))),
        row('why', p.get('why')),
        row('tier', f'{stt} · {short} —— {mean}'),
        row('acb', a.get('autoConfirmBasis')),
        row('by', a.get('reviewedBy')),
        row('end', [f'{e.get("by")} {e.get("at") or ""} {e.get("note") or ""}'
                    for e in (a.get('endorsements') or [])] or None),
        row('disp', [f'{d.get("issue") or ""} {d.get("note") or ""} {d.get("by") or ""}'
                     for d in (a.get('disputes') or [])] or None),
        row('adj', (f'{adj.get("by") or ""} {adj.get("note") or ""}'
                    + ('（待人工异议）' if adj.get('pendingObjection') else '')) if adj else None),
        row('ick', (f'{ck.get("method")}；passed={str(ck.get("passed")).lower()}；'
                    f'overlap={ck.get("overlap")}') if ck else None),
        row('rep', f'{rep.get("kind") or ""} {rep.get("why") or ""}' if rep else None),
        row('objl', [f'{o.get("at") or ""} {o.get("by") or ""}：{o.get("text") or ""}'
                     for o in objs] or None),
    ])


# ── 常显区：关系 / 标签 / 清单 / 异议 ────────────────────────────────────────
def edge_card(e, oid, ost, odep, direction):
    """一条边。type / strength / failureSignature 三个字段必显示 —— 现在几乎全是空的，
    正因为全是空的才必须显示：不显示就看不出边重标（specs/001）还没跑。"""
    ttl = (f'<a href="../{oid}/">{esc(cut(ost, 46))}</a>' if not odep
           else f'{esc(cut(ost, 46))}<span class=mo>（已弃用）</span>')
    return (f'<article class=e><h4><span class=dir>{direction}</span>{ttl}'
            f'<code>{esc(oid)}</code></h4>'
            + row('et', e.get('type'))
            + row('es', e.get('strength'))
            + row('ef', e.get('failureSignature'))
            + row('eg', None if e.get('inInferenceGraph') is None
                  else str(e['inInferenceGraph']).lower())
            + row('er', e.get('reason'))
            + row('ek', '、'.join(EV_KIND_CN.get(x.get('kind'), x.get('kind') or '')
                                  for x in (e.get('evidence') or [])) or None)
            + row('erv', e.get('reviewStatus'))
            + row('ec', e.get('counterEvidenceCount'))
            + '</article>')


def sec_rel(pre_edges, suc_edges, me):
    pres = [x for _, x in pre_edges]
    sucs = [x for _, x in suc_edges]
    if not pres and not sucs:
        body = '<p class=warn>这一条<b>既没有前置也没有后继</b>。</p><i data-n=iso></i>'
    else:
        body = subgraph(pres, sucs, me)
        if len(pres) > MAXG or len(sucs) > MAXG:
            body += (f'<p class=mo>图里每排最多画 {MAXG} 个'
                     f'（前置 {len(pres)} 条、后继 {len(sucs)} 条，下面逐条列）。</p>')
        body += ''.join(edge_card(e, *x, '前置') for e, x in pre_edges)
        body += ''.join(edge_card(e, *x, '后继') for e, x in suc_edges[:12])
        if len(suc_edges) > 12:
            body += (f'<p class=mo>另有 {len(suc_edges) - 12} 条后继未在此展开'
                     f'（本条后继共 {len(suc_edges)} 条，全部画在上图与 /2d 图谱里）。</p>')
    return (f'<section class=sec><h2>关系 · 前置 {len(pres)} / 后继 {len(sucs)}</h2>'
            f'<i data-n=reldir></i>{body}</section>')


def sec_tags(a, cc_cn, lit_ok):
    def chips(xs, cls=''):
        return ''.join(f'<span class="k {cls}">{esc(x)}</span>' for x in xs) or None
    lit = a.get('literacy') or []
    bad = [x for x in lit if x not in lit_ok.get(a['discipline'], [])]
    lh = chips(lit)
    if lh and bad:
        lh += f'<p class=warn>不在该学科课标印的闭合清单内：{esc("、".join(bad))}</p>'
    ccs = [cc_cn.get(x, x) for x in (a.get('crosscutting') or [])]
    prs = [cc_cn.get(x, x) for x in (a.get('practice') or [])]
    return ('<section class=sec><h2 data-h=tags></h2><i data-n=tags></i>'
            + row('tcog', f'<span class=k>{esc(a["cognitive"])}</span>', raw=True)
            + row('tlit', lh, raw=bool(lh))
            + row('tcc', chips(ccs, 'cc'), raw=bool(ccs))
            + row('tpr', chips(prs, 'cc'), raw=bool(prs))
            + row('tccw', (a.get('provenance') or {}).get('crosscuttingWhy'))
            + row('tak', None) + '</section>')


def sec_list(a, li):
    body = None
    if li:
        body = (f'共 <b>{sum(li.values())}</b> 条<ul>'
                + ''.join(f'<li><code>{esc(k)}</code> {n} 条</li>' for k, n in sorted(li.items()))
                + '</ul>')
    tg = a.get('stageTargets') or []
    return ('<section class=sec><h2 data-h=li></h2>'
            + row('li', body, raw=bool(li))
            + row('lt', [f'{x.get("band") or x.get("stage")}：累计 {x.get("target")}' for x in tg] or None)
            + '</section>')


# ── 单页 ───────────────────────────────────────────────────────────────────
def build(a, src_file, pre_edges, suc_edges, cc_cn, lit_ok, li, rel):
    aid, stt = a['id'], a['reviewStatus']
    cit = stt in CITABLE
    short, mean = STATUS_CN.get(stt, (stt, ''))
    objs = a.get('objections') or []
    sucs = [x for _, x in suc_edges]

    # ★ 规则 2：红绿灯 + 理由同级，且理由是**静态 HTML** —— 不进 CSS、不进 JS。
    #   这是全页唯一一句「不许靠别的文件才看得见」的话。
    light = (f'<div class="light {"ok" if cit else "no"}" role=status>'
             f'<b>{"可以被 L3 档案引用" if cit else "不可以被 L3 档案引用"}</b>'
             f'<span>依据：reviewStatus = <code>{esc(stt)}</code> · {esc(short)} —— {esc(mean)}</span>'
             + ('<span class=cav>它计入可用集合的前提是「没人反对」。'
                '如果你认为不该成立，请在下方提异议。</span>' if stt == 'ai-adjudicated' else '')
             + '</div>')

    banner = ''
    if a.get('evidenceSource') == 'capability-rewrite':
        banner = ('<div class=rwb><b>这一条不是课标转述</b><i data-n=rw></i>'
                  + row('why', (a.get('provenance') or {}).get('why'))
                  + f'<div id=rw data-id={aid}></div></div>')

    sh = a.get('stageHint') or {}
    meta = ' · '.join(x for x in [a['discipline'], a.get('strand') or '', a.get('topic') or '',
                                  STAGE_CN.get(sh.get('min'), ''), a.get('courseType') or '',
                                  a['track']] if x)
    tabs = ''.join(f'<input type=radio name=v id=v{i}{" checked" if not i else ""}>' for i in range(4))
    tabs += '<div class=tabs>' + ''.join(f'<label for=v{i}></label>' for i in range(4)) + '</div>'

    return f'''<!doctype html><html lang=zh-CN><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{esc(cut(a["statement"], 30))} · {esc(aid)}</title>
<link rel=stylesheet href="../_assets/a.css"></head><body>
<nav><div class=in><b>K12</b><a href="/">3D 图谱</a><a href="/2d/">2D 俯视</a><a href="/list/">全部能力点</a><a href="/about/">关于</a><a class=sp href="/data/">数据集</a></div></nav>
<main class=pg>
{light}
<h1>{esc(a["statement"])}</h1>
<p class=meta><code>{esc(aid)}</code> · {esc(meta)}</p>
{banner}
<div class=vw>{tabs}<div class=panels><div class=p0>{panel_cite(a, src_file, cit, len(objs))}</div>\
<div class=p1>{panel_judge(a)}</div><div class=p2>{panel_grow(a, sucs)}</div>\
<div class=p3>{panel_trace(a, objs)}</div></div></div>
{sec_rel(pre_edges, suc_edges, aid)}
{sec_tags(a, cc_cn, lit_ok)}
{sec_list(a, li)}
<section class=sec><h2>异议 · 已公开 {len(objs)} 条</h2><i data-n=objway></i>
<div id=obj data-id={aid}></div></section>
<footer><h2 data-h=m></h2><i data-n=m1></i><i data-n=m2></i><i data-n=m3></i>
<p class=rl>{rel}</p></footer>
</main><script src="../_assets/a.js"></script></body></html>'''


# ── 共享资源 ───────────────────────────────────────────────────────────────
# 深浅色两套：跟 tools/make_state_page.py 一样，媒体查询 + data-theme 双保险。
CSS = r'''*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#eef1f0;--card:#fff;--ink:#16201c;--mut:#5f6d67;--dim:#8a958f;--rule:#d8dedb;
--ok:#0e6e5b;--no:#a43b4e;--rw:#7a4bb0;--cc:#8a6516;--acc:#0e6e5b}
@media(prefers-color-scheme:dark){:root{--bg:#0d1214;--card:#141b1d;--ink:#e4eae7;--mut:#8b9995;
--dim:#68766f;--rule:#222c2f;--ok:#4fd1ac;--no:#f0798f;--rw:#b478dc;--cc:#d9a548;--acc:#4fd1ac}}
:root[data-theme=dark]{--bg:#0d1214;--card:#141b1d;--ink:#e4eae7;--mut:#8b9995;--dim:#68766f;
--rule:#222c2f;--ok:#4fd1ac;--no:#f0798f;--rw:#b478dc;--cc:#d9a548;--acc:#4fd1ac}
:root[data-theme=light]{--bg:#eef1f0;--card:#fff;--ink:#16201c;--mut:#5f6d67;--dim:#8a958f;
--rule:#d8dedb;--ok:#0e6e5b;--no:#a43b4e;--rw:#7a4bb0;--cc:#8a6516;--acc:#0e6e5b}
body{background:var(--bg);color:var(--ink);
font:15px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--acc)}
:focus-visible{outline:2px solid var(--acc);outline-offset:2px;border-radius:3px}
nav{border-bottom:1px solid var(--rule);background:var(--card)}
nav .in{max-width:900px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px;
height:52px;overflow-x:auto}
nav b{font-weight:800;letter-spacing:.13em;font-size:14px}
nav a{color:var(--mut);text-decoration:none;font-size:13.5px;white-space:nowrap}
nav a:hover{color:var(--ink)}nav .sp{margin-left:auto}
.pg{max-width:900px;margin:0 auto;padding:24px 20px 90px}
h1{font-size:26px;font-weight:640;letter-spacing:-.02em;line-height:1.35;margin:18px 0 8px}
.meta{color:var(--mut);font-size:13px;margin-bottom:20px}
code{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--card);
border:1px solid var(--rule);border-radius:5px;padding:1px 6px}
.light{border:1px solid var(--rule);border-left-width:5px;border-radius:11px;padding:13px 16px;
background:var(--card)}
.light b{display:block;font-size:16.5px;font-weight:660}
.light span{display:block;color:var(--mut);font-size:13px;margin-top:4px}
.light.ok{border-left-color:var(--ok)}.light.ok b{color:var(--ok)}
.light.no{border-left-color:var(--no)}.light.no b{color:var(--no)}
.light .cav{color:var(--cc)}
.rwb{border:1px solid var(--rw);border-radius:11px;padding:13px 16px;margin:20px 0 0;background:var(--card)}
.rwb>b{color:var(--rw);font-size:15.5px}
/* 视图切页：radio + :checked ~，零 JS。原生 radio group 自带左右箭头切换。 */
.vw>input{position:absolute;width:1px;height:1px;opacity:0}
.tabs{display:flex;gap:6px;margin-top:22px;overflow-x:auto;border-bottom:1px solid var(--rule)}
.tabs label{flex:none;cursor:pointer;padding:9px 15px 8px;border:1px solid transparent;border-bottom:0;
border-radius:9px 9px 0 0;color:var(--mut);white-space:nowrap;text-align:center}
.tabs label::before{display:block;font-size:14.5px;font-weight:600}
.tabs label::after{display:block;font-size:11px;opacity:.8}
label[for=v0]::before{content:"引用"}label[for=v0]::after{content:"开发者"}
label[for=v1]::before{content:"判定"}label[for=v1]::after{content:"教师"}
label[for=v2]::before{content:"成长"}label[for=v2]::after{content:"家长"}
label[for=v3]::before{content:"溯源"}label[for=v3]::after{content:"研究者"}
.tabs label:hover{color:var(--ink)}
.panels>div{display:none;padding:16px 0 4px}
#v0:checked~.tabs label[for=v0],#v1:checked~.tabs label[for=v1],
#v2:checked~.tabs label[for=v2],#v3:checked~.tabs label[for=v3]{
color:var(--ink);background:var(--card);border-color:var(--rule)}
#v0:checked~.panels .p0,#v1:checked~.panels .p1,
#v2:checked~.panels .p2,#v3:checked~.panels .p3{display:block}
/* .tabs 是 overflow-x:auto 的滚动容器，outline 会被它切掉上下两条边，
   只剩两根竖线 —— 焦点框改用 inset box-shadow，画在元素里面就不会被裁。 */
#v0:focus-visible~.tabs label[for=v0],#v1:focus-visible~.tabs label[for=v1],
#v2:focus-visible~.tabs label[for=v2],#v3:focus-visible~.tabs label[for=v3]{
box-shadow:inset 0 0 0 2px var(--acc)}
/* 字段。名字由 ::before 打出，空值由 :empty::after 打出「尚未定义」。 */
i[data-k]{display:block;font-style:normal;padding:10px 0;border-bottom:1px solid var(--rule)}
i[data-k]:last-child{border-bottom:0}
i[data-k]::before{display:block;font-size:11.5px;letter-spacing:.06em;color:var(--dim);font-weight:600}
i[data-k]:empty::after{content:"— 尚未定义";color:var(--no);font-size:13.5px}
i[data-k=forbid]:empty::after{content:"— 不做。这是设计结论，不是还没做";color:var(--cc)}
i[data-k] ul{margin:3px 0 0 19px}
i[data-k] blockquote{color:var(--mut);border-left:2px solid var(--rule);padding-left:11px;margin-top:3px}
.wh{display:block;font-style:normal;color:var(--dim);font-size:12.5px;margin-top:3px}
i[data-n]{display:block;font-style:normal;color:var(--dim);font-size:12.5px;margin-bottom:10px}
.warn{color:var(--cc);font-size:13px;margin:4px 0}
.mo{color:var(--dim);font-size:12.5px;margin-top:4px}
.k{display:inline-block;font-size:12px;padding:2px 10px;border-radius:99px;border:1px solid var(--rule);
color:var(--mut);margin:4px 5px 0 0;background:var(--card)}
.k.cc{color:var(--cc);border-color:var(--cc)}
.sec{margin-top:32px;border-top:1px solid var(--rule);padding-top:16px}
.sec h2,footer h2{font-size:11px;letter-spacing:.15em;color:var(--dim);font-weight:600;margin-bottom:8px}
h2[data-h=tags]::before{content:"四套认知标签"}
h2[data-h=li]::before{content:"挂在这一条上的清单条目"}
h2[data-h=m]::before{content:"这一页为什么长这样"}
.e{border:1px solid var(--rule);border-radius:11px;padding:11px 15px;margin:11px 0;background:var(--card)}
.e h4{font-size:14.5px;font-weight:560;margin-bottom:2px;line-height:1.5}
.e h4 code{margin-left:7px;font-size:11px}
.dir{display:inline-block;font-size:11px;color:var(--dim);border:1px solid var(--rule);border-radius:5px;
padding:0 6px;margin-right:7px;vertical-align:2px}
svg.g{display:block;width:100%;height:auto;margin:4px 0 14px;background:var(--card);
border:1px solid var(--rule);border-radius:11px}
svg.g rect.n{fill:var(--bg);stroke:var(--rule)}
svg.g rect.me{fill:var(--card);stroke:var(--acc);stroke-width:2}
svg.g rect.dep{stroke-dasharray:3 3}
svg.g text{fill:var(--ink);font:12px -apple-system,"PingFang SC",sans-serif}
svg.g text.lb,svg.g text.mo{fill:var(--dim);font-size:11px}
svg.g line{stroke:var(--rule);stroke-width:1.5}
svg.g a:hover rect{stroke:var(--acc)}
footer{margin-top:38px;border-top:1px solid var(--rule);padding-top:16px;color:var(--mut);font-size:13px}
footer i[data-n]{font-size:13px;color:var(--mut);margin-bottom:9px}
footer .rl{color:var(--dim);font-size:12px;margin-top:12px}
button{font:inherit;font-size:13.5px;padding:8px 15px;border-radius:9px;border:1px solid var(--rule);
background:var(--card);color:var(--ink);cursor:pointer;margin-top:6px}
button:hover{border-color:var(--acc)}
textarea{width:100%;font:inherit;font-size:13.5px;padding:9px 11px;border-radius:9px;
border:1px solid var(--rule);background:var(--card);color:inherit;margin:8px 0}
.done{color:var(--cc);font-size:13px;margin-top:7px;white-space:pre-wrap}
@media(max-width:640px){h1{font-size:21px}.tabs label{padding:8px 11px}.e{padding:10px 12px}}
'''

# JS 只干三件事：把常量长句挂上去、异议表单、撤回入口。视图切换是纯 CSS。
JS_TAIL = r'''
// ★ 说明文字**插在 <i> 后面，不是插进去** —— 插进去 :empty 就不成立，
//   「尚未定义」会当场消失。这个坑踩过一次。
document.querySelectorAll('i[data-k]').forEach(function (el) {
  var t = W[el.dataset.k]; if (!t) return;
  var n = document.createElement('i'); n.className = 'wh'; n.textContent = t;
  el.insertAdjacentElement('afterend', n);
});
document.querySelectorAll('i[data-n]').forEach(function (el) {
  var t = N[el.dataset.n]; if (t) el.textContent = t;
});
function box(host, key, label, ph, tip) {
  if (!host) return;
  var b = document.createElement('button'), d = document.createElement('div');
  b.type = 'button'; b.textContent = label;
  host.appendChild(b); host.appendChild(d);
  var k = key + ':' + host.dataset.id;
  function saved() {
    var v = null; try { v = localStorage.getItem(k); } catch (e) {}
    if (!v) return false;
    d.innerHTML = ''; var p = document.createElement('p'); p.className = 'done';
    p.textContent = '已记在你这台设备上：' + v + '\n' + tip;
    d.appendChild(p); b.hidden = true; return true;
  }
  if (saved()) return;
  b.onclick = function () {
    d.innerHTML = '';
    var ta = document.createElement('textarea'), ok = document.createElement('button');
    ta.rows = 3; ta.placeholder = ph; ta.setAttribute('aria-label', ph);
    ok.type = 'button'; ok.textContent = '记下来';
    ok.onclick = function () {
      var v = ta.value.trim(); if (!v) { ta.focus(); return; }
      try { localStorage.setItem(k, v); } catch (e) {}
      saved();
    };
    d.appendChild(ta); d.appendChild(ok); ta.focus();
  };
}
box(document.getElementById('obj'), 'obj', '我对这一条有异议',
    '说清楚哪里不对。空泛的「感觉不合适」没法处理。', N.objtip);
box(document.getElementById('rw'), 'rw', '这条应该撤掉',
    '为什么这条自造的能力断言不该存在？', N.rwtip);
'''


def main():
    ANC = []
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for line in f.open(encoding='utf-8'):
            if line.strip():
                a = json.loads(line)
                a['_file'] = f.name
                ANC.append(a)
    by_id = {a['id']: a for a in ANC}
    live = [a for a in ANC if not a.get('deprecated')]

    E = [json.loads(l) for f in sorted((ROOT / 'edges').glob('*.jsonl'))
         for l in f.open(encoding='utf-8') if l.strip()]
    E = [e for e in E if not e.get('retired')]
    pre_of, suc_of = collections.defaultdict(list), collections.defaultdict(list)
    for e in E:
        pre_of[e['anchorId']].append(e)
        suc_of[e['prerequisiteId']].append(e)

    items, n_items = collections.defaultdict(collections.Counter), 0
    for f in sorted((ROOT / 'lists').glob('*/*.jsonl')):
        for line in f.open(encoding='utf-8'):
            if line.strip():
                it = json.loads(line)
                n_items += 1
                for aid in (it.get('anchorIds') or []):
                    items[aid][it['listId']] += 1

    cc = json.loads((ROOT / 'mappings/crosscutting.json').read_text(encoding='utf-8'))
    cc_cn = {x['id']: x['zh'] for k in ('crosscutting', 'practice') for x in cc[k]}
    lit_raw = json.loads((ROOT / 'mappings/literacy.json').read_text(encoding='utf-8'))['disciplines']
    lit_ok = {k: (v if isinstance(v, list) else (v.get('literacy') or v.get('values') or []))
              for k, v in lit_raw.items()}
    mf = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))

    # 全库统计：**页面里的每一个数都从这里来，没有一个是手打的。**
    S = {
        'live': len(live), 'edges': len(E), 'items': n_items, 'item_anchors': len(items),
        'disc': len({a['discipline'] for a in live}),
        'usable': sum(1 for a in live if a['reviewStatus'] in CITABLE),
        'expert': sum(1 for a in live if a['reviewStatus'] == 'expert-confirmed'),
        'rewrite': sum(1 for a in live if a.get('evidenceSource') == 'capability-rewrite'),
        'fallback': sum(1 for a in live if a.get('evidenceSource') == 'fallback'),
        'spec': sum(1 for a in live if a.get('assessmentSpec')),
        'obj': sum(1 for a in live if a.get('objections')),
        'etype': sum(1 for e in E if e.get('type')),
        'efail': sum(1 for e in E if e.get('failureSignature')),
        'iso': sum(1 for a in live if not pre_of[a['id']] and not suc_of[a['id']]),
    }

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / 'a/_assets').mkdir(parents=True)
    css = CSS + ''.join(f'i[data-k={k}]::before{{content:"{lab}"}}\n' for k, (lab, _) in LBL.items())
    (OUT / 'a/_assets/a.css').write_text(css, encoding='utf-8')
    W = {k: n.format(**S) for k, (_, n) in LBL.items() if n}
    N = {k: v.format(**S) for k, v in NOTES.items()}
    (OUT / 'a/_assets/a.js').write_text(
        'const W=' + json.dumps(W, ensure_ascii=False, separators=(',', ':'))
        + ',N=' + json.dumps(N, ensure_ascii=False, separators=(',', ':')) + ';' + JS_TAIL,
        encoding='utf-8')

    rel = (f'K12 教育的能力结构 · release {esc(mf.get("release"))} · '
           f'数据 {esc(mf.get("generatedAt"))} · <a href="/data/">数据集</a> · '
           f'<a href="{REPO}">GitHub</a>')

    total = 0
    for a in live:
        aid = a['id']

        def side(edges, key):
            out = [(e, (by_id[e[key]]['id'], by_id[e[key]]['statement'],
                        bool(by_id[e[key]].get('deprecated'))))
                   for e in edges if e[key] in by_id]
            out.sort(key=lambda x: x[1][1])
            return out

        page = build(a, a['_file'], side(pre_of[aid], 'prerequisiteId'),
                     side(suc_of[aid], 'anchorId'), cc_cn, lit_ok,
                     dict(items.get(aid) or {}), rel)
        d = OUT / 'a' / aid
        d.mkdir(parents=True, exist_ok=True)
        (d / 'index.html').write_text(page, encoding='utf-8')
        total += len(page.encode('utf-8'))

    print(f"  → {OUT}/a/<id>/index.html")
    print(f"    {len(live):,} 页 · HTML 合计 {total / 1048576:.2f}MB · "
          f"平均 {total // len(live) / 1024:.1f}KB/页")
    print(f"    共享 a.css {len(css.encode()) / 1024:.1f}KB · "
          f"a.js {(OUT / 'a/_assets/a.js').stat().st_size / 1024:.1f}KB")
    print(f"    可引用 {S['usable']}／{S['live']:,}（{S['usable'] * 100 // S['live']}%） · "
          f"转写层 {S['rewrite']} · 孤立 {S['iso']} · 边 {S['edges']:,}"
          f"（标了 type 的 {S['etype']}，写了 failureSignature 的 {S['efail']}）")
    print(f"    全库尚未定义：assessmentSpec {S['live'] - S['spec']:,} 条 · "
          f"objections {S['live'] - S['obj']:,} 条 · 教师签字 {S['live'] - S['expert']:,} 条")


if __name__ == '__main__':
    main()
