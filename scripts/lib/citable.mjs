// citable.mjs — 「可被 L3 档案引用」的唯一定义，从 mappings/citable.json 现读。
// **不许在别处再写一遍这个集合。** 写第二遍的那天它就开始发散，
// 而发散的表现是两个页面报不同的数，没人知道该信哪个。
import { readFileSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const J = JSON.parse(readFileSync(join(ROOT, 'mappings/citable.json'), 'utf8'));
export const CITABLE = new Set(J.citable);
export const HUMAN_CONFIRMED = new Set(J.humanConfirmed);
export const CITABLE_DECISION = J.decision;
export const TIERS = J.tiers;   // 图上的成色分档，和 CITABLE 是两件事
