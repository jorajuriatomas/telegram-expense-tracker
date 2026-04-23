import { createApp } from "./app.js";
import { env } from "./config/env.js";

const app = createApp();

app.listen(env.port, () => {
  // Startup log is intentionally simple for step 2 bootstrap.
  console.log(`connector-service listening on port ${env.port}`);
});
