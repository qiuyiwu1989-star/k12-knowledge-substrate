#!/usr/bin/env node
/**
 * decide.mjs — 可判定性过滤器的唯一对外入口（stdin/stdout，JSONL）。
 *
 * 抽取流水线是 Python，闸门是 JS。**过滤器绝不能有第二份实现**——
 * 两份实现必然漂移，那时「入库时通过、校验时被拒」的记录会成批出现，
 * 而且没人说得清哪一份才对。所以 Python 侧一律 shell 出来调这个。
 *
 *   echo '{"statement":"能计算两位数加两位数的进位加法"}' | node scripts/decide.mjs
 *   → {"statement":"…","ok":true,"verb":"计算","reasons":[]}
 */
import { checkDecidable } from './lib/decidability.mjs';
import { normalizeText } from './lib/normalize.mjs';

const chunks = [];
for await (const c of process.stdin) chunks.push(c);
const lines = Buffer.concat(chunks).toString('utf8').split('\n').filter((l) => l.trim());

for (const line of lines) {
  let rec;
  try {
    rec = JSON.parse(line);
  } catch {
    process.stdout.write(JSON.stringify({ error: '无法解析', raw: line.slice(0, 80) }) + '\n');
    continue;
  }
  const normalized = normalizeText(rec.statement ?? '', { discipline: rec.discipline ?? '' });
  const d = checkDecidable(normalized);
  process.stdout.write(JSON.stringify({ ...rec, normalized, ok: d.ok, verb: d.verb, reasons: d.reasons }) + '\n');
}
