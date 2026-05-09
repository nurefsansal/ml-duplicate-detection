/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', "Manrope", "Segoe UI", "system-ui", "sans-serif"],
      },
      colors: {
        primary: {
          50: "#ecfeff",
          100: "#cffafe",
          200: "#a5f3fc",
          300: "#67e8f9",
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
          700: "#0e7490",
          800: "#155e75",
          900: "#164e63",
        },
        surface: {
          DEFAULT: "#f4f7fb",
          elevated: "#ffffff",
          muted: "#e8eef6",
        },
        danger: {
          50: "#fff1f2",
          100: "#ffe4e6",
          200: "#fecdd3",
          600: "#e11d48",
          700: "#be123c",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgb(15 23 42 / 0.05), 0 4px 16px rgb(15 23 42 / 0.06)",
        "card-lg": "0 4px 6px rgb(15 23 42 / 0.04), 0 12px 28px rgb(15 23 42 / 0.08)",
        nav: "4px 0 24px rgb(15 23 42 / 0.06)",
      },
      backgroundImage: {
        "mesh-light":
          "radial-gradient(at 40% 20%, rgb(224 242 254 / 0.9) 0px, transparent 50%), radial-gradient(at 80% 0%, rgb(237 233 254 / 0.5) 0px, transparent 45%), radial-gradient(at 0% 50%, rgb(207 250 254 / 0.4) 0px, transparent 50%)",
        "gradient-primary": "linear-gradient(135deg, #0891b2 0%, #6366f1 100%)",
      },
    },
  },
  plugins: [],
};
