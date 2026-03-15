"""
Mock data for development
"""
from .schemas import ModelMeta, Preset, ProviderConfig, AccountInfo


MOCK_MODELS: list[ModelMeta] = [
    # Claude Series
    ModelMeta(
        id="claude-opus-4-6",
        name="Claude Opus 4.6",
        provider="anthropic",
        category="Claude",
        tier=2,
        priceInput=15.0,
        priceOutput=75.0,
        tags=["reasoning", "coding", "recommended"],
        contextWindow=200000,
    ),
    ModelMeta(
        id="claude-sonnet-4-6",
        name="Claude Sonnet 4.6",
        provider="anthropic",
        category="Claude",
        tier=1,
        priceInput=3.0,
        priceOutput=15.0,
        tags=["fast", "coding", "recommended"],
        contextWindow=200000,
    ),
    ModelMeta(
        id="claude-haiku-4-5",
        name="Claude Haiku 4.5",
        provider="anthropic",
        category="Claude",
        tier=0,
        priceInput=0.25,
        priceOutput=1.25,
        tags=["fast"],
        contextWindow=200000,
    ),
    # OpenAI Series
    ModelMeta(
        id="gpt-4.1",
        name="GPT-4.1",
        provider="openai",
        category="OpenAI",
        tier=2,
        priceInput=30.0,
        priceOutput=60.0,
        tags=["reasoning", "coding"],
        contextWindow=128000,
    ),
    ModelMeta(
        id="gpt-4.1-mini",
        name="GPT-4.1 Mini",
        provider="openai",
        category="OpenAI",
        tier=1,
        priceInput=3.0,
        priceOutput=6.0,
        tags=["fast", "recommended"],
        contextWindow=128000,
    ),
    ModelMeta(
        id="gpt-4.1-nano",
        name="GPT-4.1 Nano",
        provider="openai",
        category="OpenAI",
        tier=0,
        priceInput=0.3,
        priceOutput=0.6,
        tags=["fast"],
        contextWindow=128000,
    ),
    ModelMeta(
        id="o3-mini",
        name="o3-mini",
        provider="openai",
        category="OpenAI",
        tier=1,
        priceInput=1.1,
        priceOutput=4.4,
        tags=["reasoning"],
        contextWindow=200000,
    ),
    # Google Series
    ModelMeta(
        id="gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        provider="google",
        category="Google",
        tier=2,
        priceInput=1.25,
        priceOutput=10.0,
        tags=["reasoning", "vision", "recommended"],
        contextWindow=1000000,
    ),
    ModelMeta(
        id="gemini-2.0-flash",
        name="Gemini 2.0 Flash",
        provider="google",
        category="Google",
        tier=0,
        priceInput=0.075,
        priceOutput=0.3,
        tags=["fast", "vision"],
        contextWindow=1000000,
    ),
    # DeepSeek
    ModelMeta(
        id="deepseek-r1",
        name="DeepSeek R1",
        provider="deepseek",
        category="DeepSeek",
        tier=1,
        priceInput=0.55,
        priceOutput=2.19,
        tags=["reasoning", "coding", "recommended"],
        contextWindow=64000,
    ),
    ModelMeta(
        id="deepseek-v3",
        name="DeepSeek V3",
        provider="deepseek",
        category="DeepSeek",
        tier=0,
        priceInput=0.14,
        priceOutput=0.28,
        tags=["fast", "coding"],
        contextWindow=64000,
    ),
    # 国产
    ModelMeta(
        id="qwen-plus",
        name="Qwen Plus",
        provider="moonshot",
        category="国产",
        tier=1,
        priceInput=0.8,
        priceOutput=2.0,
        tags=["coding", "recommended"],
        contextWindow=131072,
    ),
    ModelMeta(
        id="qwen-turbo",
        name="Qwen Turbo",
        provider="moonshot",
        category="国产",
        tier=0,
        priceInput=0.3,
        priceOutput=0.6,
        tags=["fast"],
        contextWindow=131072,
    ),
    ModelMeta(
        id="kimi-k2",
        name="Kimi K2",
        provider="moonshot",
        category="国产",
        tier=1,
        priceInput=2.0,
        priceOutput=8.0,
        tags=["coding"],
        contextWindow=256000,
    ),
]


MOCK_PRESETS: list[Preset] = [
    Preset(
        id="preset-coding",
        name="编程对决",
        models=["claude-sonnet-4-6", "gpt-4.1-mini", "deepseek-r1"],
        builtin=True,
        icon="code",
    ),
    Preset(
        id="preset-reasoning",
        name="深度推理",
        models=["claude-opus-4-6", "deepseek-r1", "gemini-2.5-pro"],
        builtin=True,
        icon="brain",
    ),
    Preset(
        id="preset-fast",
        name="快速响应",
        models=["gemini-2.0-flash", "qwen-turbo", "claude-haiku-4-5"],
        builtin=True,
        icon="zap",
    ),
    Preset(
        id="preset-balanced",
        name="均衡之选",
        models=["claude-sonnet-4-6", "gpt-4.1-mini", "gemini-2.5-pro"],
        builtin=True,
        icon="scale",
    ),
    Preset(
        id="preset-economy",
        name="经济实惠",
        models=["deepseek-v3", "qwen-turbo", "gemini-2.0-flash"],
        builtin=True,
        icon="wallet",
    ),
]


MOCK_PROVIDERS: list[ProviderConfig] = [
    ProviderConfig(
        id="anthropic",
        name="Anthropic",
        enabled=True,
        hasOAuth=True,
        hasApiKey=True,
        baseUrl="https://api.anthropic.com",
    ),
    ProviderConfig(
        id="openai",
        name="OpenAI",
        enabled=True,
        hasOAuth=False,
        hasApiKey=True,
        baseUrl="https://api.openai.com",
    ),
    ProviderConfig(
        id="google",
        name="Google",
        enabled=True,
        hasOAuth=True,
        hasApiKey=True,
        baseUrl="https://generativelanguage.googleapis.com",
    ),
    ProviderConfig(
        id="deepseek",
        name="DeepSeek",
        enabled=True,
        hasOAuth=False,
        hasApiKey=True,
        baseUrl="https://api.deepseek.com",
    ),
    ProviderConfig(
        id="moonshot",
        name="Moonshot",
        enabled=True,
        hasOAuth=False,
        hasApiKey=True,
        baseUrl="https://api.moonshot.cn",
    ),
]


MOCK_ACCOUNTS: list[AccountInfo] = [
    AccountInfo(
        id="anthropic-1",
        provider="anthropic",
        name="Claude Account",
        email="user@example.com",
        isActive=True,
    ),
]


MOCK_SESSIONS: list[dict] = [
    {
        "id": "sess-001",
        "mode": "chat",
        "title": "前端架构讨论",
        "models": ["claude-sonnet-4-6", "gpt-4.1-mini"],
        "createdAt": "2024-03-15T10:00:00Z",
        "updatedAt": "2024-03-15T10:30:00Z",
        "messageCount": 5,
    },
    {
        "id": "sess-002",
        "mode": "discuss",
        "title": "API 设计方案评审",
        "models": ["claude-opus-4-6", "deepseek-r1", "gemini-2.5-pro"],
        "createdAt": "2024-03-14T15:00:00Z",
        "updatedAt": "2024-03-14T16:00:00Z",
        "messageCount": 1,
    },
]
