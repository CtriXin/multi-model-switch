import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 4173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (outgoing, incoming) => {
            const host = incoming.headers.host || "";
            if (
              /^(127\.0\.0\.1|localhost):\d+$/.test(host) &&
              incoming.headers.origin === "http://" + host
            ) {
              outgoing.setHeader("Origin", "http://127.0.0.1:8765");
            }
          });
        },
      },
    },
  },
  build: { target: "es2022" },
});
