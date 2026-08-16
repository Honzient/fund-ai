/** 技术指标计算（纯函数，供图表叠加层使用）。 */

export function sma(values: number[], n: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= n) sum -= values[i - n];
    out.push(i >= n - 1 ? Number((sum / n).toFixed(4)) : null);
  }
  return out;
}

export function ema(values: number[], n: number): number[] {
  const k = 2 / (n + 1);
  const out: number[] = [];
  let prev = values[0] ?? 0;
  out.push(prev);
  for (let i = 1; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
}

export interface MacdResult {
  dif: number[];
  dea: number[];
  hist: number[];
}

export function macd(values: number[], fast = 12, slow = 26, signal = 9): MacdResult {
  const emaFast = ema(values, fast);
  const emaSlow = ema(values, slow);
  const dif = emaFast.map((f, i) => f - emaSlow[i]);
  const dea = ema(dif, signal);
  const hist = dif.map((d, i) => (d - dea[i]) * 2);
  return { dif, dea, hist };
}

export function rsi(values: number[], n = 14): (number | null)[] {
  const out: (number | null)[] = [null];
  if (values.length < 2) return out;
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i < values.length; i++) {
    const diff = values[i] - values[i - 1];
    const gain = Math.max(diff, 0);
    const loss = Math.max(-diff, 0);
    if (i <= n) {
      avgGain += gain;
      avgLoss += loss;
      if (i === n) {
        avgGain /= n;
        avgLoss /= n;
      }
    } else {
      avgGain = (avgGain * (n - 1) + gain) / n;
      avgLoss = (avgLoss * (n - 1) + loss) / n;
    }
    if (i < n) {
      out.push(null);
    } else {
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      out.push(Number((100 - 100 / (1 + rs)).toFixed(2)));
    }
  }
  return out;
}

/** 日收益率序列（百分比） */
export function dailyReturns(values: number[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < values.length; i++) {
    const prev = values[i - 1];
    out.push(prev ? ((values[i] - prev) / prev) * 100 : 0);
  }
  return out;
}

/** 年化波动率（%） */
export function annualVolatility(values: number[]): number {
  const rets = dailyReturns(values);
  if (rets.length < 2) return 0;
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const variance = rets.reduce((a, b) => a + (b - mean) * (b - mean), 0) / (rets.length - 1);
  return Math.sqrt(variance) * Math.sqrt(252);
}

/** 最大回撤（正数表示回撤幅度） */
export function maxDrawdown(values: number[]): number {
  let peak = -Infinity;
  let mdd = 0;
  for (const v of values) {
    if (v > peak) peak = v;
    const dd = peak > 0 ? (peak - v) / peak : 0;
    if (dd > mdd) mdd = dd;
  }
  return mdd;
}

/** N 日动量（%） */
export function momentum(values: number[], n: number): number {
  if (values.length < n + 1) return 0;
  const start = values[values.length - 1 - n];
  const end = values[values.length - 1];
  return start ? ((end - start) / start) * 100 : 0;
}

/** 区间收益（%） */
export function rangeReturn(values: number[], lookback: number): number {
  return momentum(values, Math.min(lookback, Math.max(1, values.length - 1)));
}
