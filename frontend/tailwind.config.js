/** @type {import('tailwindcss').Config} */

// Every brand colour below reads from CSS variables in src/theme.css, so the whole UI can
// be re-branded by editing that one file. "indigo" stays as an alias of "brand" so any
// older indigo-* class still renders in the brand blue.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;
const scale = (name, shades) => Object.fromEntries(shades.map((s) => [s, v(`${name}-${s}`)]));
const all = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900];

const brand = { ...scale('brand', all), DEFAULT: v('brand-600') };
const navy = { ...scale('navy', all), DEFAULT: v('navy-700') };
const accent = { ...scale('accent', [50, 100, 500, 600, 700]), DEFAULT: v('accent-500') };

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand,
        indigo: brand,
        navy,
        accent,
        app: v('app'),
        surface: v('surface'),
        ink: v('ink'),
        muted: { DEFAULT: v('muted'), strong: v('muted-strong') },
        line: v('line'),
      },
      borderColor: { DEFAULT: v('line') },
      ringColor: { DEFAULT: v('brand-600') },
      // Consistent radii from theme.css: controls 10px, panels 14px, hero cards 18px.
      borderRadius: {
        md: 'var(--radius-control)',
        lg: 'var(--radius-panel)',
        xl: 'var(--radius-hero)',
      },
      boxShadow: {
        // Soft, navy-tinted shadows with a 1px inner top highlight for the glass edge.
        card: '0 1px 2px rgb(13 34 59 / 0.04), 0 4px 16px -4px rgb(13 34 59 / 0.10), inset 0 1px 0 rgb(255 255 255 / 0.6)',
        pop: '0 24px 60px -12px rgb(13 34 59 / 0.35), 0 4px 14px rgb(13 34 59 / 0.10), inset 0 1px 0 rgb(255 255 255 / 0.7)',
        lift: '0 2px 4px rgb(13 34 59 / 0.05), 0 12px 28px -6px rgb(13 34 59 / 0.18), inset 0 1px 0 rgb(255 255 255 / 0.6)',
        glow: '0 4px 14px -2px rgb(36 102 165 / 0.45), inset 0 1px 0 rgb(255 255 255 / 0.18)',
      },
      backdropBlur: { glass: 'var(--glass-blur)' },
    },
  },
  plugins: [],
};
