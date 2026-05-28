/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        shield: {
          green: '#16a34a',
          orange: '#ea580c',
          red: '#dc2626',
        },
      },
    },
  },
  plugins: [],
}
