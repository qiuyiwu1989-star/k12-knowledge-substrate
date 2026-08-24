# k12-substrate · MCP server

底座的只读查询接口。零依赖，`node mcp/server.mjs` 直接跑。

## 接上

Claude Code / Claude Desktop 的 MCP 配置里加：

```json
{
  "mcpServers": {
    "k12-substrate": {
      "command": "node",
      "args": ["/绝对路径/os-k12-taxonomy/mcp/server.mjs"]
    }
  }
}
```

`search_anchors` 会 shell out 调 `tools/mapper.py`，所以机器上要有 `python3`。

## 四个工具

| | 干什么 |
|---|---|
| `search_anchors` | 把一段教学内容映射到锚点。**给 discipline**，不给会跨科召回 |
| `get_anchor` | 一条锚点的全部：断言、课标逐字原文、判定问句、前置与后继 |
| `get_prerequisites` | 沿前置边往上走，hard 边优先，`convention` 排最后（那不是真依赖） |
| `list_slice` | 静态分片。stage=归属 · grade=投影 · subject=学科 |

## 每个返回都带的三样

不是可选项，由 `present.mjs` 统一产出，任何工具都漏不掉：

```
provenance    出自教育部哪份文件哪一页 + 逐字原文
verifiedBy    "ai" | "human" | null
grain.warning 这条覆盖几个年级
```

**`verifiedBy` 只有两值，不暴露库里的四档复核成色。** 那四档除 `expert-confirmed`
之外全是机器判的，而 `expert-confirmed` 目前是 **0 条**。对外说
「ai-adjudicated 比 ai-reviewed 更可信」是在卖一个从没被外部验证过的排序 ——
虚假精度。想看原始档位：`get_anchor` 返回里有 `reviewStatusRaw`。

**`grain.warning` 是这个接口最重要的一个字段。** 67.6% 的锚点覆盖 3 个年级，
映射「成功」但信息量接近于零，是这个库最容易骗到调用方的地方。详见 `../GRAIN.md`。

## 两条硬规矩

**只读。** 整个 `mcp/` 在 `no-writeback` 那道闸的名单上，一个写原语都不许有。

**映射结果不写回底座。** 别人的标注是别人的判断；混进来，底座就不再是
「每条都能翻回教育部文件某一页」，而那是它唯一的护城河。

## 版本

数据版本读根目录 `VERSION`。兼容性承诺见 `../CONTRACT.md`。
已发布快照：`https://k12.yongle.school/data/v/<版本>.tgz`，索引在 `/data/v/index.json`。

## 自测

```
npm run mcp-test
```

起真进程、走真 stdio、做真握手 —— 不 import 直接调函数，那测不到协议层，
而调用方看到的恰恰只有协议层。
