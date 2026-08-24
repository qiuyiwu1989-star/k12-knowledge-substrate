#!/usr/bin/env node
// version-diff.mjs — 拦「破坏了调用方，但版本号没动」。
//
// 契约里那句「破坏性变更必须进 major」，如果只写在文档里，
// 它的寿命大概是半年 —— 这个项目已经验证过三次，手写的承诺一定会腐烂。
// 所以把它变成一道闸：**改了什么，由机器分类；版本号动没动，由机器核对。**
//
// ## 四类变更
//
//   breaking     ID 从整个仓库消失 / 学科变 / 出处变
//                → 调用方存的 ID 解析到了别的东西，或者解析不到。必须进 major。
//   deprecating  某条被标弃用
//                → 他档案里引的这条还在，但已经不该再用了。必须进 minor + 写进 CHANGELOG。
//   revising     断言原文改了 / 学段范围改了
//                → 他缓存的文案过时，或年级匹配算错。必须进 minor。
//   additive     新增锚点、新增边
//                → 纯增益，minor 就够。
//
// reviewStatus 升档不进任何一类 —— 复核变好不该惊动任何人。
//
// ## 为什么 breaking 还要求逐条写进 CHANGELOG
//
// 版本号是给机器看的，CHANGELOG 是给人看的。要求逐个 ID 写进去，
// 是**逼一个人真的去看每一条** —— 破坏性变更少到能一条条看，
// 多到看不完的时候，本身就说明这次不该发。
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fingerprint } from './release-manifest.mjs';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
const parse = (v) => { const [a, b] = String(v).trim().split('.'); return { maj: +a || 0, min: +b || 0 }; };

const dir = join(ROOT, 'releases');
const rels = existsSync(dir)
  ? readdirSync(dir).filter((n) => n.endsWith('.json')).map((n) => n.replace(/\.json$/, ''))
      .sort((a, b) => { const x = parse(a), y = parse(b); return x.maj - y.maj || x.min - y.min; })
  : [];
if (!rels.length) {
  console.log('✓ 还没有任何发布版本，无从比对（先跑 node scripts/release-manifest.mjs <版本>）');
  process.exit(0);
}
const last = rels[rels.length - 1];
const prev = JSON.parse(readFileSync(join(dir, `${last}.json`), 'utf8'));
const cur = fingerprint();
const V = parse(readFileSync(join(ROOT, 'VERSION'), 'utf8'));
const P = parse(last);

const breaking = [], deprecating = [], revising = [];
let additive = 0;
for (const [id, o] of Object.entries(prev.anchors)) {
  const n = cur.anchors[id];
  if (!n) { breaking.push(`${id} 从仓库消失`); continue; }
  if (n.d !== o.d) breaking.push(`${id} 学科 ${o.d}→${n.d}`);
  else if (n.site !== o.site && !o.site.includes('?') && !n.site.includes('?')) breaking.push(`${id} 出处 ${o.site}→${n.site}`);
  else if (!o.dep && n.dep) deprecating.push(`${id} 被标弃用`);
  else if (n.st !== o.st) revising.push(`${id} 断言原文改了`);
  else if (n.stage !== o.stage) revising.push(`${id} 学段 ${o.stage}→${n.stage}`);
}
for (const id of Object.keys(cur.anchors)) if (!prev.anchors[id]) additive++;
const dEdges = cur.counts.edges - prev.counts.edges;

const changed = breaking.length + deprecating.length + revising.length + additive || dEdges !== 0;
console.log(`与 ${last} 相比：破坏 ${breaking.length} · 弃用 ${deprecating.length} · 修订 ${revising.length} · 新增锚点 ${additive} · 边 ${dEdges >= 0 ? '+' : ''}${dEdges}`);
for (const l of [...breaking, ...deprecating].slice(0, 10)) console.log(`   ${l}`);

let fail = 0;
if (breaking.length && V.maj <= P.maj) {
  console.error(`\n✗ 有 ${breaking.length} 处破坏性变更，但 VERSION 还是 ${V.maj}.${V.min}（上个版本 ${last}）。`);
  console.error(`  破坏性变更必须进 major：改成 ${P.maj + 1}.0`);
  fail++;
}
if (changed && V.maj === P.maj && V.min <= P.min) {
  console.error(`\n✗ 数据变了但 VERSION 没动（还是 ${V.maj}.${V.min}）。至少要进 minor：${P.maj}.${P.min + 1}`);
  fail++;
}
// 破坏与弃用必须逐条出现在 CHANGELOG —— 逼人真的去看每一条
const need = [...breaking, ...deprecating].map((s) => s.split(' ')[0]);
if (need.length) {
  const cl = existsSync(join(ROOT, 'CHANGELOG.md')) ? readFileSync(join(ROOT, 'CHANGELOG.md'), 'utf8') : '';
  const absent = need.filter((id) => !cl.includes(id));
  if (absent.length) {
    console.error(`\n✗ ${absent.length} 条破坏/弃用没写进 CHANGELOG.md：${absent.slice(0, 6).join(' ')}`);
    console.error('  版本号是给机器看的，CHANGELOG 是给人看的 —— 逐条写，是为了逼人真的去看每一条。');
    fail++;
  }
}
if (fail) process.exit(1);
console.log(changed ? `✓ 版本号 ${V.maj}.${V.min} 与变更类型相符` : `✓ 与 ${last} 相比没有变化`);
