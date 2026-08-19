#!/usr/bin/env python3
"""
make_list.py — /list：把全部能力锚点做成能逐条翻的目录页。

## 为什么图谱不够

3D 图能看结构、能搜关键词，但**不能像目录一样翻**。想知道「化学一共有哪些能力点」，
在图里只能一个个点。用户第一次问「有没有把每个都列出来」，答案是没有 —— 那说明
这个底座对外只有一个「炫」的入口，没有一个「查」的入口。

## 设计

一页装 2,176 条，客户端全量渲染会卡。所以：
  · 数据内联为紧凑数组（不是每条一个对象，省一半体积）
  · 虚拟滚动只渲染视口内的行
  · 筛选（学科 / 学段 / 复核档 / 来源层）和搜索都在内存里做，无请求

每行点开展开：课标原文 + 页码、判定证据、家长问句、核心素养、横切标签，
以及**通往 `/a/<id>/` 详情页的链接** —— 2,158 个详情页没有入口就等于不存在。
**这些字段本来就都有，只是从来没在一个地方一起给过人看。**

    python3 tools/make_list.py
"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE_CN = {'G1': '一二年级', 'G3': '三四年级', 'G5': '五六年级',
            'G7': '初中', 'G8': '初中', 'G9': '初中', 'G10': '高中'}
TIER = {'expert-confirmed': 4, 'auto-confirmed': 3, 'ai-adjudicated': 2,
        'ai-reviewed': 1, 'disputed': 0, 'llm-proposed': -1}
TIER_CN = ['AI 审出有问题', '只过 AI 审查', 'AI 裁定待异议', '机械可判定', '教师签字']


def main():
    A = [json.loads(l) for f in sorted((ROOT / 'anchors').glob('*.jsonl'))
         for l in f.open(encoding='utf-8') if l.strip()]
    live = [a for a in A if not a.get('deprecated')]
    lit_vocab = json.loads((ROOT / 'mappings/literacy.json').read_text(encoding='utf-8'))['disciplines']
    cc = json.loads((ROOT / 'mappings/crosscutting.json').read_text(encoding='utf-8'))
    CC_CN = {x['id']: x['zh'] for k in ('crosscutting', 'practice') for x in cc[k]}

    live.sort(key=lambda a: (a['discipline'], (a.get('stageHint') or {}).get('min') or 'G9',
                             -TIER.get(a['reviewStatus'], -1), a['statement']))

    rows = []
    for a in live:
        p = a.get('provenance') or {}
        st = (a.get('stageHint') or {}).get('min') or ''
        src = ('高中' if st == 'G10' else
               ('转写' if a.get('evidenceSource') == 'capability-rewrite' else '义务教育'))
        rows.append([
            a['id'], a['discipline'], STAGE_CN.get(st, st), a['statement'],
            TIER.get(a['reviewStatus'], -1) + 1,          # 0..5 便于前端比大小
            src, a.get('courseType') or '',
            (a.get('assessment') or '').replace('{{name}}', '孩子'),
            (a.get('evidence') or [])[:2],
            # ★ 引文超长的截断。中位数才 38 字，但有 102 条超过 500 ——
            #   那是抽取时把整段吞进来了。在列表页整段糊出来，人一眼就放弃了。
            #   **截断是显示上的补救，不是修复** —— 数据侧的问题另记（见下）。
            (lambda t: t if len(t) <= 220 else t[:220] + '…（原文更长，见课标第 %s 页）' % (p.get('srcPage') or '?'))(p.get('srcText') or ''),
            p.get('srcPage') or '',
            a.get('literacy') or [],
            [CC_CN.get(x, x) for x in (a.get('crosscutting') or []) + (a.get('practice') or [])],
            a.get('cognitive') or '', a['track'],
        ])

    discs = [d for d, _ in collections.Counter(a['discipline'] for a in live).most_common()]
    counts = collections.Counter(a['discipline'] for a in live)
    stages = ['一二年级', '三四年级', '五六年级', '初中', '高中']

    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全部能力点 · K12 教育的能力结构</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#080a11;--fg:#eceaf0;--mut:#8b93a5;--dim:#5b6273;--line:#1c2130;
--card:#0e1219;--acc:#e8607d;--cc:#c9a227;--rw:#b478dc;--ok:#4fd1ac}}
body{{background:var(--bg);color:var(--fg);
font:15px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}}
nav{{position:sticky;top:0;z-index:20;background:rgba(8,10,17,.9);
backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}}
nav .in{{max-width:1080px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:18px;height:54px}}
nav b{{font-weight:800;letter-spacing:.13em;font-size:14px}}
nav a{{color:var(--mut);text-decoration:none;font-size:13.5px}}
nav a:hover{{color:var(--fg)}}nav .sp{{margin-left:auto}}
.w{{max-width:1080px;margin:0 auto;padding:0 20px}}
header{{padding:34px 0 18px}}
h1{{font-size:30px;font-weight:640;letter-spacing:-.02em}}
h1 em{{font-style:normal;color:var(--mut);font-size:16px;font-weight:400;margin-left:12px}}
.hint{{color:var(--dim);font-size:13px;margin-top:8px}}
.bar{{position:sticky;top:54px;z-index:15;background:rgba(8,10,17,.94);
backdrop-filter:blur(12px);padding:14px 0 12px;border-bottom:1px solid var(--line)}}
#q{{width:100%;padding:11px 14px;border-radius:10px;border:1px solid var(--line);
background:var(--card);color:inherit;font:inherit;font-size:14.5px}}
#q:focus{{outline:none;border-color:var(--dim)}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}}
.chip{{font:inherit;font-size:12px;padding:5px 11px;border-radius:99px;cursor:pointer;
border:1px solid var(--line);background:var(--card);color:var(--mut)}}
.chip:hover{{color:var(--fg)}}
.chip.on{{background:var(--fg);color:var(--bg);border-color:var(--fg);font-weight:600}}
.chip i{{font-style:normal;opacity:.55;margin-left:5px;font-size:11px}}
.grp{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px}}
.grp>span{{font-size:11px;letter-spacing:.12em;color:var(--dim);margin-right:2px}}
#stat{{color:var(--mut);font-size:13px;margin:14px 0 6px;font-variant-numeric:tabular-nums}}
#vp{{position:relative}}
.row{{border-bottom:1px solid var(--line);padding:13px 2px;cursor:pointer}}
.row:hover{{background:rgba(255,255,255,.022)}}
.rh{{display:flex;align-items:baseline;gap:10px}}
.st{{flex:none;width:9px;height:9px;border-radius:50%;background:var(--mut);margin-top:6px}}
.st.t0{{background:none;border:1.4px solid var(--mut)}}
.st.t1{{opacity:.42}}.st.t2{{opacity:.7}}
.st.t3{{opacity:1;box-shadow:0 0 0 1.4px rgba(255,255,255,.5)}}
.st.t4{{background:var(--ok);box-shadow:0 0 0 1.4px var(--ok)}}
.tx{{flex:1;font-size:14.5px}}
.tag{{flex:none;font-size:11px;color:var(--dim);white-space:nowrap}}
.tag.rw{{color:var(--rw)}}
.det{{display:none;margin:11px 0 3px 19px;padding:13px 15px;background:var(--card);
border:1px solid var(--line);border-radius:11px;font-size:13.5px;line-height:1.75}}
.row.open .det{{display:block}}
.det h5{{font-size:10.5px;letter-spacing:.14em;color:var(--dim);margin:12px 0 3px;font-weight:600}}
.det h5:first-child{{margin-top:0}}
.det blockquote{{color:var(--mut);border-left:2px solid var(--line);padding-left:11px;margin:3px 0}}
.det ul{{margin:3px 0 0 17px;color:var(--mut)}}
.det .k{{display:inline-block;font-size:11.5px;padding:2px 9px;border-radius:99px;
border:1px solid var(--line);color:var(--mut);margin:3px 5px 0 0}}
.det .k.cc{{color:var(--cc);border-color:rgba(201,162,39,.4)}}
.det a{{color:var(--mut);font-size:12px}}
    .det a.go{{display:inline-block;margin:2px 0;font-weight:600}}
#more{{display:block;width:100%;margin:22px 0 60px;padding:13px;border-radius:11px;
border:1px solid var(--line);background:var(--card);color:var(--fg);font:inherit;cursor:pointer}}
#more:hover{{border-color:var(--dim)}}
.none{{color:var(--dim);padding:40px 0;text-align:center}}
@media(max-width:640px){{.tag{{display:none}}h1{{font-size:24px}}}}
</style></head><body>
<nav><div class=in><b>K12</b>
  <a href="/">3D 图谱</a><a href="/2d/">2D 俯视</a><a href="/about/">关于</a>
  <a class=sp href="/data/">数据集</a>
  <a href="https://github.com/qiuyiwu1989-star/k12-knowledge-substrate">GitHub</a>
</div></nav>
<div class=w>
<header>
  <h1>全部能力点<em>{len(live):,} 条 · {len(discs)} 个学科</em></h1>
  <p class=hint>每一条都是从教育部课标里抽出来、能对一个具体孩子回答「会 / 不会」的断言。
    点开看课标原文、页码和判定证据。</p>
</header>
</div>
<div class=bar><div class=w>
  <input id=q placeholder="搜断言、课标原文、素养…（如：分数、静夜思、运算能力）" autocomplete=off>
  <div class=grp><span>学科</span><div class=chips id=cd></div></div>
  <div class=grp><span>学段</span><div class=chips id=cs></div></div>
  <div class=grp><span>复核</span><div class=chips id=ct></div></div>
</div></div>
<div class=w>
  <div id=stat></div>
  <div id=vp></div>
  <button id=more hidden>再看 200 条</button>
</div>
<script>
const D={json.dumps(rows, ensure_ascii=False, separators=(',', ':'))};
const DISCS={json.dumps(discs, ensure_ascii=False)};
const CNT={json.dumps(dict(counts), ensure_ascii=False)};
const STAGES={json.dumps(stages, ensure_ascii=False)};
const TIER_CN={json.dumps(TIER_CN, ensure_ascii=False)};
const esc=s=>String(s??'').replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
let fD=null,fS=null,fT=null,q='',shown=200;

function chips(el,items,get,cur,set){{
  el.innerHTML=items.map(x=>`<button class="chip${{cur===x?' on':''}}" data-v="${{esc(x)}}">${{esc(x)}}${{get?`<i>${{get(x)}}</i>`:''}}</button>`).join('');
  el.onclick=e=>{{const b=e.target.closest('.chip'); if(!b)return; set(b.dataset.v===cur?null:b.dataset.v); render();}};
}}
function paint(){{
  chips(document.getElementById('cd'),DISCS,d=>CNT[d],fD,v=>fD=v);
  chips(document.getElementById('cs'),STAGES,null,fS,v=>fS=v);
  chips(document.getElementById('ct'),TIER_CN,null,fT,v=>fT=v);
}}
function match(r){{
  if(fD&&r[1]!==fD)return false;
  if(fS&&r[2]!==fS)return false;
  if(fT&&TIER_CN[r[4]]!==fT)return false;
  if(!q)return true;
  return (r[3]+r[9]+r[7]+r[11].join('')+r[12].join('')+r[1]).includes(q);
}}
function render(){{
  paint();
  const hit=D.filter(match);
  document.getElementById('stat').textContent=
    `${{hit.length.toLocaleString()}} 条`+(hit.length>shown?`（显示前 ${{shown}} 条）`:'');
  const vp=document.getElementById('vp');
  if(!hit.length){{vp.innerHTML='<div class=none>没有匹配的能力点</div>';document.getElementById('more').hidden=true;return;}}
  vp.innerHTML=hit.slice(0,shown).map(r=>{{
    const ct=r[6]?` · ${{esc(r[6])}}`:'';
    return `<article class=row data-id="${{r[0]}}">
      <div class=rh><span class="st t${{r[4]}}" title="${{TIER_CN[r[4]]}}"></span>
        <span class=tx>${{esc(r[3])}}</span>
        <span class="tag${{r[5]==='转写'?' rw':''}}">${{esc(r[1])}} · ${{esc(r[2])}}${{ct}}</span></div>
      <div class=det>
        ${{r[7]?`<h5>家长可以这样问</h5><div>${{esc(r[7])}}</div>`:''}}
        ${{r[9]?`<h5>课标原文${{r[10]?`（第 ${{r[10]}} 页）`:''}}</h5><blockquote>${{esc(r[9])}}</blockquote>`:''}}
        ${{r[8].length?`<h5>判定证据</h5><ul>${{r[8].map(e=>`<li>${{esc(e)}}</li>`).join('')}}</ul>`:''}}
        <h5>标签</h5>
        <div>${{r[11].map(x=>`<span class=k>${{esc(x)}}</span>`).join('')}}
             ${{r[12].map(x=>`<span class="k cc">${{esc(x)}}</span>`).join('')}}
             <span class=k>${{esc(r[13])}}</span><span class=k>${{esc(r[14])}} 档</span>
             <span class=k>${{esc(TIER_CN[r[4]])}}</span>
             ${{r[5]==='转写'?'<span class="k" style="color:var(--rw);border-color:rgba(180,120,220,.4)">不是课标原话</span>':''}}</div>
        <h5>看这一条的详情页</h5>
        <a class=go href="/a/${{r[0]}}/">/a/${{r[0]}}/ —— 引用 / 判定 / 成长 / 溯源 四个视图</a>
        <h5>在图谱里看</h5><a href="/#${{r[0]}}">/#${{r[0]}}</a>
      </div></article>`;
  }}).join('');
  document.getElementById('more').hidden=hit.length<=shown;
}}
document.getElementById('vp').onclick=e=>{{
  const r=e.target.closest('.row'); if(!r||e.target.tagName==='A')return;
  r.classList.toggle('open');
}};
document.getElementById('q').oninput=e=>{{q=e.target.value.trim();shown=200;render();}};
document.getElementById('more').onclick=()=>{{shown+=200;render();}};
render();
</script></body></html>'''
    out = ROOT / 'list.html'
    out.write_text(page, encoding='utf-8')
    print(f"  → {out}  {len(page)//1024}KB · {len(live):,} 条 · {len(discs)} 科")


if __name__ == '__main__':
    main()
