# 自定义数据源目录

将用户自定义数据（JSON 文件）放入本目录，系统会作为 `CustomDataProvider` 参与分析。
所有记录请标记 `"source": "custom"`（或由系统自动标记）。

## 支持的 JSON 结构（可拆分为多个文件，按 key 合并）

```json
{
  "funds": [
    {"fund_code": "999999", "fund_name": "示例基金", "fund_type": "混合型",
     "company": "示例公司", "manager": "示例经理", "benchmark": "沪深300",
     "establish_date": "2020-01-01"}
  ],
  "nav": [
    {"fund_code": "999999", "date": "2026-05-28", "nav": 1.234, "accumulated_nav": 1.5, "daily_return": 0.0012}
  ],
  "holdings": [
    {"fund_code": "999999", "report_date": "2026-03-31", "stock_code": "600519",
     "stock_name": "贵州茅台", "weight": 8.5, "industry": "食品饮料"}
  ],
  "indexes": [
    {"index_code": "MYINDEX", "date": "2026-05-28", "open": 100, "high": 102, "low": 99, "close": 101.5}
  ],
  "macro": [
    {"indicator": "自定义指标", "value": 1.5, "unit": "%", "period": "2026-05", "published_at": "2026-06-15"}
  ],
  "news": [
    {"title": "示例新闻", "content": "内容", "source": "custom", "url": "",
     "published_at": "2026-06-15T10:00:00", "related_industry": "新能源",
     "sentiment": 0.5, "importance": 0.7}
  ],
  "policies": [
    {"title": "示例政策", "content": "内容", "source": "custom", "url": "",
     "published_at": "2026-06-15T10:00:00", "department": "示例部门",
     "policy_type": "产业政策", "related_industry": "半导体",
     "sentiment": 0.6, "impact_score": 0.7, "importance": 0.8}
  ]
}
```
