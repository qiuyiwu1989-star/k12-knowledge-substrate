// grain.mjs — 一条锚点覆盖几个年级，以及该给调用方什么粒度警告。
//
// **粒度只有这一处定义。** 曾经想过在锚点上存一个 `span` 字段，
// 但那等于给粒度立了第二个定义，它一定会和 `stageHint` 漂移 ——
// 这个项目专门有一道 `no-dup-defs` 拦的就是这种事（可引用档位一度散在 8 个文件里、3 个不同的值）。
// 所以：**不存，算。**
//
// 分档阈值在 mappings/grain.json，Node 和 Python 读同一份。
import { readFileSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const CFG = JSON.parse(readFileSync(join(ROOT, 'mappings', 'grain.json'), 'utf8'));

const gnum = (x) => (typeof x === 'string' && /^G\d+$/.test(x) ? Number(x.slice(1)) : null);

/** 覆盖的年级数；算不出来返回 null */
export function grainSpan(anchor) {
  const lo = gnum(anchor?.stageHint?.min), hi = gnum(anchor?.stageHint?.max);
  if (lo === null || hi === null || hi < lo) return null;
  return hi - lo + 1;
}

/** { span, key, label, warn } —— warn 是给调用方原样透出的那句话 */
export function grainOf(anchor) {
  const n = grainSpan(anchor);
  if (n === null) return { span: null, ...CFG.unknown };
  const band = CFG.bands.find((b) => n <= b.max) ?? CFG.bands[CFG.bands.length - 1];
  return { span: n, key: band.key, label: band.label,
           warn: band.warn ? band.warn.replace('{n}', String(n)) : null };
}
