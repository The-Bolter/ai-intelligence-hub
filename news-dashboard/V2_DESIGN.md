# AI + Gaming 情报系统 v2 总体设计

## 1. 产品目标

v2 不再把系统定位为“新闻列表”，而是回答两个明确问题：

- AI 动态：首页回答“今天 AI 各方向有哪些值得关注的事情”。
- 游戏动态：首页回答“本周重点游戏有哪些值得关注的运营事件”。

## 2. v2 成功标准

### AI 动态

- 首页不能被 GitHub 项目或任何单一信息类型占满。
- 首页同时覆盖至少 4 个有效方向，并限制单一来源、单一类型的占比。
- GitHub 项目主要进入“AI 资源”，综合首页只保留少量高价值项目。
- 每个分类页顶部说明该栏目收录什么、为什么值得看。
- 分类筛选基于真实字段，切换栏目后内容集合必须发生相应变化。

### 游戏动态

- 默认展示当前自然周（周一至周日，Asia/Shanghai）的运营事件。
- 事件优先来自游戏官网、官方公告、官方社媒或可信的一手来源。
- 每条事件明确展示日期、游戏、事件类型、简要内容和 0-100 热度分。
- 不再把“中高、较高”等文字等级作为主要结果。
- 标签基于真实 `event_type` 过滤，不同标签不得展示相同的完整集合。

## 3. 总体架构

保留现有采集 → 分类 → 评分 → 翻译 → 保存主链路，通过增量模块实现 v2：

```text
现有 AI Articles ─→ ai_digest_v2.py ─→ data/ai_digest_v2.json
现有 Gaming Articles ─→ gaming_weekly_v2.py ─→ data/game_weekly_v2.json

data/*.json ─→ Flask API（集成阶段）─→ Frontend v2
```

并行开发阶段禁止三个任务直接同时修改核心入口：

- `fetcher.py`：由当前总控任务在集成阶段修改。
- `app.py`：由当前总控任务在集成阶段修改。
- `rules.py`：v2 优先新增独立配置模块，避免 AI 与 Gaming 分支冲突。
- `data/*.json`：运行产物，不提交为代码设计依据。

## 4. AI v2 数据契约

### 4.1 文章需要的标准字段

```json
{
  "id": "article-id",
  "title": "原始标题",
  "summary": "原始摘要",
  "url": "https://...",
  "published_at": "2026-08-25T10:00:00+08:00",
  "source_name": "OpenAI",
  "source_type": "rss",
  "content_type": "model_release",
  "channel": "models",
  "value_score": 72,
  "final_score": 81,
  "home_eligible": true,
  "is_github": false
}
```

### 4.2 首页方向

首版使用以下稳定栏目键：

| channel | 页面名称 | 主要内容 |
|---|---|---|
| `models` | 模型动态 | 模型发布、能力、API、价格和评测 |
| `products` | 产品与应用 | 产品上线、功能更新和应用案例 |
| `agents` | Agent 与工作流 | Agent、自动化、RAG 和开发框架 |
| `research` | 研究进展 | 论文、方法、数据集和技术突破 |
| `industry` | 行业趋势 | 公司战略、融资、政策和市场变化 |
| `resources` | AI 资源 | GitHub 项目、开源模型、工具和教程 |

### 4.3 首页编排默认策略

- 默认候选数：30 条。
- GitHub 项目最多 20%。
- 单一 `channel` 最多 30%。
- 单一 `source_name` 最多 3 条。
- 至少覆盖 4 个有有效候选的 `channel`。
- 先满足方向多样性，再按 `final_score`、时效性排序。
- 配额不足时允许其他方向递补，但不得突破 GitHub 上限。

这些是首版可配置默认值，不写死在前端。

### 4.4 输出文件

`data/ai_digest_v2.json`：

```json
{
  "schema_version": 2,
  "generated_at": "2026-08-25T12:00:00+08:00",
  "guides": {},
  "items": []
}
```

## 5. Gaming v2 数据契约

### 5.1 周热点事件

```json
{
  "id": "game-event-id",
  "game": "崩坏：星穹铁道",
  "event_date": "2026-08-26",
  "event_type": "major_update",
  "version": "4.5",
  "headline": "4.5 版本强制更新",
  "summary": "新版本上线并开放主要版本内容。",
  "heat_score": 78,
  "heat_factors": {
    "update_scale": 25,
    "event_importance": 16,
    "official_emphasis": 12,
    "discussion": 8,
    "game_attention": 12,
    "timing": 5
  },
  "sources": [
    {"name": "游戏官网", "url": "https://...", "official": true}
  ],
  "updated_at": "2026-08-25T12:00:00+08:00"
}
```

### 5.2 事件标签

| event_type | 页面名称 |
|---|---|
| `major_update` | 大版本/强制更新 |
| `monthly_update` | 月度版本 |
| `weekly_update` | 周版本 |
| `season_start` | 赛季开启 |
| `new_map` | 新地图 |
| `new_character` | 新角色 |
| `collaboration` | 联动 |
| `major_event` | 大型活动 |
| `test_or_launch` | 测试/上线 |
| `esports` | 电竞赛事 |

一个事件可以有一个主类型和多个 `tags`，页面主筛选使用 `event_type`。

### 5.3 热度评分

`heat_score` 为 0-100 的可解释分数：

- 更新规模：0-30
- 事件重要性：0-20
- 官方宣传强度：0-15
- 多来源讨论度：0-10
- 游戏关注度：0-15
- 时间临近度：0-10

页面只显示数字分。颜色可以表达强弱，但不得再显示“中高”等模糊等级。

### 5.4 聚合与去重

- 同一游戏、同一日期、同一版本/赛季、同一事件类型合并为一条事件。
- 不同游戏不得因为日期相同而合并。
- 官方来源优先决定日期、版本和事件名称。
- 无法确认日期的内容进入“待确认”，不进入本周主列表。

### 5.5 输出文件

`data/game_weekly_v2.json`：

```json
{
  "schema_version": 2,
  "timezone": "Asia/Shanghai",
  "week_start": "2026-08-24",
  "week_end": "2026-08-30",
  "generated_at": "2026-08-25T12:00:00+08:00",
  "events": []
}
```

## 6. API 契约（集成阶段实现）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v2/ai-digest` | AI 综合首页、分类说明和编排结果 |
| GET | `/api/v2/game-weekly` | 当前周游戏运营事件 |

查询参数：

- `/api/v2/ai-digest?channel=models`
- `/api/v2/game-weekly?event_type=season_start`
- `/api/v2/game-weekly?week=2026-08-24`

现有 `/api/news` 与 `/api/game-hotspots` 在 v2 验收前保留，避免破坏当前页面。

## 7. 分支与文件所有权

| 任务 | 建议分支 | 主要所有权 | 禁止直接修改 |
|---|---|---|---|
| AI Pipeline v2 | `codex/ai-pipeline-v2` | `ai_digest_v2.py`、`ai_v2_rules.py`、AI 测试 | `app.py`、前端、Gaming 模块 |
| Gaming Pipeline v2 | `codex/gaming-pipeline-v2` | `gaming_weekly_v2.py`、`gaming_v2_rules.py`、Gaming 测试 | `app.py`、前端、AI 模块 |
| Frontend v2 | `codex/frontend-v2` | `templates/index.html`、`static/*` | `fetcher.py`、评分和采集逻辑 |
| 当前总控/集成 | 当前分支 | `fetcher.py`、`app.py`、契约联调、最终验收 | 不重写已验收的独立模块 |

## 8. 开发顺序

1. 当前任务完成设计和任务书。
2. AI、Gaming、Frontend 三个任务依据固定契约并行开发。
3. 各任务完成单元测试和样例输出，不自行接入核心入口。
4. 当前任务统一接入 `fetcher.py` 和 `app.py`。
5. 启动本地服务，分别验收 AI 首页多样性、游戏周热点和标签筛选。

## 9. 总体验收清单

- AI 综合首页 GitHub 占比不超过配置上限。
- AI 首页覆盖至少 4 个有数据的方向。
- AI 分类说明与实际 `channel` 一致。
- 游戏默认展示当前自然周。
- 游戏事件均有数字热度分和至少一个来源。
- 不同游戏事件不会错误合并。
- 任一标签筛选结果均满足对应真实字段。
- v1 API 和页面在迁移完成前仍可使用。

