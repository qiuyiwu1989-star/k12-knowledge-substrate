#!/usr/bin/env node
// no-id-reuse.mjs — 拦「ID 被挪去指别的东西」。
//
// `no-shrink` 保证记录不消失，这道闸保证**同一个 ID 永远指同一处课标出处**。
// 两者合起来才是调用方真正需要的承诺：
//
//   ca_2cp77aYv 今天解析到什么，一年后还解析到什么。
//
// 少了这一条，`no-shrink` 是骗人的 —— 记录行还在，但内容换了，
// 而调用方存的是 ID，它不会知道。
//
// ## 判据为什么是出处，不是断言原文
//
// 断言原文**会合法地改**：我们修过 CID 字体抽出来的乱码
// （「能用6 1基本不等式…」→「能用基本不等式…」），那不是换了一条锚点。
// 拿 statement 做哈希，这类修复会全部误报。
//
// 而 (srcSubject, srcPage) 是「这条断言从教育部哪份文件的哪一页来的」。
// 修字不动它，**换一条锚点一定动它**。所以台账记的是出处。
//
// 台账 `ledger/ids.jsonl` 只增不改，跟着代码一起提交。
// 新 ID 自动入账（--write），已入账的 ID 出处对不上就拦。
import { readFileSync, writeFileSync, readdirSync, mkdirSync, existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
const LEDGER = join(ROOT, 'ledger', 'ids.jsonl');
const WRITE = process.argv.includes('--write');

const readJsonl = (p) => {
  try {
    return readFileSync(p, 'utf8').split('\n').filter((l) => l.trim())
      .map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
  } catch { return []; }
};

// 现存全部锚点（含 deprecated —— 弃用的 ID 更不许被再利用）
const live = new Map();
const dupes = [];
for (const dir of ['anchors', 'retired']) {
  const d = join(ROOT, dir);
  if (!existsSync(d)) continue;
  for (const name of readdirSync(d)) {
    if (!name.endsWith('.jsonl')) continue;
    for (const a of readJsonl(join(d, name))) {
      if (!a.id) continue;
      const p = a.provenance ?? {};
      const site = `${p.srcSubject ?? '?'}#p${p.srcPage ?? '?'}`;
      if (live.has(a.id) && live.get(a.id).site !== site) {
        dupes.push(`${a.id}  ${live.get(a.id).site} ≠ ${site}`);
      }
      if (!live.has(a.id)) live.set(a.id, { site, file: join(dir, name) });
    }
  }
}

const ledger = new Map(readJsonl(LEDGER).map((r) => [r.id, r]));

const moved = [];
for (const [id, cur] of live) {
  const rec = ledger.get(id);
  if (!rec) continue;                                   // 新 ID，下面入账
  // 出处未知（'?'）的不判 —— 有 155 条锚点没保住 srcText/srcPage，
  // 拿未知去比会把「一直未知」当成「被挪动」。这是已知盲区，写进 CONTRACT。
  if (rec.site.includes('?') || cur.site.includes('?')) continue;
  if (rec.site !== cur.site) moved.push(`${id}  台账 ${rec.site} → 现在 ${cur.site}  (${cur.file})`);
}

const fresh = [...live.entries()].filter(([id]) => !ledger.has(id));

if (dupes.length) {
  console.error(`✗ ${dupes.length} 个 ID 在库里出现多次且出处不同：`);
  for (const d of dupes.slice(0, 6)) console.error(`   ${d}`);
  process.exit(1);
}
if (moved.length) {
  console.error(`✗ ${moved.length} 个 ID 被挪去指向了别的课标位置：`);
  for (const m of moved.slice(0, 8)) console.error(`   ${m}`);
  console.error('\n  ID 一旦发布就不许改指向 —— 调用方存的是 ID，它不会知道内容换了。');
  console.error('  要指别的东西：建新 ID，旧的标 deprecated + supersededBy。');
  process.exit(1);
}

if (fresh.length) {
  if (!WRITE) {
    console.error(`✗ ${fresh.length} 个 ID 还没入台账。跑 \`node scripts/no-id-reuse.mjs --write\` 入账后一起提交。`);
    process.exit(1);
  }
  mkdirSync(dirname(LEDGER), { recursive: true });
  const add = fresh.map(([id, v]) => JSON.stringify({ id, site: v.site })).join('\n');
  writeFileSync(LEDGER, (readJsonl(LEDGER).length ? readFileSync(LEDGER, 'utf8').replace(/\n*$/, '\n') : '') + add + '\n');
  console.log(`✓ ${fresh.length} 个新 ID 入账，台账共 ${ledger.size + fresh.length} 条`);
} else {
  const unknown = [...live.values()].filter((v) => v.site.includes('?')).length;
  console.log(`✓ ${live.size} 个 ID 指向未变（台账 ${ledger.size} 条${unknown ? `，其中 ${unknown} 条出处未知、不参与判定` : ''}）`);
}
