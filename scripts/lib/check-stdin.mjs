#!/usr/bin/env node
/**
 * check-stdin.mjs — 批量过可判定性闸。stdin 每行一个 statement，stdout 每行一个 JSON 判定。
 *
 * 为什么要有它：`decidability.mjs` 直接跑只会跑自己的夹具，不吃 stdin，
 * 于是 Python 侧的工具只能**自己再实现一遍判定逻辑** —— 那必然和 CI 漂移，
 * 而漂移的方向永远是「本地觉得能过、CI 说不行」，每次都白跑一整批。
 *
 * 一次进程处理一批，不要每条 statement 起一个 node（167 条要多花半分钟）。
 *
 *   printf '%s\n' "能运用生活中的物品自制简易乐器" | node scripts/lib/check-stdin.mjs
 *   → {"ok":true,"verb":"运用","reasons":[]}
 */
import { checkDecidable } from './decidability.mjs';

const chunks = [];
for await (const c of process.stdin) chunks.push(c);
const lines = Buffer.concat(chunks).toString('utf8').split('\n');

const out = [];
for (const l of lines) {
  if (!l.trim()) continue;
  // 允许纯文本行，也允许 {"statement":"…"} —— 调用方怎么方便怎么来
  let s = l;
  if (l.trimStart().startsWith('{')) {
    try { s = JSON.parse(l).statement ?? ''; } catch { /* 当纯文本 */ }
  }
  out.push(JSON.stringify(checkDecidable(s)));
}
process.stdout.write(out.join('\n') + (out.length ? '\n' : ''));
