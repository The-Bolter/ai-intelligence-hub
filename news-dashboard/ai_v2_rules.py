"""Configuration for the AI Pipeline v2 digest layer.

This module is intentionally independent from ``rules.py`` so the v2 work can
be developed and tested without changing the existing scoring pipeline.
"""

CHANNEL_ORDER = (
    "models",
    "products",
    "agents",
    "research",
    "industry",
    "resources",
)

CHANNEL_GUIDES = {
    "models": {
        "name": "模型动态",
        "description": "模型发布、能力升级、API、价格与评测变化。",
    },
    "products": {
        "name": "产品与应用",
        "description": "AI 产品上线、功能更新与真实应用案例。",
    },
    "agents": {
        "name": "Agent 与工作流",
        "description": "智能体、自动化工作流、RAG 与 Agent 开发实践。",
    },
    "research": {
        "name": "研究进展",
        "description": "论文、方法、数据集、基准与技术突破。",
    },
    "industry": {
        "name": "行业趋势",
        "description": "公司战略、融资并购、政策监管与市场变化。",
    },
    "resources": {
        "name": "AI 资源",
        "description": "GitHub 项目、开源模型、框架、工具与教程。",
    },
}

HOME_POLICY = {
    "limit": 30,
    "github_ratio_max": 0.20,
    "channel_ratio_max": 0.30,
    "source_item_max": 3,
    "min_channel_coverage": 4,
    "github_min_score": 70,
    "github_min_stars": 10_000,
}

# Existing v1 category/content values are treated as strong evidence, while
# keyword scoring provides compatibility for raw or partially classified data.
PRIOR_CHANNEL_BY_VALUE = {
    "model_update": "models",
    "model": "models",
    "product_update": "products",
    "app": "products",
    "agent": "agents",
    "breakthrough": "research",
    "research": "research",
    "company": "industry",
    "market_change": "industry",
    "community_hotspot": "industry",
    "tech_direction": "industry",
    "resources": "resources",
    "resource": "resources",
    "tool": "resources",
}

CHANNEL_KEYWORDS = {
    "models": (
        "model release", "new model", "foundation model", "language model",
        "llm", "gpt", "claude", "gemini", "llama", "deepseek", "qwen",
        "mistral", "kimi", "context window", "model weights", "open weights",
        "模型发布", "新模型", "大模型", "模型更新", "模型能力",
    ),
    "products": (
        "product", "app", "feature", "launch", "release", "beta", "preview",
        "copilot", "assistant", "workspace", "customer", "use case",
        "产品", "应用", "上线", "新功能", "功能更新", "案例",
    ),
    "agents": (
        "agent", "agentic", "multi-agent", "autonomous", "workflow", "rag",
        "retrieval augmented", "tool calling", "function calling",
        "智能体", "工作流", "自动化", "多智能体",
    ),
    "research": (
        "research", "paper", "arxiv", "benchmark", "dataset", "method",
        "algorithm", "state of the art", "sota", "evaluation",
        "研究", "论文", "数据集", "基准", "算法", "技术突破",
    ),
    "industry": (
        "company", "funding", "investment", "acquisition", "merger", "revenue",
        "earnings", "market", "industry", "regulation", "policy", "lawsuit",
        "公司", "融资", "投资", "收购", "财报", "市场", "行业", "监管", "政策",
    ),
    "resources": (
        "github", "open source", "repository", "framework", "sdk", "api", "cli",
        "library", "plugin", "extension", "tutorial", "awesome list", "mcp",
        "开源", "项目", "框架", "工具", "插件", "教程", "资源",
    ),
}

CONTENT_TYPE_BY_CATEGORY = {
    "model_update": "model_release",
    "model": "model_release",
    "product_update": "product_update",
    "app": "product_application",
    "agent": "agent_workflow",
    "breakthrough": "research_breakthrough",
    "research": "research_update",
    "company": "company_update",
    "market_change": "market_change",
    "community_hotspot": "community_discussion",
    "tech_direction": "technology_trend",
    "tool": "ai_resource",
}

DEFAULT_CONTENT_TYPE = {
    "models": "model_update",
    "products": "product_update",
    "agents": "agent_workflow",
    "research": "research_update",
    "industry": "industry_update",
    "resources": "ai_resource",
}
