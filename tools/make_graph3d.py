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
body{background:#07070a;color:#e8e6e1;font:15px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}
canvas{display:block;cursor:grab}canvas.drag{cursor:grabbing}
#hero{position:fixed;left:52px;top:15%;max-width:400px;pointer-events:none;z-index:5;transition:opacity .4s;
 text-shadow:0 2px 24px #07070a,0 0 60px #07070a}
@media(max-width:1100px){#hero{top:11%;max-width:320px}#hero h1{font-size:34px}#legend{display:none}}
#hero .kicker{font-size:11px;letter-spacing:.2em;color:#8b8780;margin-bottom:20px}
#hero .kicker i{color:#e0554a;font-style:normal}
#hero h1{font-size:clamp(38px,5vw,62px);line-height:1.04;font-weight:600;letter-spacing:-.025em;margin-bottom:22px}
#hero p{color:#a5a099;font-size:14px;max-width:330px}
#hero b{color:#e8e6e1;font-weight:600}
#legend{position:fixed;left:52px;bottom:34px;z-index:6;transition:opacity .3s}
#legend h4{font-size:10px;letter-spacing:.16em;color:#6d6a64;margin-bottom:10px;font-weight:600}
.li{display:flex;align-items:center;gap:10px;padding:2.5px 0;cursor:pointer;font-size:12.5px;width:210px}
.li.off{opacity:.28}.li .dot{width:8px;height:8px;border-radius:50%;flex:none}
.li .n{margin-left:auto;color:#6d6a64;font-variant-numeric:tabular-nums;font-size:11.5px}
#panel{position:fixed;right:0;top:0;bottom:0;width:420px;background:rgba(10,10,13,.96);backdrop-filter:blur(14px);border-left:1px solid #1e1e24;padding:28px 26px;overflow:auto;transform:translateX(100%);transition:transform .28s cubic-bezier(.2,.7,.3,1);z-index:8}
#panel.on{transform:none}
#panel .tag{display:inline-block;font-size:11px;padding:2px 9px;border-radius:99px;border:1px solid #2b2b33;color:#a5a099;margin:0 5px 8px 0}
#panel h2{font-size:22px;line-height:1.42;margin:10px 0 6px;font-weight:600}
#panel h5{font-size:10px;letter-spacing:.15em;color:#6d6a64;margin:24px 0 9px;font-weight:600}
#panel ul{padding-left:17px}#panel li{margin:5px 0;color:#c2beb7;font-size:13.5px}
#panel .chain div{padding:5px 0 5px 13px;font-size:13px;color:#c2beb7;cursor:pointer;border-left:2px solid #232329}
#panel .chain div:hover{color:#fff;border-left-color:#6a6a78}
#close{position:absolute;right:18px;top:15px;background:none;border:none;color:#6d6a64;font-size:25px;cursor:pointer;line-height:1}
#top{position:fixed;left:0;right:0;top:0;padding:18px 24px;display:flex;gap:12px;align-items:center;z-index:7;pointer-events:none}
#top *{pointer-events:auto}
#q{background:rgba(16,16,20,.9);border:1px solid #22222a;border-radius:9px;color:#e8e6e1;padding:8px 13px;font:inherit;font-size:13px;width:230px}
.badge{font-size:11px;color:#8b8780;background:rgba(16,16,20,.85);border:1px solid #22222a;border-radius:99px;padding:5px 11px}
.badge.warn{color:#c98b2f;border-color:#3a2f18}
#hint{position:fixed;right:26px;bottom:22px;font-size:11px;color:#55535c;z-index:5;transition:opacity .3s}
#tip{position:fixed;pointer-events:none;background:rgba(16,16,20,.97);border:1px solid #2b2b33;border-radius:8px;padding:7px 11px;font-size:12.5px;max-width:300px;display:none;z-index:9}
#gr{position:fixed;left:14px;top:0;bottom:0;width:40px;pointer-events:none;z-index:4}
#gr div{position:absolute;font-size:10px;color:#3c3c44;letter-spacing:.1em;transform:translateY(-50%)}
</style></head><body>
<canvas id="cv"></canvas><div id="gr"></div>
<div id="hero">
  <div class="kicker"><i>●</i> 中国义务教育课程标准 2022 · 一至九年级</div>
  <h1>一个孩子<br>要学的全部。</h1>
  <p><b>__NC__</b> 条能力断言，<b>__EC__</b> 条先修依赖，<b>__DC__</b> 个学科。<br>
  <b>拖动旋转</b>，<b>点任意一个点</b>看它之前必须先掌握什么。</p>
</div>
<div id="top">
  <input id="q" placeholder="搜索能力…（回车定位）">
  <span class="badge" id="stat"></span>
  <span class="badge warn">全部未经教师复核</span>
</div>
<div id="legend"><h4>学科 · 点击开关</h4><div id="ls"></div></div>
<div id="hint">拖动旋转 · 滚轮缩放 · 点击选中</div>
<div id="panel"><button id="close">×</button><div id="pc"></div></div>
<div id="tip"></div>
<script>
const N = __NODES__, E = __EDGES__, COLOR = __COLORS__, HGT = __HGT__;
const cv = document.getElementById('cv'), ctx = cv.getContext('2d', { alpha: false });
const DPR = Math.min(2, devicePixelRatio || 1);
let W, H, yaw = 0.5, pitch = -0.18, zoom = 1, cx = 0, cy = 0;
let sel = null, hi = null, auto = true, dragging = null;
const off = new Set();
const byId = new Map(N.map(n => [n.i, n]));
const pre = new Map(), post = new Map();
for (const n of N) { pre.set(n.i, []); post.set(n.i, []); }
for (const [a, b] of E) { pre.get(b).push(a); post.get(a).push(b); }

const px = new Float32Array(N.length), py = new Float32Array(N.length), pz = new Float32Array(N.length);
const order = new Int32Array(N.length);

function resize() {
  W = cv.width = innerWidth * DPR; H = cv.height = innerHeight * DPR;
  cv.style.width = innerWidth + 'px'; cv.style.height = innerHeight + 'px';
}

/** 按当前角度量一次投影包围盒，把云团缩放到填满视口 —— 不同屏幕比例都别留一堆黑边 */
function autoFit(fill = 0.72) {
  const z0 = zoom; zoom = 1; cx = cy = 0; project();
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
  for (let k = 0; k < N.length; k++) {
    if (off.has(N[k].d)) continue;
    if (px[k] < x0) x0 = px[k]; if (px[k] > x1) x1 = px[k];
    if (py[k] < y0) y0 = py[k]; if (py[k] > y1) y1 = py[k];
  }
  const bw = (x1 - x0) || 1, bh = (y1 - y0) || 1;
  zoom = Math.min(W * fill / bw, H * fill / bh);
  if (!isFinite(zoom) || zoom <= 0) zoom = z0;
  zoom = Math.max(0.25, Math.min(9, zoom));
}

function project() {
  const sy = Math.sin(yaw), cyw = Math.cos(yaw), sp = Math.sin(pitch), cp = Math.cos(pitch);
  const f = Math.min(W, H) * 0.62 * zoom, CAM = 2600;
  for (let k = 0; k < N.length; k++) {
    const n = N[k];
    // 绕 Y 轴转（学段轴保持竖直），再绕 X 轴俯仰
    const X = n.x * cyw - n.z * sy;
    const Z0 = n.x * sy + n.z * cyw;
    const Y = n.y * cp - Z0 * sp;
    const Z = n.y * sp + Z0 * cp;
    const d = CAM + Z;
    const s = f / (d > 60 ? d : 60);
    px[k] = W / 2 + X * s + cx * DPR;
    py[k] = H / 2 + Y * s + cy * DPR;
    pz[k] = Z;
    order[k] = k;
  }
  // 画家算法：远的先画
  const arr = Array.from(order);
  arr.sort((a, b) => pz[b] - pz[a]);
  for (let k = 0; k < arr.length; k++) order[k] = arr[k];
}

function draw() {
  ctx.fillStyle = '#07070a'; ctx.fillRect(0, 0, W, H);
  project();
  const on = k => !off.has(N[k].d);
  const idxOf = new Map(N.map((n, k) => [n.i, k]));
  const zmin = -1400, zspan = 2800;

  // 边：按深度分 3 桶，每桶合成一条 path 一次 stroke（2000+ 次 draw call → 3 次）
  const buckets = [[], [], []];
  for (const [a, b] of E) {
    const ka = idxOf.get(a), kb = idxOf.get(b);
    if (ka === undefined || kb === undefined || !on(ka) || !on(kb)) continue;
    const lit = hi && hi.has(a) && (hi.has(b) || b === sel);
    if (hi && !lit) continue;
    const t = (((pz[ka] + pz[kb]) / 2) - zmin) / zspan;
    buckets[t < 0.34 ? 0 : t < 0.67 ? 1 : 2].push([ka, kb, lit]);
  }
  const alphas = hi ? [0.62, 0.46, 0.32] : [0.30, 0.20, 0.12];
  for (let bi = 0; bi < 3; bi++) {
    if (!buckets[bi].length) continue;
    ctx.strokeStyle = hi ? `rgba(255,255,255,${alphas[bi]})` : `rgba(150,155,175,${alphas[bi]})`;
    ctx.lineWidth = (hi ? 1.2 : 0.75) * DPR;
    ctx.beginPath();
    for (const [ka, kb] of buckets[bi]) { ctx.moveTo(px[ka], py[ka]); ctx.lineTo(px[kb], py[kb]); }
    ctx.stroke();
  }

  // 点：按 颜色×深度桶 批绘
  const groups = new Map();
  for (let oi = 0; oi < order.length; oi++) {
    const k = order[oi], n = N[k];
    if (!on(k)) continue;
    const lit = !hi || hi.has(n.i) || n.i === sel;
    const t = Math.max(0, Math.min(1, (pz[k] - zmin) / zspan));
    const bucket = Math.min(3, (t * 4) | 0);
    const key = n.d + '|' + bucket + '|' + (lit ? 1 : 0);
    if (!groups.has(key)) groups.set(key, { d: n.d, b: bucket, lit, items: [] });
    groups.get(key).items.push(k);
  }
  for (const g of groups.values()) {
    const fog = 1 - g.b * 0.19;
    ctx.globalAlpha = (g.lit ? 1 : 0.09) * fog;
    ctx.fillStyle = COLOR[g.d] || '#888';
    ctx.beginPath();
    for (const k of g.items) {
      const n = N[k];
      const persp = 2600 / (2600 + pz[k]);
      const r = (1.45 + Math.sqrt(n.o) * 1.0) * zoom * persp * DPR;
      ctx.moveTo(px[k] + r, py[k]);
      ctx.arc(px[k], py[k], r < 0.8 ? 0.8 : r, 0, 7);
    }
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  if (sel != null) {
    const k = idxOf.get(sel);
    if (k !== undefined) {
      const persp = 2600 / (2600 + pz[k]);
      const r = (1.45 + Math.sqrt(byId.get(sel).o) * 1.0) * zoom * persp * DPR;
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.8 * DPR;
      ctx.beginPath(); ctx.arc(px[k], py[k], Math.max(6 * DPR, r + 5 * DPR), 0, 7); ctx.stroke();
    }
  }
  // 学段刻度：跟着俯仰角走
  const gr = document.getElementById('gr');
  if (!gr.dataset.built) { gr.innerHTML = [1,3,5,7,9].map(g => `<div data-g="${g}">G${g}</div>`).join(''); gr.dataset.built = 1; }
  const sp2 = Math.sin(pitch), cp2 = Math.cos(pitch), f2 = Math.min(W, H) * 0.62 * zoom;
  gr.querySelectorAll('div').forEach(el => {
    const g = +el.dataset.g, yy = -HGT / 2 + (g - 1) / 8 * HGT;
    const Y = yy * cp2, Z = yy * sp2, s = f2 / (2600 + Z);
    el.style.top = ((H / 2 + Y * s + cy * DPR) / DPR) + 'px';
  });
}

function tick() {
  if (auto && !dragging && !sel) { yaw += 0.0016; draw(); }
  requestAnimationFrame(tick);
}

function ancestors(id, cap = 500) {
  const seen = new Set(), q = [id];
  while (q.length && seen.size < cap) { const v = q.pop();
    for (const p of pre.get(v) || []) if (!seen.has(p)) { seen.add(p); q.push(p); } }
  return seen;
}
function descendants(id, cap = 500) {
  const seen = new Set(), q = [id];
  while (q.length && seen.size < cap) { const v = q.pop();
    for (const p of post.get(v) || []) if (!seen.has(p)) { seen.add(p); q.push(p); } }
  return seen;
}

function pick(mx, my) {
  let best = -1, bd = 26 * 26;
  for (let k = 0; k < N.length; k++) {
    if (off.has(N[k].d)) continue;
    const dx = mx * DPR - px[k], dy = my * DPR - py[k];
    const d = dx * dx + dy * dy;
    if (d < bd) { bd = d; best = k; }
  }
  return best >= 0 ? N[best] : null;
}

const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
function show(n) {
  sel = n.i; hi = ancestors(n.i); hi.add(n.i); auto = false;
  const anc = [...ancestors(n.i)].map(i => byId.get(i)).filter(Boolean).sort((a, b) => a.s - b.s);
  const des = [...descendants(n.i)].map(i => byId.get(i)).filter(Boolean).sort((a, b) => a.s - b.s);
  document.getElementById('pc').innerHTML = `
    <span class="tag" style="border-color:${COLOR[n.d]};color:${COLOR[n.d]}">${esc(n.d)}</span>
    <span class="tag">${esc(n.st || '未标注领域')}</span>
    <span class="tag">${n.s ? 'G' + n.s : '学段未定'}</span>
    <h2>${esc(n.t)}</h2>
    <div style="color:#6d6a64;font-size:12px">${esc(n.i)} · 课标 p${esc(n.p)}</div>
    ${n.e && n.e.length ? `<h5>掌握证据（机器起草，未复核）</h5><ul>${n.e.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    <h5>之前必须先掌握（${anc.length}）</h5>
    ${anc.length ? `<div class="chain">${anc.map(a => `<div onclick="jump('${a.i}')">${a.s ? 'G' + a.s + ' · ' : ''}${esc(a.t)}</div>`).join('')}</div>`
      : '<div style="color:#6d6a64;font-size:13px">没有前置 —— 这是一个起点</div>'}
    <h5>解锁了什么（${des.length}）</h5>
    ${des.length ? `<div class="chain">${des.slice(0, 50).map(a => `<div onclick="jump('${a.i}')">${a.s ? 'G' + a.s + ' · ' : ''}${esc(a.t)}</div>`).join('')}</div>`
      : '<div style="color:#6d6a64;font-size:13px">暂无后继</div>'}`;
  document.getElementById('panel').classList.add('on');
  for (const id of ['hero', 'legend', 'hint']) document.getElementById(id).style.opacity = 0;
  draw();
}
window.jump = id => { const n = byId.get(id); if (n) show(n); };
function clear() {
  sel = null; hi = null; auto = true;
  document.getElementById('panel').classList.remove('on');
  for (const id of ['hero', 'legend', 'hint']) document.getElementById(id).style.opacity = 1;
  draw();
}

cv.addEventListener('mousedown', e => { dragging = [e.clientX, e.clientY, yaw, pitch, false]; cv.classList.add('drag'); });
addEventListener('mousemove', e => {
  if (dragging) {
    const dx = e.clientX - dragging[0], dy = e.clientY - dragging[1];
    if (Math.abs(dx) + Math.abs(dy) > 3) dragging[4] = true;
    yaw = dragging[2] + dx * 0.0055;
    pitch = Math.max(-1.15, Math.min(1.15, dragging[3] + dy * 0.0045));
    draw(); return;
  }
  const n = pick(e.clientX, e.clientY), tip = document.getElementById('tip');
  if (n) { tip.style.display = 'block'; tip.style.left = Math.min(innerWidth - 320, e.clientX + 14) + 'px';
    tip.style.top = (e.clientY + 16) + 'px'; tip.textContent = n.t; cv.style.cursor = 'pointer'; }
  else { tip.style.display = 'none'; cv.style.cursor = dragging ? 'grabbing' : 'grab'; }
});
addEventListener('mouseup', e => {
  const moved = dragging && dragging[4];
  dragging = null; cv.classList.remove('drag');
  if (moved) return;
  const n = pick(e.clientX, e.clientY);
  if (n) show(n); else if (e.target === cv) clear();
});
cv.addEventListener('wheel', e => {
  e.preventDefault(); zoom *= e.deltaY < 0 ? 1.1 : 1 / 1.1;
  zoom = Math.max(0.25, Math.min(9, zoom)); draw();
}, { passive: false });
// 触屏：单指转，双指缩放
let tp = null;
cv.addEventListener('touchstart', e => {
  if (e.touches.length === 1) tp = { x: e.touches[0].clientX, y: e.touches[0].clientY, yaw, pitch };
  else if (e.touches.length === 2) tp = { d: Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
    e.touches[0].clientY - e.touches[1].clientY), z: zoom };
}, { passive: true });
cv.addEventListener('touchmove', e => {
  if (!tp) return;
  if (e.touches.length === 1 && tp.yaw !== undefined) {
    yaw = tp.yaw + (e.touches[0].clientX - tp.x) * 0.006;
    pitch = Math.max(-1.15, Math.min(1.15, tp.pitch + (e.touches[0].clientY - tp.y) * 0.005));
  } else if (e.touches.length === 2 && tp.d) {
    zoom = Math.max(0.25, Math.min(9, tp.z * Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
      e.touches[0].clientY - e.touches[1].clientY) / tp.d));
  }
  draw();
}, { passive: true });
cv.addEventListener('touchend', () => { tp = null; }, { passive: true });

document.getElementById('close').onclick = clear;
document.getElementById('q').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const v = e.target.value.trim(); if (!v) return;
  const n = N.find(x => x.t.includes(v));
  if (n) { zoom = Math.max(zoom, 2); show(n); }
});
addEventListener('keydown', e => { if (e.key === 'Escape') clear(); });

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
        'e': (n.get('evidence') or [])[:3],
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
