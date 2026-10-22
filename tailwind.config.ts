import type { Config } from "tailwindcss";
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: { extend: { colors: { navy: "#102a38", teal: "#087f75" } } },
  plugins: [],
} satisfies Config;
