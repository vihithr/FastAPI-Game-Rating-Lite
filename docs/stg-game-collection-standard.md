# STG 游戏数据采集标准（stg-game-v1）

- 版本：1.0
- 日期：2026-10-27
- 状态：草案，可作为采集工具与站内导入器的数据契约
- 适用对象：自动采集工具、人工补录、批量导入脚本

---

## 1. 目标与边界

本标准的目的是让不同来源、不同工具采集到的 STG 游戏数据可以被稳定地校验、去重和导入，而不是要求采集阶段就把所有字段填满。

边界：

- 只采集**游戏元数据、分类信息、封面素材**。
- **不采集评分、难度分数、评论、用户信息**。这些必须由社区用户产生，导入器不应写入。
- 采集端保留原始素材；导入端负责压缩、裁剪、生成站内版本。
- 导入默认 `dry-run`，人工确认后才写库。

---

## 2. 交付结构

推荐以单个 zip 交付，传输层不受单文件大小限制：

```text
bundle.zip
├── games.jsonl
├── manifest.json
└── covers/
    ├── raw/
    │   └── <record_id>.jpg
    └── derived/                 # 可选：已压缩好的入库文件
        └── <record_id>.webp
```

规则：

- `games.jsonl` 使用 UTF-8、无 BOM，一行一个 JSON，不要整包数组。
- 封面按 `record_id` 或稳定哈希命名，不使用空格和中文标点。
- `raw/` 保存原始/高清封面，大小不限；`derived/` 可选，供直接入库。
- 批量 zip 在传输上没有“单文件 1MB”限制；导入器解压后逐条校验、压缩、去重。
- 目前站内网页上传仍校验单图 ≤1MB；内部导入器应在写入前压好，或单独放宽导入限制。

`manifest.json` 示例：

```json
{
  "schema_version": "stg-game-v1",
  "generated_at": "2026-10-27T12:00:00Z",
  "collector": "stg-collector/0.1",
  "record_count": 1,
  "cover_count": 1,
  "files": {
    "games": "games.jsonl",
    "covers": "covers/"
  }
}
```

---

## 3. 最小记录（硬性要求）

一条记录至少包含：

- `schema_version`
- `record_id`
- `game.title`
- `game.company`
- `sources` 至少一条

其余字段都可以为空。最小示例：

```json
{"schema_version":"stg-game-v1","record_id":"mobygames:1234","game":{"title":"怒首领蜂 大往生","company":"Cave"},"sources":[{"url":"https://example.com/source","type":"database","retrieved_at":"2026-10-27"}]}
```

> 先把“能稳定去重和追溯”的字段保证好，再追求字段完整度。宁可留空，不要猜。

---

## 4. 完整记录示例

> 以下示例仅用于说明结构，字段值不代表已经核实的事实数据。

```json
{
  "schema_version": "stg-game-v1",
  "record_id": "shmups_wiki:dodonpachi-daioujou",
  "game": {
    "title": "怒首领蜂 大往生",
    "company": "Cave",
    "description": "2002 年推出的纵版弹幕射击游戏，以高密度弹幕和连击得分为核心。",
    "tags": ["纵版", "弹幕", "街机"],
    "translations": ["怒首领蜂 大往生"],
    "aliases": ["怒首領蜂 大往生", "DoDonPachi DaiOuJou", "DOJ"],
    "difficulty_levels": ["Easy", "Normal", "Hard", "Ultra"],
    "ship_types": ["Type-A", "Type-B", "Type-C"],
    "cover": {
      "source_file": "covers/raw/dodonpachi-daioujou.jpg",
      "derivative_file": "covers/derived/dodonpachi-daioujou.webp",
      "source_url": "https://example.com/cover",
      "credit": "Cave / official press material",
      "license": "official-press-kit"
    }
  },
  "meta": {
    "original_title": "怒首領蜂 大往生",
    "developer": "Cave",
    "publisher": "Cave",
    "release_date": "2002-04-05",
    "region": "JP",
    "platforms": ["arcade"],
    "series": "DoDonPachi",
    "players": {"min": 1, "max": 2, "coop": false},
    "external_ids": {
      "shmups_wiki": "dodonpachi-daioujou",
      "mobygames": 1234
    },
    "confidence": "high",
    "notes": ""
  },
  "sources": [
    {
      "url": "https://example.com/official",
      "type": "official",
      "fields": ["title", "original_title", "release_date", "developer"],
      "retrieved_at": "2026-10-27"
    },
    {
      "url": "https://example.com/database",
      "type": "database",
      "fields": ["platforms", "publisher", "ship_types"],
      "retrieved_at": "2026-10-27"
    }
  ]
}
```

---

## 5. 字段定义

### 5.1 顶层字段

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `schema_version` | 是 | string | 固定为 `stg-game-v1` |
| `record_id` | 是 | string | 稳定 ID，优先 `source:external_id`，不要用标题生成 |
| `game` | 是 | object | 游戏主体数据 |
| `meta` | 否 | object | 当前模型暂不持久化的扩展信息 |
| `sources` | 是 | array | 至少一条来源 |

### 5.2 `game` 字段

| 字段 | 必填 | 类型 | 规则 |
|---|---|---|---|
| `title` | 是 | string | 展示主标题；当前数据库要求唯一；不要加平台后缀 |
| `company` | 是 | string | 当前只有一个公司字段，填**开发商**；不要拼接发行商 |
| `description` | 推荐 | string | 80–300 字；事实性介绍；不写评分、不写营销文案 |
| `tags` | 推荐 | string[] | 使用受控词表；最多 12 个；不要放公司/系列名 |
| `translations` | 推荐 | string[] | 中文译名/本地化标题 |
| `aliases` | 推荐 | string[] | 原名、罗马字、英文名、缩写、俗称、常见误写 |
| `difficulty_levels` | 否 | string[] | 游戏内真实难度名，保留原大小写；不知道就留空 |
| `ship_types` | 否 | string[] | 游戏内真实机体/角色名；不知道就留空 |
| `cover` | 否 | object | 封面素材，见第 7 节 |

### 5.3 `meta` 字段（可选，建议保留）

| 字段 | 类型 | 说明 |
|---|---|---|
| `original_title` | string | 日文/原文标题 |
| `developer` | string | 开发商；与 `game.company` 重复时可省略 |
| `publisher` | string | 发行商 |
| `release_date` | string | ISO 8601：`YYYY-MM-DD` 或 `YYYY-MM`；未知用 `null` |
| `region` | string | ISO 3166-1 alpha-2；全球用 `WW` |
| `platforms` | string[] | `arcade`、`pc`、`sfc`、`fc`、`md`、`ps1`、`ps2`、`psp`、`switch`、`xbox`、`mobile`、`other` |
| `series` | string | 系列名，例如 `DoDonPachi` |
| `players` | object | `{"min":1,"max":2,"coop":false}` |
| `external_ids` | object | 各来源的稳定 ID，例如 `shmups_wiki`、`mobygames`、`steam`、`klov` |
| `confidence` | string | `high` / `medium` / `low` |
| `notes` | string | 不确定项、版本差异、合并说明 |

### 5.4 `sources` 字段

```json
{
  "url": "https://example.com/source",
  "type": "official",
  "fields": ["title", "release_date"],
  "retrieved_at": "2026-10-27"
}
```

- `type`：`official` / `database` / `wiki` / `manual`
- `fields`：该来源支持哪些字段，便于后续核对
- 至少一条来源；`confidence=high` 建议两条独立来源
- 未知字段用 `null` 或空数组，不要填 `Unknown`、`N/A`、`待补充`

---

## 6. 标签词表

当前数据库的 `tags` 是一个扁平表，因此先用固定写法；以后可以给标签增加分类字段。

建议的轴：

- **方向**：`纵版`、`横版`、`多方向`、`伪3D`、`轨道`
- **类型**：`弹幕`、`传统射击`、`跑轰`、`战术射击`
- **平台**（短期可继续放 tags）：`街机`、`PC`、`SFC`、`FC`、`MD`、`PS1`、`PS2`、`PSP`、`Switch`、`Xbox`、`移动端`
- **来源**：`商业`、`同人`
- **人数**：`单人`、`双人`、`多人`
- **机制/功能**：`消弹`、`擦弹`、`自动射击`、`练习模式`、`分数系统`
- **题材**：`和风`、`美少女`、`科幻`、`军事`

规则：

- 固定拼写，不允许同义词和错别字（例如统一 `横版`，不要出现 `横板`）。
- 公司、系列名不要放进 tags；公司用 `game.company`，系列放 `meta.series`。
- 不确定的标签宁可不加。
- 当前库里 `CAVE`、`CAVE系`、`SNES`、`SFC`、`横板` 等混用，批量采集前应先做一次词表归一。

---

## 7. 封面素材

### 7.1 采集端

- `source_file` 可以是原始高清图，大小不限，不要为了 1MB 提前牺牲画质。
- 优先使用官方 press kit、商店页或明确允许使用的素材。
- 记录 `source_url`、`credit`、`license`；无法确认授权时宁可不传封面。
- 不要使用带水印、带 UI、明显拉伸或粉丝二创且无授权的图。

### 7.2 入库端

- 目标比例：3:4 竖版优先。
- 建议长边 1200–1600，WebP quality 80–85，不放大。
- 当前网页上传限制单图 ≤1MB；批量导入器应在写入前压缩到该范围内。
- 站内会再生成 400w / 800w WebP 缩略图。
- 导入端仍需限制图片像素数（例如 20MP）和读取大小，防止压缩炸弹。
- 如果提供 `derivative_file`，应已经满足上述尺寸和大小；否则导入器从 `source_file` 生成。

---

## 8. 去重与合并

匹配优先级：

1. 相同 `external_id`（同一来源）
2. 归一化后的 `title + release_year + developer`
3. 标题/别名交叉匹配

归一化规则：

- Unicode NFKC
- 拉丁字母转小写
- 去掉多余空格、常见标点、全角/半角差异
- 日文原名、罗马字、英文名、中文译名都参与匹配
- 仅用于匹配，写入时保留原始展示值

合并规则：

- 一个游戏一条记录；不同平台/区域发行放在 `meta.platforms`，不拆成多条。
- 重制版、续作、明显不同的版本单独一条。
- 匹配到多个候选时不要自动合并，输出“待人工确认”报告。
- 当前数据库 `title` 是唯一索引；导入前必须检查标题和别名冲突，不能靠改名绕过。

---

## 9. 来源与可信度

- 至少一条官方或权威资料库来源；高置信度建议两条独立来源。
- 每条记录保留 `retrieved_at`；链接失效时仍能追溯采集时间。
- 采集工具不得编造字段。没有来源的字段留空，并在 `notes` 标记不确定。
- 描述必须自己组织语言，不整段复制受版权保护的文本。
- 遵守目标站点的 robots.txt、服务条款和访问频率限制；不绕过付费墙或登录。
- 不采集社区评分、评论、难度分数。

---

## 10. 导入流程

建议的内部流程（不暴露公网端口）：

1. 校验 `games.jsonl` 和 `manifest.json` 的结构、必填字段、来源。
2. 归一化标题、别名、标签、日期。
3. 与现有游戏按 `external_id`、标题、别名做去重。
4. 处理封面：校验、裁剪、压缩，生成站内版本。
5. 输出 `dry-run` 报告：新增 / 重复 / 冲突 / 缺字段 / 图片问题。
6. 人工确认后以系统用户身份导入；建议先备份数据库。
7. 按 `record_id` 保持幂等：重复导入同一记录应更新而不是新建。

当前数据库没有 `record_id` 字段，导入器需要自行维护映射（或后续新增 `external_ids` 表）。

---

## 11. 与当前站内模型的映射

当前 `Game` 模型（`app/models.py`）可承接：

| 标准字段 | 当前字段 | 说明 |
|---|---|---|
| `game.title` | `Game.title` | 唯一索引 |
| `game.company` | `Game.company` | 必填，建议填开发商 |
| `game.description` | `Game.description` | 可空 |
| `game.tags` | `Game.tags` | 扁平标签，全局共享 |
| `game.translations` | `Game.translations` | 每个游戏独立 |
| `game.aliases` | `Game.aliases` | 每个游戏独立 |
| `game.difficulty_levels` | `Game.difficulty_levels` | 每个游戏独立 |
| `game.ship_types` | `Game.ship_types` | 每个游戏独立 |
| `game.cover` | `Game.image_url` | 上传后保存为 `/static/...` |
| `sources` / `meta` | 无 | 当前不持久化，需要扩展 |

当前模型的缺口：

- 没有 `original_title`、`release_date`、`developer`、`publisher`
- 没有 `platforms`、`series`、`external_ids`
- 没有来源、封面授权、置信度字段
- `title` 唯一索引会阻止同名/跨区版本
- 导入需要 `created_by`，应使用一个系统用户

如果要做长期批量收集，建议至少补充：

- `original_title`
- `release_date`
- `developer` / `publisher`
- `platforms`
- `series`
- `external_ids`（来源 + 外部 ID，唯一）
- `sources`（或导入留档表）
- `cover_source_url` / `cover_credit`

这些属于模型变更，需要单独确认后再做迁移。

---

## 12. 当前数据现状（清理参考）

截至 2026-10-27：

- 60 条游戏，全部有封面
- 仅 18 条有别名
- 4 条没有介绍
- 标签混用了方向、类型、平台、公司、系列，且存在 `横板` 拼写和测试数据
- 难度等级中存在 `112233` 这类测试值

批量导入前建议先做一次标签词表归一和测试数据清理，否则新增数据会继续放大脏数据。

---

## 13. 交付验收清单

- [ ] `games.jsonl` 是 UTF-8、一行一个 JSON
- [ ] `schema_version` 正确，`record_id` 唯一且稳定
- [ ] `game.title`、`game.company`、`sources` 均存在
- [ ] 没有评分、评论、用户数据
- [ ] 标签全部在受控词表内
- [ ] 未知字段为 `null` 或空数组，没有猜测值
- [ ] 封面有来源/授权记录，尺寸和大小符合入库要求
- [ ] 已用别名和外部 ID 做过去重
- [ ] 已生成 `dry-run` 报告并核对新增/重复/冲突数量
- [ ] `manifest.json` 的记录数与实际行数一致

---

## 14. 版本与变更

- `stg-game-v1`：首个采集契约，区分源文件与入库文件，最小必填字段，支持批量 zip。
- 后续新增字段应保持向后兼容；删除或重命名字段需要升级 `schema_version`。
