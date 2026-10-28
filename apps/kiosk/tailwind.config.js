/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}', './.storybook/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Fredoka', 'ui-rounded', 'system-ui', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        ink: 'rgb(var(--pp-ink) / <alpha-value>)',
        paper: 'rgb(var(--pp-paper) / <alpha-value>)',
        card: 'rgb(var(--pp-card) / <alpha-value>)',
        muted: 'rgb(var(--pp-muted) / <alpha-value>)',
        accent: 'rgb(var(--pp-accent) / <alpha-value>)',
        accent2: 'rgb(var(--pp-accent2) / <alpha-value>)',
        line: 'rgb(var(--pp-line) / <alpha-value>)',
      },
      borderRadius: { tile: 'var(--pp-radius)' },
      boxShadow: { soft: 'var(--pp-shadow)' },
    },
  },
  plugins: [],
};
