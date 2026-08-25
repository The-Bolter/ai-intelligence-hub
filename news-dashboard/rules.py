AI_TECH_TYPE_KEYWORDS = {
    "Video Generation": ["video generation", "text-to-video", "sora", "视频生成"],
    "Audio/Speech": ["speech", "tts", "voice", "music generation", "语音"],
    "Multimodal": ["multimodal", "vision-language", "多模态"],
    "Code Generation": ["code generation", "code completion", "code review", "代码生成"],

    "Agent": ["agent","智能体","rag","multi-agent"],
    "Image Generation": ["image generation","text-to-image","stable diffusion"],
    "Other": [],
}
AI_LLM_EVIDENCE = {
    "threshold": 6,
    "groups": {
        "high": {"weight": 10, "keywords": [
            "gpt-4o","gpt-4","gpt-4.5","gpt-3.5","o1","o3",
            "claude 3","claude 3.5","claude 4",
            "llama 3","llama 4","llama 3.1",
            "gemini 2","gemini 2.5",
            "deepseek","deepseek v3","deepseek r1",
            "qwen","qwen2","qwen2.5",
            "kimi","kimi k3","mistral","mixtral",
            "phi-3","phi-4","gemma",
            "command r","command r+",
            "grok","grok 3","dbrx","falcon","yi","yi-lightning",
            "llm","large language model","language model",
            "transformer","attention mechanism",
            "reasoning","chain of thought","chain-of-thought","cot",
            "fine-tuning","finetuning","sft","rlhf",
            "pre-training","pretraining","post-training",
            "context window","token","tokenizer",
            "in-context learning","few-shot",
            "alignment","instruction tuning",
            "model weights","open weights",
            "function calling","tool calling",
            "chatgpt","claude code","gemini","copilot",
        ]},
        "medium": {"weight": 5, "keywords": [
            "openai","anthropic",
            "google deepmind","deepmind",
            "meta ai","mistral ai","cohere",
            "hugging face","ai21","xai",
            "inflection","character.ai",
            "moonshot ai","zhipu","baichuan","minimax",
            "prompt","prompt engineering",
            "completion","generation",
            "inference","training run",
            "benchmark","mmlu","human-eval","leaderboard",
            "agent","rag","retrieval augmented",
            "multimodal","vision language",
            "agentic","multi-agent",
        ]},
        "low": {"weight": 2, "keywords": [
            "ai","artificial intelligence",
            "model","neural","neural network",
            "chatbot","chat bot",
            "machine learning","deep learning",
            "algorithm","compute",
            "training data","dataset",
            "gpu","nvidia","cuda",
            "google","microsoft","meta","amazon","apple","ibm",
        ]},
        "negative": {"weight": -5, "keywords": [
            "investment","funding","series a","series b","series c",
            "revenue","earnings","quarterly","fiscal",
            "acquisition","merger","ipo",
            "stock","buyback","dividend",
            "lawsuit","regulatory","regulator",
            "layoff","layoffs","hiring","salary","compensation",
            "chip","semiconductor","processor",
            "manufacturing","fabrication",
        ]},
    }
}
AI_APPLICATION_KEYWORDS = {


    "Research": ["research", "paper", "arxiv", "benchmark", "研究"],
    "Business": ["enterprise", "business", "企业", "商业"],
    "Gaming": ["game", "gaming", "游戏"],
    "Automation": ["automation", "workflow", "pipeline"],

    "Development": ["code","api","sdk","framework"],
    "Creation": ["create","design","image","video"],
    "Productivity": ["productivity","automation","workflow"],
    "Other": [],
}
GAMING_CATEGORY_SCORING = {
    "New Release": {
        "high": {"weight": 3, "keywords": [
            "release date","launch date","out now","now available","release window",
            "coming to","arrives on","releases on",
            "pre-order","preorder",
        ]},
        "medium": {"weight": 2, "keywords": [
            "release","launch","arrives","arriving",
            "early access","beta","demo",
            "trailer","teaser","first look","hands-on",
        ]},
        "low": {"weight": 1, "keywords": [
            "announce","announced","revealed","reveal",
            "coming soon","gets a","preview","estimated file size","round up",
        ]},
        "negative": {"weight": -4, "keywords": [
            "revenue","earnings","quarterly","fiscal",
            "acquisition","funding","investment",
            "lawsuit","layoff","shutdown","closure",
            "report","survey","backlash","protest",
            "says","claims",
        ]},
    },
    "Game Update": {
        "high": {"weight": 3, "keywords": [
            "patch notes","content update","major update",
            "free update","new content","next patch",
            "version","hotfix",
        ]},
        "medium": {"weight": 2, "keywords": [
            "update","patch","dlc","expansion",
            "season","roadmap","battle pass",
        ]},
        "low": {"weight": 1, "keywords": [
            "adding","adds","giving players",
        ]},
    },
    "Industry": {
        "high": {"weight": 3, "keywords": [
            "acquisition","funding","investment",
            "revenue","earnings","quarterly","fiscal",
            "layoff","layoffs","shutdown","closure",
            "lawsuit","legal",
            "subscription",
        ]},
        "medium": {"weight": 2, "keywords": [
            "partnership","collaboration","report","survey",
            "backlash","protest","calls for",
            "price","pricing","founded","opens",
            "digital","physical",
        ]},
        "low": {"weight": 1, "keywords": [
            "says","claims","will you",
        ]},
    },
    "Tech/Hardware": {
        "high": {"weight": 3, "keywords": [
            "unreal engine 5","unreal engine","unity",
            "dlss","ray tracing","frame generation",
            "performance mode","frame rate","60fps",
            "resolution","4k",
            "load times","ssd",
        ]},
        "medium": {"weight": 2, "keywords": [
            "graphics","fps",
            "console","handheld",
            "nintendo switch","ps5","ps6","xbox series",
            "steam deck",
            "controller","headset","vr","engine",
        ]},
        "low": {"weight": 1, "keywords": [
            "ai npc","next-gen",
        ]},
    },
    "Operation": {
        "high": {"weight": 3, "keywords": [
            "live service","free-to-play","free to play",
            "battle pass","season pass",
            "player count",
        ]},
        "medium": {"weight": 2, "keywords": [
            "community","event","challenge","quest","reward",
            "monetization","retention",
            "monthly","players",
        ]},
        "low": {"weight": 1, "keywords": [
            "limited time",
        ]},
    },
}

# Source quality mapping (by source name)
AI_SOURCE_QUALITY = {
    "The Decoder": "high",
    "TechCrunch AI": "high",
    "MIT Tech Review": "high",
    "VentureBeat AI": "high",
    "机器之心": "high",
    "InfoQ 中文": "high",
    "智东西": "high",
    "量子位": "high",
    "36氪": "medium",
    "Hacker News": "medium",
}
GAMING_SOURCE_QUALITY = {
    "IGN": "high",
    "PC Gamer": "high",
    "Eurogamer": "high",
    "Gematsu": "high",
    "Nintendo Life": "high",
    "VG247": "high",
    "GamesIndustry": "high",
    "机核": "medium",
}

AI_TAXONOMY = {
    "updates": {
        "company": [
            "company", "enterprise", "partnership", "collaboration",
            "funding", "acquisition", "investment", "merger", "ipo",
            "revenue", "earnings", "lawsuit", "regulation", "policy", "layoff",
            "企业", "公司", "融资", "收购", "投资", "合作", "战略",
            "监管", "政策", "财报", "裁员",
        ],
        "model_update": [
            "model release", "model launch", "new model", "model weights",
            "open weights", "foundation model", "llm", "large language model",
            "gpt-4", "gpt-5", "gpt-4o", "o1", "o3", "claude", "gemini",
            "llama", "deepseek", "qwen", "mistral", "kimi",
            "模型发布", "新模型", "大模型", "基础模型", "模型更新",
        ],
        "product_update": [
            "release", "launch", "update", "new feature", "beta", "preview",
            "upgrade", "version", "copilot", "cursor", "claude code",
            "app", "tool", "api", "sdk",
            "产品", "发布", "上线", "更新", "新功能", "版本",
        ],
        "breakthrough": [
            "breakthrough", "milestone", "state of the art", "sota",
            "research", "paper", "arxiv", "benchmark", "algorithm",
            "技术突破", "突破", "研究", "论文", "成果",
        ],
    },
    "resources": {
        "agent": [
            "agent", "agentic", "multi-agent", "autonomous", "workflow",
            "mcp", "model context protocol", "rag",
            "智能体", "工作流",
        ],
        "model": [
            "llm", "language model", "foundation model", "transformer",
            "diffusion", "multimodal", "vision", "tts", "speech",
            "model", "推理", "模型", "多模态",
        ],
        "tool": [
            "tool", "framework", "sdk", "api", "cli", "library", "plugin",
            "extension", "工具", "框架", "插件", "库",
        ],
        "app": [
            "app", "application", "product", "应用", "产品",
        ],
    },
    "trend": {
        "tech_direction": [
            "trend", "direction", "outlook", "roadmap", "survey", "analysis",
            "趋势", "方向", "展望", "路线图", "分析", "盘点",
        ],
        "market_change": [
            "market", "industry", "funding", "acquisition", "revenue",
            "regulation", "policy", "economy",
            "市场", "行业", "监管", "政策", "融资", "收购", "财报", "格局",
        ],
        "community_hotspot": [
            "hotspot", "hottest", "community", "debate", "controversy",
            "热点", "社区", "讨论", "争议", "爆火",
        ],
    },
}
AI_CATEGORY_BASE_SCORE = {
    "agent": 35,
    "model": 35,
    "tool": 30,
    "app": 25,
    "model_update": 35,
    "product_update": 30,
    "company": 20,
    "breakthrough": 30,
    "tech_direction": 25,
    "market_change": 20,
    "community_hotspot": 20,
}
GAMING_CATEGORY_BASE_SCORE = {"New Release":35,"Game Update":20,"Industry":15,"Tech/Hardware":20,"Operation":15,"Other":0}
AI_SCORE_DIMENSIONS = {"practicality":{"keywords":{"ai":8,"model":8,"gpt":10,"api":10},"weight":0.40,"max":100},"efficiency":{"keywords":{"faster":12,"performance":10,"workflow":12},"weight":0.35,"max":100},"trend":{"keywords":{"new":8,"breakthrough":15},"weight":0.25,"max":100}}
GAMING_SCORE_DIMENSIONS = {"product":{"keywords":{"game":8,"release":10,"review":12,"trailer":10},"weight":0.35,"max":100},"business":{"keywords":{"revenue":10,"game pass":12,"pricing":10},"weight":0.25,"max":100},"operation":{"keywords":{"update":8,"season":10,"event":8},"weight":0.20,"max":100},"market":{"keywords":{"acquisition":10,"console":8,"steam":8,"nintendo":5,"playstation":5},"weight":0.20,"max":100}}
IMPORTANCE_AI = [("S",60),("A",40),("B",20),("C",8)]
IMPORTANCE_GAMING = [("S",60),("A",40),("B",20),("C",8)]
SOURCE_WEIGHT_BONUS = {"ai":{8:5,7:3,6:2},"gaming":{8:5,7:3,6:2}}
TRANSLATION_POLICY = {
    "enable_auto_translate": True,
    "min_value_score": 60,
    "importance_levels": ["S", "A"],
    "min_source_priority": 80,
}
GITHUB_STARS_SCORES = (
    (100000, 40), (50000, 36), (20000, 32), (10000, 28),
    (5000, 24), (2000, 18), (1000, 14), (500, 10), (100, 6),
)
GITHUB_FORKS_SCORES = (
    (20000, 20), (10000, 18), (5000, 15), (2000, 12),
    (1000, 10), (500, 7), (100, 4),
)
GITHUB_TOPIC_SCORE_MAX = 20
GITHUB_TOPIC_SCORE_PER = 2
GITHUB_ACTIVITY_SCORES = ((7, 20), (30, 15), (90, 10), (180, 5))
SOURCE_WEIGHT_BONUS = {"ai":{8:5,7:3,6:2},"gaming":{8:5,7:3,6:2}}

GAME_ENTITIES = {
    "CN Mobile": {
        "region": "CN",
        "type": "Mobile",
        "games": {
            "\u539f\u795e": ["genshin", "\u539f\u795e"],
            "\u5d29\u574f\uff1a\u661f\u7a79\u94c1\u9053": ["honkai star rail", "\u661f\u7a79\u94c1\u9053", "\u5d29\u574f\u661f\u7a79\u94c1\u9053"],
            "\u7edd\u533a\u96f6": ["zenless zone zero", "\u7edd\u533a\u96f6"],
            "\u738b\u8005\u8363\u8000": ["\u738b\u8005\u8363\u8000", "honor of kings", "arena of valor"],
            "\u548c\u5e73\u7cbe\u82f1": ["\u548c\u5e73\u7cbe\u82f1", "game for peace"],
            "\u86cb\u4ed4\u6d3e\u5bf9": ["eggy party", "\u86cb\u4ed4\u6d3e\u5bf9"],
            "\u7b2c\u4e94\u4eba\u683c": ["\u7b2c\u4e94\u4eba\u683c", "identity v"],
            "\u660e\u65e5\u65b9\u821f": ["\u660e\u65e5\u65b9\u821f", "arknights"],
            "\u9e23\u6f6e": ["\u9e23\u6f6e", "wuthering waves"],
        }
    },
    "Global Live Service": {
        "region": "Global",
        "type": "Live Service",
        "games": {
            "Fortnite": ["fortnite", "\u5821\u5792\u4e4b\u591c"],
            "Roblox": ["roblox"],
            "Minecraft": ["minecraft", "\u6211\u7684\u4e16\u754c"],
            "League of Legends": ["league of legends", "\u82f1\u96c4\u8054\u76df"],
            "Valorant": ["valorant", "\u74e6\u7f57\u5170\u7279"],
            "PUBG": ["pubg", "playerunknown", "\u7edd\u5730\u6c42\u751f"],
            "Apex Legends": ["apex legends"],
            "Call of Duty": ["call of duty", "\u4f7f\u547d\u53ec\u5524"],
            "Overwatch": ["overwatch", "\u5b88\u671b\u5148\u950b"],
        }
    },
    "Emerging": {
        "region": "Global",
        "type": "Emerging",
        "games": {
            "Black Myth Wukong": ["black myth wukong", "\u9ed1\u795e\u8bdd\u609f\u7a7a", "\u9ed1\u795e\u8bdd"],
            "Palworld": ["palworld", "\u5e7b\u517d\u5e15\u9c81"],
            "Monster Hunter": ["monster hunter", "\u602a\u7269\u730e\u4eba"],
        }
    },
}

GAME_EVENT_TYPE_KEYWORDS = {
    "Version Update": ["update", "patch", "version", "\u7248\u672c", "\u66f4\u65b0"],
    "Season/Event": ["season", "event", "festival", "\u8d5b\u5b63", "\u6d3b\u52a8", "\u8d5b\u4e8b"],
    "Character/Content": ["character", "hero", "content", "\u89d2\u8272", "\u5185\u5bb9"],
    "Collaboration": ["collab", "collaboration", "crossover", "\u8054\u52a8", "\u5408\u4f5c"],
    "Release": ["release", "launch", "\u53d1\u5e03", "\u4e0a\u7ebf"],
    "Community Hotspot": ["community", "player", "players", "\u73a9\u5bb6", "\u4e89\u8bae", "\u8ba8\u8bba"],
    "Industry": ["revenue", "earnings", "acquisition", "layoff", "\u8d22\u62a5", "\u6536\u8d2d", "\u88c1\u5458"],
}
