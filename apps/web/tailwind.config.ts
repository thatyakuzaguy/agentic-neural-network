import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#07091a",
        foreground: "#d4dff7",
        card: "#0c1221",
        "card-foreground": "#d4dff7",
        primary: "#00d0ff",
        "primary-foreground": "#07091a",
        secondary: "#111b32",
        "secondary-foreground": "#8899c0",
        muted: "#0a1020",
        "muted-foreground": "#4a5a78",
        accent: "#00d0ff",
        "accent-foreground": "#07091a",
        destructive: "#ff3757",
        border: "rgba(0, 208, 255, 0.1)",
        canvas: "#0f1216",
        panel: "#171b21",
        panel2: "#202630",
        line: "#303846",
        text: "#e7ebf2",
        legacyMuted: "#9aa6b7",
        legacyAccent: "#57c7a3",
        warn: "#f4b860",
        danger: "#ff6b6b"
      }
    }
  },
  plugins: []
};

export default config;
