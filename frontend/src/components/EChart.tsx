import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';

interface EChartProps {
  option: EChartsOption;
  style?: React.CSSProperties;
  className?: string;
  onReady?: (chart: echarts.ECharts) => void;
}

/**
 * 通用 ECharts 容器：自动 init / setOption / resize / dispose。
 * 直接使用 echarts 而非 echarts-for-react。
 */
export default function EChart({ option, style, className, onReady }: EChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = echarts.init(el);
    chartRef.current = chart;
    onReady?.(chart);
    const ro = new ResizeObserver(() => {
      chart.resize();
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.setOption(option, { notMerge: true });
    }
  }, [option]);

  return <div ref={containerRef} className={className} style={{ width: '100%', ...style }} />;
}
