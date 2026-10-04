// One self-contained HTML file per view (vite-plugin-singlefile handles one
// entry per build, as in the ext-apps examples).
import { build } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

const VIEWS = ["current", "forecast", "world-clock"];

for (const [i, view] of VIEWS.entries()) {
  await build({
    configFile: false,
    logLevel: "warn",
    plugins: [viteSingleFile()],
    build: {
      outDir: "dist",
      emptyOutDir: i === 0,
      rollupOptions: { input: `${view}.html` },
    },
  });
  console.log(`built dist/${view}.html`);
}
