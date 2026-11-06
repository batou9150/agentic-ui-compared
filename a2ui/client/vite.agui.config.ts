// Builds the AG-UI transport alone (connection + @ag-ui/client), without what
// the A2A client already ships (A2UI renderer, catalog, Lit), to measure what
// AG-UI adds to the client: `make measure` reports dist-agui/ as an add-on.
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "dist-agui",
    emptyOutDir: true,
    lib: { entry: "src/agui-connection.ts", formats: ["es"], fileName: "agui-connection" },
    rolldownOptions: {
      external: [/^@a2ui\//, /^lit/, /\/catalog$/, /^chart\.js/],
      // Minified like the app bundle (lib mode leaves ES output unminified).
      output: { minify: true },
    },
  },
});
