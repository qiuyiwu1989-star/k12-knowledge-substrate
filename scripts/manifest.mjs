#!/usr/bin/env node
/**
 * manifest.mjs — 生成 manifest.json（计数 + 每文件 SHA-256）。
 * 每次数据变更后跑一次；validate.mjs 会核对，不一致即 CI 失败。
 *
 *   node scripts/manifest.mjs
 */
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync, existsSync, writeFileSync } from 'node:fs';
import { dirname, resolve, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const walk = (d) => (!existsSync(d) ? [] : readdirSync(d).flatMap((n) => {
  const p = join(d, n);
  return statSync(p).isDirectory() ? walk(p) : p.endsWith('.jsonl') ? [p] : [];
}));

const files = {};
const counts = { anchors: 0, candidates: 0, edges: 0, listItems: 0, mappings: 0 };
const byDiscipline = {};
const byTrack = {};
const byReview = {};

for (const [dir, counter] of [['anchors', 'anchors'], ['candidates', 'candidates'], ['edges', 'edges'], ['lists', 'listItems'], ['mappings', 'mappings']]) {
  for (const f of walk(join(ROOT, dir)).sort()) {
    const buf = readFileSync(f);
    files[relative(ROOT, f)] = { bytes: buf.length, sha256: createHash('sha256').update(buf).digest('hex') };
    for (const line of buf.toString('utf8').split('\n')) {
      const t = line.trim();
      if (!t || t.startsWith('//')) continue;
      counts[counter]++;
      if (counter !== 'anchors' && counter !== 'candidates') continue;
      const r = JSON.parse(t);
      if (counter === 'candidates') { byReview['candidate:llm-proposed'] = (byReview['candidate:llm-proposed'] ?? 0) + 1; continue; }
      byDiscipline[r.discipline] = (byDiscipline[r.discipline] ?? 0) + 1;
      byTrack[r.track] = (byTrack[r.track] ?? 0) + 1;
      byReview[r.reviewStatus] = (byReview[r.reviewStatus] ?? 0) + 1;
    }
  }
}

const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
const manifest = {
  dataset: 'K12 知识底座 (K12 Knowledge Substrate)',
  release: pkg.version,
  schemaVersion: '0.1.0',
  generatedAt: process.env.SOURCE_DATE || new Date().toISOString().slice(0, 10),
  counts: { ...counts, byDiscipline, byTrack, byReview },
  // 复核率是这个项目唯一重要的进度指标：llm-proposed 的锚点不许被档案引用，
  // 所以「可用锚点数」= 总数 - llm-proposed 数。
  // 唯一重要的进度指标：候选不算数，llm-proposed 不算数，只有复核过的才是可用锚点
  usableAnchors: counts.anchors - (byReview['llm-proposed'] ?? 0),
  files,
};
writeFileSync(join(ROOT, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`✓ manifest.json 已生成 — 锚点 ${counts.anchors}（可用 ${manifest.usableAnchors}）· 边 ${counts.edges} · 清单 ${counts.listItems} · 映射 ${counts.mappings}`);
