# 前端说明（基金智能分析预测平台）

React 18 + TypeScript + Vite + TailwindCSS + ECharts，深色金融终端风格（红涨绿跌）。

## 运行

```bash
npm install
npm run dev      # http://localhost:5173（/api 自动代理到 http://localhost:8000）
npm run build    # 产物 dist/；后端启动后自动托管于 http://localhost:8000
```

演示账号：`demo / demo123456`（登录页已预填）。

## 页面

| 路由 | 说明 |
| --- | --- |
| `/login` | 登录 / 注册（JWT 存 localStorage） |
| `/` | Dashboard：市场指数条、市场状态卡、自选基金卡（AI 评分 + 迷你走势）、风险/趋势排名、重要新闻与政策、AI 每日总结 |
| `/funds` | 基金搜索 + 自选管理（分组/置顶/删除） |
| `/funds/:code` | 基金详情：K线/净值图（MA/MACD/RSI/BOLL、日周月、与基准指数对比 + Alpha/Beta/超额收益）、技术指标、风险指标、持仓与行业分布、AI 分析（评分雷达 + 预测概率 + 正负因子 + 风险）、相关新闻/政策、内嵌 AI 对话 |
| `/market` | 指数行情 + 指数K线 + 市场状态 |
| `/news` `/policy` | 新闻/政策列表（情绪徽章、行业筛选、详情弹窗） |
| `/analysis` | 多基金对比（评分/风险/趋势表格 + 雷达图叠加 + 因子明细） |
| `/chat` | AI 对话：左侧会话列表，顶部基金 chips（增删基金），助手消息可点「数据来源」查看注入的 Context 明细；`fallback=true` 时显示「量化引擎摘要」徽章 |
| `/reports` | 定时分析任务管理（daily/weekly/monthly/cron、渠道、立即运行）+ 报告 Markdown/HTML 查看 |
| `/settings` | LLM 设置（DeepSeek Key 状态与设置）、邮件通知、数据源与免责声明 |
| 顶栏铃铛 | 站内通知（未读数、已读操作） |

## 关键组件

- `components/KlineChart.tsx`：ECharts 蜡烛/净值主图 + MA 叠加 + 成交量 + MACD + RSI 副图，dataZoom、十字光标 tooltip、周期切换。
- `components/EChart.tsx`：ECharts 轻量 React 封装（深色主题、resize）。
- `components/Markdown.tsx`：markdown-it 渲染助手回复。
- `api/client.ts`：fetch 封装 + Authorization 头 + 401 跳登录；所有接口类型见 `types/api.ts`，与 `docs/api.md` 一一对应。
- `store/app.ts`（zustand）：auth 持久化、通知未读数、自选刷新。

## 与 API 契约的偏差

- 图表 K 线数据来自 `/funds/{code}/indicators`（序列字段 series）与 `/funds/{code}/history`；无偏差。
- 多选基金上限 10（契约一致）。
- 所有返回均按契约渲染「最新可用数据 / 盘中估值」状态徽章，未伪造实时。

## 构建注意事项

- `package.json` 中 `overrides.esbuild = "npm:esbuild-wasm@0.21.5"`：在受限沙箱（禁止子进程/管道）环境下
  使用 WASM 版 esbuild 仍可完成构建；普通环境无需改动。
- `base: './'`：产物可被后端任意路径静态托管。
