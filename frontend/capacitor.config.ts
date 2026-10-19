import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "ru.buhgalteria.app",
  appName: "Бухгалтерия",
  webDir: "dist",
  android: {
    // Позволяет обращаться к серверу по http в локальной сети (например, http://192.168.1.10:8000).
    allowMixedContent: true,
  },
};

export default config;
