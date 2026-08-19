#!/usr/bin/env python3
"""
make_data_index.py — /data/ 的索引页。

README 和站点导航都链到 /data/，而那里是 **404** —— nginx 关了 autoindex
（关得对，目录列表会把内部结构全暴露），但没人补一个索引页。
链接指向 404 比没有链接更糟：它让人以为项目是坏的。

这一页给两类人看：
  · 想直接取数据的开发者 —— 每个文件干什么、怎么取、许可是什么
  · 只是好奇点进来的人 —— 一句话说清这是什么，并指回给人看的页面

    python3 tools/make_data_index.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = 'https://k12.yongle.school/data'


def main():
    M = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    c = M['counts']

    def group(prefix, cn):
        fs = sorted((k, v) for k, v in M['files'].items() if k.startswith(prefix))
        rows = ''.join(
            f'<tr><td><a href="{BASE}/{k}">{k.split("/",1)[1]}</a></td>'
            f'<td class=n>{v["bytes"]/1024:,.0f} KB</td>'
            f'<td class=h>{v["sha256"][:12]}</td></tr>' for k, v in fs)
        return (f'<h3>{cn}<em>{len(fs)} 个文件</em></h3>'
                f'<div class=tw><table><tr><th>文件</th><th class=n>大小</th>'
                f'<th class=h>SHA-256</th></tr>{rows}</table></div>') if fs else ''

    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>数据集 · K12 教育的能力结构</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#080a11;--fg:#eceaf0;--mut:#8b93a5;--dim:#5b6273;--line:#1c2130;--card:#0e1219;--ok:#4fd1ac}}
body{{background:var(--bg);color:var(--fg);
font:15.5px/1.72 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}}
nav{{position:sticky;top:0;z-index:9;background:rgba(8,10,17,.9);backdrop-filter:blur(14px);
border-bottom:1px solid var(--line)}}
nav .in{{max-width:820px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:18px;height:54px}}
nav b{{font-weight:800;letter-spacing:.13em;font-size:14px}}
nav a{{color:var(--mut);text-decoration:none;font-size:13.5px}}nav a:hover{{color:var(--fg)}}
nav .sp{{margin-left:auto}}
.w{{max-width:820px;margin:0 auto;padding:0 20px}}
header{{padding:44px 0 10px}}
h1{{font-size:32px;font-weight:640;letter-spacing:-.025em}}
.lede{{color:var(--mut);margin-top:14px}}
h2{{font-size:21px;font-weight:640;margin:44px 0 10px}}
h3{{font-size:15px;font-weight:640;margin:26px 0 8px;display:flex;align-items:baseline;gap:10px}}
h3 em{{font-style:normal;color:var(--dim);font-size:12px;font-weight:400}}
p{{color:#c3c8d4;margin:12px 0}}
b{{color:var(--fg)}}
a{{color:var(--fg)}}
pre{{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:16px 18px;
overflow-x:auto;font:12.5px/1.9 ui-monospace,SFMono-Regular,Menlo,monospace;color:#b9c0cf;margin:16px 0}}
.tw{{overflow-x:auto;margin:12px 0}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;min-width:420px}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}}
th{{color:var(--dim);font-size:10.5px;letter-spacing:.13em;font-weight:600;text-transform:uppercase}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums;color:var(--mut)}}
td.h,th.h{{color:var(--dim);font:11.5px ui-monospace,Menlo,monospace}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:18px 0}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1px;
background:var(--line);border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:24px 0}}
.stats div{{background:var(--card);padding:15px 16px}}
.stats em{{display:block;font-style:normal;font-size:24px;font-weight:640;letter-spacing:-.02em;
font-variant-numeric:tabular-nums}}
.stats span{{display:block;color:var(--dim);font-size:11.5px;margin-top:3px}}
footer{{margin:70px 0 50px;padding-top:22px;border-top:1px solid var(--line);color:var(--dim);font-size:13px}}
html,body{{max-width:100%;overflow-x:hidden}}
</style></head><body>
<nav><div class=in><b>K12</b>
  <a href="/">3D 图谱</a><a href="/list/">全部能力点</a><a href="/about/">关于</a>
  <a class=sp href="https://github.com/qiuyiwu1989-star/k12-knowledge-substrate">GitHub</a>
</div></nav>
<div class=w>
<header>
  <h1>数据集</h1>
  <p class=lede>全部 <b>{c['liveAnchors']:,} 条能力断言</b>可以直接取，
    不用 clone 仓库。跨域已放开，浏览器里 <code>fetch</code> 就能读。</p>
</header>

<div class=stats>
  <div><em>{c['liveAnchors']:,}</em><span>能力断言</span></div>
  <div><em>{c['edges']:,}</em><span>先修依赖</span></div>
  <div><em>{c['listItems']:,}</em><span>清单知识点</span></div>
  <div><em>{len(c['byDiscipline'])}</em><span>学科</span></div>
</div>

<div class=card>
<b>想看不想取？</b>
<p style="margin-bottom:0"><a href="/list/">全部能力点</a>是给人翻的目录，
可按学科、学段、复核状态筛，能搜；<a href="/">3D 图谱</a>看结构；
<a href="/about/">关于</a>讲方法论。这一页是给程序用的。</p>
</div>

<h2>最快的用法</h2>
<pre># 先取 manifest：所有计数、每个文件的 SHA-256 都在里面
curl {BASE}/manifest.json

# 取某一科的锚点（JSONL，一行一条）
curl {BASE}/anchors/math.jsonl

# 浏览器里直接读（已放开跨域）
const m = await (await fetch('{BASE}/manifest.json')).json()
console.log(m.counts.liveAnchors, m.usableAnchors, m.humanConfirmedAnchors)</pre>

<h2>一条锚点长什么样</h2>
<pre>{{
  "id": "ca_7Kd9mQxL",           // 无语义、永不复用。**档案只引用这个**
  "discipline": "数学",
  "statement": "能在 0 到 1 的数轴上标出四分之三并说明理由",
  "verb": "标出", "object": "四分之三",
  "stageHint": {{ "min": "G3", "max": "G4" }},
  "courseType": null,             // 高中才有：必修 / 选择性必修 / 选修
  "cognitive": "理解",
  "literacy": ["数感"],           // 核心素养，闭合词表
  "crosscutting": ["patterns"],   // 横切概念，参照 NGSS
  "evidence": ["…能看见的具体行为…"],
  "assessment": "{{{{name}}}}能在数轴上指出四分之三在哪里吗？",
  "reviewStatus": "ai-adjudicated",
  "provenance": {{ "srcPage": 27, "srcText": "…课标原句…" }}
}}</pre>

<h2>先看懂这三个数，再用</h2>
<div class=card>
<pre style="margin:0;background:none;border:none;padding:0">liveAnchors           {c['liveAnchors']:,}   一共有多少条
usableAnchors           {M['usableAnchors']}   <b>能被个人档案引用的</b>
humanConfirmedAnchors     {M['humanConfirmedAnchors']}   <b>有教师签字的</b></pre>
<p style="margin-bottom:0">第三个数是 <b>{M['humanConfirmedAnchors']}</b>，它没有写错。
底座里 {c['liveAnchors']:,} 条，<b>没有任何一条经过教师复核</b>。
标为「可用」的 {M['usableAnchors']} 条靠的是机械可判定（字表词表这类数得清的东西）
或 AI 裁定待异议 —— 那是「没人反对」，不是「有人认可」。
<b>拿去做产品前请自己判断这个可信度够不够。</b></p>
</div>

<h2>文件清单</h2>
<p>每个文件的 SHA-256 都在 <a href="{BASE}/manifest.json">manifest.json</a> 里，
可校验完整性。目录本身没有自动索引（那会把内部结构全暴露），所以有了这一页。</p>
{group('anchors/', '锚点 anchors/')}
{group('edges/', '先修边 edges/')}
{group('lists/', '清单 lists/')}
{group('mappings/', '映射 mappings/')}

<h2>许可</h2>
<pre>L0 锚点 + 依赖图、L1 映射（数据库结构与关系）   ODbL 1.0
本项目撰写的文本（statement / evidence / assessment）  CC BY-SA 4.0
provenance.srcText 句子级课标引文              权利归教育部，按合理引用附带</pre>
<p><b>一条铁律：应用层不得自己定义知识点，只能引用 L0 的 ID。</b>
这条一破，底座立刻退化成又一个数据集，所有产品的档案重新变成互相读不懂的孤岛。</p>

<footer>
<p>永乐教育 · 数据依据中华人民共和国教育部课程标准 ·
<a href="https://github.com/qiuyiwu1989-star/k12-knowledge-substrate">GitHub</a></p>
<p style="margin-top:6px">本页由 <code>tools/make_data_index.py</code> 从 manifest.json 生成。</p>
</footer>
</div></body></html>'''
    out = ROOT / 'data-index.html'
    out.write_text(page, encoding='utf-8')
    print(f"  → {out}  {len(page)//1024}KB · 列出 {len(M['files'])} 个文件")


if __name__ == '__main__':
    main()
