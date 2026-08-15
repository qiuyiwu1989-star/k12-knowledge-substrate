#!/usr/bin/env python3
"""
make_graph3d.py — 3D 互动图谱（单文件，Canvas 2D 手写投影，无任何外部依赖）。

为什么不用 WebGL/three.js：这一页要能离线双击打开、能塞进邮件发给校长、
能在教室的老机器上跑。1,191 节点 + 2,064 边用 Canvas 2D 的画家算法完全够，
代价是要自己做透视投影和深度排序 —— 值得。

布局：**Y 轴锚定学段，X/Z 在水平面力导向**。
纯随机的 3D 云团转起来好看但没信息；把年级放在竖轴上，转到任何角度
「低年级在上、高年级在下」这条线索都还在，图就同时是好看的和能读的。

性能：边按深度分桶后合并成 3 条 path 一次性 stroke，节点按「颜色×深度」分桶批绘，
把 2,000+ 次 draw call 压到 60 次以内，老机器也能 60fps。

  python3 tools/make_graph3d.py
"""
import argparse, collections, json, math, random
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_graph import load, COLORS, STAGE_ORD   # noqa: E402

R = 900.0          # 水平面半径
HGT = 1250.0       # 竖直跨度（学段轴）


def layout3d(nodes, edges, iters=420, seed=7):
    rnd = random.Random(seed)
    idx = {n['id']: i for i, n in enumerate(nodes)}
    N = len(nodes)

    ytar = []
    for n in nodes:
        s = STAGE_ORD.get((n.get('stageHint') or {}).get('min'), 5)
        ytar.append(-HGT / 2 + (s - 1) / 8.0 * HGT)

    discs = sorted({n['discipline'] for n in nodes})
    seed_xy = {}
    for i, d in enumerate(discs):
        ang = 2 * math.pi * i / len(discs)
        seed_xy[d] = (math.cos(ang) * R * 0.62, math.sin(ang) * R * 0.62)
    x = [seed_xy[n['discipline']][0] + rnd.uniform(-120, 120) for n in nodes]
    z = [seed_xy[n['discipline']][1] + rnd.uniform(-120, 120) for n in nodes]
    y = [ytar[i] + rnd.uniform(-25, 25) for i in range(N)]

    E = [(idx[e['prerequisiteId']], idx[e['anchorId']]) for e in edges
         if e['prerequisiteId'] in idx and e['anchorId'] in idx]
    disc_idx = collections.defaultdict(list)
    for i, n in enumerate(nodes):
        disc_idx[n['discipline']].append(i)

    CELL = 110.0
    for it in range(iters):
        t = 1.0 - it / iters
        fx = [0.0] * N; fy = [0.0] * N; fz = [0.0] * N
        # 斥力：3D 网格分桶
        grid = collections.defaultdict(list)
        for i in range(N):
            grid[(int(x[i] // CELL), int(y[i] // CELL), int(z[i] // CELL))].append(i)
        for cell, members in grid.items():
            gx, gy, gz = cell
            near = []
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    for oz in (-1, 0, 1):
                        near += grid.get((gx + ox, gy + oy, gz + oz), ())
            for i in members:
                for j in near:
                    if i >= j:
                        continue
                    ddx = x[i] - x[j]; ddy = y[i] - y[j]; ddz = z[i] - z[j]
                    d2 = ddx * ddx + ddy * ddy + ddz * ddz + 0.01
                    if d2 > CELL * CELL * 4:
                        continue
                    f = 2200.0 / d2
                    fx[i] += ddx * f; fy[i] += ddy * f; fz[i] += ddz * f
                    fx[j] -= ddx * f; fy[j] -= ddy * f; fz[j] -= ddz * f
        # 引力：边把两端拽近（竖向让位给学段锚）
        for a, b in E:
            ddx = x[b] - x[a]; ddy = y[b] - y[a]; ddz = z[b] - z[a]
            d = math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) + 0.01
            f = (d - 70.0) * 0.040
            fx[a] += ddx / d * f * 80; fz[a] += ddz / d * f * 80; fy[a] += ddy / d * f * 12
            fx[b] -= ddx / d * f * 80; fz[b] -= ddz / d * f * 80; fy[b] -= ddy / d * f * 12
        # 同学科弱聚类（24% 的锚点没有边，靠这个才不飘散）
        for d, members in disc_idx.items():
            cx = sum(x[i] for i in members) / len(members)
            cz = sum(z[i] for i in members) / len(members)
            for i in members:
                fx[i] += (cx - x[i]) * 0.009
                fz[i] += (cz - z[i]) * 0.009
        for i in range(N):
            fy[i] += (ytar[i] - y[i]) * 0.20
            # 弱向心：把云团收成球，别摊成饼
            fx[i] -= x[i] * 0.0016
            fz[i] -= z[i] * 0.0016
            step = 2.0 * t + 0.22
            cl = lambda v: max(-26, min(26, v))
            x[i] = max(-R * 1.5, min(R * 1.5, x[i] + cl(fx[i]) * step))
            y[i] = max(-HGT, min(HGT, y[i] + cl(fy[i]) * step))
            z[i] = max(-R * 1.5, min(R * 1.5, z[i] + cl(fz[i]) * step))

    # 居中 + 水平面归一化。弱向心力压不住 1,191 个点的漂移（实测 X 范围
    # 跑到 -963..1309，云团整个偏到右边），与其调力的参数不如算完直接平移缩放——
    # 布局是离线算的，事后修正是免费且确定的。
    mx = sum(x) / N; mz = sum(z) / N; my = sum(y) / N
    x = [v - mx for v in x]; z = [v - mz for v in z]; y = [v - my for v in y]
    rad = max(math.hypot(x[i], z[i]) for i in range(N)) or 1.0
    k = (R * 0.92) / rad
    x = [v * k for v in x]; z = [v * k for v in z]
    return x, y, z


HTML = r"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#080a11;--fg:#eceaf0;--mut:#7d8496;--dim:#565d6e;--line:#1c2130;--card:rgba(13,16,25,.94)}
body{background:var(--bg);color:var(--fg);font:15px/1.62 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}
canvas{display:block;cursor:grab}canvas.drag{cursor:grabbing}
#logo{position:fixed;left:44px;top:34px;font-size:19px;font-weight:800;letter-spacing:.16em;z-index:6}
#logo span{color:var(--mut);font-weight:500;letter-spacing:.1em;font-size:12px;display:block;margin-top:5px}
/* hero 常驻，不随选中消失 —— 它是这一页的说明书 */
#hero{position:fixed;left:44px;top:23%;max-width:396px;pointer-events:none;z-index:5}
#hero h1{font-size:clamp(40px,4.6vw,64px);line-height:1.02;font-weight:600;letter-spacing:-.03em;margin-bottom:26px}
#hero h1 i{color:#e8607d;font-style:normal}
#hero p{color:var(--mut);font-size:13.5px;margin-bottom:11px;max-width:352px}
#hero b{color:var(--fg);font-weight:600}
#hero .sub{color:var(--dim);font-size:12.5px}
#cta{position:fixed;left:44px;top:calc(23% + 330px);display:flex;gap:14px;align-items:center;z-index:6}
#cta a{font-size:12.5px;color:var(--fg);background:rgba(20,24,36,.9);border:1px solid var(--line);border-radius:99px;padding:8px 16px;text-decoration:none}
#cta a:hover{border-color:var(--dim)}
#cta em{font-style:normal;font-size:10.5px;letter-spacing:.13em;color:var(--dim)}
#legend{position:fixed;left:44px;bottom:36px;z-index:6}
#legend h4{font-size:10px;letter-spacing:.17em;color:var(--dim);margin-bottom:11px;font-weight:600}
.li{display:flex;align-items:center;gap:11px;padding:2.5px 0;cursor:pointer;font-size:12.5px;width:290px;color:var(--mut);transition:color .2s,opacity .2s}
.li .dot{width:8px;height:8px;border-radius:50%;flex:none;transition:opacity .2s}
.li .n{margin-left:auto;font-variant-numeric:tabular-nums;font-size:11.5px;color:var(--dim)}
.li:hover,.li.active{color:var(--fg)}
.li.active .n{color:var(--fg)}
.li.off{opacity:.3}
.li.faded{opacity:.34}
/* 面板：标题 → 家长向问句 → 全部前置总数 → 直接前置 → 解锁什么 */
#panel{position:fixed;right:26px;top:26px;width:412px;max-height:calc(100vh - 52px);background:var(--card);backdrop-filter:blur(16px);
 border:1px solid var(--line);border-radius:18px;padding:24px 26px 26px;overflow:auto;z-index:8;
 opacity:0;transform:translateY(-8px) scale(.985);pointer-events:none;transition:opacity .22s,transform .22s}
#panel.on{opacity:1;transform:none;pointer-events:auto}
#panel .hdr{display:flex;align-items:center;gap:9px;margin-bottom:11px}
#panel .hdr .dot{width:8px;height:8px;border-radius:50%;flex:none}
#panel .hdr span{font-size:10.5px;letter-spacing:.15em;color:var(--mut);text-transform:uppercase}
#panel h2{font-size:23px;line-height:1.34;font-weight:600;letter-spacing:-.01em;margin-bottom:13px}
#panel .ask{color:var(--mut);font-size:14px;line-height:1.62}
#panel .big{font-size:44px;font-weight:600;letter-spacing:-.03em;margin:26px 0 0;line-height:1}
#panel .big em{font-style:normal;font-size:13.5px;font-weight:400;color:var(--mut);margin-left:9px;letter-spacing:0}
#panel .bignote{color:var(--dim);font-size:12.5px;margin-top:7px}
#panel h5{font-size:10.5px;letter-spacing:.15em;color:var(--dim);margin:26px 0 3px;font-weight:600;text-transform:uppercase}
#panel h5 b{color:var(--fg);margin-left:5px;font-weight:600}
.row{display:flex;align-items:flex-start;gap:10px;padding:8px 0;cursor:pointer;border-bottom:1px solid rgba(255,255,255,.035)}
.row:last-child{border-bottom:none}
.row:hover .t{color:#fff}
.row .dot{width:7px;height:7px;border-radius:50%;flex:none;margin-top:7px}
.row .t{font-size:13.5px;line-height:1.45;flex:1;color:#cdd2dd;transition:color .15s}
.row .g{font-size:11.5px;color:var(--dim);flex:none;margin-top:1px}
.none{color:var(--dim);font-size:13px;font-style:italic;padding:6px 0}
#back{background:none;border:1px solid var(--line);border-radius:8px;color:var(--mut);font:inherit;font-size:12px;padding:4px 11px;cursor:pointer;margin-bottom:14px}
#back:hover{color:var(--fg);border-color:var(--dim)}
#close{position:absolute;right:16px;top:15px;background:none;border:none;color:var(--dim);font-size:22px;cursor:pointer;line-height:1}
#close:hover{color:var(--fg)}
#q{position:fixed;right:26px;top:26px;background:rgba(20,24,36,.9);border:1px solid var(--line);border-radius:9px;color:var(--fg);padding:8px 14px;font:inherit;font-size:13px;width:212px;z-index:7}
#hint{position:fixed;right:30px;bottom:26px;font-size:11.5px;color:var(--dim);z-index:5}
#hint b{color:var(--mut);font-weight:600}
/* 悬停是信息卡，不是小提示条 */
#tip{position:fixed;pointer-events:none;background:var(--card);backdrop-filter:blur(14px);border:1px solid var(--line);
 border-radius:14px;padding:15px 17px;max-width:330px;display:none;z-index:9;box-shadow:0 12px 40px rgba(0,0,0,.5)}
#tip .hdr{display:flex;align-items:center;gap:8px;margin-bottom:8px}
#tip .hdr .dot{width:7px;height:7px;border-radius:50%}
#tip .hdr span{font-size:10px;letter-spacing:.14em;color:var(--mut);text-transform:uppercase}
#tip h3{font-size:16px;line-height:1.36;font-weight:600;margin-bottom:7px}
#tip p{font-size:12.8px;line-height:1.55;color:var(--mut)}
#gr{position:fixed;left:0;top:0;bottom:0;width:34px;pointer-events:none;z-index:4}
#gr div{position:absolute;font-size:9.5px;color:#333a4a;letter-spacing:.1em;transform:translateY(-50%);left:12px}
#warn{position:fixed;left:50%;transform:translateX(-50%);top:26px;font-size:11px;color:#c98b2f;background:rgba(30,24,12,.8);
 border:1px solid #3a2f18;border-radius:99px;padding:5px 13px;z-index:7;white-space:nowrap}
/* 窄屏：hero 让位给图，但警示条和搜索必须都还在，且不能叠 */
@media(max-width:1180px){
  #hero,#legend,#cta{display:none}
  #logo{left:18px;top:16px;font-size:15px}#logo span{display:none}
  #warn{left:auto;right:18px;top:16px;transform:none}
  #q{top:52px;right:18px;width:180px}
  #hint{left:18px;right:18px;bottom:16px;text-align:center;font-size:10.5px}
  #panel{right:10px;top:88px;width:calc(100vw - 20px);max-width:400px;max-height:calc(100vh - 108px)}
}
@media(max-width:620px){#logo,#q{display:none}}
</style></head><body>
<canvas id="cv"></canvas><div id="gr"></div>
<div id="logo">K12 底座<span>YONGLE · 永乐教育</span></div>
<div id="hero">
  <h1>一个孩子<br>要学的全部<i>。</i></h1>
  <p><b>__NC__</b> 条能力断言、<b>__EC__</b> 条先修依赖，从认字到方程。</p>
  <p>每条依赖都写明了<b>什么必须排在前面、为什么</b>。<b>点任意一个点</b>，
     看一个学习者在此之前必须掌握的全部。</p>
  <p class="sub">由 AI 从教育部《义务教育课程标准（2022年版）》1,594 页扫描件构建，<br>开放数据，等待教师复核。</p>
</div>
<div id="cta">
  <a href="https://github.com/qiuyiwu1989-star/k12-knowledge-substrate" target="_blank" rel="noopener">在 GitHub 上查看</a>
  <a href="/2d/">2D 视角</a>
  <em>开放数据 · ODBL 1.0</em>
</div>
<div id="warn">全部条目未经教师复核</div>
<input id="q" placeholder="搜索能力…（回车定位）">
<div id="legend"><h4>学科 · 点击开关</h4><div id="ls"></div></div>
<div id="hint"><b>拖动</b>旋转 · <b>滚轮</b>缩放 · <b>点一个点</b>，然后顺着它的前置往回走</div>
<div id="panel"><button id="close">×</button><div id="pc"></div></div>
<div id="tip"></div>
<script>
const N = __NODES__, E = __EDGES__, COLOR = __COLORS__, HGT = __HGT__;
const cv = document.getElementById('cv'), ctx = cv.getContext('2d', { alpha: false });
const DPR = Math.min(2, devicePixelRatio || 1);
let W, H, yaw = .5, pitch = -.18, zoom = 1, sel = null, hi = null, auto = true, dragging = null;
let stack = [];                       // 面板导航历史，支持 ← Back 一跳一跳往回走
const off = new Set();
const byId = new Map(N.map(n => [n.i, n]));
const pre = new Map(), post = new Map();
for (const n of N) { pre.set(n.i, []); post.set(n.i, []); }
for (const [a, b] of E) { pre.get(b).push(a); post.get(a).push(b); }
const px = new Float32Array(N.length), py = new Float32Array(N.length), pz = new Float32Array(N.length);
let order = [];

function resize() {
  W = cv.width = innerWidth * DPR; H = cv.height = innerHeight * DPR;
  cv.style.width = innerWidth + 'px'; cv.style.height = innerHeight + 'px';
}
function project() {
  const sy = Math.sin(yaw), cyw = Math.cos(yaw), sp = Math.sin(pitch), cp = Math.cos(pitch);
  const f = Math.min(W, H) * .62 * zoom, CAM = 2600;
  for (let k = 0; k < N.length; k++) {
    const n = N[k];
    const X = n.x * cyw - n.z * sy, Z0 = n.x * sy + n.z * cyw;
    const Y = n.y * cp - Z0 * sp, Z = n.y * sp + Z0 * cp;
    const s = f / Math.max(60, CAM + Z);
    px[k] = W / 2 + X * s + W * .13; py[k] = H / 2 + Y * s; pz[k] = Z;
  }
  order = Array.from({ length: N.length }, (_, k) => k).sort((a, b) => pz[b] - pz[a]);
}
function autoFit(fill = .74) {
  const z0 = zoom; zoom = 1; project();
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
  for (let k = 0; k < N.length; k++) {
    if (off.has(N[k].d)) continue;
    if (px[k] < x0) x0 = px[k]; if (px[k] > x1) x1 = px[k];
    if (py[k] < y0) y0 = py[k]; if (py[k] > y1) y1 = py[k];
  }
  zoom = Math.min(W * .58 * fill / ((x1 - x0) || 1), H * fill / ((y1 - y0) || 1));
  if (!isFinite(zoom) || zoom <= 0) zoom = z0;
  zoom = Math.max(.25, Math.min(9, zoom));
}

const idxOf = new Map(N.map((n, k) => [n.i, k]));
function draw() {
  ctx.fillStyle = '#080a11'; ctx.fillRect(0, 0, W, H);
  project();
  const on = k => !off.has(N[k].d);
  const zmin = -1400, zspan = 2800;
  const selColor = sel ? (COLOR[byId.get(sel).d] || '#fff') : null;

  // 高亮时用「学科色」画子图，不用白色 —— 白色会盖掉学科这层信息
  const dim = [], lit = [];
  for (const [a, b] of E) {
    const ka = idxOf.get(a), kb = idxOf.get(b);
    if (ka === undefined || kb === undefined || !on(ka) || !on(kb)) continue;
    (hi && hi.has(a) && (hi.has(b) || b === sel) ? lit : dim).push([ka, kb]);
  }
  if (!hi || dim.length) {
    const bk = [[], [], []];
    for (const e of dim) {
      const t = ((pz[e[0]] + pz[e[1]]) / 2 - zmin) / zspan;
      bk[t < .34 ? 0 : t < .67 ? 1 : 2].push(e);
    }
    const al = hi ? [.028, .018, .01] : [.13, .085, .05];
    for (let i = 0; i < 3; i++) {
      if (!bk[i].length) continue;
      ctx.strokeStyle = `rgba(140,152,184,${al[i]})`; ctx.lineWidth = .65 * DPR;
      ctx.beginPath();
      for (const [a, b] of bk[i]) { ctx.moveTo(px[a], py[a]); ctx.lineTo(px[b], py[b]); }
      ctx.stroke();
    }
  }
  if (lit.length) {
    ctx.strokeStyle = selColor; ctx.globalAlpha = .55; ctx.lineWidth = 1.15 * DPR;
    ctx.beginPath();
    for (const [a, b] of lit) { ctx.moveTo(px[a], py[a]); ctx.lineTo(px[b], py[b]); }
    ctx.stroke(); ctx.globalAlpha = 1;
  }

  const groups = new Map();
  for (const k of order) {
    if (!on(k)) continue;
    const n = N[k], isLit = !hi || hi.has(n.i) || n.i === sel;
    const b = Math.min(3, (Math.max(0, Math.min(1, (pz[k] - zmin) / zspan)) * 4) | 0);
    const key = n.d + b + (isLit ? 1 : 0);
    if (!groups.has(key)) groups.set(key, { d: n.d, b, lit: isLit, it: [] });
    groups.get(key).it.push(k);
  }
  for (const g of groups.values()) {
    ctx.globalAlpha = (g.lit ? 1 : .07) * (1 - g.b * .2);
    ctx.fillStyle = COLOR[g.d] || '#888';
    ctx.beginPath();
    for (const k of g.it) {
      const r = (1.5 + Math.sqrt(N[k].o) * 1.05) * zoom * (2600 / (2600 + pz[k])) * DPR;
      ctx.moveTo(px[k] + r, py[k]); ctx.arc(px[k], py[k], Math.max(.85, r), 0, 7);
    }
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  if (sel != null) {
    const k = idxOf.get(sel);
    const r = (1.5 + Math.sqrt(byId.get(sel).o) * 1.05) * zoom * (2600 / (2600 + pz[k])) * DPR;
    ctx.fillStyle = selColor; ctx.beginPath(); ctx.arc(px[k], py[k], Math.max(4.5 * DPR, r), 0, 7); ctx.fill();
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.7 * DPR;
    ctx.beginPath(); ctx.arc(px[k], py[k], Math.max(8 * DPR, r + 5 * DPR), 0, 7); ctx.stroke();
  }
  const gr = document.getElementById('gr');
  if (!gr.dataset.b) { gr.innerHTML = [1,3,5,7,9].map(g => `<div data-g="${g}">G${g}</div>`).join(''); gr.dataset.b = 1; }
  const sp2 = Math.sin(pitch), cp2 = Math.cos(pitch), f2 = Math.min(W, H) * .62 * zoom;
  gr.querySelectorAll('div').forEach(el => {
    const g = +el.dataset.g, yy = -HGT / 2 + (g - 1) / 8 * HGT;
    el.style.top = ((H / 2 + yy * cp2 * f2 / (2600 + yy * sp2)) / DPR) + 'px';
  });
}
function tick() { if (auto && !dragging && !sel) { yaw += .0015; draw(); } requestAnimationFrame(tick); }

function ancestors(id, cap = 900) {
  const seen = new Set(), q = [id];
  while (q.length && seen.size < cap) { const v = q.pop();
    for (const p of pre.get(v) || []) if (!seen.has(p)) { seen.add(p); q.push(p); } }
  return seen;
}
const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const gLabel = n => n.s ? 'G' + n.s : '';

/** Marble 的关键设计：大字给「全部前置总数」，列表只列直接前置。
 *  一次倒出 200 条传递前置，人是读不动的；一跳一跳走才走得下去。 */
function show(n, push = true) {
  if (push && sel && sel !== n.i) stack.push(sel);
  sel = n.i; hi = ancestors(n.i); hi.add(n.i); auto = false;
  const total = ancestors(n.i).size;
  const dp = (pre.get(n.i) || []).map(i => byId.get(i)).filter(Boolean).sort((a, b) => a.s - b.s);
  const dn = (post.get(n.i) || []).map(i => byId.get(i)).filter(Boolean).sort((a, b) => a.s - b.s);
  const c = COLOR[n.d] || '#888';
  const row = a => `<div class="row" onclick="jump('${a.i}')">
      <span class="dot" style="background:${COLOR[a.d] || '#888'}"></span>
      <span class="t">${esc(a.t)}</span><span class="g">${gLabel(a)}</span></div>`;
  document.getElementById('pc').innerHTML =
    (stack.length ? `<button id="back" onclick="goBack()">← 返回</button>` : '') + `
    <div class="hdr"><span class="dot" style="background:${c}"></span>
      <span>${esc(n.st || n.d)} · ${gLabel(n) || '学段未定'}</span></div>
    <h2>${esc(n.t)}</h2>
    ${n.a ? `<p class="ask">${esc(n.a)}</p>` : ''}
    <div class="big">${total}<em>条前置，合计</em></div>
    <div class="bignote">一个学习者在此之前必须掌握的全部，一路回溯到底。</div>
    <h5>直接建立在<b>${dp.length}</b></h5>
    ${dp.length ? dp.map(row).join('') : '<div class="none">没有前置 —— 这是一个起点</div>'}
    <h5>接下来解锁<b>${dn.length}</b></h5>
    ${dn.length ? dn.slice(0, 24).map(row).join('') : '<div class="none">暂无后继</div>'}`;
  document.getElementById('panel').classList.add('on');
  document.getElementById('q').style.display = 'none';
  document.querySelectorAll('.li').forEach(el => el.classList.toggle('faded', el.dataset.d !== n.d));
  draw();
}
window.jump = id => { const n = byId.get(id); if (n) show(n); };
window.goBack = () => { const p = stack.pop(); if (p) show(byId.get(p), false); else clear(); };
function clear() {
  sel = null; hi = null; auto = true; stack = [];
  document.getElementById('panel').classList.remove('on');
  document.getElementById('q').style.display = '';
  document.querySelectorAll('.li').forEach(el => el.classList.remove('faded'));
  draw();
}
function pick(mx, my) {
  let best = -1, bd = 24 * 24;
  for (let k = 0; k < N.length; k++) {
    if (off.has(N[k].d)) continue;
    const dx = mx * DPR - px[k], dy = my * DPR - py[k], d = dx * dx + dy * dy;
    if (d < bd) { bd = d; best = k; }
  }
  return best >= 0 ? N[best] : null;
}
cv.addEventListener('mousedown', e => { dragging = [e.clientX, e.clientY, yaw, pitch, false]; cv.classList.add('drag'); });
addEventListener('mousemove', e => {
  if (dragging) {
    const dx = e.clientX - dragging[0], dy = e.clientY - dragging[1];
    if (Math.abs(dx) + Math.abs(dy) > 3) dragging[4] = true;
    yaw = dragging[2] + dx * .0055; pitch = Math.max(-1.15, Math.min(1.15, dragging[3] + dy * .0045));
    draw(); return;
  }
  const n = pick(e.clientX, e.clientY), tip = document.getElementById('tip');
  if (n && n.i !== sel) {
    tip.style.display = 'block';
    tip.innerHTML = `<div class="hdr"><span class="dot" style="background:${COLOR[n.d] || '#888'}"></span>
      <span>${esc(n.st || n.d)} · ${gLabel(n) || '学段未定'}</span></div>
      <h3>${esc(n.t)}</h3>${n.a ? `<p>${esc(n.a)}</p>` : ''}`;
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.min(innerWidth - r.width - 16, e.clientX + 18) + 'px';
    tip.style.top = Math.min(innerHeight - r.height - 16, e.clientY + 18) + 'px';
    cv.style.cursor = 'pointer';
  } else { tip.style.display = 'none'; cv.style.cursor = 'grab'; }
});
addEventListener('mouseup', e => {
  const moved = dragging && dragging[4]; dragging = null; cv.classList.remove('drag');
  if (moved) return;
  const n = pick(e.clientX, e.clientY);
  if (n) show(n); else if (e.target === cv) clear();
});
cv.addEventListener('wheel', e => { e.preventDefault();
  zoom = Math.max(.25, Math.min(9, zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1))); draw(); }, { passive: false });
let tp = null;
cv.addEventListener('touchstart', e => {
  if (e.touches.length === 1) tp = { x: e.touches[0].clientX, y: e.touches[0].clientY, yaw, pitch };
  else if (e.touches.length === 2) tp = { d: Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
    e.touches[0].clientY - e.touches[1].clientY), z: zoom };
}, { passive: true });
cv.addEventListener('touchmove', e => {
  if (!tp) return;
  if (e.touches.length === 1 && tp.yaw !== undefined) {
    yaw = tp.yaw + (e.touches[0].clientX - tp.x) * .006;
    pitch = Math.max(-1.15, Math.min(1.15, tp.pitch + (e.touches[0].clientY - tp.y) * .005));
  } else if (e.touches.length === 2 && tp.d) {
    zoom = Math.max(.25, Math.min(9, tp.z * Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
      e.touches[0].clientY - e.touches[1].clientY) / tp.d));
  }
  draw();
}, { passive: true });
cv.addEventListener('touchend', () => { tp = null; }, { passive: true });
document.getElementById('close').onclick = clear;
addEventListener('keydown', e => {
  if (e.key === 'Escape') clear();
  if (e.key === 'Backspace' && sel && document.activeElement.id !== 'q') { e.preventDefault(); goBack(); }
});
document.getElementById('q').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const v = e.target.value.trim(); if (!v) return;
  const n = N.find(x => x.t.includes(v));
  if (n) { zoom = Math.max(zoom, 2.2); show(n); }
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
addEventListener('resize', () => { resize(); if (!sel) autoFit(); draw(); });
resize(); autoFit(); draw(); tick();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(Path(__file__).resolve().parent.parent / 'graph-3d.html'))
    ap.add_argument('--iters', type=int, default=420)
    a = ap.parse_args()

    anchors, edges = load()
    ids = {x['id'] for x in anchors}
    edges = [e for e in edges if e['anchorId'] in ids and e['prerequisiteId'] in ids]
    print(f"节点 {len(anchors)} · 边 {len(edges)}")

    x, y, z = layout3d(anchors, edges, iters=a.iters)
    outdeg = collections.Counter(e['prerequisiteId'] for e in edges)
    nodes = [{
        'i': n['id'], 'd': n['discipline'], 'st': n.get('strand') or '', 't': n['statement'],
        's': STAGE_ORD.get((n.get('stageHint') or {}).get('min'), 0),
        'x': round(x[k], 1), 'y': round(y[k], 1), 'z': round(z[k], 1),
        'o': outdeg.get(n['id'], 0), 'p': (n.get('provenance') or {}).get('srcPage', ''),
        # 家长向问句直接展示，{{name}} 换成「孩子」——占位符漏到界面上很业余
        'a': (n.get('assessment') or '').replace('{{name}}', '孩子').strip(),
    } for k, n in enumerate(anchors)]

    html = (HTML.replace('__TITLE__', 'K12 知识底座 · 3D 能力图谱')
            .replace('__NODES__', json.dumps(nodes, ensure_ascii=False, separators=(',', ':')))
            .replace('__EDGES__', json.dumps([[e['prerequisiteId'], e['anchorId']] for e in edges], separators=(',', ':')))
            .replace('__COLORS__', json.dumps(COLORS, ensure_ascii=False))
            .replace('__NC__', f"{len(nodes):,}").replace('__EC__', f"{len(edges):,}")
            .replace('__DC__', str(len({n['d'] for n in nodes})))
            .replace('__HGT__', str(HGT)))
    p = Path(a.out); p.write_text(html, encoding='utf-8')
    print(f"→ {p}  {p.stat().st_size/1024:.0f}KB")


if __name__ == '__main__':
    main()
