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
import { CITABLE } from './lib/citable.mjs';
import { grainSpan } from './lib/grain.mjs';
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
// 定义见 mappings/citable.json —— 不在这里写第二遍
const USABLE = CITABLE;
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
  row('ai-reviewed', null, '能（2026-08-20 起 —— **AI 看过、没挑出毛病**，不是教师签字）'),
  row('disputed', null, '**不能** —— AI 复核挑出了具体问题'),
  row('llm-proposed', null, '**不能** —— 没有任何东西看过一眼'),
  `| **存活合计** | **${M.counts.liveAnchors}** | 其中 **${usable}** 可用 |`,
].join('\n');


// 粒度：定义在 scripts/lib/grain.mjs（阈值在 mappings/grain.json）。
// 这里**只统计、不定义** —— 第一版我在这个文件里另写了一套 gspan/grainPct，
// 那就是给粒度立了第二个定义，和 citable 当年散在 8 个文件里是同一个病。
const grainPct = (n) => (live.length
  ? (live.filter((a) => grainSpan(a) === n).length / live.length * 100).toFixed(1) : '0');

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
  aiReviewedCount: n('ai-reviewed'),
  humanConfirmed2: M.humanConfirmedAnchors,
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
  // ── SPEC.md（对外引用规范）用到的键。**一个都不许手打** ──
  //    这份文件是给外部开发者看的契约，数字腐烂的后果比内部文档严重得多：
  //    别人照着它写的校验会在下一次快照后静默失配。
  release: M.release ?? '0.1.0',
  schemaVersion: M.schemaVersion ?? '0.1.0',
  generatedAt: String(M.generatedAt ?? '').slice(0, 10),
  anchorsAll: M.counts.anchors,
  manifestFiles: Object.keys(M.files ?? {}).length,
  supersededAnchors: anchors.filter((a) => a.deprecated && a.supersededBy).length,
  droppedNoSuccessor: anchors.filter((a) => a.deprecated && !a.supersededBy).length,
  assessmentSpecAnchors: live.filter((a) => a.assessmentSpec).length,
  compositeAnchors: live.filter((a) => a.composite).length,
  splitChildren: live.filter((a) => a.provenance?.splitFrom).length,
  fieldIssueAnchors: live.filter((a) => (a.fieldIssues ?? []).length).length,
  edgesInGraph: edges.filter((e) => e.inInferenceGraph === true).length,
  edgesConvention: edges.filter((e) => e.type === 'convention').length,
  edgesComponent: edges.filter((e) => e.type === 'component').length,
  edgesUntyped: edges.filter((e) => !e.type).length,
  edgesUnreviewed: edges.filter((e) => e.reviewStatus === 'llm-proposed').length,
  edgesHard: edges.filter((e) => e.strength === 'hard').length,
  // ── CONTRACT.md / GRAIN.md（对外数据契约）用到的键 ──
  //    这两份是给调用方看的，数字腐烂的后果最严重：别人照着它写的兼容性判断会静默失配。
  contractVersion: readFileSync(join(ROOT, 'VERSION'), 'utf8').trim(),
  ledgerIds: (() => { try { return readFileSync(join(ROOT, 'ledger/ids.jsonl'), 'utf8')
    .split('\n').filter((l) => l.trim()).length; } catch { return 0; } })(),
  // 两个数量的是不同的东西，别混：
  //   unknownProvenance —— 出处不完整（缺 srcText 或 srcPage），影响的是「能不能翻回原文」
  //   blindIds          —— 缺 srcSubject/srcPage，no-id-reuse 判不了指向，是那道闸的盲区
  //                        它扫 anchors + retired，所以基数比上面大
  unknownProvenance: anchors.filter((a) => !a.provenance?.srcPage || !a.provenance?.srcText).length,
  blindIds: (() => {
    let n = 0;
    for (const d of ['anchors', 'retired']) for (const f of walk(join(ROOT, d)))
      for (const l of readFileSync(f, 'utf8').split('\n')) {
        if (!l.trim()) continue;
        try { const a = JSON.parse(l);
          if (a.id && (!a.provenance?.srcSubject || !a.provenance?.srcPage)) n++; } catch { /* validate 报 */ }
      }
    return n;
  })(),
  // 粒度：一条锚点覆盖几个年级。贯穿 CONTRACT / GRAIN / 接口的粒度警告，只此一处算
  grainSpan1: grainPct(1),
  grainSpan3: grainPct(3),
  grainSpanWide: live.length ? (live.filter((a) => (grainSpan(a) ?? 0) >= 4).length / live.length * 100).toFixed(1) : '0',
  reviewTable,
};

const RE = /<!--N:([A-Za-z][\w-]*)-->([\s\S]*?)<!--\/N-->/g;
let stale = 0, filled = 0, unknown = 0;

// SPEC.md 是对外契约，**必须一起扫** —— 不扫等于它里面的数字全是手打的。
for (const name of ['README.md', 'PROVENANCE.md', 'SPEC.md', 'CONTRACT.md', 'GRAIN.md']) {
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
