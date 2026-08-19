#!/usr/bin/env node
/**
 * sync-docs.mjs — 把 README / PROVENANCE 里的数字从 manifest.json 灌进去，并在 CI 核对。
 *
 * ## 为什么要有它
 *
 * 手打的数字一定会陈旧。实测：README 开头同一段里，第 13 行写「138 条可用」、
 * 第 16 行写「usableAnchors 依然是 0」—— 两个都错，而且**互相矛盾**，
 * 挂在首页好几轮没人发现。PROVENANCE 里「课标原文一律不发」同理。
 *
 * 手打数字不是疏忽问题，是机制问题：没有任何东西会在数据变了的时候提醒文档。
 * 所以数字改成从 manifest.json 生成，`--check` 进 CI —— 数据一变文档就红。
 *
 * ## 用法
 *
 *   node scripts/sync-docs.mjs           # 写回文档
 *   node scripts/sync-docs.mjs --check   # 只核对，不一致退出码 1（CI 用）
 *
 * ## 怎么加一个新数字
 *
 * 文档里写 `<!--N:键名-->随便什么占位<!--/N-->`，然后在下面 VALUES 里加同名键。
 * 值可以是数字、字符串，或整块 markdown（表格就是这么灌的）。
 */
import { readFileSync, writeFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const CHECK = process.argv.includes('--check');

const M = JSON.parse(readFileSync(join(ROOT, 'manifest.json'), 'utf8'));

const walk = (d) => (!existsSync(d) ? [] : readdirSync(d).flatMap((n) => {
  const p = join(d, n);
  return statSync(p).isDirectory() ? walk(p) : p.endsWith('.jsonl') ? [p] : [];
}));

const anchors = walk(join(ROOT, 'anchors'))
  .flatMap((f) => readFileSync(f, 'utf8').split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l)));
const live = anchors.filter((a) => !a.deprecated);

// 可用集合的定义只此一处。它曾经被写成「总数 − llm-proposed」，那是错的 ——
// ai-reviewed 和 disputed 都不可用，按那个算法却算进去了。
const USABLE = new Set(['auto-confirmed', 'expert-confirmed', 'ai-adjudicated']);
const R = M.counts.byReview;
const n = (k) => R[k] || 0;

const usableSet = live.filter((a) => USABLE.has(a.reviewStatus));
const usable = usableSet.length;
// reviewedBy 里现在全是 `ai:extraction-pipeline` —— 那是流水线自己签的，不是人。
// 字段非空 ≠ 有人看过，必须按前缀排除，否则「教师签字数」会虚报 512。
const human = live.filter((a) => (a.reviewedBy || []).some((r) => !String(r).startsWith('ai:'))).length;

const byId = new Map(live.map((a) => [a.id, a]));
const edges = walk(join(ROOT, 'edges'))
  .flatMap((f) => readFileSync(f, 'utf8').split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l)));
const uid = new Set(usableSet.map((a) => a.id));
const cross = edges.filter((e) => byId.get(e.anchorId)?.discipline !== byId.get(e.prerequisiteId)?.discipline).length;

// 横切关联对数：同一横切概念/科学实践下的两条锚点，且**分属不同学科**。
// 这是「能力跨界」的实际载体，不是先修边 —— 和 crossEdges 分开算，别混。
//
// 只数跨学科的对。同学科内两条都练「找规律」不算跨界，那是本来就该有的。
// `crosscutting` 和 `practice` 都是数组（practice 曾被当成字符串，算出 58,189 的虚数）。
const vals = (a, k) => (Array.isArray(a[k]) ? a[k] : a[k] ? [a[k]] : []);
const crossPairsOn = (key) => {
  const idx = new Map();
  for (const a of live) for (const v of vals(a, key)) {
    if (!idx.has(v)) idx.set(v, []);
    idx.get(v).push(a.discipline);
  }
  let t = 0;
  for (const ds of idx.values()) {
    const c = new Map();
    for (const d of ds) c.set(d, (c.get(d) || 0) + 1);
    // 全部对数 − 同学科内部对数 = 跨学科对数
    t += (ds.length * (ds.length - 1)) / 2;
    for (const m of c.values()) t -= (m * (m - 1)) / 2;
  }
  return t;
};

const row = (k, label, can) => `| \`${k}\` | ${n(k)} | ${can} |`;
const reviewTable = [
  '| 状态 | 条数 | 能否被 L3 档案引用 |',
  '|---|---:|---|',
  row('auto-confirmed', null, '能'),
  row('ai-adjudicated', null, '能（AI 裁定，**待人工异议**）'),
  row('expert-confirmed', null, '能'),
  row('ai-reviewed', null, '不能 —— AI 审查是筛子不是合格证'),
  row('disputed', null, '不能'),
  row('llm-proposed', null, '不能'),
  `| **存活合计** | **${M.counts.liveAnchors}** | 其中 **${usable}** 可用 |`,
].join('\n');

const VALUES = {
  liveAnchors: M.counts.liveAnchors,
  deprecatedAnchors: M.counts.deprecatedAnchors,
  edges: M.counts.edges,
  listItems: M.counts.listItems,
  disciplines: Object.keys(M.counts.byDiscipline).length,
  usable,
  disputed: n('disputed'),
  aiReviewed: n('ai-reviewed'),
  humanConfirmed: human,
  srcTextAnchors: live.filter((a) => a.provenance?.srcText).length,
  artAnchors: M.counts.byDiscipline['艺术'] || 0,
  scienceAnchors: M.counts.byDiscipline['科学'] || 0,
  usableMatrix: usableSet.filter((a) => a.track === 'MATRIX').length,
  usableDag: usableSet.filter((a) => a.track === 'DAG').length,
  usableEdges: edges.filter((e) => uid.has(e.anchorId) && uid.has(e.prerequisiteId)).length,
  crossEdges: cross,
  crossPct: (cross / edges.length * 100).toFixed(1),
  autoConfirmed: n('auto-confirmed'),
  aiAdjudicated: n('ai-adjudicated'),
  // 「reviewedBy 非空」和「教师签字」是两回事 —— 前者含 ai:extraction-pipeline。
  // PROVENANCE 里专门解释这个坑，那句里的数字也得跟着数据走。
  aiSigned: live.filter((a) => (a.reviewedBy || []).length).length,
  crosscuttingPairs: crossPairsOn('crosscutting'),
  practicePairs: crossPairsOn('practice'),
  crosscuttingTagged: live.filter((a) => vals(a, 'crosscutting').length || vals(a, 'practice').length).length,
  // 「25 条不变式」这种手打数字腐烂过一次：加了 3 条 schema 注入用例之后
  // README 还写着 25。数字从源文件里数出来，不许手打。
  selftestCases: (readFileSync(join(ROOT, 'scripts/selftest.mjs'), 'utf8')
    .match(/^\s{2}\['/gm) || []).length + 1,   // +1 是基线「干净数据必须通过」
  reviewLoopCases: (readFileSync(join(ROOT, 'scripts/review-loop-test.mjs'), 'utf8')
    .match(/\bok\(/g) || []).length,
  reviewTable,
};

const RE = /<!--N:([A-Za-z][\w-]*)-->([\s\S]*?)<!--\/N-->/g;
let stale = 0, filled = 0, unknown = 0;

for (const name of ['README.md', 'PROVENANCE.md']) {
  const p = join(ROOT, name);
  if (!existsSync(p)) continue;
  const src = readFileSync(p, 'utf8');
  const out = src.replace(RE, (whole, key, cur) => {
    if (!(key in VALUES)) {
      console.error(`  ✗ ${name}: 未知的数字键 <!--N:${key}--> —— 在 sync-docs.mjs 的 VALUES 里加上它`);
      unknown++;
      return whole;
    }
    const want = String(VALUES[key]);
    // 表格这类整块值前后带换行，比较时统一去掉首尾空白
    if (cur.trim() !== want.trim()) {
      stale++;
      console.log(`  ${CHECK ? '✗' : '·'} ${name} [${key}]  ${JSON.stringify(cur.trim().slice(0, 40))} → ${JSON.stringify(want.slice(0, 40))}`);
    }
    filled++;
    return `<!--N:${key}-->${want}<!--/N-->`;
  });
  if (!CHECK && out !== src) writeFileSync(p, out, 'utf8');
}

if (unknown) process.exit(2);

if (CHECK) {
  if (stale) {
    console.error(`\n✗ ${stale} 处文档数字与 manifest.json 不一致。跑 \`node scripts/sync-docs.mjs\` 修。`);
    process.exit(1);
  }
  console.log(`✓ 文档数字与数据一致（核对 ${filled} 处）`);
} else {
  console.log(stale ? `\n✓ 更新了 ${stale} 处（共 ${filled} 处标记）` : `✓ 已是最新（${filled} 处标记）`);
}
