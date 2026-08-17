#!/usr/bin/env python3
"""
make_child_view.py — 「一个孩子的视角」：底座摊到一个具体学段上是什么样。

**这一页首先是检验工具，其次才是产品。**

它诞生于一次抽查：我只是问「一个二年级孩子打开会看到什么」，随手看了 8 条，
就发现了「甲骨文被归到科学」—— 而那条错误躲过了可判定闸、命题闸、接地校验、
独立验证四道关。原因很简单：那四道闸都在**逐条**看数据，而这个视角是**成批**
看同一个人会读到的东西，错配一眼就跳出来。

所以这页每次数据变更后重跑，当体检用。

设计上两条：
· 家长读到的是 assessment（「{{name}}能把《静夜思》完整背下来吗？」），
  不是 statement —— 后者是给机器看的
· 可信度必须在每一条上可见。453 条里 307 条无人签字，混在一起显示
  等于默认它们一样可靠

    python3 tools/make_child_view.py
"""
import collections, glob, html, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USE = {'auto-confirmed', 'expert-confirmed', 'ai-adjudicated'}
BANDS = [('G1-2', 1, 2, '一二年级'), ('G3-4', 3, 4, '三四年级'),
         ('G5-6', 5, 6, '五六年级'), ('G7-9', 7, 9, '初中'),
         # 高中课标按模块给内容不按年级，所以这一档是整个高中三年。
         # 真实区分在 courseType（必修/选择性必修/选修）上，不在年级上。
         ('G10-12', 10, 12, '高中')]


def grade(a, k):
    h = (a.get('stageHint') or {})
    try:
        return int(str(h.get(k, ''))[1:])
    except Exception:
        return None


def main():
    A = [json.loads(l) for f in sorted((ROOT / 'anchors').glob('*.jsonl'))
         for l in f.open(encoding='utf-8') if l.strip()]
    live = [a for a in A if not a.get('deprecated')]
    use = [a for a in live if a['reviewStatus'] in USE]

    L = [json.loads(l) for f in sorted(ROOT.glob('lists/**/*.jsonl'))
         for l in f.open(encoding='utf-8') if l.strip()]
    gated = collections.Counter()
    for x in L:
        for aid in (x.get('anchorIds') or []):
            gated[aid] += 1

    targets = {}
    p = ROOT / 'mappings/stage-targets.json'
    if p.exists():
        d = json.loads(p.read_text(encoding='utf-8'))
        for t in d['targets']:
            targets[t['stage']] = t

    def esc(s):
        return html.escape(str(s or ''))

    bands_html = []
    for code, lo, hi, name in BANDS:
        hit = [a for a in use
               if grade(a, 'min') and grade(a, 'max')
               and grade(a, 'min') <= hi and grade(a, 'max') >= lo]
        by = collections.defaultdict(list)
        for a in hit:
            by[a['discipline']].append(a)

        subs = []
        for d, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
            items = []
            for a in sorted(v, key=lambda x: (x['reviewStatus'] != 'auto-confirmed', x['statement'])):
                n = gated[a['id']]
                obj = a['reviewStatus'] == 'auto-confirmed'
                ask = (a.get('assessment') or a['statement']).replace('{{name}}', '孩子')
                items.append(
                    f'<label class="q{" obj" if obj else ""}">'
                    f'<input type=checkbox data-id="{esc(a["id"])}" data-d="{esc(d)}" '
                    f'data-n="{n}" data-obj="{1 if obj else 0}">'
                    f'<span class=t>{esc(ask)}</span>'
                    f'<span class=badge>{"判定客观" if obj else "AI 裁定·待异议"}</span>'
                    + (f'<span class=cnt>{n} 条可逐项勾</span>' if n else '')
                    + '</label>')
            subs.append(f'<section class=sub><h3>{esc(d)}<em>{len(v)}</em></h3>{"".join(items)}</section>')

        tg = targets.get(code)
        tgt = (f'<div class=target>课标给这个学段的识字目标：'
               f'累计认识 <b>{tg["recognize"]}</b> 字，会写 <b>{tg["write"]}</b> 字</div>') if tg else ''
        obj_n = sum(1 for a in hit if a['reviewStatus'] == 'auto-confirmed')
        # 一个学段可能一条可用锚点都没有 —— 高中现在就是这样。
        # **不能只显示 0 就完了**：家长会以为「高中没内容」，
        # 而真相是「有 891 条，但一条都还没人复核，所以不摊给你看」。
        # 空状态必须说清是哪一种空。
        if not hit:
            total_stage = sum(1 for a in live
                              if grade(a, 'min') and grade(a, 'max')
                              and grade(a, 'min') <= hi and grade(a, 'max') >= lo)
            bands_html.append(
                f'<div class=band data-band="{code}" hidden>'
                f'<div class=summary>这个学段<b>暂时没有可用锚点</b>。'
                + (f'底座里已经有 <b>{total_stage}</b> 条，但一条都还没经过复核 —— '
                   f'没复核的东西不摊给家长看，那比不显示更糟。'
                   if total_stage else '底座里还没有这个学段的内容。')
                + '</div></div>')
            continue
        bands_html.append(
            f'<div class=band data-band="{code}" hidden>'
            f'<div class=summary>这个学段共 <b>{len(hit)}</b> 条能力锚点，'
            f'其中 <b>{obj_n}</b> 条判定客观、<b>{len(hit) - obj_n}</b> 条是 AI 裁定待异议。{tgt}</div>'
            f'{"".join(subs)}</div>')

    tabs = ''.join(f'<button class=tab data-band="{c}">{n}</button>' for c, _, _, n in BANDS)

    page = f'''<meta charset=utf-8><title>K12 底座 · 一个孩子的视角</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#f6f7f6;--card:#fff;--ink:#1a2320;--mut:#5f6d67;--rule:#dde3e0;--ok:#0e6e5b;--pend:#8a6516}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0e1315;--card:#151c1e;--ink:#e5eae8;--mut:#8b9995;--rule:#232d30;--ok:#4fd1ac;--pend:#d9a548}}}}
:root[data-theme=dark]{{--bg:#0e1315;--card:#151c1e;--ink:#e5eae8;--mut:#8b9995;--rule:#232d30;--ok:#4fd1ac;--pend:#d9a548}}
:root[data-theme=light]{{--bg:#f6f7f6;--card:#fff;--ink:#1a2320;--mut:#5f6d67;--rule:#dde3e0;--ok:#0e6e5b;--pend:#8a6516}}
body{{background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,"PingFang SC",sans-serif;padding:34px 20px 150px}}
.w{{max-width:860px;margin:0 auto}}
h1{{font-size:26px;font-weight:640;letter-spacing:-.02em}}
.lede{{color:var(--mut);font-size:13.5px;margin-top:8px;max-width:62ch}}
.tabs{{display:flex;gap:8px;margin:24px 0 18px;flex-wrap:wrap}}
.tab{{font:600 13.5px inherit;padding:9px 16px;border-radius:9px;border:1px solid var(--rule);background:var(--card);color:var(--ink);cursor:pointer}}
.tab.on{{background:var(--ok);border-color:var(--ok);color:var(--bg)}}
.summary{{background:var(--card);border:1px solid var(--rule);border-radius:11px;padding:14px 16px;font-size:13.5px;margin-bottom:18px}}
.target{{margin-top:8px;color:var(--mut);font-size:13px}}
.sub{{background:var(--card);border:1px solid var(--rule);border-radius:12px;margin-bottom:14px;overflow:hidden}}
.sub h3{{font-size:13px;font-weight:640;padding:11px 16px;border-bottom:1px solid var(--rule);display:flex;justify-content:space-between;align-items:center}}
.sub h3 em{{font-style:normal;color:var(--mut);font-size:12px;font-variant-numeric:tabular-nums}}
.q{{display:flex;gap:11px;align-items:flex-start;padding:10px 16px;border-bottom:1px solid var(--rule);cursor:pointer;font-size:14px}}
.q:last-child{{border-bottom:0}}
.q input{{margin-top:3px;width:16px;height:16px;accent-color:var(--ok);flex:none}}
.q .t{{flex:1}}
.badge{{font-size:10.5px;padding:2px 8px;border-radius:99px;white-space:nowrap;border:1px solid var(--pend);color:var(--pend)}}
.q.obj .badge{{border-color:var(--ok);color:var(--ok)}}
.cnt{{font-size:11px;color:var(--mut);white-space:nowrap}}
#dock{{position:fixed;left:0;right:0;bottom:0;background:color-mix(in srgb,var(--bg) 93%,transparent);backdrop-filter:blur(12px);border-top:1px solid var(--rule);padding:14px 20px}}
#dock .in{{max-width:860px;margin:0 auto}}
#stat{{font-size:14px;font-variant-numeric:tabular-nums}}
#warn{{font-size:12.5px;color:var(--pend);margin-top:5px}}
.bar{{height:6px;border-radius:3px;background:var(--rule);margin-top:9px;overflow:hidden}}
.bar i{{display:block;height:100%;background:var(--ok);width:0;transition:width .2s}}
</style>
<div class=w>
<h1>一个孩子的视角</h1>
<p class=lede>选一个学段，看底座摊到这个孩子身上是什么样。每条都是家长/老师能直接照着问的一句话。
<b>这一页首先是体检工具</b> —— 它诞生于一次抽查，两分钟找出了四道自动闸都没找出的错误。</p>
<div class=tabs>{tabs}</div>
{''.join(bands_html)}
</div>
<div id=dock><div class=in>
  <div id=stat>还没勾</div>
  <div class=bar><i id=fill></i></div>
  <div id=warn></div>
</div></div>
<script>
const tabs=[...document.querySelectorAll('.tab')], bands=[...document.querySelectorAll('.band')];
function show(code){{
  tabs.forEach(t=>t.classList.toggle('on',t.dataset.band===code));
  bands.forEach(b=>b.hidden=b.dataset.band!==code);
  calc();
}}
tabs.forEach(t=>t.onclick=()=>show(t.dataset.band));
function calc(){{
  const b=bands.find(x=>!x.hidden); if(!b) return;
  const all=[...b.querySelectorAll('input')], on=all.filter(x=>x.checked);
  const obj=on.filter(x=>x.dataset.obj==='1').length;
  document.getElementById('stat').textContent =
    on.length ? `已掌握 ${{on.length}} / ${{all.length}} 条` : '还没勾';
  document.getElementById('fill').style.width = (all.length? on.length/all.length*100:0)+'%';
  document.getElementById('warn').textContent = on.length
    ? `其中 ${{obj}} 条判定客观，${{on.length-obj}} 条是 AI 裁定、尚无教师签字 —— 后者别当定论`
    : '';
}}
document.addEventListener('change',calc);
show('{BANDS[0][0]}');
</script>'''
    out = ROOT / 'docs/child-view.html'
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding='utf-8')
    print(f"  → {out}")
    for code, lo, hi, name in BANDS:
        hit = [a for a in use if grade(a, 'min') and grade(a, 'max')
               and grade(a, 'min') <= hi and grade(a, 'max') >= lo]
        obj = sum(1 for a in hit if a['reviewStatus'] == 'auto-confirmed')
        print(f"    {name}：{len(hit)} 条（判定客观 {obj}）")


if __name__ == '__main__':
    main()
