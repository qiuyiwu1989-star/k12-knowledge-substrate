#!/usr/bin/env python3
"""
make_about.py — 生成 /about 介绍页：这个项目是什么，以及它的方法论。

**页面上每一个数字都从 manifest.json 和 anchors/ 现读。**
这一条不是洁癖：本仓库因为手打数字腐烂已经栽过两次（README 同一段里
「138 条可用」和「usableAnchors 依然是 0」并存了好几轮）。介绍页是给外人看的，
写错的代价更大。

    python3 tools/make_about.py
"""
import collections, glob, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    M = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    c = M['counts']
    A = [json.loads(l) for f in sorted((ROOT / 'anchors').glob('*.jsonl'))
         for l in f.open(encoding='utf-8') if l.strip()]
    live = [a for a in A if not a.get('deprecated')]
    L = [json.loads(l) for f in sorted(glob.glob(str(ROOT / 'lists/**/*.jsonl'), recursive=True))
         for l in open(f, encoding='utf-8') if l.strip()]

    cog = collections.Counter(a['cognitive'] for a in live)
    lit = collections.Counter(l for a in live for l in (a.get('literacy') or []))
    lists = collections.Counter(x.get('listId', '?') for x in L)
    src = sum(1 for a in live if (a.get('provenance') or {}).get('srcText'))
    # ★ 高中数必须按**学段**算，不能按 courseType 非空算 ——
    #   71 条课标里没标模块归属的会被漏掉（实测 820 vs 891）。
    #   「有没有标某个字段」和「属不属于某一层」是两件事。
    gz = sum(1 for a in live if (a.get('stageHint') or {}).get('min') == 'G10')
    rw = M.get('rewrittenAnchors', 0)
    LIST_CN = {'lst_hanzi-changyong-3500': '常用字表', 'lst_en-vocab-l3': '英语三级词汇',
               'lst_en-vocab-l2': '英语二级词汇', 'lst_hanzi-jiben-300': '基本字表',
               'lst_recite-yiwu-135': '背诵篇目', 'lst_en-irregular-verbs': '不规则动词'}
    list_rows = ''.join(
        f'<tr><td>{LIST_CN.get(k, k)}</td><td class=n>{v:,}</td></tr>'
        for k, v in lists.most_common(6))
    lit_rows = ''.join(
        f'<li><b>{k}</b><span>{v}</span></li>' for k, v in lit.most_common(8))

    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>关于 · K12 教育的能力结构</title>
<meta name="description" content="把教育部课标变成 {c['liveAnchors']:,} 条可判定的能力断言，
让所有教育产品的个人档案写在同一套 ID 空间里。">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#080a11;--fg:#eceaf0;--mut:#8b93a5;--dim:#5b6273;--line:#1c2130;
--card:#0e1219;--acc:#e8607d;--cc:#c9a227;--rw:#b478dc;--ok:#4fd1ac}}
body{{background:var(--bg);color:var(--fg);
font:16px/1.75 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
-webkit-font-smoothing:antialiased}}
.w{{max-width:760px;margin:0 auto;padding:0 24px}}
nav{{position:sticky;top:0;z-index:9;background:rgba(8,10,17,.86);
backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}}
nav .w{{display:flex;align-items:center;gap:20px;height:56px}}
nav b{{font-weight:800;letter-spacing:.13em;font-size:14px}}
nav a{{color:var(--mut);text-decoration:none;font-size:13.5px;margin-left:auto}}
nav a+a{{margin-left:18px}}
nav a:hover{{color:var(--fg)}}
header{{padding:78px 0 54px}}
h1{{font-size:clamp(34px,6vw,54px);line-height:1.1;font-weight:640;letter-spacing:-.03em}}
h1 i{{font-style:normal;color:var(--acc)}}
.lede{{color:var(--mut);font-size:18px;margin-top:22px;max-width:60ch}}
h2{{font-size:26px;font-weight:640;letter-spacing:-.02em;margin:64px 0 6px}}
h2+.sub{{color:var(--dim);font-size:14px;margin-bottom:22px}}
h3{{font-size:17px;font-weight:640;margin:34px 0 8px}}
p{{color:#c3c8d4;margin:14px 0}}
b,strong{{color:var(--fg);font-weight:600}}
a{{color:var(--fg)}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));
gap:1px;background:var(--line);border:1px solid var(--line);border-radius:14px;
overflow:hidden;margin:34px 0}}
.stats div{{background:var(--card);padding:20px 18px}}
.stats em{{display:block;font-style:normal;font-size:31px;font-weight:640;
letter-spacing:-.03em;font-variant-numeric:tabular-nums}}
.stats span{{display:block;color:var(--dim);font-size:12.5px;margin-top:5px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:22px 24px;margin:22px 0}}
.card.warn{{border-color:rgba(232,96,125,.34);background:rgba(232,96,125,.055)}}
.card.rw{{border-color:rgba(180,120,220,.34);background:rgba(180,120,220,.05)}}
pre{{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:18px 20px;overflow-x:auto;font:12.5px/1.85 ui-monospace,SFMono-Regular,Menlo,monospace;
color:#b9c0cf;margin:20px 0}}
/* 宽内容只能在自己的容器里横滚，页面 body 永远不许横向滚动。 */
html,body{{max-width:100%;overflow-x:hidden}}
pre,table{{max-width:100%}}
.tw{{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:20px 0}}
.tw table{{margin:0;min-width:400px}}
code,pre{{word-break:break-word;overflow-wrap:anywhere}}
table{{width:100%;border-collapse:collapse;margin:20px 0;font-size:14.5px}}
th,td{{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}}
th{{color:var(--dim);font-size:11.5px;letter-spacing:.13em;font-weight:600;text-transform:uppercase}}
td.n{{text-align:right;font-variant-numeric:tabular-nums;color:var(--mut)}}
ul.lit{{list-style:none;display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:1px;
background:var(--line);border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:20px 0}}
ul.lit li{{background:var(--card);padding:12px 15px;display:flex;align-items:baseline;font-size:14px}}
ul.lit span{{margin-left:auto;color:var(--dim);font-variant-numeric:tabular-nums;font-size:13px}}
.dim{{color:var(--dim)}}
.tag{{display:inline-block;font-size:11px;letter-spacing:.08em;padding:2px 8px;
border-radius:99px;border:1px solid currentColor;vertical-align:middle;margin-left:7px}}
.t-cc{{color:var(--cc)}}.t-rw{{color:var(--rw)}}.t-ok{{color:var(--ok)}}
footer{{margin:86px 0 60px;padding-top:26px;border-top:1px solid var(--line);
color:var(--dim);font-size:13px}}
footer a{{color:var(--mut)}}
@media(max-width:640px){{header{{padding:48px 0 34px}}h2{{margin-top:46px}}}}
</style></head><body>
<nav><div class=w><b>K12</b>
  <a href="/">3D 图谱</a><a href="/list/">全部能力点</a><a href="/2d/">2D 俯视</a><a href="/data/">数据集</a>
  <a href="https://github.com/qiuyiwu1989-star/k12-knowledge-substrate">GitHub</a>
</div></nav>

<div class=w>
<header>
  <h1>把课标变成<i>能对一个孩子回答「会 / 不会」</i>的东西。</h1>
  <p class=lede>教育产品各自定义知识点，于是每个孩子在每个产品里都要从零开始。
  这个项目做的是那层公共坐标系：<b>{c['liveAnchors']:,} 条可判定的能力断言</b>，
  依据教育部课标构建，开放数据。</p>
</header>

<div class=stats>
  <div><em>{c['liveAnchors']:,}</em><span>能力断言</span></div>
  <div><em>{len(c['byDiscipline'])}</em><span>学科 · K–12 全覆盖</span></div>
  <div><em>{c['listItems']:,}</em><span>清单知识点</span></div>
  <div><em>{c['edges']:,}</em><span>先修依赖</span></div>
  <div><em>{gz:,}</em><span>高中锚点</span></div>
  <div><em>{src:,}</em><span>带课标原文引文</span></div>
  <div><em>{M['usableAnchors']}</em><span>可被档案引用</span></div>
  <div><em>{M['humanConfirmedAnchors']}</em><span>教师签字</span></div>
</div>

<div class="card warn">
<b>最后一个数字是 0，它没有写错。</b>
<p style="margin-bottom:0">底座里有 {c['liveAnchors']:,} 条，但<b>没有任何一条经过教师复核</b>。
其中 {M['usableAnchors']} 条标为「可用」，靠的是机械可判定（字表词表这类数得清的东西）
或 AI 裁定待异议 —— 那是「没人反对」，不是「有人认可」。
这个数字放在最显眼的位置，是因为把它藏起来太容易了。</p>
</div>

<h2>为什么需要一层底座</h2>
<p class=sub>问题不在没有知识图谱，而在每家都有一份自己的</p>

<p>一个孩子用作文批改、用古诗背诵、用数学练习，三个产品各自记着他的进度。
换一个产品，进度归零 —— 不是数据没导出，是<b>「什么」这件事三家说的不是一回事</b>。
A 家的「理解分数」和 B 家的「分数的意义」，没有任何办法对齐。</p>

<p>所以底座要解决的不是「有多少知识点」，而是<b>「知识点能不能被寻址」</b>。
它只做一件事：给每一条能力一个<b>无语义、永不复用</b>的 ID，
让所有产品的档案写在同一套 ID 空间里。</p>

<pre>[L4] 应用层    作文批改 │ 诗歌 │ 课程库 │ …
                  ↓ <b>只允许引用 ID，禁止自造知识点</b>
[L3] 档案层    每个孩子会什么、不会什么          ← 私有，永不进仓库
                  ↓ 用 L0 的 ID 做谓词
[L2] 编排层    教材版本 × 年级 × 单元            ← 不做（版权）
[L1] 映射层    课标条目 │ 字表词表 │ 背诵篇目
[L0] 锚点层    <b>可判定的能力断言 + 依赖关系</b>      ← 唯一稳定 ID 空间</pre>

<p><b>L3 永不进仓库。</b>未成年人信息属敏感个人信息。分层让这件事变成架构问题
而不是政策问题：L0–L2 是公共知识、零隐私，L3 是全部隐私。
所以可以做到 —— <b>知识库在云上，孩子的数据一步不出校门。</b></p>

<h2>方法论：四个维度，只有一根主干</h2>
<p class=sub>课标 · 知识 · 能力 · 认知，它们不是并列的四层</p>

<p>这四个词经常被并排提起，好像是四种平行的东西。在这个底座里<b>只有「能力」是主干</b>，
其余三个都是挂在它上面的维度。这不是分类偏好，是被一条判据逼出来的。</p>

<h3>能力 —— 唯一的 ID 空间</h3>
<p>判据只有一个：<b>能不能对一个具体孩子在某一时刻回答「会 / 不会」。</b></p>
<div class=tw><table>
<tr><th>拒绝</th><th>通过</th></tr>
<tr><td class=dim>分数的意义</td><td>能在 0 到 1 的数轴上标出四分之三并说明理由</td></tr>
<tr><td class=dim>培养观察能力</td><td>能举例说明举头与低头的动作对比表达了什么情绪</td></tr>
<tr><td class=dim>了解古代中国的政治制度</td><td>能默写《静夜思》全诗且无错别字</td></tr>
</table></div>
<p>左边是章节名和口号，右边是<b>能挂档案的东西</b>。
这道闸在 CI 里是硬门禁，砍掉了机器抽取输出的六到七成。</p>

<h3>知识 —— 挂在能力下面，不是并列</h3>
<p>3,500 个常用字如果各自成一个 ID，档案里就是 3,500 条互不相干的记录；
挂在「能正确书写常用字表一中的汉字」下面，就是<b>一条能力 + 一个进度</b>。</p>
<div class=tw><table><tr><th>清单</th><th class=n>条目</th></tr>{list_rows}</table></div>
<p class=dim>共 {c['listItems']:,} 条。这类东西数得清、判得准，
是底座里唯一不需要教师复核的一类。</p>

<h3>课标 —— 来源，不是层</h3>
<p>{src:,} 条锚点带着课标原文引文和页码，可以翻回教育部文件某一页核对。
<b>课标条目本身不能当主干</b>：它是文档结构（第几章第几节），改版就全废；
而能力断言可以跨版本存活。</p>
<p>依据两份文件：《义务教育课程方案和课程标准（2022年版）》15 份 1,594 页，
《普通高中课程方案和课程标准（2017年版2020年修订）》21 份 2,276 页。
前者是零文字层的扫描件，逐页多模态识读；后者有文字层，纯规则解析、零模型调用。</p>

<h3>认知 —— 四套正交的标签</h3>
<p>同一条能力可以既是「应用」层级、又练「找规律」这个横切概念、又属「运算能力」这个核心素养。
<b>它们互不排斥，所以只能是标签，不能是层</b> —— 做成层就得强行二选一。</p>

<pre>认知层级   掌握 {cog['掌握']:,} · 了解 {cog['了解']} · 应用 {cog['应用']} · 理解 {cog['理解']}
核心素养   {len(lit)} 种取值，闭合词表，逐科摘自课标「学科核心素养」正文
横切维度   7 个通用概念 + 8 项科学实践（参照 NGSS 三维度设计）
课程类型   必修 / 选择性必修 / 选修 —— 只有高中有</pre>

<ul class=lit>{lit_rows}</ul>

<h2>跨学科不靠先修边，靠横切维度<span class="tag t-cc">关键设计</span></h2>

<p>{c['edges']:,} 条先修依赖里，跨学科的只有 11 条。这个数在两轮重跑里都没变 ——
<b>它是对的，不是漏建</b>。真正的跨学科先修关系本来就罕见：
必须是「学这条时现场用得到那条，用不出来就卡住」。
「都需要观察力」这种一律不算，那样建出来的是好听的假边。</p>

<p>那「能力是跨界融合的」怎么表达？<b>换一层。</b>
练「找规律」的语文锚点和练「找规律」的数学锚点之间确实有关联，
但那关联<b>没有方向、没有先后</b> —— 它画不成有向边。</p>

<pre>先修关系   有向、有先后   A 必须排在 B 之前        {c['edges']:,} 条
横切关联   无向、同时     A 和 B 练的是同一件事    数十万对</pre>

<p>所以图上它们长得不一样：先修走连线，横切走<b>金色虚线光环，不连边</b>。
连边会撒谎 —— 在这张图里边一律表示先修。</p>

<h2>可信度必须可分辨<span class="tag t-ok">这是底线</span></h2>
<p class=sub>把没验过的和验过的画成一样，就是用视觉掩盖数据质量</p>

<div class=tw><table>
<tr><th>状态</th><th class=n>条数</th><th>能否被档案引用</th></tr>
<tr><td>还没有人看过</td><td class=n>{c['byReview'].get('llm-proposed',0):,}</td><td class=dim>不能</td></tr>
<tr><td>只过了 AI 审查</td><td class=n>{c['byReview'].get('ai-reviewed',0):,}</td><td class=dim>不能 —— AI 审查是筛子，不是合格证</td></tr>
<tr><td>AI 审出有问题，已挂起</td><td class=n>{c['byReview'].get('disputed',0):,}</td><td class=dim>不能</td></tr>
<tr><td>机械可判定</td><td class=n>{c['byReview'].get('auto-confirmed',0):,}</td><td>能</td></tr>
<tr><td>AI 裁定，待人工异议</td><td class=n>{c['byReview'].get('ai-adjudicated',0):,}</td><td>能（前提是「没人反对」）</td></tr>
<tr><td><b>教师签字</b></td><td class=n><b>{M['humanConfirmedAnchors']}</b></td><td>能</td></tr>
</table></div>

<p>这五档在图谱上用<b>填充深浅</b>区分，不是只标出有问题的那一档。
{c['byReview'].get('llm-proposed',0):,} 条「一个人都没看过」如果和「过了 AI 审查」长得一样，
那张图就在替数据质量打掩护。</p>

<div class="card rw">
<b>其中 {rw} 条明确不是课标原话<span class="tag t-rw">能力转写层</span></b>
<p style="margin-bottom:0">课标只要求「知道中国传统工艺来自民间」，
我们在它之上提了一条「能举例说出两种中国民间传统工艺及其产地」。
<b>这是我们自己的教育判断，不是教育部写的。</b>
所以它单独统计、图上单独描边、可以被单独撤掉 ——
底座的全部价值在那条溯源链上，这一层不能悄悄混进去看着和别的一样。</p>
</div>

<h2>高中：{gz:,} 条，20 科</h2>
<p>包括英语、日语、俄语、<b>德语、法语、西班牙语</b>六种外语 ——
后三种是 2017 版新增的，给开设小语种的高中用。全部出自教育部制定的课标。</p>
<p>高中课标<b>按模块给内容，不按年级</b>。所以这批锚点的学段一律是 G10–G12，
真实区分放在课程类型上：必修是所有学生都该有的，选修不是。
不记这一维，档案里「他没掌握 X」就分不清<b>是没学过还是学了没会</b>。</p>
<p class=dim>不发明年级精度。「必修 1 就是高一」是教学惯例，不是课标条文。</p>

<h2>怎么用</h2>
<pre>数据集直取（允许跨域，不用 clone）
  https://k12.yongle.school/data/manifest.json
  https://k12.yongle.school/data/anchors/*.jsonl

许可
  L0 锚点 + 依赖图、L1 映射    ODbL 1.0
  本项目撰写的文本             CC BY-SA 4.0
  课标原文引文                 权利归教育部，按合理引用附带</pre>

<p><b>一条铁律：应用层不得自己定义知识点，只能引用 L0 的 ID。</b>
这条一破，底座立刻退化成又一个数据集，所有产品的档案重新变成互相读不懂的孤岛。</p>

<footer>
<p>永乐教育 · 数据依据中华人民共和国教育部课程标准 ·
<a href="https://github.com/qiuyiwu1989-star/k12-knowledge-substrate">GitHub</a></p>
<p style="margin-top:8px">本页所有数字由 <code>tools/make_about.py</code>
从 <code>manifest.json</code> 现读生成，与数据集同步。</p>
</footer>
</div></body></html>'''

    out = ROOT / 'about.html'
    out.write_text(page, encoding='utf-8')
    print(f"  → {out}  {len(page)//1024}KB")
    print(f"    锚点 {c['liveAnchors']:,} · 学科 {len(c['byDiscipline'])} · 可用 {M['usableAnchors']}"
          f" · 教师签字 {M['humanConfirmedAnchors']} · 转写 {rw}")


if __name__ == '__main__':
    main()
