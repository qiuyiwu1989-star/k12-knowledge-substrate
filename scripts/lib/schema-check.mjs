// schema-check.mjs — 够用的 JSON Schema 子集校验器。
//
// 为什么自己写：这个仓库**零依赖**是有意的选择（没有 node_modules，
// clone 下来直接 node 就能跑校验）。为了让 schema/ 从摆设变成闸，
// 不值得破坏这一点。支持的关键字就是 schema/*.json 实际用到的那些，
// **遇到不认识的关键字直接报错**而不是忽略 —— 悄悄跳过一条约束，
// 比没有这条约束更糟：它看着像被校验了。
const KNOWN = new Set(['$schema', '$id', 'title', 'description', 'type', 'properties',
  'required', 'additionalProperties', 'items', 'enum', 'const', 'pattern',
  'minLength', 'maxLength', 'minItems', 'maxItems', 'minimum', 'maximum',
  'default', 'format', 'examples', 'forbidden']);

const typeOf = (v) => v === null ? 'null' : Array.isArray(v) ? 'array' : typeof v;

export function check(schema, value, path = '', out = []) {
  for (const k of Object.keys(schema)) {
    if (!KNOWN.has(k)) throw new Error(`schema 用了未实现的关键字「${k}」于 ${path || '/'}`);
  }
  const bad = (m) => out.push(`${path || '/'}: ${m}`);

  if (schema.type) {
    const want = [].concat(schema.type);
    const got = typeOf(value);
    // JSON Schema 里 integer 不是 typeof 的结果，单独判
    const ok = want.some((t) => t === got || (t === 'integer' && Number.isInteger(value)));
    if (!ok) { bad(`应为 ${want.join('|')}，实为 ${got}`); return out; }
  }
  if (schema.const !== undefined && value !== schema.const) bad(`应恒为 ${JSON.stringify(schema.const)}`);
  if (schema.enum && !schema.enum.includes(value)) bad(`不在枚举内：${JSON.stringify(value)}`);

  if (typeof value === 'string') {
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) bad(`不匹配 /${schema.pattern}/：${JSON.stringify(value.slice(0, 40))}`);
    if (schema.minLength != null && value.length < schema.minLength) bad(`长度 ${value.length} < ${schema.minLength}`);
    if (schema.maxLength != null && value.length > schema.maxLength) bad(`长度 ${value.length} > ${schema.maxLength}`);
  }
  if (typeof value === 'number') {
    if (schema.minimum != null && value < schema.minimum) bad(`${value} < ${schema.minimum}`);
    if (schema.maximum != null && value > schema.maximum) bad(`${value} > ${schema.maximum}`);
  }
  if (Array.isArray(value)) {
    if (schema.minItems != null && value.length < schema.minItems) bad(`${value.length} 项 < ${schema.minItems}`);
    if (schema.maxItems != null && value.length > schema.maxItems) bad(`${value.length} 项 > ${schema.maxItems}`);
    if (schema.items) value.forEach((v, i) => check(schema.items, v, `${path}[${i}]`, out));
  }
  if (value && typeOf(value) === 'object') {
    for (const k of schema.required || []) {
      if (!(k in value)) bad(`缺必填字段 ${k}`);
    }
    for (const [k, v] of Object.entries(value)) {
      const sub = schema.properties?.[k];
      // forbidden: 这个字段存在本身就是错。用来表达「这三个字段的缺席是设计结论」
      // —— 写进 schema 才不会有人「顺手加个难度系数」。
      if (sub?.forbidden) bad(`出现禁止字段 ${k} — ${sub.description ?? ''}`);
      else if (sub) check(sub, v, `${path}.${k}`, out);
      else if (schema.additionalProperties === false) bad(`出现 schema 未声明的字段 ${k}`);
    }
  }
  return out;
}
