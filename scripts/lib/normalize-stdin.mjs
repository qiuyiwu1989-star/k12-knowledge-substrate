#!/usr/bin/env node
/**
 * normalize-stdin.mjs — 批量归一文本。stdin 每行一个 JSON `{text, discipline}`，
 * stdout 每行一个归一后的 JSON 字符串。
 *
 * 为什么要有它：Python 侧的写盘工具没法调 normalize.mjs，于是写进去的东西
 * 常常带着全角引号和句末句号，等 CI 报「未规范化」才发现 —— 实测一次 60 处。
 * 归一规则只能有一份（scripts/lib/normalize.mjs），谁都不许自己再写一遍。
 *
 *   printf '%s\n' '{"text":"能算“绝艺”的次数。","discipline":"数学"}' | node scripts/lib/normalize-stdin.mjs
 */
import { normalizeText } from './normalize.mjs';

const chunks = [];
for await (const c of process.stdin) chunks.push(c);
const out = [];
for (const l of Buffer.concat(chunks).toString('utf8').split('\n')) {
  if (!l.trim()) continue;
  const { text = '', discipline = '' } = JSON.parse(l);
  out.push(JSON.stringify(normalizeText(text, { discipline })));
}
process.stdout.write(out.join('\n') + (out.length ? '\n' : ''));
