/** @type {import('tailwindcss').Config} */
const v = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        card: v("card"),
        ink: v("ink"),
        muted: v("muted"),
        line: v("line"),
        accent: v("accent"),
        "accent-soft": v("accent-soft"),
        "on-accent": v("on-accent"),
        danger: v("danger"),
        warn: v("warn"),
      },
      fontFamily: { sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"] },
      borderRadius: { xl: "14px", "2xl": "18px" },
    },
  },
  plugins: [],
};
