// usage.mjs — 回收**一个信号**，不回收任何判断。
//
// ## 为什么这个文件不在 mcp/ 里
//
// `no-writeback` 那道闸把整个 `mcp/` 列为只读，一个写原语都不许有。
// 计数要落盘，所以它必须在名单外 —— 而这看起来像是给自己的闸开后门，
// 所以反过来给它加了一道更严的：**这个文件只许写一个硬编码常量路径**，
// 由 `no-writeback` 单独核对（见那边的 COUNTER 段）。
//
// ## 只记什么
//
//   anchorId → { hits, lastSeen }
//
// **绝不记查询内容。** 查询里可能有孩子的名字、老师的评语、错题原文 ——
// 那是 L3 级别的东西，L3 数据一个字都不许进这个仓库。
// **绝不联网。** 只写本地文件。
//
// ## 它是干什么用的
//
// 底座唯一能替代教师签字的信号：**长期没有任何人映射得上的锚点，
// 大概率是坏锚点或者粒度错的锚点。** 不是有人说它对，是有人真的用上了它。
//
// 「映射结果不写回底座」这条规矩不变 —— 记的是「这条被碰过几次」，
// 不是「别人认为它对应什么」。前者是使用痕迹，后者是别人的判断。
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = process.env.K12_ROOT ?? resolve(dirname(fileURLToPath(import.meta.url)), '..');
const FILE = join(ROOT, 'var', 'usage.json');    // ← 唯一的写入目标，no-writeback 核对这一行
const OFF = process.env.K12_USAGE === '0';

let mem = null;
const load = () => {
  if (mem) return mem;
  try { mem = JSON.parse(readFileSync(FILE, 'utf8')); } catch { mem = { since: null, anchors: {} }; }
  return mem;
};

let dirty = false, timer = null;
/** 记一次命中。ids 是锚点 ID 数组，别的什么都不传 —— 这个签名故意不接受查询文本。 */
export function record(ids) {
  if (OFF || !ids?.length) return;
  const d = load();
  const now = new Date().toISOString().slice(0, 10);       // 只到天，不到秒
  if (!d.since) d.since = now;
  for (const id of ids) {
    const e = d.anchors[id] ?? (d.anchors[id] = { hits: 0, lastSeen: null });
    e.hits++; e.lastSeen = now;
  }
  dirty = true;
  if (!timer) timer = setTimeout(flush, 2000).unref?.() ?? setTimeout(flush, 2000);
}

export function flush() {
  timer = null;
  if (OFF || !dirty || !mem) return;
  mkdirSync(dirname(FILE), { recursive: true });
  writeFileSync(FILE, JSON.stringify(mem));
  dirty = false;
}
export { FILE as USAGE_FILE };
