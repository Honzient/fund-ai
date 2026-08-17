# Future Improvements（未处理问题清单）

> 分阶段开发原则：发现的问题如不属于当前任务范围，一律记录于此，不顺手修改。
> 每个阶段开始时从中挑选下一阶段任务。

## 数据质量

- **10 年期国债收益率真实数据源**：东财数据中心无公开债券收益率报表（已探测 RPT_BOND_* 系列均不存在）；
  候选方案为中债登（chinabond）`yield.chinabond.com.cn/cbweb-mn/yc/downYearBzqx`（官方，返回 xlsx，
  需引入 openpyxl 依赖并实现解析；每日 17:30 发布当日曲线，`available_at`=数据日）。接入后补充
  `10年期国债收益率` 指标。
- **宏观指标扩展**：东财数据中心另有 PPI/M2/社融等报表（RPT_ECONOMY_* 系列），后续按需逐个接入，
  保持「一次 2~3 个指标」节奏。
- **eastmoney 持仓报告期失真**：`providers/eastmoney.py::get_holdings` 将 `report_date` 硬编码为
  `date(year, month, 28)`（请求年月），未解析接口返回的真实报告期与披露日（`REPORT_DATE`/`END_DATE`）。
  后果：`available_at` 近似基于失真的报告期。应在解析逻辑中提取真实报告期与公告日并填入
  `HoldingItem.available_at`（v0.3 已预留该字段）。
- **存量持仓行业标签**：`fund_holdings.industry` 由同步时 `industry_of(as_of=report_date)` 写入（v0.3 起），
  但 v0.3 之前同步的存量行仍带"当前行业"标签，未按历史有效行业重打。若 `SecurityIndustry` 出现带
  `valid_from/valid_to` 的记录，需回填重打存量标签。
- **NAV 当日可用性边界**：`FundDailyData.date` 为净值所属日，净值通常 T 日收盘后公布；
  预测时点使用 T 日 NAV 特征属轻微前瞻（行业普遍简化）。严格化需特征改用 T-1 日 NAV（影响全部技术特征，需谨慎评估）。
- **新闻/政策发布时间精度**：`published_at` 为抓取/入库近似时间，非真实发布分钟级时间；mock 数据源为生成时间。

## 模型与特征

- **基金规模历史序列**：无历史规模数据源（可评估接入 eastmoney 规模变动接口），
  当前历史训练样本 `fund_size` 诚实缺失（掩码标记），预测样本使用当前值。
- **行业序列历史覆盖**：mock/演示数据仅生成一期持仓，历史样本的行业类特征大多缺失；
  真实数据源应同步多期历史持仓（eastmoney `FundArchivesDatas.aspx` 支持按年月翻页）。

## 运维

- **Docker 实机验证**：沙箱内 Docker Desktop 引擎 DNS 异常无法运行容器；
  `docker compose config` 已验证通过，需在正常网络环境实机验证容器启动与健康检查。
