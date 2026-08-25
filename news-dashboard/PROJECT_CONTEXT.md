# 项目上下文文档

## 项目目标与定位

个人 AI + Gaming 双领域情报系统：实时抓取海外 RSS 与 GitHub AI 项目，自动分类、评分、翻译，并聚合游戏运营热点，帮助用户跟进两个领域的关键动态。

## 当前整体架构

```
数据源层        RSS Feeds + GitHub Search API
                ↓
采集层          fetcher.py / github_fetcher.py
                ↓
处理层          去重 → 分类 → value_score 评分 → importance
                ↓
增强层          自动翻译（bing） / Gaming Hotspot 聚合
                ↓
存储层：
运行时生成数据：
- data/news_*.json
- data/translations.json
- data/game_hotspots.json
注意：
以上文件仅用于运行结果展示，不属于代码上下文。
除非任务明确要求分析数据，否则禁止读取。
                ↓
展示层          Flask API → 前端（tabs / 搜索 / 筛选 / 热点 / 翻译）
```

## 数据流流程

### AI 流程
```
RSS feeds + GitHub API → Article dict
  → _classify_tech_types / _classify_ai_category / _classify_applications
  → _compute_value_score → _get_importance
  → auto-translate（score ≥ 40 或 GitHub 高价值）
  → save news_ai.json
```

### Gaming 流程
```
RSS feeds → Article dict
  → _classify_gaming_category
  → _extract_game_entity / _extract_event_type（GAME_ENTITIES）
  → _compute_value_score → _get_importance
  → auto-translate（game_entity + event_type ∈ 运营四类）
  → save news_gaming.json
  → game_hotspot.build_game_hotspots() → game_hotspots.json
```

## 核心文件职责

| 文件 | 职责 |
|---|---|
| `app.py` | Flask 服务 + API 路由 |
| `fetcher.py` | RSS 抓取、分类、评分、翻译触发、热点构建入口 |
| `rules.py` | 分类关键词、评分配置、GAME_ENTITIES、翻译策略 |
| `config.py` | RSS 源、刷新间隔、数据文件路径 |
| `github_fetcher.py` | GitHub AI 项目采集 + Article 转换 |
| `translation_service.py` | 翻译封装、缓存层、过滤逻辑 |
| `game_hotspot.py` | Gaming 热点聚合、事件时间、等级、影响标签 |
| `run.py` | 服务器启动入口 |
| `templates/index.html` | 单页前端模板 |
| `static/script.js` | 前端逻辑（加载、排序、渲染、热点） |
| `static/style.css` | 前端样式 |
| `data/` | 运行时数据（news/translations/hotspots） |

## Completed Major Features

## 已完成核心功能

### AI 情报流水线
✅ RSS + GitHub AI 项目数据采集  
✅ AI 内容分类体系  
✅ 价值评分与重要性分级  
✅ 自动翻译与缓存机制  


### 游戏情报流水线
✅ 游戏实体识别  
✅ 游戏热点聚合分析  


### 前端展示
✅ 情报 Dashboard 页面

1. **数据源与评分解耦**：采集层只产出 Article dict，评分/分类完全由 rules.py + fetcher.py 处理。
2. **配置驱动**：关键词、评分权重、游戏 Watchlist、翻译策略都在 rules.py/config.py，业务代码不硬编码。
3. **评分独立**：文章 `value_score` 与热点 `hot_score` 完全独立，互不影响。
4. **翻译缓存优先**：同一 article_id 只翻译一次，结果缓存到 translations.json。
5. **Watchlist + 自动发现**：GAME_ENTITIES 为人工重点关注，未来支持自动发现新游戏（未实现）。
6. **单页应用**：前端通过 /api/* 动态加载，不刷新页面。

## 禁止随意修改的模块

- `rules.py` 的分类关键词、评分权重、BASE_SCORE、GAME_ENTITIES（改动需先对齐）
- `fetcher.py` 的 `_compute_value_score()` 评分公式
- `translation_service.py` 的翻译逻辑与缓存策略
- AI pipeline（分类 → 评分 → 翻译链路）
- RSS 采集逻辑（config.py 源配置可加，采集核心不动）

