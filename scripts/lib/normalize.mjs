/**
 * normalize.mjs — 文本规范化。必须前置成独立工序，不能塞在抽取里顺手做。
 *
 * 诗歌资产库那次的教训：正文混用全角/半角标点，导致同一实体在库里分裂成多条。
 * 到 15,000 锚点规模，同样的问题量级要大一个数量级，而且分裂发生在 ID 空间上——
 * 一旦档案已经引用了分裂出来的错误锚点，就再也合不回去了。
 */

// 半角 → 全角（中文语境下标点一律用全角，这是唯一的规范形）
const PUNCT_MAP = {
  ',': '，', ';': '；', ':': '：', '?': '？', '!': '！',
  '(': '（', ')': '）', '<': '《', '>': '》',
};

// 常见异体/易混字符统一
const CHAR_MAP = {
  '·': '·', '‧': '·', '•': '·',
  '—': '—', '―': '—', '─': '—',
  '“': '"', '”': '"', '‘': "'", '’': "'", // 先归一再决定引号形态
};

/** 数学/英语语境保留半角标点的白名单学科 */
const HALFWIDTH_OK = new Set(['英语']);

export function normalizeText(raw, { discipline = '' } = {}) {
  if (typeof raw !== 'string') return raw;
  let s = raw.normalize('NFKC');

  // 零宽字符、BOM、不间断空格
  s = s.replace(/[​-‍﻿ ]/g, '');
  // 连续空白折叠；中文之间的空格直接删掉
  s = s.replace(/\s+/g, ' ').trim();
  s = s.replace(/(?<=[一-鿿])\s+(?=[一-鿿])/g, '');

  for (const [from, to] of Object.entries(CHAR_MAP)) s = s.split(from).join(to);

  if (!HALFWIDTH_OK.has(discipline)) {
    for (const [from, to] of Object.entries(PUNCT_MAP)) {
      if (from === '(' || from === ')') continue;   // 括号单独处理，见下
      // 不动数字之间的半角标点（如 3,000 / 1:2）
      s = s.replace(new RegExp(`(?<![0-9A-Za-z+\\-*/=])\\${from}(?![0-9A-Za-z])`, 'g'), to);
    }
    s = s.replace(/(?<![0-9A-Za-z])\.(?![0-9A-Za-z])/g, '。');

    // 括号按「是否紧邻中文」判定，不按「是否紧邻数字」。
    // 原先的数字规则有个隐藏 bug：NFKC 会把全角「）」压成半角，而「）2.3」这种
    // 后面跟数字的收尾括号永远还原不回来 —— 同一条断言就有了两种写法，直接污染去重签名。
    const CJK = '[\\u4e00-\\u9fff\\u3000-\\u303f]';
    s = s.replace(new RegExp(`(?<=${CJK})\\(`, 'g'), '（').replace(new RegExp(`\\)(?=${CJK})`, 'g'), '）');
    s = s.replace(new RegExp(`\\((?=${CJK})`, 'g'), '（').replace(new RegExp(`(?<=${CJK})\\)`, 'g'), '）');
    // 再补一次配对：「（例6)」这种混用收尾是 OCR 常态
    s = s.replace(/（([^（）()]*)\)/g, '（$1）').replace(/\(([^（）()]*)）/g, '（$1）');
  }

  // 句末句号在断言里一律去掉（statement 是短语不是句子）
  s = s.replace(/[。．.]+$/, '');
  return s;
}

/** 去重签名：同一学科下 (动词, 对象) 归一后相同 → 判为重复候选 */
export function dedupeSignature(anchor) {
  const strip = (x) =>
    normalizeText(String(x ?? ''), { discipline: anchor.discipline })
      .replace(/[（）《》「」【】，。、；：？！"'·—\s]/g, '')
      .toLowerCase();
  return `${anchor.discipline}|${strip(anchor.verb)}|${strip(anchor.object)}`;
}

/** 返回 [{field, raw, normalized}]，raw !== normalized 即为未规范化 */
export function findUnnormalized(obj, fields, discipline) {
  const out = [];
  for (const f of fields) {
    const raw = obj[f];
    if (typeof raw !== 'string') continue;
    const n = normalizeText(raw, { discipline });
    if (n !== raw) out.push({ field: f, raw, normalized: n });
  }
  return out;
}
