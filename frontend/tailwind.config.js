/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0b0e14',
        surface: '#11151f',
        'surface-2': '#161b28',
        'surface-3': '#1d2436',
        up: '#ef4444',
        down: '#10b981',
        accent: '#3b82f6',
        gold: '#f59e0b',
      },
      fontFamily: {
        sans: [
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'PingFang SC',
          'Hiragino Sans GB',
          'Microsoft YaHei',
          'Noto Sans SC',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Consolas',
          'Liberation Mono',
          'monospace',
        ],
      },
      boxShadow: {
        card: '0 1px 2px rgba(0,0,0,0.4)',
        glow: '0 0 0 1px rgba(59,130,246,0.25), 0 0 16px rgba(59,130,246,0.15)',
      },
    },
  },
  plugins: [],
};
