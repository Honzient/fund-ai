import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChart from './EChart';
import { cn } from '../utils/format';
import { sma, macd, rsi } from '../utils/indicators';
import {
  CHART_UP,
  CHART_DOWN,
  CHART_UP_SOFT,
  CHART_DOWN_SOFT,
  MA_COLORS,
  TEXT,
  TEXT_LIGHT,
  TOOLTIP_STYLE,
  AXIS_LABEL_STYLE,
  SPLIT_STYLE,
} from '../utils/chart';
import { Skeleton, EmptyState } from './ui';

export interface KlineItem {
  date: string;
  /** 无 OHLC 时（基金净值）传入的收盘值 */
  value?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
}

export type KlinePeriod = 'daily' | 'weekly' | 'monthly';

interface KlineChartProps {
  data: KlineItem[];
  loading?: boolean;
  height?: number;
  /** K 线名称（工具提示） */
  name?: string;
  /** 数据周期（日/周/月），由父组件持有以便重新拉取 */
  period?: KlinePeriod;
  onPeriodChange?: (p: KlinePeriod) => void;
  showPeriodSwitch?: boolean;
  showMacd?: boolean;
  showRsi?: boolean;
  showVolume?: boolean;
  showSlider?: boolean;
  className?: string;
  emptyText?: string;
}

/** 计算 MA 序列（与 K 线等长，前面补 null） */
function maSeries(values: number[], n: number): (number | null)[] {
  return sma(values, n);
}

function toFixedArr(arr: number[], digits = 3): number[] {
  return arr.map((v) => Number(v.toFixed(digits)));
}

/**
 * K 线图：蜡烛 + MA5/10/20/60 + 成交量 + MACD + RSI + 双 dataZoom + 十字光标。
 * 基金净值数据无 OHLC 时自动用「昨收=今开、高低=max/min」合成蜡烛。
 */
export default function KlineChart({
  data,
  loading,
  height = 430,
  name = '净值',
  period = 'daily',
  onPeriodChange,
  showPeriodSwitch = true,
  showMacd = true,
  showRsi = true,
  showVolume = true,
  showSlider = true,
  className,
  emptyText = '暂无行情数据',
}: KlineChartProps) {
  const processed = useMemo(() => {
    const dates: string[] = [];
    const candles: [number, number, number, number][] = [];
    const closes: number[] = [];
    const vols: number[] = [];
    const upFlags: boolean[] = [];
    let prevClose: number | null = null;
    for (const it of data) {
      const close = it.close ?? it.value;
      if (close === null || close === undefined || Number.isNaN(close)) continue;
      const open = it.open ?? prevClose ?? close;
      const high = it.high ?? Math.max(open, close);
      const low = it.low ?? Math.min(open, close);
      dates.push(it.date);
      candles.push([open, close, low, high]);
      closes.push(close);
      vols.push(it.volume ?? 0);
      upFlags.push(close >= open);
      prevClose = close;
    }
    return { dates, candles, closes, vols, upFlags };
  }, [data]);

  const option = useMemo<EChartsOption | null>(() => {
    const { dates, candles, closes, vols, upFlags } = processed;
    if (dates.length === 0) return null;

    const ma5 = maSeries(closes, 5);
    const ma10 = maSeries(closes, 10);
    const ma20 = maSeries(closes, 20);
    const ma60 = maSeries(closes, 60);
    const { dif, dea, hist } = macd(closes);
    const rsiArr = rsi(closes, 14);

    const xAxisIndexes = showMacd && showRsi ? [0, 1, 2, 3] : showMacd || showRsi ? [0, 1, 2] : showVolume ? [0, 1] : [0];
    const volGridTop = showMacd && showRsi ? '50%' : showMacd || showRsi ? '56%' : showVolume ? '62%' : '0%';
    const macdGridTop = showMacd && showRsi ? '63%' : showMacd ? '70%' : '0%';
    const rsiGridTop = '80%';

    const grids: EChartsOption['grid'] = [];
    const xAxes: EChartsOption['xAxis'] = [];
    const yAxes: EChartsOption['yAxis'] = [];

    // 主图
    grids.push({ left: 10, right: 14, top: 36, height: showVolume ? '42%' : '74%' });
    xAxes.push({
      type: 'category',
      data: dates,
      gridIndex: 0,
      boundaryGap: true,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.10)' } },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false },
    });
    yAxes.push({
      scale: true,
      gridIndex: 0,
      position: 'right',
      splitLine: SPLIT_STYLE,
      axisLabel: { ...AXIS_LABEL_STYLE, formatter: (v: number) => v.toFixed(2) },
    });

    // 成交量
    if (showVolume) {
      grids.push({ left: 10, right: 14, top: volGridTop, height: '8%' });
      xAxes.push({
        type: 'category',
        data: dates,
        gridIndex: 1,
        boundaryGap: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false },
      });
      yAxes.push({
        gridIndex: 1,
        position: 'right',
        splitLine: { show: false },
        axisLabel: { show: false },
      });
    }

    // MACD
    if (showMacd) {
      const gi = showVolume ? 2 : 1;
      grids.push({ left: 10, right: 14, top: macdGridTop, height: '13%' });
      xAxes.push({
        type: 'category',
        data: dates,
        gridIndex: gi,
        boundaryGap: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false },
      });
      yAxes.push({
        gridIndex: gi,
        position: 'right',
        scale: true,
        splitLine: { show: false },
        axisLabel: { ...AXIS_LABEL_STYLE, fontSize: 9 },
      });
    }

    // RSI
    if (showRsi) {
      const gi = (showVolume ? 1 : 0) + (showMacd ? 1 : 0);
      grids.push({ left: 10, right: 14, top: rsiGridTop, height: '12%' });
      xAxes.push({
        type: 'category',
        data: dates,
        gridIndex: gi,
        boundaryGap: true,
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.10)' } },
        axisTick: { show: false },
        axisLabel: { ...AXIS_LABEL_STYLE, fontSize: 9 },
        splitLine: { show: false },
      });
      yAxes.push({
        gridIndex: gi,
        position: 'right',
        min: 0,
        max: 100,
        splitLine: SPLIT_STYLE,
        axisLabel: { ...AXIS_LABEL_STYLE, fontSize: 9 },
      });
    }

    const series: EChartsOption['series'] = [];

    series.push({
      name,
      type: 'candlestick',
      data: candles,
      itemStyle: {
        color: CHART_UP,
        color0: CHART_DOWN,
        borderColor: CHART_UP,
        borderColor0: CHART_DOWN,
      },
    } as never);

    const maDefs: { name: string; data: (number | null)[]; color: string }[] = [
      { name: 'MA5', data: ma5, color: MA_COLORS[0] },
      { name: 'MA10', data: ma10, color: MA_COLORS[1] },
      { name: 'MA20', data: ma20, color: MA_COLORS[2] },
      { name: 'MA60', data: ma60, color: MA_COLORS[3] },
    ];
    for (const m of maDefs) {
      series.push({
        name: m.name,
        type: 'line',
        data: m.data,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1, color: m.color },
        emphasis: { disabled: true },
      } as never);
    }

    if (showVolume) {
      series.push({
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: vols.map((v, i) => ({
          value: v,
          itemStyle: { color: upFlags[i] ? CHART_UP_SOFT : CHART_DOWN_SOFT },
        })),
      } as never);
    }

    if (showMacd) {
      const gi = showVolume ? 2 : 1;
      series.push({
        name: 'MACD',
        type: 'bar',
        xAxisIndex: gi,
        yAxisIndex: gi,
        data: hist.map((v) => ({
          value: Number(v.toFixed(4)),
          itemStyle: { color: v >= 0 ? 'rgba(239,68,68,0.65)' : 'rgba(16,185,129,0.65)' },
        })),
      } as never);
      series.push({
        name: 'DIF',
        type: 'line',
        xAxisIndex: gi,
        yAxisIndex: gi,
        data: toFixedArr(dif, 4),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1, color: '#f59e0b' },
        emphasis: { disabled: true },
      } as never);
      series.push({
        name: 'DEA',
        type: 'line',
        xAxisIndex: gi,
        yAxisIndex: gi,
        data: toFixedArr(dea, 4),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1, color: '#38bdf8' },
        emphasis: { disabled: true },
      } as never);
    }

    if (showRsi) {
      const gi = (showVolume ? 1 : 0) + (showMacd ? 1 : 0);
      series.push({
        name: 'RSI14',
        type: 'line',
        xAxisIndex: gi,
        yAxisIndex: gi,
        data: rsiArr,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.2, color: '#a78bfa' },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: 'rgba(255,255,255,0.22)', type: 'dashed' },
          label: { show: false },
          data: [{ yAxis: 70 }, { yAxis: 30 }],
        },
        emphasis: { disabled: true },
      } as never);
    }

    const dataZoom: EChartsOption['dataZoom'] = [];
    if (showSlider) {
      dataZoom.push(
        {
          type: 'inside',
          xAxisIndex: xAxisIndexes,
          start: dates.length > 150 ? 62 : 0,
          end: 100,
        },
        {
          type: 'slider',
          xAxisIndex: xAxisIndexes,
          bottom: 2,
          height: 16,
          borderColor: 'rgba(255,255,255,0.08)',
          backgroundColor: 'rgba(255,255,255,0.02)',
          fillerColor: 'rgba(59,130,246,0.15)',
          handleStyle: { color: 'rgba(255,255,255,0.4)' },
          textStyle: { color: TEXT, fontSize: 9 },
          start: dates.length > 150 ? 62 : 0,
          end: 100,
        },
      );
    }

    return {
      backgroundColor: 'transparent',
      animation: false,
      legend: {
        data: [name, 'MA5', 'MA10', 'MA20', 'MA60'],
        top: 4,
        left: 8,
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { color: TEXT, fontSize: 11 },
      },
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        confine: true,
        formatter: (params: unknown) => {
          const list = (params as { axisValue: string; seriesName: string; value: unknown }[]);
          if (!Array.isArray(list) || list.length === 0) return '';
          const date = list[0]?.axisValue ?? '';
          const rows: string[] = [`<div style="font-weight:600;margin-bottom:4px">${date}</div>`];
          const seen = new Set<string>();
          for (const p of list) {
            const key = p.seriesName;
            if (seen.has(key)) continue;
            seen.add(key);
            const raw = p.value;
            let text = '--';
            if (Array.isArray(raw)) {
              const [o, c, l, h] = raw as number[];
              if (c !== undefined) {
                const col = c >= o ? CHART_UP : CHART_DOWN;
                text = `<span style="color:${col}">开 ${o.toFixed(3)} 收 ${c.toFixed(3)} 高 ${h.toFixed(3)} 低 ${l.toFixed(3)}</span>`;
              }
            } else if (typeof raw === 'number') {
              text = raw.toFixed(3);
            }
            rows.push(`<div>${key}：${text}</div>`);
          }
          return rows.join('');
        },
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom,
      series,
    };
  }, [processed, name, showMacd, showRsi, showVolume, showSlider, period]);

  if (loading) {
    return <Skeleton style={{ height }} className="w-full rounded-lg" />;
  }
  if (!option) {
    return (
      <div style={{ height }} className="flex w-full items-center justify-center">
        <EmptyState title={emptyText} icon="📉" />
      </div>
    );
  }

  return (
    <div className={cn('w-full', className)}>
      {showPeriodSwitch && onPeriodChange && (
        <div className="mb-1 flex items-center justify-end">
          <div className="inline-flex items-center rounded-md border border-white/10 bg-surface-2 p-0.5">
            {(
              [
                { value: 'daily', label: '日' },
                { value: 'weekly', label: '周' },
                { value: 'monthly', label: '月' },
              ] as { value: KlinePeriod; label: string }[]
            ).map((o) => (
              <button
                key={o.value}
                onClick={() => onPeriodChange(o.value)}
                className={cn(
                  'rounded px-2.5 py-0.5 text-[11px] font-medium transition',
                  period === o.value
                    ? 'bg-accent/20 text-accent'
                    : 'text-zinc-500 hover:text-zinc-200',
                )}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
      )}
      <EChart option={option} style={{ height }} />
    </div>
  );
}
