#!/usr/bin/env node
// release-manifest.mjs — 给当前库拍一张**指纹**，供 version-diff 比对。
//
// 存指纹不存全量：一次发布的全量数据 4MB 上下，长期留在 git 里会把仓库撑爆；
// 而判断「变了什么、算不算破坏性」只需要每条锚点的几个字段。
// 调用方要 pin 的**真实数据**发到站上 /data/v/<版本>/，那份才是全量、不可变。
//
// 指纹里放什么，取决于「调用方存了 ID 之后，什么变化会让他措手不及」：
//   discipline / 出处   变了 = 这个 ID 指向了别的东西
//   statement           变了 = 他缓存的文案过时了
//   stageHint           变了 = 他算的年级匹配错了
//   deprecated          变了 = 他档案里引的这条被弃用了
// reviewStatus 故意**不进指纹** —— 复核升档是纯增益，不该触发任何版本动作。
import { readFileSync, writeFileSync, readdirSync, mkdirSync, existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
const h = (s) => createHash('sha256').update(String(s)).digest('hex').slice(0, 12);

export function fingerprint() {
  const out = {};
  for (const dir of ['anchors', 'retired']) {
    const d = join(ROOT, dir);
    if (!existsSync(d)) continue;
    for (const name of readdirSync(d)) {
      if (!name.endsWith('.jsonl')) continue;
      for (const l of readFileSync(join(d, name), 'utf8').split('\n')) {
        if (!l.trim()) continue;
        let a; try { a = JSON.parse(l); } catch { continue; }
        if (!a.id) continue;
        const p = a.provenance ?? {}, s = a.stageHint ?? {};
        out[a.id] = {
          d: a.discipline ?? null,
          site: `${p.srcSubject ?? '?'}#p${p.srcPage ?? '?'}`,
          st: h(a.statement ?? ''),
          stage: `${s.min ?? '?'}-${s.max ?? '?'}`,
          dep: a.deprecated ? 1 : 0,
        };
      }
    }
  }
  let edges = 0;
  for (const name of readdirSync(join(ROOT, 'edges'))) {
    if (name.endsWith('.jsonl')) {
      edges += readFileSync(join(ROOT, 'edges', name), 'utf8').split('\n').filter((l) => l.trim()).length;
    }
  }
  return { anchors: out, counts: { anchors: Object.keys(out).length, edges } };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const ver = process.argv[2];
  if (!ver) { console.error('用法：node scripts/release-manifest.mjs <版本号>  例如 1.0'); process.exit(1); }
  const fp = fingerprint();
  mkdirSync(join(ROOT, 'releases'), { recursive: true });
  const p = join(ROOT, 'releases', `${ver}.json`);
  if (existsSync(p)) { console.error(`✗ releases/${ver}.json 已存在。发布版本不可变，换个版本号。`); process.exit(1); }
  writeFileSync(p, JSON.stringify({ version: ver, ...fp }, null, 0) + '\n');
  console.log(`✓ releases/${ver}.json  锚点 ${fp.counts.anchors} · 边 ${fp.counts.edges}`);
}
