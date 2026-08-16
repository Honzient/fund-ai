/**
 * API 类型定义 —— 与 docs/api.md 契约一一对应。
 * 所有字段按后端可能缺失的情况设为可空，前端一律防御性渲染。
 */

// ---------- 通用 ----------
export interface Health {
  status: string;
  db: string;
  llm: string;
  data_provider: string;
  time: string;
}

// ---------- 认证 ----------
export interface User {
  id: number;
  username: string;
  email: string | null;
  display_name: string | null;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  user: User;
}

// ---------- 基金 ----------
export type DataStatus = 'latest_available' | 'estimate';

export interface FundSummary {
  id: number;
  fund_code: string;
  fund_name: string;
  fund_type: string;
  company: string | null;
  latest_nav: number | null;
  latest_nav_date: string | null;
  estimate_nav: number | null;
  estimate_return: number | null;
  return_1d: number | null;
  return_5d: number | null;
  return_20d: number | null;
  return_60d: number | null;
  return_1y: number | null;
  return_ytd: number | null;
  score: number | null;
  risk_level: string | null;
  source: string;
  retrieved_at: string | null;
  data_status: DataStatus;
}

export interface Fees {
  management_fee: number;
  purchase_fee: number;
  redemption_fee: number;
}

export interface PredictionProbabilities {
  up: number;
  range: number;
  down: number;
}

export interface PredictionHorizon {
  probabilities: PredictionProbabilities;
  direction: string;
  confidence: string;
  confidence_score: number;
  score: number | null;
  feature_importance: { feature: string; importance: number }[];
  factors: {
    positive: FactorItem[];
    negative: FactorItem[];
    risks: RiskItem[];
  };
  disclaimer: string;
}

export interface FundPredictions {
  short: PredictionHorizon | null;
  medium: PredictionHorizon | null;
  long: PredictionHorizon | null;
}

export interface FundDetail extends FundSummary {
  manager: string | null;
  establish_date: string | null;
  benchmark: string | null;
  fund_size: number | null;
  fees: Fees | null;
  ai_score: number | null;
  trend: { short: string; medium: string; long: string } | null;
  predictions: FundPredictions | null;
  data_time: string | null;
}

export interface NavHistoryItem {
  date: string;
  nav: number | null;
  accumulated_nav: number | null;
  daily_return: number | null;
  volume: number | null;
  source: string | null;
}

export interface NavHistoryResponse {
  fund: { fund_code: string; fund_name: string };
  items: NavHistoryItem[];
  count: number;
  period: string;
  data_status: string;
}

export interface Holding {
  stock_code: string;
  stock_name: string;
  weight: number;
  industry: string | null;
  market_value: number | null;
  source: string | null;
}

export interface HoldingsResponse {
  fund_code: string;
  report_date: string | null;
  top10: Holding[];
  industry_distribution: { industry: string; weight: number }[];
  concentration: { top10: number | null; hhi: number | null };
  source: string;
  retrieved_at: string | null;
}

export interface IndicatorsResponse {
  fund_code: string;
  date: string | null;
  computed_at: string | null;
  indicators: Record<string, number | null>;
}

export interface RiskMetrics {
  annual_return: number | null;
  annual_volatility: number | null;
  downside_volatility: number | null;
  max_drawdown: number | null;
  sharpe: number | null;
  sortino: number | null;
  calmar: number | null;
  var_95: number | null;
  cvar_95: number | null;
  beta: number | null;
  alpha: number | null;
  information_ratio: number | null;
  best_day: number | null;
  worst_day: number | null;
}

export interface RiskResponse {
  fund_code: string;
  period: string | null;
  computed_at: string | null;
  metrics: RiskMetrics;
}

export interface FactorItem {
  factor: string;
  reason: string | null;
  evidence: string | null;
  value: number | null;
}

export interface RiskItem {
  category: string;
  detail: string;
  severity: string;
}

export interface TrendRegime {
  short: string;
  medium: string;
  long: string;
}

export interface FundAnalysisResponse {
  fund: { fund_code: string; fund_name: string };
  time_range: string;
  computed_at: string | null;
  score: number | null;
  score_breakdown: Record<string, number> | null;
  regime: TrendRegime | null;
  trend: TrendRegime | null;
  positive_factors: FactorItem[];
  negative_factors: FactorItem[];
  main_risks: RiskItem[];
  data_sources: { name: string; source: string; retrieved_at: string | null }[];
  data_status: string;
}

export type Horizon = 'short' | 'medium' | 'long';

export interface PredictionResponse {
  fund_code: string;
  model_version: string;
  horizon: Horizon;
  horizon_days: number;
  generated_at: string | null;
  data_as_of: string | null;
  probabilities: PredictionProbabilities;
  direction: string;
  confidence: string;
  confidence_score: number;
  score: number | null;
  feature_importance: { feature: string; importance: number }[];
  factors: {
    positive: FactorItem[];
    negative: FactorItem[];
    risks: RiskItem[];
  };
  disclaimer: string;
}

export interface TaskResponse {
  task_id: string;
  status: string;
}

// ---------- 自选 ----------
export interface WatchlistItem {
  id: number;
  fund: FundSummary;
  group_name: string;
  pinned: boolean;
  added_at: string;
}

// ---------- 市场 ----------
export interface MarketIndex {
  id: number;
  index_code: string;
  index_name: string;
  market: string | null;
  latest_close: number | null;
  change: number | null;
  change_pct: number | null;
  data_time: string | null;
  source: string;
  data_status: string | null;
}

export interface IndexHistoryItem {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  change_pct: number | null;
}

export interface IndexHistoryResponse {
  index: MarketIndex;
  items: IndexHistoryItem[];
  count: number;
  data_status: string;
}

export interface MarketRegime {
  label: string;
  score: number | null;
  drivers: string[];
}

export interface MarketOverview {
  indices: MarketIndex[];
  market_regime: MarketRegime | null;
  generated_at: string | null;
}

// ---------- 宏观 ----------
export interface MacroItem {
  id: number;
  indicator: string;
  value: number | null;
  unit: string | null;
  period: string | null;
  change: number | null;
  source: string;
  published_at: string | null;
}

export interface MacroResponse {
  items: MacroItem[];
  indicators: string[];
}

// ---------- 新闻 ----------
export type SentimentLabel = 'positive' | 'negative' | 'neutral';

export interface NewsItem {
  id: number;
  title: string;
  content: string | null;
  source: string | null;
  url: string | null;
  published_at: string | null;
  related_fund: string | null;
  related_industry: string | null;
  sentiment: number | null;
  sentiment_label: SentimentLabel | null;
  importance: number | null;
  retrieved_at: string | null;
}

export interface NewsListResponse {
  items: NewsItem[];
}

// ---------- 政策 ----------
export interface PolicyItem {
  id: number;
  title: string;
  content: string | null;
  source: string | null;
  url: string | null;
  published_at: string | null;
  department: string | null;
  policy_type: string | null;
  related_industry: string | null;
  sentiment: number | null;
  impact_score: number | null;
  importance: number | null;
  retrieved_at: string | null;
}

export interface PolicyListResponse {
  items: PolicyItem[];
}

// ---------- 多基金分析 ----------
export interface ComparisonRow {
  fund_code: string;
  fund_name: string;
  score: number | null;
  sharpe: number | null;
  max_drawdown: number | null;
  annual_volatility: number | null;
  return_1m: number | null;
  return_3m: number | null;
  trend_short: string | null;
  trend_medium: string | null;
  trend_long: string | null;
}

export interface AnalysisRequest {
  fund_ids: string[];
  time_range: string;
}

export interface MultiAnalysisResponse {
  generated_at: string | null;
  funds: FundAnalysisResponse[];
  comparison: {
    table: ComparisonRow[];
    best_trend: string | null;
    lowest_risk: string | null;
    highest_score: string | null;
  };
  market: { market_regime: MarketRegime | null } | null;
}

// ---------- 预测模型 ----------
export interface PredictionModel {
  version: string;
  trained_at: string | null;
  samples: number | null;
  metrics: { accuracy: number | null; up_precision: number | null; down_precision: number | null } | null;
  features: string[] | null;
}

export interface BacktestResponse {
  version: string;
  generated_at: string | null;
  metrics: {
    direction_accuracy: number | null;
    up_recall: number | null;
    down_recall: number | null;
    avg_return_5d: number | null;
    max_drawdown: number | null;
    period: string | null;
    samples: number | null;
  };
  disclaimer: string;
}

// ---------- AI 对话 ----------
export interface ChatSourcesSummary {
  funds: { fund_code: string; fund_name: string }[];
  market: boolean;
  macro: boolean;
  news_count: number | null;
  policies_count: number | null;
  prediction: boolean;
  data_as_of: string | null;
  retrieved_at: string | null;
  context_version: number | null;
}

export interface ChatResponse {
  conversation_id: string;
  reply: string;
  model: string;
  fallback: boolean;
  sources: ChatSourcesSummary | null;
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_message: string | null;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  created_at: string | null;
  model: string | null;
}

export interface ConversationDetail {
  id: string;
  title: string | null;
  messages: ChatMessage[];
  fund_codes: string[] | null;
}

/** 数据来源明细（结构以后端为准，宽松解析） */
export interface ConversationSources {
  [key: string]: unknown;
}

// ---------- 定时分析 ----------
export type ScheduleType = 'daily' | 'weekly' | 'monthly' | 'cron';

export interface Schedule {
  id: number;
  name: string;
  schedule_type: ScheduleType;
  cron_expression: string | null;
  time_of_day: string | null;
  day_of_week: number | null;
  day_of_month: number | null;
  fund_ids: string[];
  enabled: boolean;
  notification_channels: string[];
  llm_summary: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string | null;
}

export interface ScheduleInput {
  name: string;
  schedule_type: ScheduleType;
  time_of_day?: string;
  day_of_week?: number | null;
  day_of_month?: number | null;
  cron_expression?: string | null;
  fund_ids: string[];
  enabled: boolean;
  notification_channels: string[];
  llm_summary: boolean;
}

// ---------- 报告 ----------
export interface ReportSummary {
  id: number;
  title: string;
  generated_at: string | null;
  trigger: 'manual' | 'scheduled' | null;
  task_id: string | null;
}

export interface ReportDetail extends ReportSummary {
  content_md: string | null;
  content_html: string | null;
}

// ---------- 通知 ----------
export interface NotificationItem {
  id: number;
  title: string;
  content: string | null;
  type: 'analysis' | 'report' | 'system' | string;
  read: boolean;
  created_at: string | null;
}

// ---------- 任务 ----------
export interface TaskRun {
  id: number;
  name: string;
  status: 'pending' | 'running' | 'success' | 'failed' | string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  retries: number | null;
  result: string | null;
}

// ---------- 设置 ----------
export interface Settings {
  llm: {
    provider: string;
    model: string;
    base_url: string;
    has_api_key_env: boolean;
    has_user_key: boolean;
  };
  notifications: {
    email_enabled: boolean;
    email_to: string;
    channels: string[];
  };
  sync: { quote_interval_minutes: number };
  timezone: string;
}

export interface SettingsInput {
  llm?: Partial<Settings['llm']>;
  notifications?: Partial<Settings['notifications']>;
  sync?: Partial<Settings['sync']>;
}

// ---------- 首页 AI 总结 ----------
export interface DailySummary {
  generated_at: string | null;
  market: { label: string | null; score: number | null } | null;
  drivers: string[] | null;
  watchlist: {
    best: { fund_code: string; fund_name: string; return_1d: number | null } | null;
    worst: { fund_code: string; fund_name: string; return_1d: number | null } | null;
    riskiest: { fund_code: string; fund_name: string } | null;
    focus: string[] | null;
  } | null;
  text: string | null;
  fallback: boolean | null;
}
