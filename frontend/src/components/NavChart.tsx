import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChart from './EChart';
import { Skeleton, EmptyState } from './ui';
import { TEXT, TOOLTIP_STYLE, AXIS_LABEL_STYLE, SPLIT_STYLE, ACCENT } from '../utils/chart';

export interface NavSeries {
  name: string;
  /** [date, value] */
  data: [string, number | null][];
  color?: string;
  area?: boolean;
  dashed?: boolean;
}

interface NavChartProps {
  series: NavSeries[];
  height?: number;
  loading?: boolean;
  /** 将每个序列归一化到首值=100（基金 vs 基准对比时使用） */
  normalize?: boolean;
  /** y 轴按百分比显示（normalize 时启用） */
  percent?: boolean;
  emptyText?: string;
}

/** 净值/指数走势折线图（支持多序列对比、归一化） */
export default function NavChart({
  series,
  height = 340,
  loading,
  normalize = false,
  percent = false,
  emptyText = '暂无走势数据',
}: NavChartProps) {
  const option = useMemo<EChartsOption | null>(() => {
    const clean = series
      .map((s) => ({
        ...s,
        data: s.data.filter(([, v]) => v !== null && v !== undefined && !Number.isNaN(v)) as [
          string,
          number,
        ][],
      }))
      .filter((s) => s.data.length > 0);
    if (clean.length === 0) return null;

    const allDates = Array.from(new Set(clean.flatMap((s) => s.data.map(([d]) => d)))).sort();
    if (allDates.length === 0) return null;

    const toChartData = (s: (typeof clean)[number]) => {
      const map = new Map(s.data);
      const points = allDates.map((d) => {
        const raw = map.get(d);
        if (raw === undefined) return null;
        if (!normalize) return raw;
        return raw;
      });
      if (!normalize) return points;
      const first = points.find((p) => p !== null) ?? 1;
      return points.map((p) => (p === null ? null : Number(((p / first) * 100).toFixed(4))));
    };

    return {
      backgroundColor: 'transparent',
      animation: false,
      legend: {
        top: 4,
        left: 8,
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { color: TEXT, fontSize: 11 },
      },
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: 'axis',
        confine: true,
        valueFormatter: (v: unknown) =>
          typeof v === 'number' ? (percent || normalize ? `${v.toFixed(2)}%` : v.toFixed(3)) : '--',
      },
      grid: { left: 12, right: 14, top: 36, bottom: 28 },
      xAxis: {
        type: 'category',
        data: allDates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.10)' } },
        axisTick: { show: false },
        axisLabel: { ...AXIS_LABEL_STYLE, hideOverlap: true },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        scale: true,
        position: 'right',
        splitLine: SPLIT_STYLE,
        axisLabel: {
          ...AXIS_LABEL_STYLE,
          formatter: (v: number) => (percent || normalize ? `${v.toFixed(1)}%` : v.toFixed(2)),
        },
      },
      dataZoom: [
        { type: 'inside', start: 0, end: 100 },
        { type: 'slider', bottom: 0, height: 14, borderColor: 'rgba(255,255,255,0.08)' },
      ],
      series: clean.map((s, idx) => ({
        name: s.name,
        type: 'line',
        data: toChartData(s),
        smooth: true,
        showSymbol: false,
        lineStyle: {
          width: idx === 0 ? 2 : 1.2,
          color: s.color ?? (idx === 0 ? ACCENT : '#8b93a7'),
          type: s.dashed ? 'dashed' : 'solid',
        },
        areaStyle: s.area
          ? {
              color: {
                type: 'linear',
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: 'rgba(59,130,246,0.22)' },
                  { offset: 1, color: 'rgba(59,130,246,0)' },
                ],
              },
            }
          : undefined,
        emphasis: { disabled: true },
      })),
    };
  }, [series, normalize, percent]);

  if (loading) {
    return <Skeleton style={{ height }} className="w-full rounded-lg" />;
  }
  if (!option) {
    return (
      <div style={{ height }} className="flex w-full items-center justify-center">
        <EmptyState title={emptyText} icon="📈" />
      </div>
    );
  }
  return <EChart option={option} style={{ height }} />;
}
