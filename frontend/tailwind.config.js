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
      boxShadow: {
        card: '0 1px 2px rgb(23 59 101 / 0.05), 0 1px 3px rgb(23 59 101 / 0.04)',
        pop: '0 10px 30px rgb(23 59 101 / 0.14), 0 2px 6px rgb(23 59 101 / 0.06)',
      },
    },
  },
  plugins: [],
};
