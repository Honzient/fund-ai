import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChart from './EChart';
import { TEXT, TOOLTIP_STYLE } from '../utils/chart';
import { Skeleton, EmptyState } from './ui';

export interface RadarIndicator {
  name: string;
  max: number;
}

export interface RadarSeries {
  name: string;
  data: number[];
  color?: string;
}

interface RadarChartProps {
  indicators: RadarIndicator[];
  series: RadarSeries[];
  height?: number;
  loading?: boolean;
  legend?: boolean;
}

/** 雷达图（多基金评分对比 / 单基金维度评分） */
export default function RadarChart({
  indicators,
  series,
  height = 300,
  loading,
  legend = true,
}: RadarChartProps) {
  const option = useMemo<EChartsOption | null>(() => {
    const cleanSeries = series.filter((s) => s.data.length > 0);
    if (indicators.length === 0 || cleanSeries.length === 0) return null;
    const palette = ['#3b82f6', '#f59e0b', '#a78bfa', '#34d399', '#f472b6', '#22d3ee'];
    return {
      backgroundColor: 'transparent',
      animation: false,
      legend: legend
        ? {
            top: 0,
            left: 'center',
            itemWidth: 12,
            itemHeight: 8,
            textStyle: { color: TEXT, fontSize: 11 },
          }
        : undefined,
      tooltip: { ...TOOLTIP_STYLE, trigger: 'item' },
      radar: {
        indicator: indicators.map((i) => ({ name: i.name, max: i.max })),
        radius: '62%',
        center: ['50%', '56%'],
        axisName: { color: TEXT, fontSize: 11 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
        splitArea: { areaStyle: { color: ['rgba(255,255,255,0.015)', 'rgba(255,255,255,0.03)'] } },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.12)' } },
      },
      series: [
        {
          type: 'radar',
          data: cleanSeries.map((s, i) => ({
            name: s.name,
            value: s.data,
            lineStyle: { color: s.color ?? palette[i % palette.length], width: 1.6 },
            itemStyle: { color: s.color ?? palette[i % palette.length] },
            areaStyle: { color: `${s.color ?? palette[i % palette.length]}26` },
            symbolSize: 3,
          })),
        },
      ],
    };
  }, [indicators, series, legend]);

  if (loading) {
    return <Skeleton style={{ height }} className="w-full rounded-lg" />;
  }
  if (!option) {
    return (
      <div style={{ height }} className="flex w-full items-center justify-center">
        <EmptyState title="暂无评分数据" icon="🕸️" />
      </div>
    );
  }
  return <EChart option={option} style={{ height }} />;
}
