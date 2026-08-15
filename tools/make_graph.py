#!/usr/bin/env python3
"""
make_graph.py — 生成单文件图谱页（布局离线算好，烤进 HTML）。

为什么不在浏览器里跑力导向：1,400 节点的 O(n²) 斥力每帧 200 万次运算，
低端设备直接卡死，而且每次打开布局都不一样，没法讨论「左上角那一片」。
离线算一次、烤进去 → 确定性、秒开、任何设备都能跑。

布局不是纯力导向：**Y 轴锚定学段**。课标的学段序是免费且可信的结构，
用它当纵轴，图就从一团毛线变成「学习进程从上往下流」，老师一眼能看懂。

  python3 tools/make_graph.py
"""
import argparse, collections, json, math, random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE_ORD = {'G1': 1, 'G2': 2, 'G3': 3, 'G4': 4, 'G5': 5, 'G6': 6, 'G7': 7, 'G8': 8, 'G9': 9}
COLORS = {
    '数学': '#4a9eff', '语文': '#ff6b6b', '英语': '#ffa94d', '物理': '#845ef7',
    '化学': '#20c997', '生物学': '#51cf66', '历史': '#f783ac', '地理': '#38d9a9',
    '道德与法治': '#fcc419', '科学': '#22b8cf', '信息科技': '#748ffc',
    '劳动': '#a9e34b', '艺术': '#e599f7', '体育与健康': '#ff922b',
}
W, H = 2000, 1500


def load():
    anchors, edges = [], []
    for f in sorted((ROOT / 'anchors').rglob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            anchors.append(json.loads(l))
    for f in sorted((ROOT / 'edges').rglob('*.jsonl')):
        for l in f.open(encoding='utf-8'):
            edges.append(json.loads(l))
    return anchors, edges


def layout(nodes, edges, iters=460, seed=42):
    """力导向 + 学段 Y 锚定 + 学科聚类。网格分桶做斥力近似，O(n·k) 而不是 O(n²)。

    调参教训：第一版斥力压过引力，出来是整齐的点阵不是图 —— 好看的图靠的是
    「边把相关的点拽成团、斥力只负责不重叠」，斥力一大就把结构抹平了。
    另外光靠边不够：76% 的锚点才有边，孤点会飘散，所以再加一层同学科弱聚类。
    """
    rnd = random.Random(seed)
    idx = {n['id']: i for i, n in enumerate(nodes)}
    N = len(nodes)
    # Y 目标：学段决定纵向位置
    ytar = []
    for n in nodes:
        s = STAGE_ORD.get((n.get('stageHint') or {}).get('min'), 5)
        ytar.append(H * 0.08 + (s - 1) / 8.0 * H * 0.84)
    # X 初值：按学科散在一个环上，避免一开始全挤在中间，也避免排成整齐的列
    discs = sorted({n['discipline'] for n in nodes})
    dx = {}
    for i, d in enumerate(discs):
        ang = 2 * math.pi * i / len(discs)
        dx[d] = W / 2 + math.cos(ang) * W * 0.33
    x = [dx[n['discipline']] + rnd.uniform(-140, 140) for n in nodes]
    y = [ytar[i] + rnd.uniform(-30, 30) for i in range(N)]

    E = [(idx[e['prerequisiteId']], idx[e['anchorId']]) for e in edges
         if e['prerequisiteId'] in idx and e['anchorId'] in idx]
    deg = [1] * N
    for a, b in E:
        deg[a] += 1; deg[b] += 1

    # 学科质心，用来做弱聚类
    disc_idx = collections.defaultdict(list)
    for i, n in enumerate(nodes):
        disc_idx[n['discipline']].append(i)

    CELL = 92.0
    for it in range(iters):
        t = 1.0 - it / iters
        fx = [0.0] * N; fy = [0.0] * N
        # 斥力：只跟同格及相邻格的点算
        grid = collections.defaultdict(list)
        for i in range(N):
            grid[(int(x[i] // CELL), int(y[i] // CELL))].append(i)
        for (gx, gy), members in grid.items():
            near = []
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    near += grid.get((gx + ox, gy + oy), ())
            for i in members:
                for j in near:
                    if i >= j:
                        continue
                    ddx = x[i] - x[j]; ddy = y[i] - y[j]
                    d2 = ddx * ddx + ddy * ddy + 0.01
                    if d2 > CELL * CELL * 4:
                        continue
                    f = 1150.0 / d2
                    fx[i] += ddx * f; fy[i] += ddy * f
                    fx[j] -= ddx * f; fy[j] -= ddy * f
        # 引力：边把两端拽成团（横向为主，纵向让位给学段锚）
        for a, b in E:
            ddx = x[b] - x[a]; ddy = y[b] - y[a]
            d = math.hypot(ddx, ddy) + 0.01
            f = (d - 70.0) * 0.030
            fx[a] += ddx / d * f * 90; fy[a] += ddy / d * f * 16
            fx[b] -= ddx / d * f * 90; fy[b] -= ddy / d * f * 16
        # 同学科弱聚类：只有 76% 的锚点有边，孤点得靠这个才不飘散
        for d, members in disc_idx.items():
            cx = sum(x[i] for i in members) / len(members)
            for i in members:
                fx[i] += (cx - x[i]) * 0.020
        for i in range(N):
            fy[i] += (ytar[i] - y[i]) * 0.20           # 学段锚
            fx[i] += (W / 2 - x[i]) * 0.0010           # 弱向心，防飘散
            step = 2.2 * t + 0.25
            x[i] = min(W - 30, max(30, x[i] + max(-24, min(24, fx[i])) * step))
            y[i] = min(H - 30, max(30, y[i] + max(-24, min(24, fy[i])) * step))
    return x, y


HTML = r"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0c;color:#e8e6e1;font:15px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}
canvas{display:block;cursor:grab}canvas.drag{cursor:grabbing}
#hero{position:fixed;left:46px;top:100px;max-width:390px;pointer-events:none;z-index:5;transition:opacity .35s;
 background:linear-gradient(90deg,rgba(10,10,12,.94) 60%,rgba(10,10,12,0));padding:22px 40px 26px 0;border-radius:0 40px 40px 0}
#hero h1{font-size:50px;line-height:1.06;font-weight:600;letter-spacing:-.02em;margin-bottom:20px}
#hero .kicker{font-size:12px;letter-spacing:.18em;color:#8b8780;margin-bottom:22px}
#hero p{color:#a5a099;font-size:14px}
#hero b{color:#e8e6e1;font-weight:600}
#legend{position:fixed;right:24px;bottom:24px;background:rgba(18,18,21,.9);backdrop-filter:blur(8px);border:1px solid #26262b;border-radius:12px;padding:13px 15px;z-index:6;max-height:52vh;overflow:auto}
#legend{transition:opacity .3s}
#legend h4{font-size:10px;letter-spacing:.14em;color:#7d7972;margin-bottom:9px;font-weight:600}
.li{display:flex;align-items:center;gap:9px;padding:3px 0;cursor:pointer;font-size:13px;opacity:.95}
.li.off{opacity:.3}.li .dot{width:9px;height:9px;border-radius:50%;flex:none}
.li .n{margin-left:auto;color:#7d7972;font-variant-numeric:tabular-nums;font-size:12px}
#panel{position:fixed;right:0;top:0;bottom:0;width:410px;background:rgba(14,14,17,.97);backdrop-filter:blur(12px);border-left:1px solid #26262b;padding:26px 24px;overflow:auto;transform:translateX(100%);transition:transform .26s;z-index:8}
#panel.on{transform:none}
#panel .tag{display:inline-block;font-size:11px;padding:2px 9px;border-radius:99px;border:1px solid #33333a;color:#a5a099;margin:0 5px 8px 0}
#panel h2{font-size:21px;line-height:1.45;margin:10px 0 6px;font-weight:600}
#panel h5{font-size:10px;letter-spacing:.14em;color:#7d7972;margin:22px 0 8px;font-weight:600}
#panel ul{padding-left:17px}#panel li{margin:5px 0;color:#c8c4bd;font-size:13.5px}
#panel .ask{color:#a5a099;font-size:14px;line-height:1.62;margin-top:4px}
#panel .big{font-size:42px;font-weight:600;letter-spacing:-.03em;margin:24px 0 0;line-height:1}
#panel .big em{font-style:normal;font-size:13px;font-weight:400;color:#a5a099;margin-left:9px;letter-spacing:0}
#panel .bignote{color:#6d6a64;font-size:12.5px;margin-top:7px}
#panel h5 b{color:#e8e6e1;margin-left:5px}
.row{display:flex;align-items:flex-start;gap:10px;padding:8px 0;cursor:pointer;border-bottom:1px solid rgba(255,255,255,.04)}
.row:last-child{border-bottom:none}.row:hover .t{color:#fff}
.row .dot{width:7px;height:7px;border-radius:50%;flex:none;margin-top:7px}
.row .t{font-size:13.5px;line-height:1.45;flex:1;color:#c8c4bd}
.row .g{font-size:11.5px;color:#6d6a64;flex:none}
.none{color:#6d6a64;font-size:13px;font-style:italic;padding:6px 0}
#back{background:none;border:1px solid #26262b;border-radius:8px;color:#a5a099;font:inherit;font-size:12px;padding:4px 11px;cursor:pointer;margin-bottom:14px}
#back:hover{color:#fff}
#close{position:absolute;right:16px;top:14px;background:none;border:none;color:#7d7972;font-size:26px;cursor:pointer;line-height:1}
#top{position:fixed;left:0;right:0;top:0;padding:16px 22px;display:flex;gap:14px;align-items:center;z-index:7;pointer-events:none}
#top *{pointer-events:auto}
#q{background:rgba(18,18,21,.9);border:1px solid #26262b;border-radius:9px;color:#e8e6e1;padding:8px 13px;font:inherit;font-size:13px;width:240px}
.badge{font-size:11px;color:#8b8780;background:rgba(18,18,21,.85);border:1px solid #26262b;border-radius:99px;padding:5px 11px}
#axis{position:fixed;left:0;top:0;bottom:0;width:52px;pointer-events:none;z-index:4}
#axis div{position:absolute;font-size:10px;color:#4e4e55;white-space:nowrap;letter-spacing:.1em;transform:translateY(-50%)}
#tip{position:fixed;pointer-events:none;background:rgba(18,18,21,.96);border:1px solid #33333a;border-radius:8px;padding:7px 11px;font-size:12.5px;max-width:320px;display:none;z-index:9}
</style></head><body>
<canvas id="cv"></canvas>
<div id="axis"></div>
<div id="hero">
  <div class="kicker">K12 教育的能力结构 · 义务教育课程标准 2022</div>
  <h1>一个孩子<br>要学的全部。</h1>
  <p><b>__NC__</b> 条能力断言，<b>__EC__</b> 条先修依赖，覆盖 <b>__DC__</b> 个学科。<br>
  <b>点任意一个点</b>，看它之前必须先掌握什么。</p>
</div>
<div id="top">
  <input id="q" placeholder="搜索能力…（回车跳转）">
  <span class="badge" id="stat"></span>
  <span class="badge" style="color:#c98b2f">全部未经教师复核</span>
</div>
<div id="legend"><h4>学科 · 点击开关</h4><div id="ls"></div></div>
<div id="panel"><button id="close">×</button><div id="pc"></div></div>
<div id="tip"></div>
<script>
const N = __NODES__, E = __EDGES__, COLOR = __COLORS__;
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
let vw, vh, scale = 1, ox = 0, oy = 0, sel = null, hov = null;
const off = new Set();
const byId = new Map(N.map(n => [n.i, n]));
const pre = new Map(), post = new Map();
for (const n of N) { pre.set(n.i, []); post.set(n.i, []); }
for (const [a, b] of E) { pre.get(b).push(a); post.get(a).push(b); }   // a 是 b 的前置

function fit() {
  vw = cv.width = innerWidth * devicePixelRatio; vh = cv.height = innerHeight * devicePixelRatio;
  cv.style.width = innerWidth + 'px'; cv.style.height = innerHeight + 'px';
  const s = Math.min(innerWidth / __W__, innerHeight / __H__) * 0.92;
  scale = s; ox = (innerWidth - __W__ * s) / 2; oy = (innerHeight - __H__ * s) / 2;
  draw();
}
const sx = x => (x * scale + ox) * devicePixelRatio;
const sy = y => (y * scale + oy) * devicePixelRatio;

function ancestors(id, cap = 900) {
  const seen = new Set(), q = [id];
  while (q.length && seen.size < cap) {
    const v = q.pop();
    for (const p of pre.get(v) || []) if (!seen.has(p)) { seen.add(p); q.push(p); }
  }
  return seen;
}
function descendants(id, cap = 900) {
  const seen = new Set(), q = [id];
  while (q.length && seen.size < cap) {
    const v = q.pop();
    for (const p of post.get(v) || []) if (!seen.has(p)) { seen.add(p); q.push(p); }
  }
  return seen;
}

let hi = null;
function draw() {
  ctx.fillStyle = '#0a0a0c'; ctx.fillRect(0, 0, vw, vh);
  const on = n => !off.has(n.d);
  // 边
  ctx.lineWidth = Math.max(0.5, 0.7 * devicePixelRatio);
  for (const [a, b] of E) {
    const na = byId.get(a), nb = byId.get(b);
    if (!na || !nb || !on(na) || !on(nb)) continue;
    const lit = hi && (hi.has(a) && (hi.has(b) || b === sel));
    ctx.strokeStyle = lit ? 'rgba(255,255,255,.45)' : (hi ? 'rgba(120,120,132,.045)' : 'rgba(120,120,132,.11)');
    ctx.beginPath(); ctx.moveTo(sx(na.x), sy(na.y)); ctx.lineTo(sx(nb.x), sy(nb.y)); ctx.stroke();
  }
  // 点
  for (const n of N) {
    if (!on(n)) continue;
    const lit = !hi || hi.has(n.i) || n.i === sel;
    const r = (2.0 + Math.sqrt(n.o) * 1.15) * scale * devicePixelRatio;
    ctx.globalAlpha = lit ? 1 : 0.13;
    ctx.fillStyle = COLOR[n.d] || '#888';
    ctx.beginPath(); ctx.arc(sx(n.x), sy(n.y), Math.max(1.4, r), 0, 7); ctx.fill();
    if (n.i === sel) {
      ctx.globalAlpha = 1; ctx.strokeStyle = '#fff'; ctx.lineWidth = 2 * devicePixelRatio;
      ctx.beginPath(); ctx.arc(sx(n.x), sy(n.y), Math.max(5, r + 4 * devicePixelRatio), 0, 7); ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}

function pick(mx, my) {
  let best = null, bd = 1e9;
  for (const n of N) {
    if (off.has(n.d)) continue;
    const dx = mx - (n.x * scale + ox), dy = my - (n.y * scale + oy);
    const d = dx * dx + dy * dy;
    if (d < bd) { bd = d; best = n; }
  }
  return bd < 220 ? best : null;
}

const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
let stack = [];
const gL = n => n.s ? 'G' + n.s : '';
/** 与 3D 版同一套：大数给「全部前置总数」，列表只列直接前置，靠返回一跳一跳走。
 *  一次倒出 200 条传递前置，人是读不动的。 */
function show(n, push = true) {
  if (push && sel && sel !== n.i) stack.push(sel);
  sel = n.i; hi = ancestors(n.i); hi.add(n.i);
  const total = ancestors(n.i).size;
  const dp = (pre.get(n.i) || []).map(i => byId.get(i)).filter(Boolean).sort((a, b) => a.s - b.s);
  const dn = (post.get(n.i) || []).map(i => byId.get(i)).filter(Boolean).sort((a, b) => a.s - b.s);
  const c = COLOR[n.d] || '#888';
  const row = a => `<div class="row" onclick="jump('${a.i}')">
      <span class="dot" style="background:${COLOR[a.d] || '#888'}"></span>
      <span class="t">${esc(a.t)}</span><span class="g">${gL(a)}</span></div>`;
  document.getElementById('pc').innerHTML =
    (stack.length ? `<button id="back" onclick="goBack()">← 返回</button>` : '') + `
    <span class="tag" style="border-color:${c};color:${c}">${esc(n.d)}</span>
    <span class="tag">${esc(n.st || '未标注领域')}</span>
    <span class="tag">${gL(n) || '学段未定'}</span>
    <h2>${esc(n.t)}</h2>
    ${n.a ? `<p class="ask">${esc(n.a)}</p>` : ''}
    <div class="big">${total}<em>条前置，合计</em></div>
    <div class="bignote">一个学习者在此之前必须掌握的全部，一路回溯到底。</div>
    <h5>直接建立在<b>${dp.length}</b></h5>
    ${dp.length ? dp.map(row).join('') : '<div class="none">没有前置 —— 这是一个起点</div>'}
    <h5>接下来解锁<b>${dn.length}</b></h5>
    ${dn.length ? dn.slice(0, 24).map(row).join('') : '<div class="none">暂无后继</div>'}`;
  document.getElementById('panel').classList.add('on');
  document.getElementById('hero').style.opacity = 0;
  document.getElementById('legend').style.opacity = 0;
  draw();
}
window.goBack = () => { const p = stack.pop(); if (p) show(byId.get(p), false); else document.getElementById('close').onclick(); };
window.jump = id => { const n = byId.get(id); if (n) show(n); };

cv.addEventListener('click', e => {
  const n = pick(e.clientX, e.clientY);
  if (n) show(n); else { sel = null; hi = null; document.getElementById('panel').classList.remove('on');
    document.getElementById('hero').style.opacity = 1; document.getElementById('legend').style.opacity = 1; draw(); }
});
cv.addEventListener('mousemove', e => {
  const n = pick(e.clientX, e.clientY); const tip = document.getElementById('tip');
  if (n) { tip.style.display = 'block'; tip.style.left = (e.clientX + 14) + 'px'; tip.style.top = (e.clientY + 14) + 'px';
    tip.textContent = n.t; } else tip.style.display = 'none';
});
let drag = null;
cv.addEventListener('mousedown', e => { drag = [e.clientX - ox, e.clientY - oy]; cv.classList.add('drag'); });
addEventListener('mouseup', () => { drag = null; cv.classList.remove('drag'); });
addEventListener('mousemove', e => { if (drag) { ox = e.clientX - drag[0]; oy = e.clientY - drag[1]; draw(); } });
cv.addEventListener('wheel', e => {
  e.preventDefault();
  const k = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  ox = e.clientX - (e.clientX - ox) * k; oy = e.clientY - (e.clientY - oy) * k;
  scale *= k; draw();
}, { passive: false });
document.getElementById('close').onclick = () => {
  sel = null; hi = null; stack = []; document.getElementById('panel').classList.remove('on');
  document.getElementById('hero').style.opacity = 1;
  document.getElementById('legend').style.opacity = 1; draw();
};
document.getElementById('q').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const v = e.target.value.trim(); if (!v) return;
  const n = N.find(x => x.t.includes(v));
  if (n) { const k = 2.4 / scale; ox = innerWidth / 2 - n.x * scale * k; oy = innerHeight / 2 - n.y * scale * k; scale *= k; show(n); }
});

const counts = {};
for (const n of N) counts[n.d] = (counts[n.d] || 0) + 1;
document.getElementById('ls').innerHTML = Object.entries(counts).sort((a, b) => b[1] - a[1])
  .map(([d, c]) => `<div class="li" data-d="${esc(d)}"><span class="dot" style="background:${COLOR[d]}"></span>${esc(d)}<span class="n">${c}</span></div>`).join('');
document.querySelectorAll('.li').forEach(el => el.onclick = () => {
  const d = el.dataset.d;
  if (off.has(d)) { off.delete(d); el.classList.remove('off'); } else { off.add(d); el.classList.add('off'); }
  draw();
});
document.getElementById('stat').textContent = `${N.length} 个能力 · ${E.length} 条依赖`;
document.getElementById('axis').innerHTML = [[1,'一年级'],[3,'三年级'],[5,'五年级'],[7,'七年级'],[9,'九年级']].map(([g,t]) =>
  `<div style="top:${(0.08 + (g-1)/8*0.84)*100}%;left:10px">${t}</div>`).join('');
addEventListener('resize', fit); fit();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'tools/out/graph.html'))
    ap.add_argument('--iters', type=int, default=320)
    a = ap.parse_args()

    anchors, edges = load()
    ids = {x['id'] for x in anchors}
    edges = [e for e in edges if e['anchorId'] in ids and e['prerequisiteId'] in ids]
    print(f"节点 {len(anchors)} · 边 {len(edges)}")

    x, y = layout(anchors, edges, iters=a.iters)
    outdeg = collections.Counter(e['prerequisiteId'] for e in edges)

    nodes = [{
        'i': n['id'], 'd': n['discipline'], 'st': n.get('strand') or '',
        't': n['statement'], 's': STAGE_ORD.get((n.get('stageHint') or {}).get('min'), 0),
        'x': round(x[k], 1), 'y': round(y[k], 1), 'o': outdeg.get(n['id'], 0),
        'p': (n.get('provenance') or {}).get('srcPage', ''),
        'a': (n.get('assessment') or '').replace('{{name}}', '孩子').strip(),
    } for k, n in enumerate(anchors)]
    E = [[e['prerequisiteId'], e['anchorId']] for e in edges]

    html = (HTML
            .replace('__TITLE__', 'K12 教育的能力结构 · 2D 图谱')
            .replace('__NODES__', json.dumps(nodes, ensure_ascii=False, separators=(',', ':')))
            .replace('__EDGES__', json.dumps(E, separators=(',', ':')))
            .replace('__COLORS__', json.dumps(COLORS, ensure_ascii=False))
            .replace('__NC__', f"{len(nodes):,}").replace('__EC__', f"{len(E):,}")
            .replace('__DC__', str(len({n['d'] for n in nodes})))
            .replace('__W__', str(W)).replace('__H__', str(H)))
    p = Path(a.out); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding='utf-8')
    print(f"→ {p}  {p.stat().st_size/1024:.0f}KB")


if __name__ == '__main__':
    main()
