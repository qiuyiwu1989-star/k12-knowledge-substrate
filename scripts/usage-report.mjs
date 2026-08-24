#!/usr/bin/env node
// usage-report.mjs — 谁从来没被碰过。
//
// 这份报告的用处是**倒过来看**：不是「哪些锚点热门」，
// 而是「哪些锚点在有人真的用这个底座之后，依然一次都没被映射上」。
// 那一批是最该怀疑的 —— 可能是坏断言，可能是粒度错了，可能是根本没人需要。
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { USAGE_FILE } from './usage.mjs';
import { CITABLE } from './lib/citable.mjs';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
const u = existsSync(USAGE_FILE) ? JSON.parse(readFileSync(USAGE_FILE, 'utf8')) : { since: null, anchors: {} };
const live = [];
for (const f of readdirSync(join(ROOT, 'anchors'))) {
  if (!f.endsWith('.jsonl')) continue;
  for (const l of readFileSync(join(ROOT, 'anchors', f), 'utf8').split('\n')) {
    if (!l.trim()) continue;
    try { const a = JSON.parse(l); if (!a.deprecated) live.push(a); } catch { /* validate 管 */ }
  }
}
const hit = new Set(Object.keys(u.anchors));
const cold = live.filter((a) => !hit.has(a.id));
const total = Object.values(u.anchors).reduce((s, e) => s + e.hits, 0);

console.log(`调用计数自 ${u.since ?? '（还没有任何调用）'}  命中总次数 ${total}`);
console.log(`被碰过 ${live.length - cold.length} / ${live.length} 条存活锚点\n`);
if (!total) {
  console.log('还没有任何调用记录。这个数字变成非零，是整个转向的验收标准 ——');
  console.log('锚点数、边数、复核档位、页面好看程度都不算证据，它们在过去半年一直在涨。');
  process.exit(0);
}
const byDisc = {};
for (const a of cold) byDisc[a.discipline] = (byDisc[a.discipline] ?? 0) + 1;
console.log('从没被碰过的，按学科：');
for (const [d, n] of Object.entries(byDisc).sort((x, y) => y[1] - x[1]).slice(0, 12)) console.log(`  ${d.padEnd(10)} ${n}`);
const coldCitable = cold.filter((a) => CITABLE.has(a.reviewStatus));
console.log(`\n其中 ${coldCitable.length} 条是「可引用」档 —— 标着可用，却没人用得上。`);
console.log('这一批是最该怀疑的：坏断言、粒度错、或者根本没人需要。');
