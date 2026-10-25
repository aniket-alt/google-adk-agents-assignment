// Stand-in for the Gemini CLI used by the offline test: echoes how it was invoked as JSON.
const path = require("path");
const args = process.argv.slice(2);
process.stdout.write(
  JSON.stringify({
    response: `FAKE CLI ANALYSIS of ${path.basename(process.cwd())} | args: ${args.join(" ")}`,
    stats: {},
  })
);
