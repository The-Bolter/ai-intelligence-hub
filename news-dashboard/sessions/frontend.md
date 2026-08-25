# Frontend v2 任务书

## 任务目标

把页面从通用新闻列表升级为两个清晰的信息产品：AI 综合情报流和游戏周热点看板。分类说明必须清晰，标签必须真实过滤数据。

开始前必读：

1. `AGENTS.md`
2. `PROJECT_CONTEXT.md`
3. `ARCHITECTURE.md`
4. `V2_DESIGN.md`

建议分支：`codex/frontend-v2`

## 文件边界

允许修改：

- `templates/index.html`
- `static/script.js`
- `static/style.css`
- 前端测试或静态 mock 数据

禁止直接修改：

- `fetcher.py`
- `rules.py`
- `game_hotspot.py`
- AI/Gaming 评分与采集逻辑
- `app.py`；真实 API 接入由总控任务完成

## AI 页面要求

1. 综合首页明确展示多方向内容，不把“AI 资源”当作默认全部内容。
2. 每个栏目顶部展示栏目名称、收录范围和阅读价值说明。
3. 支持 `models/products/agents/research/industry/resources` 六个栏目。
4. 页面按后端编排顺序展示，前端不得再次用统一分数把 GitHub 顶回首页。
5. 保留搜索、重要性等有实际意义的筛选。

## Gaming 页面要求

1. 默认视图是本周时间线/日历式热点列表。
2. 每条事件一眼可见：日期、游戏、事件标题、简要内容、数字热度分。
3. 热度只显示 0-100 数字；可配合颜色，不显示“中高”等等级文字。
4. 标签按钮使用真实 `event_type`，点击后只展示对应事件。
5. 显示官方来源入口和信息更新时间。
6. 空结果必须说明“本周该类型暂无已确认事件”，不能回退成全部内容。

## API 与 mock

按以下契约开发，可先使用本地 mock：

- `GET /api/v2/ai-digest`
- `GET /api/v2/game-weekly`

字段以 `V2_DESIGN.md` 为准。不要为了适配临时数据自行改变字段名。

## 必须测试

- AI 六个栏目按钮对应不同数据集合。
- 分类说明随栏目切换。
- Gaming 不同事件标签产生不同结果。
- 无匹配事件时显示空状态。
- 320px、768px 和桌面宽度下核心信息不溢出。
- API 失败时保留明确错误提示，不静默展示旧的错误分类。

## 完成定义

- 使用 mock 数据完成两块页面的主要交互。
- 不修改后端业务逻辑。
- 汇报 DOM 结构、关键状态、预期 API 和人工验收步骤。
