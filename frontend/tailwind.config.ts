import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#20282e',
        muted: '#68747c',
        canvas: '#f5f4f0',
        panel: '#fffefa',
        line: '#e4e5e1',
        accent: '#315e7b',
        'accent-dark': '#234b64',
        'accent-soft': '#e7eff3',
        amber: '#a86624',
        'amber-soft': '#f8eee0',
        coral: '#b75243',
        'coral-soft': '#f8e9e5',
        sage: '#39705c',
        'sage-soft': '#e6f0eb',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['"DM Sans"', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        panel: '0 14px 40px rgba(32, 40, 46, 0.055)',
        lift: '0 8px 24px rgba(32, 40, 46, 0.09)',
      },
    },
  },
  plugins: [],
} satisfies Config;
