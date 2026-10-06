import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#05070d",
        surface: "#0d1320",
        border: "rgba(148, 163, 184, 0.18)",
        accent: "#4f9cff"
      }
    }
  },
  plugins: []
};

export default config;
