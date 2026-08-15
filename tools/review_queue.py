#!/usr/bin/env python3
"""
review_queue.py — 把「等教师复核」从一句话变成一件能干的活。

454 条待复核锚点摊给老师看，等于没给。真实情况是杠杆差着两个数量级：
判定「能仔细观察和比较」会连带解锁 34 条下游锚点；判定某条孤立的
MATRIX 锚点只影响它自己。所以队列必须按杠杆排序，老师从上往下做，
做多少算多少，随时停都有净收益。

产出两份：
  · review-queue/queue.jsonl   机器可读，带杠杆分与全部判定材料
  · review-queue/review.html   老师直接打开就能判，判完导出粘回来

判定材料一次给全（课标原文、判定标准、官方例题、下游是谁），
不让老师为了判一条去别处翻资料 —— 翻资料的成本比判断本身高得多。

    python3 tools/review_queue.py
"""
import collections, glob, html, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USABLE = {'auto-confirmed', 'expert-confirmed'}


def load():
    A = {}
    for f in sorted((ROOT / 'anchors').glob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            if l.strip():
                a = json.loads(l); A[a['id']] = a
    E = [json.loads(l) for f in sorted((ROOT / 'edges').glob('*.jsonl'))
         for l in f.open(encoding='utf-8') if l.strip()]
    L = [json.loads(l) for f in sorted(ROOT.glob('lists/**/*.jsonl'))
         for l in f.open(encoding='utf-8') if l.strip()]
    X = {}
    p = ROOT / 'examples/math.jsonl'
    if p.exists():
        for l in p.open(encoding='utf-8'):
            if l.strip():
                x = json.loads(l); X[x['no']] = x
    return A, E, L, X


def main():
    A, E, L, X = load()
    live = {k: v for k, v in A.items() if not v.get('deprecated')}

    down = collections.defaultdict(list)
    for e in E:
        down[e['prerequisiteId']].append(e['anchorId'])
    gated = collections.Counter()
    for x in L:
        for aid in (x.get('anchorIds') or []):
            gated[aid] += 1

    rows = []
    for a in live.values():
        if a['reviewStatus'] in USABLE:
            continue
        d = down.get(a['id'], [])
        g = gated[a['id']]
        # 杠杆 = 直接解锁的清单条目 + 下游锚点×3。
        # 下游权重更高是因为解锁一条下游锚点等于把整条链往前推，
        # 而清单条目是一次性的量。
        score = g + len(d) * 3
        prov = a.get('provenance') or {}
        rows.append({
            'anchorId': a['id'], 'discipline': a['discipline'], 'track': a['track'],
            'statement': a['statement'], 'reviewStatus': a['reviewStatus'],
            'stage': a.get('stageHint'), 'assessment': a.get('assessment'),
            'evidence': a.get('evidence') or [],
            'srcText': prov.get('srcText'), 'srcPage': prov.get('srcPage'),
            'exampleRefs': prov.get('exampleRefs') or [],
            'gatedItems': g, 'downstream': d[:12], 'downstreamCount': len(d),
            'leverage': score,
            'reviewNote': a.get('reviewNote'),
        })
    rows.sort(key=lambda r: (-r['leverage'], r['discipline']))

    out = ROOT / 'review-queue'
    out.mkdir(exist_ok=True)
    with (out / 'queue.jsonl').open('w', encoding='utf-8') as f:
        for i, r in enumerate(rows, 1):
            f.write(json.dumps({**r, 'rank': i}, ensure_ascii=False) + '\n')
    print(f"  → review-queue/queue.jsonl  {len(rows)} 条")

    top = rows[:120]                      # 复核台只放杠杆最高的一批，别一次给 454 条
    cum = 0
    for r in top:
        cum += r['leverage']
    total = sum(r['leverage'] for r in rows)
    print(f"  前 120 条占总杠杆的 {cum / total:.0%} —— 老师做完这批就拿走了大部分收益")

    (out / 'review.html').write_text(sheet(top, A, X, len(rows), cum / total), encoding='utf-8')
    print(f"  → review-queue/review.html  {len(top)} 条（打开即可判，判完导出）")


def sheet(rows, A, X, total_n, share):
    def esc(s):
        return html.escape(str(s or ''))

    cards = []
    for i, r in enumerate(rows, 1):
        ex = ''.join(
            f"<div class=ex><b>课标例{n}「{esc(X[n]['title'])}」</b>"
            f"<p>{esc((X[n]['note'] or X[n]['body'])[:300])}</p></div>"
            for n in r['exampleRefs'] if n in X)
        dn = ''.join(f"<li>{esc(A[d]['statement'] if d in A else d)}</li>"
                     for d in r['downstream'])
        ev = ''.join(f"<li>{esc(e)}</li>" for e in r['evidence'])
        stg = r['stage'] or {}
        cards.append(f"""
<article class=card data-id="{esc(r['anchorId'])}" data-i="{i}">
  <header>
    <span class=rank>{i}</span>
    <div class=hd>
      <div class=stmt>{esc(r['statement'])}</div>
      <div class=meta>
        <span class=pill>{esc(r['discipline'])}</span>
        <span class=pill>{esc(stg.get('min',''))}–{esc(stg.get('max',''))}</span>
        <span class="pill st-{esc(r['reviewStatus'])}">{esc(r['reviewStatus'])}</span>
        <span class=lev>解锁 {r['gatedItems']} 条目 · {r['downstreamCount']} 条下游</span>
      </div>
    </div>
  </header>
  <div class=body>
    <div class=col>
      <h4>课标原文</h4><p class=src>{esc(r['srcText']) or '（未留存）'}</p>
      <h4>怎么问</h4><p class=ask>{esc(r['assessment'])}</p>
    </div>
    <div class=col>
      <h4>算「会了」的表现</h4><ul>{ev}</ul>
      {f'<h4>下游（判通过即解锁）</h4><ul class=dn>{dn}</ul>' if dn else ''}
      {ex}
    </div>
  </div>
  <footer>
    <div class=btns>
      <button data-v=pass>通过</button>
      <button data-v=rewrite>要改写</button>
      <button data-v=drop>废弃</button>
      <button data-v=skip>拿不准</button>
    </div>
    <input class=note placeholder="改写成什么 / 为什么废弃（选填）">
  </footer>
</article>""")

    return f"""<meta charset=utf-8><title>K12 底座 · 教师复核台</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f4f6f5;color:#182420;font:15px/1.6 -apple-system,"PingFang SC",sans-serif;padding:28px 20px 120px}}
.wrap{{max-width:1080px;margin:0 auto}}
h1{{font-size:26px;font-weight:640;letter-spacing:-.02em}}
.lede{{color:#5b6b65;margin:8px 0 6px;max-width:64ch}}
.warn{{background:#fff8e6;border:1px solid #e6d199;border-radius:10px;padding:12px 15px;margin:16px 0 26px;font-size:13.5px;color:#6b5320}}
.card{{background:#fff;border:1px solid #dfe5e2;border-radius:13px;margin-bottom:16px;overflow:hidden}}
.card.done{{opacity:.5}}
header{{display:flex;gap:14px;padding:15px 18px;border-bottom:1px solid #eef1f0;align-items:flex-start}}
.rank{{flex:none;width:30px;height:30px;border-radius:8px;background:#0e6e5b;color:#fff;display:grid;place-items:center;font:600 13px ui-monospace,monospace}}
.stmt{{font-weight:600;font-size:15.5px}}
.meta{{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px;align-items:center}}
.pill{{font-size:11.5px;padding:2px 9px;border-radius:99px;background:#eef2f0;color:#4a5b55}}
.st-disputed{{background:#fbe9e8;color:#8d3d38}}
.st-llm-proposed{{background:#f0eafc;color:#5b4494}}
.lev{{font-size:12px;color:#7b8a84;font-variant-numeric:tabular-nums}}
.body{{display:grid;grid-template-columns:1fr 1fr;gap:22px;padding:16px 18px}}
h4{{font-size:11px;letter-spacing:.12em;color:#8a9a94;margin:0 0 5px;text-transform:uppercase}}
.col>*+h4{{margin-top:14px}}
.src{{background:#f7faf9;border-left:2px solid #cfdad6;padding:7px 11px;font-size:13.5px;color:#3d4f49}}
.ask{{font-size:13.5px;color:#3d4f49}}
ul{{margin-left:17px;font-size:13.5px;color:#4a5b55}}
.dn li{{color:#0e6e5b}}
.ex{{background:#f2f8f6;border:1px solid #cfe3dc;border-radius:9px;padding:10px 12px;margin-top:12px;font-size:13px}}
.ex p{{color:#3d4f49;margin-top:4px}}
footer{{display:flex;gap:12px;padding:13px 18px;background:#fafbfb;border-top:1px solid #eef1f0;align-items:center}}
.btns{{display:flex;gap:7px;flex:none}}
button{{font:600 13px inherit;padding:8px 15px;border-radius:8px;border:1px solid #cfdad6;background:#fff;cursor:pointer}}
button:hover{{border-color:#0e6e5b}}
button.on{{background:#0e6e5b;border-color:#0e6e5b;color:#fff}}
button[data-v=drop].on{{background:#8d3d38;border-color:#8d3d38}}
button[data-v=skip].on{{background:#7b8a84;border-color:#7b8a84}}
.note{{flex:1;font:inherit;font-size:13px;padding:8px 11px;border:1px solid #dfe5e2;border-radius:8px}}
#dock{{position:fixed;left:0;right:0;bottom:0;background:rgba(244,246,245,.96);backdrop-filter:blur(10px);border-top:1px solid #cfdad6;padding:13px 20px}}
#dock .in{{max-width:1080px;margin:0 auto;display:flex;gap:14px;align-items:center}}
#stat{{font-size:13.5px;color:#5b6b65;flex:1;font-variant-numeric:tabular-nums}}
#dock button{{padding:10px 18px}}
#dock button.go{{background:#0e6e5b;border-color:#0e6e5b;color:#fff}}
textarea{{position:fixed;left:-9999px}}
@media(max-width:820px){{.body{{grid-template-columns:1fr}}}}
</style>
<div class=wrap>
<h1>教师复核台</h1>
<p class=lede>按<b>杠杆</b>排序：判一条能解锁多少下游，排在前面的先判。做多少算多少，随时停都有净收益。</p>
<div class=warn><b>这里只放了杠杆最高的 {len(rows)} 条</b>（全库待复核 {total_n} 条）。
这 {len(rows)} 条占全部杠杆的 <b>{share:.0%}</b> —— 判完这批，剩下的多是孤立锚点，边际收益陡降。<br>
判定材料已一次给全（课标原文、判定标准、官方例题、下游是谁），不需要另外翻资料。</div>
{''.join(cards)}
</div>
<div id=dock><div class=in>
  <span id=stat>未判定</span>
  <button onclick="dl()">导出判定结果</button>
  <button class=go onclick="cp()">复制成给 AI 的指令</button>
</div></div>
<textarea id=buf></textarea>
<script>
const R = {{}};
document.querySelectorAll('.card').forEach(c => {{
  c.querySelectorAll('button[data-v]').forEach(b => b.onclick = () => {{
    c.querySelectorAll('button[data-v]').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    R[c.dataset.id] = {{ verdict: b.dataset.v, note: c.querySelector('.note').value,
                         statement: c.querySelector('.stmt').textContent }};
    c.classList.toggle('done', b.dataset.v !== 'rewrite');
    upd();
  }});
  c.querySelector('.note').oninput = e => {{ if (R[c.dataset.id]) R[c.dataset.id].note = e.target.value; upd(); }};
}});
function upd() {{
  const v = Object.values(R), n = v.length;
  const c = k => v.filter(x => x.verdict === k).length;
  document.getElementById('stat').textContent = n
    ? `已判 ${{n}}/{len(rows)}　通过 ${{c('pass')}}　改写 ${{c('rewrite')}}　废弃 ${{c('drop')}}　拿不准 ${{c('skip')}}`
    : '未判定';
}}
function payload() {{
  return Object.entries(R).map(([id, r]) => ({{ anchorId: id, ...r }}));
}}
function dl() {{
  const b = new Blob([payload().map(x => JSON.stringify(x)).join('\\n')],
                     {{ type: 'application/x-ndjson' }});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(b); a.download = 'review-verdicts.jsonl'; a.click();
}}
function cp() {{
  const p = payload();
  if (!p.length) {{ document.getElementById('stat').textContent = '还没判'; return; }}
  const t = '教师复核结果，按这个更新底座：\\n' + p.map(x =>
    `- ${{x.anchorId}} ${{x.verdict}}${{x.note ? '：' + x.note : ''}}　（${{x.statement}}）`).join('\\n');
  const b = document.getElementById('buf');
  b.value = t; b.select();
  navigator.clipboard.writeText(t).then(
    () => document.getElementById('stat').textContent = '已复制，粘回对话即可',
    () => document.getElementById('stat').textContent = '复制失败，已选中文本，按 ⌘C');
}}
upd();
</script>"""


if __name__ == '__main__':
    main()
