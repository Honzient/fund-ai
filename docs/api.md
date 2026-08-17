# API 契约（Frontend 依据本文档开发）

Base URL（开发）：`http://localhost:8000/api`（Vite dev 代理 `/api` → `http://localhost:8000`）
认证：`Authorization: Bearer <JWT>`（除 `/auth/*`、`/health` 外均需认证）。
演示账号：`demo / demo123456`（后端自动创建，登录页预填）。
错误格式：`{"detail": "..."}`。时间格式：ISO 8601（日期 `YYYY-MM-DD`）。

## 0. 通用

### GET /health
```json
{"status":"ok","db":"ok","llm":"missing|configured","data_provider":"eastmoney|mock","time":"..."}
```

## 1. 认证

### POST /auth/login  {username, password} → `{access_token, user}`
### POST /auth/register {username, password, email?} → `{access_token, user}`
### GET /auth/me → `{id, username, email, display_name, created_at}`

## 2. 基金

### GET /funds?search=&fund_type=&limit=100
```json
[{
  "id":1,"fund_code":"110022","fund_name":"易方达消费行业股票","fund_type":"股票型",
  "company":"易方达基金","latest_nav":3.42,"latest_nav_date":"2026-05-29",
  "estimate_nav":null,"estimate_return":null,
  "return_1d":-0.12,"return_5d":0.85,"return_20d":1.2,"return_60d":3.4,"return_1y":12.5,"return_ytd":4.2,
  "score":72,"risk_level":"中高","source":"mock","retrieved_at":"...","data_status":"latest_available"
}]
```
说明：`data_status` 为 `latest_available`（最新可用净值）或 `estimate`（盘中估值）。
`estimate_nav/estimate_return` 仅盘中估值时存在；无真实时数据时前端必须展示「最新可用数据」。

### GET /funds/{code} → 详情（在列表字段基础上增加）
```json
{
  "...FundSummary 全部字段...",
  "manager":"萧楠","establish_date":"2010-08-20","benchmark":"中证主要消费指数",
  "fund_size":150.2,
  "fees":{"management_fee":1.2,"purchase_fee":0.15,"redemption_fee":0.5},
  "ai_score":72,
  "trend":{"short":"偏多","medium":"中性","long":"中性"},
  "predictions":{"short":{...见预测...},"medium":{...},"long":{...}},
  "latest_nav_date":"2026-05-29","data_time":"2026-05-29 15:00","data_status":"latest_available"
}
```

### GET /funds/{code}/history?start=&end=&period=daily|weekly|monthly
```json
{"fund":{"fund_code":"110022","fund_name":"易方达消费行业股票"},
 "items":[{"date":"2026-05-28","nav":3.41,"accumulated_nav":4.12,"daily_return":0.3,"volume":123456,"source":"mock"}],
 "count":250,"period":"daily","data_status":"latest_available"}
```

### GET /funds/{code}/holdings
```json
{"fund_code":"110022","report_date":"2026-03-31",
 "top10":[{"stock_code":"600519","stock_name":"贵州茅台","weight":9.8,"industry":"食品饮料","market_value":15.2,"source":"mock"}],
 "industry_distribution":[{"industry":"食品饮料","weight":42.5}],
 "concentration":{"top10":68.4,"hhi":0.18},"source":"mock","retrieved_at":"..."}
```

### GET /funds/{code}/indicators → `{fund_code, date, computed_at, indicators:{ma5,ma10,ma20,ma60,ema12,ema26,macd,macd_signal,macd_hist,rsi14,bb_upper,bb_mid,bb_lower,atr14,momentum_5d,momentum_20d,momentum_60d,...}}`

### GET /funds/{code}/risk → `{fund_code, period, computed_at, metrics:{annual_return,annual_volatility,downside_volatility,max_drawdown,sharpe,sortino,calmar,var_95,cvar_95,beta,alpha,information_ratio,best_day,worst_day}}`

### GET /funds/{code}/analysis
```json
{"fund":{"fund_code":"110022","fund_name":"易方达消费行业股票"},
 "time_range":"3M","computed_at":"...",
 "score":72,
 "score_breakdown":{"trend":78,"volatility":55,"risk":60,"quality":70,"macro":65,"industry":80,"sentiment":68},
 "regime":{"short":"偏多","medium":"中性","long":"中性"},
 "trend":{"short":"偏多","medium":"中性","long":"中性"},
 "positive_factors":[{"factor":"20日动量改善","reason":"20日收益 +3.2%，位于历史60%分位","evidence":"momentum_20d=3.2","value":78}],
 "negative_factors":[{"factor":"波动率上升","reason":"20日波动率 22%，高于同类中位数","evidence":"vol_20=0.22","value":45}],
 "main_risks":[{"category":"宏观风险","detail":"CPI 连续上行，货币政策不确定性上升","severity":"medium"}],
 "data_sources":[{"name":"净值历史","source":"mock","retrieved_at":"..."}],
 "data_status":"latest_available"}
```

### GET /funds/{code}/prediction?horizon=short|medium|long
```json
{"fund_code":"110022","model_version":"v0.1","horizon":"short","horizon_days":5,
 "generated_at":"...","data_as_of":"2026-05-29",
 "probabilities":{"up":58.0,"range":27.0,"down":15.0},
 "direction":"偏多","confidence":"medium","confidence_score":0.62,
 "score":72,
 "feature_importance":[{"feature":"momentum_20d","importance":0.21}],
 "factors":{"positive":[{"factor":"...","reason":"..."}],"negative":[...],"risks":[{"category":"...","detail":"...","severity":"..."}]},
 "disclaimer":"历史回测不代表未来表现；本结果仅为概率估计，不构成投资建议。"}
```

### POST /funds/{code}/sync → `{task_id, status:"started"}`

## 3. 自选

### GET /watchlist?group= → `[{id, fund:{FundSummary}, group_name, pinned, added_at}]`
### POST /watchlist {fund_code, group_name?, pinned?} → 上述元素
### PATCH /watchlist/{id} {group_name?, pinned?}
### DELETE /watchlist/{id}
### GET /watchlist/groups → `["默认","核心基金","科技"]`

## 4. 市场

### GET /market/indexes → `[{id, index_code, index_name, market, latest_close, change, change_pct, data_time, source, data_status}]`
### GET /market/indexes/{code}/history?start=&end=&period= → `{index:{...}, items:[{date,open,high,low,close,volume,change_pct}], count, data_status}`
### GET /market/overview →
```json
{"indices":[{index_code,index_name,change_pct,...}],
 "market_regime":{"label":"中性偏多","score":62,"drivers":["沪深300 20日动量转正","两融余额回升"]},
 "generated_at":"..."}
```
### POST /market/sync → `{task_id, status}`

## 5. 宏观

### GET /macro?indicator= → `{items:[{id,indicator,value,unit,period,change,source,published_at}], indicators:["CPI","PMI",...]}`

## 6. 新闻

### GET /news?limit=50&industry=&related_fund=&min_importance=
```json
{"items":[{"id":1,"title":"...","content":"...","source":"...","url":"...","published_at":"...",
  "related_fund":null,"related_industry":"新能源","sentiment":0.6,"sentiment_label":"positive",
  "importance":0.8,"retrieved_at":"..."}]}
```
sentiment_label: positive / negative / neutral。
### GET /news/{id} → 单条详情（同结构）
### POST /news/sync → `{task_id, status}`

## 7. 政策

### GET /policies?limit=&industry= → `{items:[{id,title,content,source,url,published_at,department,policy_type,related_industry,sentiment,impact_score,importance,retrieved_at}]}`
### GET /policies/{id}
### POST /policies/sync → `{task_id, status}`

## 8. 多基金分析

### POST /analysis {fund_ids:["110022","005827"], time_range:"3M"}
```json
{"generated_at":"...","funds":[ {fund 的 /analysis 结构}, ... ],
 "comparison":{
   "table":[{"fund_code","fund_name","score","sharpe","max_drawdown","annual_volatility","return_1m","return_3m","trend_short","trend_medium","trend_long"}],
   "best_trend":"110022","lowest_risk":"005827","highest_score":"110022"},
 "market":{"market_regime":{...}}}
```

## 9. 预测模型（v0.2 更新）

### GET /funds/{code}/prediction?horizon=short|medium|long（响应结构升级）
```json
{
  "fund_code":"110022","horizon":"short","horizon_days":5,"generated_at":"...",
  "data_as_of":"2026-08-14",
  "model_name":"random_forest","model_version":"v1.0","champion":true,
  "raw_probabilities":{"up":58.0,"range":27.0,"down":15.0},
  "calibrated_probabilities":{"up":55.2,"range":29.1,"down":15.7},
  "probabilities":{"up":55.2,"range":29.1,"down":15.7},
  "calibration_method":"isotonic","calibrated":true,
  "predicted_class":"up","direction":"偏多",
  "confidence":"medium","confidence_score":0.52,
  "feature_importance":[{"feature":"ret_20","importance":0.21}],
  "feature_snapshot":{"fund_code":"110022","as_of":"...","technical":{"rsi14":{"value":58.2,"quality":"high"}}},
  "market_snapshot":{"regime":{"label":"中性","score":52},"breadth":60},
  "note":null,
  "disclaimer":"历史回测不代表未来表现；本结果仅为基于历史数据的概率估计与情景分析，不构成投资建议，不承诺任何收益。"
}
```
- `probabilities` = 校准后概率（前端展示用）；`raw_probabilities` = 模型原始输出；
- `calibration_method`: isotonic | sigmoid | uncalibrated（样本不足自动降级）；
- 模型未就绪/数据不足时：`model_version="baseline"` + `note` 说明原因。

### GET /prediction/models → 注册表元数据（含 champion/status/metrics/baseline_comparison/calibration_method）
### POST /prediction/retrain?horizon= → `{task_id, status}`（后台执行，不阻塞）
### POST /prediction/backtest（body: `{"horizon":"short","model_name":null}`）→ `{task_id, status}`（后台执行）
### GET /prediction/backtest/result/{task_id} → `{status: pending|running|success|failed, result, error}`
回测结果结构：
```json
{"version":"latest","available":true,"horizon":"short","horizon_days":5,
 "samples":420,"retrains":7,
 "metrics":{"accuracy":0.52,"balanced_accuracy":0.51,"brier_score":0.86,"log_loss":0.99,
            "ece":0.08,"hit_rate":0.52,"model_score":48.2,"up_precision":0.5},
 "baselines":{"momentum":{"accuracy":0.55,"model_score":50.1},
              "majority":{},"random":{},"simple_trend":{},"always_up":{}},
 "note":"Walk-Forward 滚动回测（Purged 窗口，按时间顺序训练与预测）","disclaimer":"..."}
```

### GET /prediction/health?horizon=
```json
{"short":{
  "horizon":"short",
  "champion":{"model_name":"random_forest","version":"v1.0","trained_at":"...","training_end":"...",
              "calibration_method":"isotonic","model_score":48.2,
              "metrics":{"brier_score":0.86,"log_loss":0.99,"balanced_accuracy":0.51,"ece":0.08,"hit_rate":0.52},
              "validation":"PurgedTimeSeriesSplit(embargo=5, purge=4, folds=4)",
              "baseline_comparison":{"momentum":{"model_score":50.1,"balanced_accuracy":0.5}}},
  "ledger":{"last_30":{"count":12,"hit_rate":58.3,"directional_hit_rate":60.0},
            "last_100":{},"all":{}},
  "status":"healthy|warning|degraded|no_model|insufficient_data",
  "note":"近30次预测表现与验证期一致",
  "retrain_recommended":false,
  "generated_at":"..."}, "medium":{},"long":{}}
```

### GET /prediction/ledger?fund_code=&limit=
```json
{"records":[{"id":1,"fund_id":2,"prediction_date":"2026-08-14","horizon":"short","horizon_days":5,
  "model_name":"random_forest","model_version":"v1.0","calibrated":true,"calibration_method":"isotonic",
  "raw_probabilities":{"up":58.0},"calibrated_probabilities":{},
  "predicted_class":"up","confidence":"medium","confidence_score":0.52,
  "data_as_of":"2026-08-14",
  "actual_return":0.42,"actual_class":"up","evaluated_at":"..."}],
 "stats":{"overall":{"last_30":{"count":12,"hit_rate":58.3,"directional_hit_rate":60.0},
                     "last_100":{},"all":{}},
          "by_model":{"random_forest v1.0":{}}}}
```
- `actual_return/actual_class/evaluated_at` 为 null 表示尚未评价（等待未来数据）。
### POST /prediction/evaluate → `{task_id, status}`（后台评价待定预测）

## 9.1 前端新增（v0.2）
- `/models`：模型健康页（导航「模型健康」）——三周期 Champion、指标卡（Brier/LogLoss/BalancedAcc/ECE/HitRate）、
  基线对比表、台账命中率（近30/100/全部）、状态徽章（healthy/warning/degraded/no_model/insufficient_data）、
  重训按钮（POST /prediction/retrain）、版本列表（GET /prediction/models）、回测按钮（POST /prediction/backtest + 轮询 result）。
- 基金详情新增「预测历史」Tab：GET /prediction/ledger?fund_code={code} → 表格
  （日期 / 周期 / 预测类别 / 校准概率 / 置信度 / 实际结果 / 命中 ✓✗）。
- 基金详情「AI分析」Tab：概率显示校准后值，附加校准方法徽章 + raw vs calibrated 对比（小字），
  `note` 非空时显示「统计基线」提示条。

## 10. AI 对话（自动 Context 注入）

### POST /chat {message, fund_ids:["110022"], conversation_id?}
→ `{conversation_id:"uuid", reply:"...", model:"deepseek-chat|rule-engine", fallback:true|false, sources:{...}}`
- 请求只发用户消息与基金代码，后端自动注入 Context（用户无需粘贴基金资料）。
- `fallback:true` 表示 LLM 不可用、由量化引擎生成结构化摘要。
- `sources`: `{funds:[{fund_code,fund_name}], market:true, macro:true, news_count:3, policies_count:2, prediction:true, data_as_of:"...", retrieved_at:"...", context_version:1}`

### GET /chat/conversations → `[{id,title,created_at,updated_at,last_message}]`
### POST /chat/conversations {title?} → `{id,title,...}`
### GET /chat/conversations/{id} → `{id,title,messages:[{role:"user"|"assistant",content,created_at,model}],fund_codes:["110022"]}`
### DELETE /chat/conversations/{id}
### GET /chat/conversations/{id}/sources → 最近一次交换的数据来源明细（含各数据模块更新时间与来源，用于「查看本次分析数据来源」按钮）

## 11. 定时分析

### GET /schedules →
`[{id,name,schedule_type:"daily"|"weekly"|"monthly"|"cron",cron_expression,time_of_day,day_of_week,day_of_month,fund_ids:[...],enabled,notification_channels:["in_app","email"],llm_summary,last_run_at,next_run_at,created_at}]`
### POST /schedules {name, schedule_type, time_of_day:"16:00", day_of_week?, day_of_month?, cron_expression?, fund_ids:[], enabled, notification_channels:[], llm_summary:true}
### PATCH /schedules/{id}（同上字段，可部分）
### DELETE /schedules/{id}
### POST /schedules/{id}/run → `{task_id, status}`

## 12. 报告

### GET /reports → `[{id,title,generated_at,trigger:"manual"|"scheduled",task_id}]`
### GET /reports/{id} → `{..., content_md, content_html}`
### POST /reports/generate → `{task_id, status}`

## 13. 通知

### GET /notifications?unread_only=true → `[{id,title,content,type:"analysis"|"report"|"system",read,created_at}]`
### POST /notifications/{id}/read、POST /notifications/read-all

## 14. 任务

### GET /tasks?limit=50 → `[{id,name,status:"pending|running|success|failed",started_at,finished_at,error,retries,result}]`

## 15. 设置

### GET /settings →
```json
{"llm":{"provider":"deepseek","model":"deepseek-chat","base_url":"https://api.deepseek.com",
        "has_api_key_env":true,"has_user_key":false},
 "notifications":{"email_enabled":false,"email_to":"","channels":["in_app"]},
 "sync":{"quote_interval_minutes":5},"timezone":"Asia/Shanghai"}
```
### PUT /settings {llm?, notifications?, sync?}（仅非敏感字段）
### POST /settings/keys {deepseek_api_key} → 后端加密保存（永不回显）
### DELETE /settings/keys/deepseek

## 16. 首页 AI 总结

### GET /summary/daily →
```json
{"generated_at":"...",
 "market":{"label":"中性偏多","score":62},
 "drivers":["...","..."],
 "watchlist":{"best":{"fund_code","fund_name","return_1d"},"worst":{...},"riskiest":{...},"focus":[codes]},
 "text":"今日市场 AI 总结...（Markdown）","fallback":false}
```

## 17. 演示数据

后端首次启动自动建库并注入：约 10 只基金（真实代码，含股票/混合/指数/债券/QDII 型）、
3 年日频净值、持仓、8 个指数、2 年宏观数据、新闻、政策、演示用户 demo。
当 Eastmoney 数据源可用时自动同步真实数据并合并；不可用时全部显示 `source:"mock"` 与
「最新可用数据」状态，前端必须能完整展示演示数据。
