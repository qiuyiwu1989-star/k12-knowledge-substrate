#!/usr/bin/env node
// edge-retagged.mjs — 拦「建了边，但重标没跟上」。
//
// 2026-08-25 立这道闸。起因：143 条边缺 type，追下来 142 条全是同一个 commit
// （5bed04b0「跨学段建边 7% → 30%」）带进来的 —— 那次跑了 gen_edges 落库 2,527 条，
// **retag_edges 那一步没跑完就提交了**。
//
// 而当时留下的记录是 `reports/edge-retag-summary.md` 里的一句
// 「（未重标）19 条 —— 调用失败，重跑即补」。那句话提交之后腐烂了，
// 六个 commit 过去没人回头看，数字也从 19 长到了 143。
//
// **根因不是判据不好，是「建边」和「重标」是两步，而第二步没有闸强制它跟上。**
// 手写的待办一定会烂；能拦住下一次的只有机器。
//
// 两条：
//   1. 每条边必须有 type
//   2. 有 type 就必须有 retagHash —— 那是「两段式重标真的跑过」的凭证。
//      有 type 没 retagHash = 类型是手填的或来路不明。
//
// 这道闸只看 edges/，不进 validate —— validate 还要跑 selftest 的夹具，
// 而夹具是为别的规则造的，不该被这条连累。
import { readFileSync, readdirSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
let noType = [], noHash = [], total = 0;
for (const name of readdirSync(join(ROOT, 'edges'))) {
  if (!name.endsWith('.jsonl')) continue;
  const lines = readFileSync(join(ROOT, 'edges', name), 'utf8').split('\n');
  lines.forEach((l, i) => {
    if (!l.trim()) return;
    let e; try { e = JSON.parse(l); } catch { return; }   // 坏行交给 validate 报
    total++;
    const at = `${name}:${i + 1} ${e.prerequisiteId}→${e.anchorId}`;
    if (!e.type) noType.push(at);
    else if (!e.retagHash) noHash.push(at);
  });
}
if (noType.length || noHash.length) {
  if (noType.length) {
    console.error(`✗ ${noType.length} 条边没有 type —— 只有「A 排在 B 之前」一种语义，无法推理也无法证伪`);
    for (const x of noType.slice(0, 5)) console.error(`   ${x}`);
  }
  if (noHash.length) {
    console.error(`✗ ${noHash.length} 条边有 type 却没有 retagHash —— 两段式重标没跑过，类型来路不明`);
    for (const x of noHash.slice(0, 5)) console.error(`   ${x}`);
  }
  console.error('\n  建完边必须跟着跑 tools/retag_edges.py。');
  console.error('  这道闸存在的理由：上一次漏跑，143 条边带着「无法证伪」的语义在库里躺了 6 个 commit。');
  process.exit(1);
}
console.log(`✓ ${total} 条边全部完成两段式重标（都有 type 和 retagHash）`);
