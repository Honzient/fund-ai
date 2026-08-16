import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChart from './EChart';
import { CHART_UP, CHART_DOWN } from '../utils/chart';

interface SparklineProps {
  data: number[];
  color?: string;
  height?: number;
  /** 是否按涨跌着色（红涨绿跌） */
  trendColor?: boolean;
  fill?: boolean;
}

/** 卡片内迷你走势图 */
export default function Sparkline({
  data,
  color,
  height = 36,
  trendColor = false,
  fill = true,
}: SparklineProps) {
  const option = useMemo<EChartsOption>(() => {
    const values = data.filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
    const up = values.length >= 2 ? values[values.length - 1] >= values[0] : true;
    const lineColor = color ?? (trendColor ? (up ? CHART_UP : CHART_DOWN) : '#3b82f6');
    return {
      backgroundColor: 'transparent',
      animation: false,
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: { type: 'category', show: false, data: values.map((_, i) => i) },
      yAxis: { type: 'value', show: false, scale: true },
      tooltip: { show: false },
      series: [
        {
          type: 'line',
          data: values,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.4, color: lineColor },
          areaStyle: fill
            ? {
                color: {
                  type: 'linear',
                  x: 0,
                  y: 0,
                  x2: 0,
                  y2: 1,
                  colorStops: [
                    { offset: 0, color: `${lineColor}44` },
                    { offset: 1, color: `${lineColor}00` },
                  ],
                },
              }
            : undefined,
          emphasis: { disabled: true },
        },
      ],
    };
  }, [data, color, trendColor, fill]);

  return <EChart option={option} style={{ height }} />;
}
