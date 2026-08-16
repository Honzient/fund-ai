import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChart from './EChart';
import { TEXT } from '../utils/chart';

interface GaugeProps {
  value: number | null | undefined;
  name?: string;
  max?: number;
  height?: number;
  /** 是否按分数区间着色 */
  colorByScore?: boolean;
}

/** 仪表盘（AI 评分等 0-100 指标） */
export default function Gauge({
  value,
  name,
  max = 100,
  height = 200,
  colorByScore = true,
}: GaugeProps) {
  const option = useMemo<EChartsOption>(() => {
    const v = value === null || value === undefined ? 0 : Math.max(0, Math.min(max, value));
    let color = '#3b82f6';
    if (colorByScore) {
      color = v >= 80 ? '#ef4444' : v >= 65 ? '#f59e0b' : v >= 50 ? '#3b82f6' : '#8b93a7';
    }
    return {
      backgroundColor: 'transparent',
      series: [
        {
          type: 'gauge',
          startAngle: 210,
          endAngle: -30,
          min: 0,
          max,
          radius: '95%',
          center: ['50%', '58%'],
          progress: {
            show: true,
            width: 14,
            roundCap: true,
            itemStyle: { color },
          },
          axisLine: { lineStyle: { width: 14, color: [[1, 'rgba(255,255,255,0.07)']] } },
          pointer: { show: false },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          anchor: { show: false },
          title: {
            show: name !== undefined,
            offsetCenter: [0, '78%'],
            fontSize: 12,
            color: TEXT,
          },
          detail: {
            valueAnimation: true,
            offsetCenter: [0, '28%'],
            fontSize: 30,
            fontWeight: 700,
            color,
            formatter: (val: number) => `${Math.round(val)}`,
          },
          data: [{ value: v, name: name ?? '' }],
        },
      ],
    };
  }, [value, name, max, colorByScore]);

  return <EChart option={option} style={{ height }} />;
}
