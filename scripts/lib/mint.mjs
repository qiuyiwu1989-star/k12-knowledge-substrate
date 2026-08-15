/**
 * mint.mjs — ID 铸造。无语义、永不复用。
 *
 * 唯一的硬约束：铸造前必须先加载全部已用 ID。ID 一旦进过档案就不可回收，
 * 「复用一个看起来没人用的 ID」是这套系统里最贵的错误——它会把两个孩子的
 * 不同能力记录悄悄合并，而且没有任何报错。
 */
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // 去掉 0/O/1/l/I

export function loadUsedIds(root) {
  const used = new Set();
  const walk = (dir) => {
    if (!existsSync(dir)) return;
    for (const n of readdirSync(dir)) {
      const p = join(dir, n);
      if (statSync(p).isDirectory()) walk(p);
      else if (p.endsWith('.jsonl')) {
        for (const line of readFileSync(p, 'utf8').split('\n')) {
          const m = line.match(/"(?:id|anchorId|prerequisiteId|supersededBy)"\s*:\s*"(ca_[A-Za-z0-9]{8})"/g) ?? [];
          for (const hit of m) used.add(hit.match(/(ca_[A-Za-z0-9]{8})/)[1]);
        }
      }
    }
  };
  // 弃用记录也算已用——绝不回收
  for (const d of ['anchors', 'edges', 'lists', 'mappings', 'retired']) walk(join(root, d));
  return used;
}

export function mintId(used, rand = () => Math.floor(Math.random() * ALPHABET.length)) {
  for (let attempt = 0; attempt < 1000; attempt++) {
    let s = 'ca_';
    for (let i = 0; i < 8; i++) s += ALPHABET[rand()];
    if (!used.has(s)) { used.add(s); return s; }
  }
  throw new Error('ID 空间冲突过于频繁——检查 used 集合是否被正确加载');
}
