/** @type {import('tailwindcss').Config} */

// The primary accent ("indigo" in class names) reads from CSS variables defined in
// src/theme.css, so the whole UI can be re-branded by editing that one file.
const shades = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900];
const brand = Object.fromEntries(shades.map((s) => [s, `rgb(var(--brand-${s}) / <alpha-value>)`]));

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        indigo: brand,
        brand,
      },
    },
  },
  plugins: [],
};
