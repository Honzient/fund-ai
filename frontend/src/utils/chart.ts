/** 图表配色与主题常量。 */

export const CHART_UP = '#ef4444'; // 红涨
export const CHART_DOWN = '#10b981'; // 绿跌
export const CHART_UP_SOFT = 'rgba(239,68,68,0.85)';
export const CHART_DOWN_SOFT = 'rgba(16,185,129,0.85)';
export const AXIS_LINE = 'rgba(255,255,255,0.10)';
export const SPLIT_LINE = 'rgba(255,255,255,0.05)';
export const TEXT = '#8b93a7';
export const TEXT_LIGHT = '#e5e7eb';
export const ACCENT = '#3b82f6';
export const GOLD = '#f59e0b';
export const PURPLE = '#a78bfa';
export const MA_COLORS = ['#f59e0b', '#38bdf8', '#a78bfa', '#f472b6'];

export const TOOLTIP_STYLE = {
  backgroundColor: 'rgba(20,25,38,0.96)',
  borderColor: 'rgba(255,255,255,0.12)',
  borderWidth: 1,
  textStyle: { color: TEXT_LIGHT, fontSize: 12 },
  padding: [8, 12] as [number, number],
};

export const AXIS_LABEL_STYLE = { color: TEXT, fontSize: 10 };
export const SPLIT_STYLE = { lineStyle: { color: SPLIT_LINE } };
