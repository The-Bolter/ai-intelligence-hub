# AI Pipeline v2 任务书

## 任务目标

将 AI 动态从“全量文章按分数排序”升级为“多方向、来源均衡的综合情报流”。
综合首页不能被 GitHub 项目占满，分类页必须有清晰、真实的内容边界。

开始前必读：

1. `AGENTS.md`
2. `PROJECT_CONTEXT.md`
3. `ARCHITECTURE.md`
4. `V2_DESIGN.md`

建议分支：`codex/ai-pipeline-v2`

## 文件边界

允许新增或修改：

- 新增 `ai_digest_v2.py`
- 新增 `ai_v2_rules.py`
- 新增 AI v2 单元测试
- 必要时对 `github_fetcher.py` 做最小字段补充

禁止直接修改：

- `app.py`
- `templates/`、`static/`
- Gaming 相关文件
- `fetcher.py` 主链路；集成点交由总控任务处理

## 实现要求

1. 将文章映射为 `models/products/agents/research/industry/resources` 六个稳定栏目。
2. 输出 `content_type`、`channel`、`home_eligible`、`is_github`。
3. 实现可配置的首页编排函数，满足：
   - GitHub 最多 20%；
   - 单一栏目最多 30%；
   - 单一来源最多 3 条；
   - 有足够候选时覆盖至少 4 个栏目。
4. GitHub 项目主要进入 `resources`，只有高价值候选进入综合首页。
5. 生成符合 `V2_DESIGN.md` 的 `ai_digest_v2.json` 样例。
6. 不改变现有文章价值评分公式；v2 编排发生在评分之后。

## 必须测试

- 30 个 GitHub 项目 + 少量 RSS 时，首页仍有多方向内容。
- 某方向候选不足时可以递补，但 GitHub 上限不被突破。
- 同一来源不会超过配置上限。
- 分类页数据只包含目标 `channel`。
- 同一输入产生稳定、可复现的排序。

## 完成定义

- 独立模块和测试通过。
- 提供一份小型样例输出，不运行全量刷新作为唯一测试手段。
- 汇报新增文件、对外函数、输入输出字段和集成方式。
- 不自行接入 `fetcher.py` 或 `app.py`。

---

## v1 背景记录

## 模块范围

- RSS AI 数据源（config.py AI_FEEDS）
- GitHub AI 项目采集（github_fetcher.py）
- AI 分类体系（rules.py + fetcher.py _classify_*）
- AI 评分体系（_compute_value_score / _github_value_bonus / importance）
- AI 翻译策略（translation_service.py + fetcher.py _should_translate_article）
- AI 文章质量优化（chinese_summary / summary_type / 排序）

## 数据流

RSS / GitHub → Article dict → 去重 → 分类 → value_score → importance
→ final_score 排序 → 自动翻译（配额 10/刷新）→ data/news_ai.json

## 来源配置字段

每个 AI RSS 源配置：

- source_name：来源显示名
- source_type：rss / github
- source_region：CN / Global
- source_priority：0-10，越高权重越大
- 兼容旧字段：name / url / weight / lang

GitHub 来源统一使用 config.GITHUB_SOURCE，priority=7。

## 评分规则

- value_score = 分类 base + 内容维度 + source_weight bonus（上限 100）
- GitHub 项目额外加 stars/forks bonus（上限 15）
- importance：S >= 60 / A >= 40 / B >= 20 / C >= 8
- final_score = value_score + source_priority + hotness
  - hotness 已包含发布时间衰减（freshness）
  - AI 列表按 final_score 降序，rank 随之重排

## 翻译规则

AI 文章满足任一条件才进入自动翻译：

- importance 属于 S / A
- 或 value_score >= 60
- 或 source_priority >= 8

说明：S/A 阈值当前为 value_score >= 40，因此实际英文翻译门槛为
value_score >= 40 或高 priority 来源。中文来源自动跳过（is_chinese_text）。

## 2026-08-04 变更

- AI_FEEDS 增加 source_name/source_type/source_region/source_priority
- 新增国内来源：机器之心、InfoQ 中文、智东西
- 新增 final_score 并用于 AI 排序
- TRANSLATION_POLICY 改为 S/A + 高价值 + 高优先级来源
- 更新 translation_service.should_translate 为真实策略

## 测试方式

- 不做全量 refresh：python -m py_compile 检查语法
- 用样例 dict 验证 _compute_final_score / _should_translate_article
- 下次手动 POST /api/refresh 后检查 news_ai.json 的 source_* 与 final_score
