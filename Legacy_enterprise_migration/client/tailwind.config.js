/** @type {import('tailwindcss').Config} */
// Every colour is a CSS variable (see index.css) so the whole UI flips between light and dark.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: v('ink-950'), 900: v('ink-900'), 800: v('ink-800'), 700: v('ink-700'), 600: v('ink-600') },
        slate: { 100: v('s100'), 200: v('s200'), 300: v('s300'), 400: v('s400'), 500: v('s500'), 600: v('s600'), 700: v('s700') },
        fg: v('fg'),
        brand: { DEFAULT: v('brand'), soft: v('brand-soft') },
        ok: v('ok'), warn: v('warn'), bad: v('bad'),
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'], mono: ['JetBrains Mono', 'ui-monospace', 'monospace'] },
      boxShadow: { glow: '0 0 0 1px rgb(var(--brand) / .35), 0 8px 30px rgb(var(--brand) / .15)' },
    },
  },
  plugins: [],
}
