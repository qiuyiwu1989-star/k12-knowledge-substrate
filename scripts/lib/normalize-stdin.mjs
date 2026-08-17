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

/** 归一到不动点。
 *
 * `normalizeText` **单次调用不幂等** —— 实测 99 条里，第一遍留下尾空格、
 * 第二遍才去掉（大概是某个变换先 trim、后又移除了一个字符，把空格暴露出来）。
 * 只跑一遍的后果：带尾空格的句子被写进库，等 CI 报「未规范化」才发现，
 * 而那时已经铸了 494 个 ID。
 *
 * 跑到不动点，调用方就不必关心内部顺序。上限 4 轮 —— 真要振荡就该报错，
 * 而不是静默返回一个中间态。 */
function normalizeFixpoint(text, opts) {
  let cur = text;
  for (let i = 0; i < 4; i++) {
    const next = normalizeText(cur, opts);
    if (next === cur) return cur;
    cur = next;
  }
  const last = normalizeText(cur, opts);
  if (last !== cur) {
    process.stderr.write(`归一在 4 轮内没收敛：${JSON.stringify(text)}\n`);
    process.exit(3);
  }
  return cur;
}

const chunks = [];
for await (const c of process.stdin) chunks.push(c);
const out = [];
for (const l of Buffer.concat(chunks).toString('utf8').split('\n')) {
  if (!l.trim()) continue;
  const { text = '', discipline = '' } = JSON.parse(l);
  out.push(JSON.stringify(normalizeFixpoint(text, { discipline })));
}
process.stdout.write(out.join('\n') + (out.length ? '\n' : ''));
