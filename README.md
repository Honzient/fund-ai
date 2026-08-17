# 基金智能分析预测平台（Fund AI）

面向个人投资研究的智能基金分析平台：把**基金行情 / 净值 / 持仓 / 市场指数 / 宏观经济 / 新闻 / 政策 / 用户自定义数据**与
**量化分析引擎 / 概率预测模型 / DeepSeek 大模型**统一起来，对自选基金进行数据驱动的分析、风险评估、趋势判断与辅助决策。

> **免责声明**：本软件属于投资研究与辅助分析工具。所有预测均输出为概率、评分、置信度与情景分析，
> **不能也不承诺准确预测涨跌或收益**，不构成投资建议。历史回测不代表未来表现。

## ✨ 核心功能

| 模块 | 说明 |
| --- | --- |
| 基金搜索 / 自选 | 按代码或名称搜索，加入自选，分组（核心基金/科技/新能源…）、置顶、删除 |
| 行情与图表 | 最新净值 / 盘中估值（明确标注「最新可用数据」，绝不伪装实时）、交互式净值走势图（MA/MACD/RSI/BOLL、日/周/月、基准对比） |
| 量化分析 | 7 维多因子评分 0-100 分，正面/负面因素均可点击查看原始数据 |
| 风险指标 | 最大回撤、Sharpe、Sortino、Calmar、VaR/CVaR、Beta、Alpha；基金 vs 基准超额收益与相对强弱 |
| **概率预测（v0.2 重构）** | 未来 5/20/60 日 上涨/震荡/下跌概率；**Purged Walk-Forward（embargo+purge，无标签重叠泄露）**；**概率校准**（isotonic/sigmoid，样本不足自动 uncalibrated 并标注）；**完整指标**（Accuracy/BalancedAcc/F1/ROC-AUC/LogLoss/Brier/ECE/HitRate/平均前向收益）；**Baseline 对比**（momentum/majority/random/simple_trend/always_up）；**Prediction Ledger 预测台账**（每次预测持久化 + 事后自动评价 → 真实命中率）；**模型注册表 + Champion 机制**（语义版本、数据集/特征/校准版本、状态，重训不覆盖历史） |
| **模型健康页** | Champion 信息、验证指标、基线对比、台账近 30/100 次真实命中率、healthy/warning/degraded 状态、手动重训与回测 |
| AI 对话 | DeepSeek 对话；**自动注入基金 Context**（领域 Provider 组装 + context_hash 指纹）；多基金对比问答；「查看本次分析数据来源」保证透明；**外部数据（新闻/政策）XML 隔离防注入**；**LLM 不得修改量化数字** |
| 新闻 / 政策 / 宏观 | 去重、情绪、行业映射、重要性评分；**数据质量（high/medium/low）+ as_of 溯源 + 陈旧检测** |
| 定时分析 | cron 定时分析 → Markdown/HTML 报告 → 站内通知 + Email；长任务后台线程池执行，不阻塞 API |
| 数据来源 | 统一 `DataProvider` 接口 + 领域拆分（Fund/Market/Mock/Custom）；缓存 + 增量同步 + 重试 + 限流 + 自动降级；**行业分类表（SecurityIndustry，可扩展申万/中信/GICS，未知标注 unknown）** |

## 数据与预测的可信边界（重要）

- **真实数据源**：天天基金/东方财富公开接口（基金搜索、净值历史、盘中估值、持仓、指数K线/快照，无需 Key）。
  新闻/政策/宏观当前为**演示数据（Mock）**，可经 `backend/data/custom/*.json` 导入真实数据或扩展新 Provider。
- **不是真实数据的地方会明确标注**：所有 Mock 数据 `source="mock"`，界面显示「最新可用数据」。
- **缺失数据不会被填成 0**：特征层用 NaN + 缺失掩码；宏观/新闻/政策缺失时模型与 LLM 都被告知「数据缺失」并降低置信度。
- **模型表现诚实展示**：Champion 由 Brier/LogLoss/BalancedAcc/HitRate/ECE 综合评分选出（非只看 Accuracy）；
  若模型不如 momentum 基线，健康页会如实显示；近 30 次命中率显著低于验证期 → 状态 degraded 并建议重训。
- 审计与设计文档：`docs/audit-v0.2.md`、`docs/architecture.md`、`docs/api.md`。

## 🚀 快速开始

### 方式一：本地开发（推荐先跑通）

**后端**（Python 3.11+）：

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy ..\.env.example .env            # Linux/macOS: cp ../.env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

首次启动自动：建库（SQLite `backend/fund.db`）→ 注入演示数据（10 只基金、3 年日净值、8 指数、宏观/新闻/政策）
→ 创建演示账号 `demo / demo123456` → 启动调度器。联网时 Eastmoney 数据源自动生效（优先级 `eastmoney,mock`）。

**前端**：

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 （/api 已代理到 8000）
```

打开 http://localhost:5173 ，用 `demo / demo123456` 登录。

> 若已执行 `npm run build`（生成 `frontend/dist`），后端会直接托管前端，
> 访问 http://localhost:8000 即可，无需单独启动前端。

### 方式二：Docker Compose（生产形态）

```bash
copy .env.example .env     # 按需填写 DEEPSEEK_API_KEY / SMTP_* / SECRET_KEY
docker compose up -d
# 前端: http://localhost:8080   后端 API 文档: http://localhost:8000/docs
```

### 启用 DeepSeek 对话

1. 在 https://platform.deepseek.com 申请 API Key；
2. 写入 `backend/.env` 的 `DEEPSEEK_API_KEY=`（或 docker-compose 环境变量）；
3. 或在应用内「设置 → LLM 设置」填写用户级 Key（后端 Fernet 加密存储，永不回显）。

未配置 Key 时聊天自动降级为**量化引擎结构化摘要**（标注「LLM 服务当前不可用」），其余功能不受影响。

## 📦 数据源与限制（重要）

| Provider | 数据 | 来源 | 限制 |
| --- | --- | --- | --- |
| `eastmoney` | 基金搜索/净值历史/元数据/盘中估值/持仓/指数K线与快照 | 天天基金、东方财富公开接口（无需 Key） | 第三方公开接口，随时可能调整；盘中估值仅交易时段返回；个股行业映射内置约 60 只常见股票，其余标注「其他」 |
| `mock` | 全部演示数据 | 内置确定性生成 | `source="mock"`，仅用于离线演示与测试，界面显示「最新可用数据」 |
| `custom` | 用户自定义 JSON | `backend/data/custom/*.json`（见目录内 README） | 用户自备 |

- 实时性说明：基金净值为 T 日盘后更新，盘中为**估值**（前端明确展示「盘中估值/最新可用数据」与数据时间，不伪装实时）。
- 新闻/政策/宏观默认使用演示数据（`mock`）。Eastmoney 新闻接口不稳定，未纳入第一版；如需真实新闻/宏观，
  请扩展新 Provider（见下），或通过 `custom` 目录导入。
- 每个外部调用均有：超时 → 重试（指数退避）→ 限流 → 降级到下一数据源；全部失败时核心功能仍可用（演示数据）。

## 🧩 架构

```
frontend (React + TS + Vite + Tailwind + ECharts)
    │ REST /api/*
    ▼
backend (FastAPI)
├── providers/   DataProvider 接口 + Eastmoney/Mock/Custom + 注册表（fallback/缓存/限流/重试）
├── analytics/   技术指标 / 风险指标 / 多因子评分 / 情绪词典
├── prediction/  特征工程（无未来数据）/ 模型层 / 模型注册表 / Walk-Forward 回测
├── llm/         DeepSeekProvider + ContextBuilder + PromptBuilder（自动 Context 注入）
├── scheduler/   APScheduler（行情刷新/每日同步/用户定时分析）
├── notification/ 站内 + Email（可扩展 Telegram/钉钉/飞书…）
├── tasks/       任务流水（状态/重试/错误记录）
└── api/         REST 路由（JWT 认证、用户数据隔离）
```

详见 `docs/architecture.md`（架构设计）与 `docs/api.md`（完整 API 契约）。

## 📦 打包为可安装 EXE（Windows）

一键脚本（自动：装依赖 → 构建前端 → PyInstaller 打包 → Inno Setup 封装安装器）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

产物在 `dist_exe/`：

| 文件 | 说明 |
| --- | --- |
| `FundAI/` | 绿色版（免安装，整个文件夹拷走即可，双击 `FundAI.exe`） |
| `FundAI-Setup-0.1.0.exe` | 安装器：开始菜单/桌面快捷方式、卸载程序，**无需管理员权限** |

桌面版特性（**原生客户端软件**）：

- 双击启动后直接弹出**独立客户端窗口**（WebView2 渲染，非浏览器）：自己的标题栏/任务栏图标，
  无地址栏、无命令行窗口、不依赖任何浏览器；
- 窗口即服务：后端进程内运行、仅绑定 127.0.0.1；**关闭窗口即退出**；
- 数据库/日志/模型保存在 `%LOCALAPPDATA%\FundAI`，卸载不影响其他程序；
- 首次启动需 10–20 秒初始化演示数据，之后秒开；离线可用（内置演示数据），联网自动同步真实数据；
- 若系统缺少 WebView2 运行库（Windows 10/11 默认自带），自动回退浏览器模式并提示；
- 安装器含开始菜单/桌面快捷方式与完整卸载；手工打包：
  `cd backend && .venv\Scripts\python -m PyInstaller fund_ai.spec --noconfirm`，
  再 `ISCC.exe installer\fund_ai.iss`（需安装 Inno Setup 6）。
- 开发者调试可加环境变量 `FUNDAI_OPEN_BROWSER=1` 切回浏览器模式。

> 注意：PyInstaller 产物可能被个别杀毒软件误报（无数字签名），企业分发建议做代码签名。

## 🧪 测试

```bash
cd backend
.venv\Scripts\python -m pytest tests -v
```

81 个用例，覆盖：技术/风险/多因子指标、**特征无未来数据泄露**、**Purged 切分（embargo+purge 无标签重叠）**、
**概率校准（含样本不足降级）**、**Baseline 对比**、**Prediction Ledger（记录/去重/评价/统计）**、
**模型注册表（语义版本/不覆盖/Champion 迁移/校准器同版本）**、**缺失特征掩码**、**数据溯源与陈旧检测**、
**未知行业分类**、Provider fallback、**LLM 注入隔离/密钥轮换失效/context_hash/日志脱敏**、
**跨用户数据隔离/无效 JWT**、API 集成全链路。

## 🔌 扩展新数据源 / 新 LLM

- 新数据源：实现 `app/providers/base.py::DataProvider`，在 `DATA_PROVIDER_ORDER` 中追加名称 —— 无需改动其他代码。
- 新 LLM：实现 `app/llm/base.py::LLMProvider`，注册到 `app/llm/manager.py::PROVIDER_CLASSES`。
- 新通知渠道：实现 `app/notification/base.py::NotificationProvider`，注册到 `NotificationManager._providers`。
- 新资产类型（股票/ETF/黄金/加密…）：底层已预留 `AssetType` 抽象，`DataProvider` 按资产扩展即可。

## ⚠️ 安全说明

- API Key 只存后端（环境变量 / Fernet 加密的用户设置），前端永远不可见；
- JWT 认证 + PBKDF2 密码哈希；自选/对话/任务/设置/通知均按用户隔离；
- SQLAlchemy 参数化查询防注入、Pydantic 输入校验、CORS 白名单、日志脱敏（绝不记录 Key/密码）；
- 生产部署务必修改 `SECRET_KEY` 与演示账号密码。

## 📂 目录

```
fund/
├── backend/            FastAPI 后端（app/ + tests/ + requirements.txt + Dockerfile）
├── frontend/           React 前端（src/ + Dockerfile + nginx.conf）
├── docs/               architecture.md / api.md
├── scripts/            开发辅助脚本
├── docker-compose.yml  postgres + redis + backend + frontend
├── .env.example
└── README.md
```
