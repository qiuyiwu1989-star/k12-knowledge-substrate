#!/usr/bin/env node
// signature-stdin.mjs — 批量算去重签名，一行一条 JSON，输出一行一个签名字符串。
//
// 存在的理由和 check-stdin.mjs 一样：**Python 工具不许自己再实现一遍**。
// 落库工具里各写一份 (discipline, verb, object) 元组，签名一改就全部悄悄失配 ——
// 而失配的表现是「本该拦的没拦」，不会报错。
import { dedupeSignature } from './normalize.mjs';
const chunks = [];
for await (const c of process.stdin) chunks.push(c);
for (const line of Buffer.concat(chunks).toString('utf8').split('\n')) {
  if (!line.trim()) continue;
  process.stdout.write(dedupeSignature(JSON.parse(line)) + '\n');
}
