#!/usr/bin/env node
// no-shrink.mjs — 拦「记录凭空消失」。
//
// 这个项目的一条硬不变式：**ID 永不复用，记录只增不减。**
// 一条锚点可以被标 deprecated（有 supersededBy 或 dropReason），
// 但它的那一行**必须还在文件里** —— 否则已有的档案引用就解析不到了。
//
// 2026-08-22 立这道闸，因为 `gaozhong_commit.py` 用 `open('w')` 只写新行，
// 把德语 5 条、美术 8 条、思想政治 10 条静默冲掉（共 29 条）。
// 而它的注释白纸黑字写着「**追加**到 anchors/gaozhong-<学科>.jsonl」——
// **注释和代码说反了，而注释是给人看的，代码是执行的。**
//
// 同一天撞到三个同类 bug（split_reqs 的条件切分、evidenceSource 引用未定义的 ev、
// 这一个）。逐个审工具审不过来，立不变式才拦得住下一个还没写出来的工具。
//
// 判据是**和 HEAD 比 ID 集合**，不是比行数 —— 行数相等也可能是「删 5 条加 5 条」。
import { execFileSync } from 'node:child_process';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
const ids = (txt, key) => new Set(
  txt.split('\n').filter((l) => l.trim())
    .map((l) => { try { return JSON.parse(l)[key]; } catch { return null; } })
    .filter(Boolean));

let gone = 0;
const walk = (dir, key) => {
  for (const name of readdirSync(join(ROOT, dir))) {
    const rel = join(dir, name);
    if (statSync(join(ROOT, rel)).isDirectory()) { walk(rel, key); continue; }
    if (!name.endsWith('.jsonl')) continue;
    let head;
    try {
      head = execFileSync('git', ['show', `HEAD:${rel}`], { cwd: ROOT, encoding: 'utf8' });
    } catch { continue; }                       // 新文件，没有 HEAD 版本
    const before = ids(head, key), after = ids(readFileSync(join(ROOT, rel), 'utf8'), key);
    const lost = [...before].filter((i) => !after.has(i));
    if (lost.length) {
      gone += lost.length;
      console.error(`✗ ${rel}  ${lost.length} 条记录从文件里消失了：${lost.slice(0, 4).join(' ')}${lost.length > 4 ? ' …' : ''}`);
    }
  }
};
walk('anchors', 'id');
// 边没有独立 ID，用 (前置→后继) 当键
const edgeKey = (txt) => new Set(txt.split('\n').filter((l) => l.trim()).map((l) => {
  try { const e = JSON.parse(l); return `${e.prerequisiteId}→${e.anchorId}`; } catch { return null; }
}).filter(Boolean));
for (const name of readdirSync(join(ROOT, 'edges'))) {
  if (!name.endsWith('.jsonl')) continue;
  const rel = join('edges', name);
  let head;
  try { head = execFileSync('git', ['show', `HEAD:${rel}`], { cwd: ROOT, encoding: 'utf8' }); } catch { continue; }
  const before = edgeKey(head), after = edgeKey(readFileSync(join(ROOT, rel), 'utf8'));
  const lost = [...before].filter((k) => !after.has(k));
  if (lost.length) {
    gone += lost.length;
    console.error(`✗ ${rel}  ${lost.length} 条边从文件里消失了：${lost.slice(0, 3).join(' ')}`);
  }
}

if (gone) {
  console.error(`\n共 ${gone} 条。**记录只增不减** —— 要弃用就标 deprecated 并留下那一行，`);
  console.error('  不许从文件里删掉：已有的档案引用要解析得到它。');
  console.error('  多半是某个工具用了 open(\'w\') 只写新行。');
  process.exit(1);
}
console.log('✓ 没有记录凭空消失（与 HEAD 比对 ID 集合）');
