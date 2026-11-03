/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        obsidian: {
          950: "#050811",
          900: "#0a0f1d",
          850: "#0e1628",
          800: "#152037",
          700: "#1e2e4f",
          600: "#2d426d",
        },
        navy: {
          950: "#050811",
          900: "#0b132b",
          850: "#0e1733",
          800: "#1c2541",
          700: "#3a506b",
        },
        cyan: {
          300: "#7dd3fc",
          400: "#38bdf8",
          500: "#0ea5e9",
          600: "#0284c7",
        },
      },
      boxShadow: {
        "bevel": "inset 0 1px 1px 0 rgba(255, 255, 255, 0.08)",
        "bevel-glow": "inset 0 1px 2px 0 rgba(255, 255, 255, 0.12), 0 0 20px -5px rgba(56, 189, 248, 0.15)",
        "glow-cyan": "0 0 30px -5px rgba(56, 189, 248, 0.3)",
        "glow-emerald": "0 0 30px -5px rgba(16, 185, 129, 0.25)",
        "glow-rose": "0 0 30px -5px rgba(244, 63, 94, 0.25)",
        "ambient": "0 25px 50px -12px rgba(0, 0, 0, 0.75)",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Display",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "SF Mono",
          "Fira Code",
          "Cascadia Code",
          "monospace",
        ],
      },
      animation: {
        "pulse-slow": "pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "float": "float 6s ease-in-out infinite",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
      },
    },
  },
  plugins: [],
}
