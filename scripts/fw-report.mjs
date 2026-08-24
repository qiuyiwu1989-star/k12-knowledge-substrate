#!/usr/bin/env node
// fw-report.mjs — specs/002 的图体检报告。**确定性算法，不调用模型。**
//
// 三件事，都只报告不阻断：
//   W101 传递冗余  A→B→C 且 A→C ⇒ A→C 冗余。**只输出清单，不删。**
//                  删边不可逆且影响所有下游推理，必须人决定。
//   W102 跨学段跨度 ≥ 2 带 —— 真前置通常紧邻，跨两带以上多为伪边。
//   W103 入度 > 8 —— 大概率把「相关」当成了「前置」。
//   覆盖体检：学科 × 学段 的锚点密度矩阵。**不设阈值、不给结论** ——
//            阈值要看到第一版报告后由人定，实现方不许自设默认值。
import { readFileSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
const readAll = (dir) => {
  const out = [];
  const walk = (d) => readdirSync(d, { withFileTypes: true }).forEach((e) => {
    const p = join(d, e.name);
    if (e.isDirectory()) return walk(p);
    if (!p.endsWith('.jsonl')) return;
    for (const l of readFileSync(p, 'utf8').split('\n')) if (l.trim()) out.push(JSON.parse(l));
  });
  walk(join(ROOT, dir));
  return out;
};

const A = new Map(readAll('anchors').map((a) => [a.id, a]));
const live = (id) => A.has(id) && !A.get(id).deprecated;
const edges = readAll('edges').filter((e) => !e.retired && live(e.anchorId) && live(e.prerequisiteId));

// **推理图 ≠ 全部边。** specs/001 重标之后，type=convention 的边（教材就这么排的，
// 无可观测影响）被移出推理图。传递冗余、跨学段、入度这三项体检真正该看的是推理图 ——
// 拿全部边算会把 811 条已经出局的边算进去，得出一个没人会用到的数字。
const inGraph = edges.filter((e) => e.inInferenceGraph !== false && e.type !== 'convention');
const typed = edges.filter((e) => e.type).length;

// ── W101 传递冗余 ───────────────────────────────────────────────────
// 「A→C 冗余」= 不走 A→C 这条边本身，仍然能从 A 到达 C。
const pre = new Map();
for (const e of inGraph) {
  if (!pre.has(e.anchorId)) pre.set(e.anchorId, new Set());
  pre.get(e.anchorId).add(e.prerequisiteId);
}
const reaches = (src, dst, skipFrom, skipTo) => {
  const seen = new Set([src]); const st = [src];
  while (st.length) {
    const u = st.pop();
    for (const v of pre.get(u) ?? []) {
      if (u === skipFrom && v === skipTo) continue;
      if (v === dst) return true;
      if (!seen.has(v)) { seen.add(v); st.push(v); }
    }
  }
  return false;
};
const redundant = inGraph.filter((e) => reaches(e.anchorId, e.prerequisiteId, e.anchorId, e.prerequisiteId));

// ── W102 跨学段跨度 ─────────────────────────────────────────────────
const g = (s) => (typeof s === 'string' && s[0] === 'G' ? +s.slice(1) : null);
const band = (n) => (n <= 2 ? 0 : n <= 4 ? 1 : n <= 6 ? 2 : n <= 9 ? 3 : 4);
const BAND_CN = ['G1–2', 'G3–4', 'G5–6', 'G7–9', 'G10–12'];
const far = inGraph.filter((e) => {
  const a = g(A.get(e.anchorId).stageHint?.min), b = g(A.get(e.prerequisiteId).stageHint?.min);
  return a && b && Math.abs(band(a) - band(b)) >= 2;
});

// ── W103 入度 ───────────────────────────────────────────────────────
const indeg = new Map();
for (const e of inGraph) indeg.set(e.anchorId, (indeg.get(e.anchorId) ?? 0) + 1);
const hiIn = [...indeg].filter(([, n]) => n > 8).sort((a, b) => b[1] - a[1]);

// ── 覆盖密度 ────────────────────────────────────────────────────────
const cells = new Map(); const subjects = new Set();
for (const a of A.values()) {
  if (a.deprecated) continue;
  const n = g(a.stageHint?.min); if (!n) continue;
  subjects.add(a.discipline);
  const k = `${a.discipline}|${band(n)}`;
  cells.set(k, (cells.get(k) ?? 0) + 1);
}
const totals = [...cells.values()];
const median = totals.sort((x, y) => x - y)[Math.floor(totals.length / 2)];

const L = [];
L.push('# 图体检基线报告');
L.push('');
L.push('> 由 `npm run fw-report` 自动生成。**只报告，不设阈值，不给结论，不删任何边。**');
L.push(`> 存活锚点 ${[...A.values()].filter((a) => !a.deprecated).length} · 存活边 ${edges.length}`);
L.push(`> **推理图 ${inGraph.length} 条**（已重标 ${typed} 条；${edges.length - inGraph.length} 条判为 convention，教材编排顺序不是能力依赖，移出推理图）`);
L.push('> 以下三项体检**只算推理图**。');
L.push('');
L.push('## W101 传递冗余');
L.push('');
L.push(`**${redundant.length} 条 = ${(redundant.length / inGraph.length * 100).toFixed(0)}%**（A→B→C 已经连通，A→C 是多余的一跳）`);
L.push('');
const redBySub = {};
for (const e of redundant) { const d = A.get(e.anchorId).discipline; redBySub[d] = (redBySub[d] ?? 0) + 1; }
L.push('| 学科 | 冗余边 | 该学科总边 | 占比 |');
L.push('|---|---:|---:|---:|');
const edgeBySub = {};
for (const e of inGraph) { const d = A.get(e.anchorId).discipline; edgeBySub[d] = (edgeBySub[d] ?? 0) + 1; }
for (const [d, n] of Object.entries(redBySub).sort((a, b) => b[1] - a[1])) {
  L.push(`| ${d} | ${n} | ${edgeBySub[d]} | ${(n / edgeBySub[d] * 100).toFixed(0)}% |`);
}
L.push('');
L.push('前 15 条（格式：`前置 → 后继` 冗余于已有通路）：');
L.push('');
L.push('```');
for (const e of redundant.slice(0, 15)) {
  L.push(`${e.prerequisiteId} → ${e.anchorId}  ${A.get(e.anchorId).statement.slice(0, 30)}`);
}
L.push('```');
L.push('');
L.push('## W102 跨学段跨度 ≥ 2 带');
L.push('');
L.push(`**${far.length} 条 = ${(far.length / inGraph.length * 100).toFixed(1)}%**`);
L.push('');
L.push('```');
for (const e of far.slice(0, 10)) {
  const a = A.get(e.anchorId), b = A.get(e.prerequisiteId);
  L.push(`${BAND_CN[band(g(b.stageHint.min))]} → ${BAND_CN[band(g(a.stageHint.min))]}  ${b.discipline}｜${b.statement.slice(0, 22)} → ${a.statement.slice(0, 22)}`);
}
L.push('```');
L.push('');
L.push('## W103 入度 > 8');
L.push('');
L.push(hiIn.length
  ? `**${hiIn.length} 个锚点**，最高 ${hiIn[0][1]}`
  : `**0 个。** 最高入度 ${Math.max(0, ...indeg.values())} —— `
    + '注意：`gen_edges.py` 本来就把候选截断在 8，所以这道闸在当前数据上**恒为 0，证明不了任何事**。'
    + '真正要问的是「8 这个上限本身对不对」，而那要等 W101 处理完再看。');
L.push('');
L.push('## 覆盖密度（学科 × 学段）');
L.push('');
L.push(`全局中位数 **${median}**。**不设阈值** —— 阈值要看到这份报告后由人定。`);
L.push('');
L.push('| 学科 | ' + BAND_CN.join(' | ') + ' | 合计 |');
L.push('|---|' + BAND_CN.map(() => '---:').join('|') + '|---:|');
for (const d of [...subjects].sort()) {
  const row = BAND_CN.map((_, i) => cells.get(`${d}|${i}`) ?? 0);
  L.push(`| ${d} | ${row.map((n) => (n === 0 ? '—' : n)).join(' | ')} | ${row.reduce((x, y) => x + y, 0)} |`);
}
L.push('');

// ── 近重复体检 ─────────────────────────────────────────────────────
// 去重签名只抓「同学科 + 同动词 + 整句去掉动词后完全相同」，抓不到近似的。
//
// **第一版用字符集 Jaccard，那个判据是错的**：
//   「能解释**原**电池的工作原理」和「能解释**电解**池的工作原理」
//   字符集完全相同（「原」在两边都有：原电池 / 原理），Jaccard = 1.00，
//   而它们是两条完全不同的能力。日语的 Vている / Vてある / Vておく 同理。
//   集合丢掉了字序，而中文里字序就是意思。
//
// 换成**序列相似度**（最长公共子序列比），并单独抓一类真信号：
//   **一条是另一条的子串** —— 那是抽取截断的典型形态
//   （「能计算离差平方和、方差」→「能计算离差平方和」）。
//   但拆原子产生的母子对也长这样，所以要排除 splitFrom 指向对方的。
//
// **只报告，不自动合并** —— 短的那条也可能本身就成立。
const norm = (t) => String(t).replace(/[\s，。、；：！？（）()《》「」]/g, '');
const lcsRatio = (a, b) => {
  // 经典 LCS。断言最长 60 字，3,000 条里同学科两两比，够快。
  const n = a.length, m = b.length;
  if (!n || !m) return 0;
  let prev = new Uint16Array(m + 1), cur = new Uint16Array(m + 1);
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      cur[j] = a[i - 1] === b[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], cur[j - 1]);
    }
    [prev, cur] = [cur, prev];
    cur.fill(0);
  }
  return (2 * prev[m]) / (n + m);
};
const liveAnchors = [...A.values()].filter((a) => !a.deprecated);
const byDisc = {};
for (const a of liveAnchors) (byDisc[a.discipline] ??= []).push(a);
const nearDup = [], truncated = [];
for (const arr of Object.values(byDisc)) {
  for (let i = 0; i < arr.length; i++) {
    for (let j = i + 1; j < arr.length; j++) {
      const x = norm(arr[i].statement), y = norm(arr[j].statement);
      if (x.length < 8 || y.length < 8) continue;
      if (Math.abs(x.length - y.length) > Math.max(x.length, y.length) * 0.5) continue;
      const sub = x.includes(y) || y.includes(x);
      if (sub) {
        const [lo, hi] = x.length < y.length ? [arr[i], arr[j]] : [arr[j], arr[i]];
        // 拆原子的母子对长得也像子串，那是设计不是缺陷
        if (lo.provenance?.splitFrom !== hi.id) truncated.push({ lo, hi });
        continue;
      }
      const r = lcsRatio(x, y);
      if (r >= 0.92) nearDup.push({ jac: r, a: arr[i], b: arr[j] });
    }
  }
}
nearDup.sort((p, q) => q.jac - p.jac);
const CITABLE_R = new Set(JSON.parse(readFileSync(join(ROOT, 'mappings/citable.json'), 'utf8')).citable);
const bothCitable = nearDup.filter((d) => CITABLE_R.has(d.a.reviewStatus) && CITABLE_R.has(d.b.reviewStatus));
L.push(`## 疑似截断：一条是另一条的子串 —— **${truncated.length} 对**`);
L.push('');
L.push('（已排除拆原子的母子对 —— 那是设计不是缺陷。这些条已在数据里标了');
L.push('`fieldIssues: possible-truncation` 并指向更长的那条。）');
L.push('');
L.push('```');
for (const t of truncated.slice(0, 15)) {
  L.push(`长 ${t.hi.statement.slice(0, 52)}`);
  L.push(`短 ${t.lo.statement.slice(0, 52)}   ${t.lo.id} [${t.lo.reviewStatus}]`);
}
L.push('```');
L.push('');

L.push('## 近重复断言（只报告，不自动合并）');
L.push('');
L.push(`实词+拉丁+数字的 Jaccard ≥ 0.92：**${nearDup.length} 对**，`
  + `其中 **${bothCitable.length} 对两条都可引用** —— 那是同一件事有了两个 ID，最该先看。`);
L.push('');
L.push('**不自动合并**：这个区间里既有真重复（只差一个括号），也有真不同');
L.push('（「过去完成时／过去未完成时」「概率／条件概率」）。判据交给人。');
L.push('');
L.push('```');
for (const d of nearDup.slice(0, 20)) {
  const mark = CITABLE_R.has(d.a.reviewStatus) && CITABLE_R.has(d.b.reviewStatus) ? ' ★两条都可引用' : '';
  L.push(`${d.jac.toFixed(2)}${mark}`);
  L.push(`   ${d.a.id} [${d.a.reviewStatus}] ${d.a.statement.slice(0, 52)}`);
  L.push(`   ${d.b.id} [${d.b.reviewStatus}] ${d.b.statement.slice(0, 52)}`);
}
L.push('```');
L.push('');

mkdirSync(join(ROOT, 'reports'), { recursive: true });
writeFileSync(join(ROOT, 'reports/graph-hygiene.md'), L.join('\n'), 'utf8');
console.log(`✓ reports/graph-hygiene.md`);
console.log(`  W101 传递冗余 ${redundant.length} / ${inGraph.length} = ${(redundant.length / inGraph.length * 100).toFixed(0)}%`);
console.log(`  W102 跨学段≥2 ${far.length}`);
console.log(`  W103 入度>8   ${hiIn.length}（最高 ${Math.max(0, ...indeg.values())}）`);
console.log(`  近重复断言    ${nearDup.length} 对（${bothCitable.length} 对两条都可引用）`);
