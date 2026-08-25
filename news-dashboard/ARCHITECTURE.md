# 架构文档

## 模块调用关系

```
run.py
  └→ app.py (Flask app)
       ├→ fetcher.py
       │    ├→ config.py
       │    ├→ rules.py
       │    ├→ github_fetcher.py
       │    ├→ translation_service.py
       │    └→ game_hotspot.py
       ├→ translation_service.py
       └→ game_hotspot.py（API 读取 data 文件）

fetcher.py → refresh_all()
  ├→ fetch_category("ai") → github_fetcher.fetch_github_projects()
  ├→ fetch_category("gaming") → game_entity/event_type 识别
  ├→ _run_auto_translate() → translation_service.try_translate_article()
  └→ build_game_hotspots() → game_hotspot.py
```

## 数据流向

### 写路径（刷新时）
```
RSS/GitHub → Article dicts
  → fetch_category() 内联分类+评分
  → save_news(cat, items) → data/news_{ai,gaming}.json
  → _run_auto_translate() → data/translations.json
  → build_game_hotspots() → data/game_hotspots.json
```

### 读路径（前端请求）
```
GET /api/news?category=X → data/news_X.json
GET /api/translations      → data/translations.json
GET /api/game-hotspots     → data/game_hotspots.json（按游戏聚合）
GET /api/status            → 两份 news 文件的元信息
```

## Module Modification Boundary

允许增量修改：

rules.py
- 新增关键词
- 新增配置


github_fetcher.py
- 新增 GitHub 数据源


game_hotspot.py
- 优化热点算法


static/
- UI展示优化


禁止直接修改：

fetcher.py 主流程：
RSS/GitHub
→ 分类
→ 评分
→ 翻译
→ 保存

除非明确要求。

## API 关系

| 方法 | 路径 | 功能 | 数据源 |
|---|---|---|---|
| GET | `/` | 首页 HTML | templates/index.html |
| GET | `/api/news?category=ai\|gaming` | 文章列表 | data/news_*.json |
| POST | `/api/refresh` | 手动刷新 | fetcher.refresh_all() |
| GET | `/api/status` | 数据状态 | news 元信息 |
| GET | `/api/translations` | 翻译缓存 | data/translations.json |
| POST | `/api/test-translate` | 单篇翻译测试 | try_translate_article() |
| GET | `/api/game-hotspots` | 游戏热点（按游戏聚合） | data/game_hotspots.json |
| GET | `/api/ai-insights` | AI 洞察 | data/ai_insights.json |
| POST | `/api/ai-analyze` | AI 分析触发 | 预留 |

## 前后端交互关系

```
页面加载
  ├→ GET /（HTML + CSS + JS）
  ├→ script.js:
  │    ├→ loadTranslations() → GET /api/translations
  │    ├→ loadNews("ai")     → GET /api/news?category=ai
  │    ├→ loadHotspots("ai") → GET /api/game-hotspots（仅 Gaming tab）
  │    └→ renderItems()      按 importance>value_score>hotness 排序
  │                          有翻译优先显示中文
  └→ 切换 tab → switchTab(cat) → loadNews + loadHotspots
```

前端关键状态：
- `allItems`：当前分类全部文章（已排序）
- `translations`：article_id → {title_cn, summary_cn}
- `hotspots`：游戏聚合热点数组
- `importanceFilter/categoryFilter`：筛选状态

## 关键函数入口

### fetcher.py
| 函数 | 作用 |
|---|---|
| `refresh_all()` | 全量刷新入口（AI+Gaming+翻译+热点） |
| `fetch_category(cat)` | 单分类抓取→分类→评分→返回 items |
| `_compute_value_score(item, cat)` | 评分核心（base + dims + source_bonus） |
| `_github_value_bonus(item)` | GitHub metadata 加分 |
| `_classify_ai_category(title, summary, item)` | AI 分类 + GitHub topic 特殊处理 |
| `_classify_gaming_category(title, summary)` | Gaming 分类 |
| `_extract_game_entity(title, summary)` | 游戏实体识别（返回 game/region/type） |
| `_extract_event_type(title, summary)` | 事件类型识别 |
| `_run_auto_translate(articles, cat)` | 自动翻译调度（配额 10/刷新） |
| `_should_translate_article(article, cat, min_score)` | 翻译资格判断 |

### translation_service.py
| 函数 | 作用 |
|---|---|
| `translate_text(text)` | 单段翻译（bing） |
| `translate_article(title, summary)` | 文章翻译，返回 dict |
| `try_translate_article(id, title, summary)` | 过滤 + 翻译 + 缓存入口 |
| `translate_and_cache(id, title, summary)` | 缓存优先翻译 |
| `get_cached_translation(id)` | 读缓存 |
| `is_chinese_text(text)` / `is_valid_summary(summary)` | 过滤 |

### game_hotspot.py
| 函数 | 作用 |
|---|---|
| `build_game_hotspots()` | 聚合入口，写 game_hotspots.json |
| `_extract_event_entity(title, summary, event_type)` | 版本/赛季/角色/事件提取 |
| `_compute_event_time(articles, title, summary)` | 事件时间（标题>正文>官方>发布） |
| `_hot_level(event_type, event_entity, score)` | 等级 S/A/B/C |
| `_hot_score(articles, event, has_entity)` | 独立热点评分 |

### github_fetcher.py
| 函数 | 作用 |
|---|---|
| `fetch_github_projects()` | GitHub Search API → Article dict 列表 |

## 推荐读取顺序（后续 Agent 修改时）

1. `PROJECT_CONTEXT.md`（整体定位 + 已完成功能）
2. `ARCHITECTURE.md`（模块关系 + 入口）
3. `rules.py`（配置改动时）
4. 对应功能文件：
   - 改分类/评分 → `fetcher.py` 相关函数 + `rules.py`
   - 改翻译 → `translation_service.py`
   - 改热点 → `game_hotspot.py`
   - 改 API → `app.py`
   - 改前端 → `static/script.js` + `templates/index.html`

不需要每次读取：`data/*.json`、`config.py` 全量、`run.py`、`static/style.css`（除非改样式）。
