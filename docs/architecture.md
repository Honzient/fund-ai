# 基金智能分析预测平台 — 架构设计

> 投资研究与辅助分析工具。所有预测输出均为概率、评分、置信度与情景分析，不构成投资建议，
> 不承诺收益，不宣称能够准确预测市场。

## 1. 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11+ / FastAPI / Pydantic v2 / SQLAlchemy 2 / APScheduler |
| 数据/量化 | pandas / numpy / scikit-learn / scipy / httpx |
| LLM | DeepSeek（OpenAI 兼容接口），Provider 可扩展 |
| 数据库 | SQLite（开发默认）/ PostgreSQL（生产，Docker） |
| 缓存 | 本地 TTL 缓存（默认）/ Redis（可选） |
| 前端 | React 18 + TypeScript + Vite + TailwindCSS + ECharts |
| 部署 | Docker Compose（frontend / backend / postgres / redis） |

## 2. 总体架构

```
Frontend (React/Vite/ECharts)
        │  REST /api/*
        ▼
FastAPI Backend
├── api/          路由层（认证、基金、自选、行情、分析、预测、聊天、调度、报告、通知、任务）
├── services/     业务编排（FundService / AnalysisService / PredictionService / ChatService / SyncService）
├── providers/    数据源层（Provider 接口 + 注册表 + fallback + 限流/重试/缓存）
├── analytics/    量化引擎（技术指标 / 风险指标 / 多因子评分 / 情绪）
├── prediction/   预测引擎（特征工程 / 模型层 / 时间序列验证 / 回测 / 模型注册表）
├── llm/          LLMProvider 接口 + DeepSeekProvider + ContextBuilder + PromptBuilder
├── scheduler/    APScheduler 定时任务（数据同步 / 定时分析 / 报告）
├── notification/ 通知渠道（站内 / Email，Provider 可扩展）
├── tasks/        任务管理器（状态、重试、错误记录）
├── models/       SQLAlchemy 模型
└── core/         配置 / 日志 / 安全（JWT、加密存储）
```

## 3. 数据源抽象

所有外部数据必须经过 `DataProvider` 接口，通过 `ProviderRegistry` 按优先级调用，
失败自动 fallback，绝不将任何单一网站写死为唯一数据源：

```
DataProvider (ABC)
├── EastmoneyProvider    # 天天基金公开接口：搜索/净值/估值/持仓 + 东财指数K线
├── MockProvider         # 离线演示数据（确定性随机生成，source="mock"）
└── CustomDataProvider   # 用户自定义 JSON/CSV（data/custom/）
```

每个 Provider 适配层统一处理：超时、重试（指数退避）、限流、数据缺失、去重。
系统级再叠加 TTL 缓存与增量同步（只拉取缺失日期区间）。

## 4. 数据库实体（核心）

Fund、FundDailyData、FundHolding、MarketIndex、MarketIndexData、MacroData、
News、Policy、User、Watchlist、ScheduledAnalysis、Conversation、Message、
Notification、TaskRun、AnalysisSnapshot、UserSetting、Report。

所有外部数据行保留 `source` / `retrieved_at`（/ `published_at`）用于数据来源透明。

## 5. 量化分析引擎

多因子评分（0–100）+ 趋势/风险/质量/宏观/行业/情绪 7 个维度：

- 趋势：MA/EMA/MACD/RSI/动量（短/中/长）
- 波动：历史波动率 / ATR / 下行波动率
- 风险：最大回撤 / Sharpe / Sortino / Calmar / VaR / CVaR / Beta / Alpha
- 质量：规模 / 成立年限 / 持仓集中度 / 行业集中度
- 宏观：PMI / CPI / PPI / M2 / 利率 / 汇率 / 国债收益率
- 行业：行业动量 / 政策与新闻情绪
- 情绪：市场广度 / 新闻情绪 / 政策影响

每个结论附带 evidence（可追溯到原始数据）。

## 6. 预测引擎

- 输出：未来 N 日 上涨/震荡/下跌 概率 + 置信度 + 特征重要性 + 正负因子，绝不输出确定涨跌。
- 周期：短期 5 日 / 中期 20 日 / 长期 60 日。
- 模型层：Logistic Regression / Random Forest（可扩展 XGBoost/LightGBM）。
- 验证：TimeSeriesSplit / Walk-Forward，禁止随机切分时间序列，严格避免未来数据泄露。
- 回测：方向准确率、各类别识别率、平均收益、最大回撤（附“历史回测不代表未来表现”声明）。
- 模型注册表：`storage/models/v{version}.joblib + meta.json`，重新训练不覆盖历史结果。
- 数据不足或训练失败时降级为「统计基线引擎」（历史条件分布），置信度封顶为 Low/Medium。

## 7. LLM 与自动 Context 注入

```
用户消息 + fund_ids
   │
   ▼
ContextBuilder.build(fund_ids) ──→ 基金画像/行情/技术指标/风险/持仓/宏观/新闻/政策/预测
   │
   ▼
PromptBuilder ──→ System(行为规范 + Context) + History + User Message
   │
   ▼
DeepSeekProvider（超时/重试/降级）
   │
   ▼
回复 + 数据来源快照（可点击查看，保证透明）
```

- LLM 不可用时自动降级为量化引擎结构化摘要，软件其余功能不受影响。
- 系统提示强制：明确数据时间、区分事实与推断、给出风险与情景、禁止编造数据/新闻/政策、
  禁止宣称能准确预测市场。
- API Key 仅存后端（环境变量，用户自定义 Key 经 Fernet 加密存储），前端永远不可见。

## 8. 调度与通知

- APScheduler：行情快照（可配，默认 5 分钟）、每日数据同步、用户定时分析任务（cron）。
- 任务流水：TaskRun 记录状态/起止时间/错误/重试次数。
- 通知渠道：站内通知 + Email（SMTP），`NotificationProvider` 接口可扩展
  Telegram/Discord/企业微信/钉钉/飞书。

## 9. 目录结构

```
fund/
├── frontend/            # React + TS + Vite
├── backend/
│   ├── app/
│   │   ├── api/ core/ db/ models/ schemas/ services/
│   │   ├── providers/ analytics/ prediction/ llm/
│   │   ├── scheduler/ notification/ tasks/ cache/ data/ utils/
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
├── docs/
├── scripts/
├── docker-compose.yml
├── .env.example
└── README.md
```

## 10. 安全

JWT 认证、PBKDF2 密码哈希、Fernet 加密存储用户 Key、用户数据隔离（自选/对话/任务/设置
均按 user_id 过滤）、SQLAlchemy 参数化查询防注入、Pydantic 输入校验、CORS 白名单、
日志脱敏（绝不记录 API Key / 密码）。
