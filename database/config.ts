import { homedir } from "os";
import { join } from "path";

// Get database path from env or use default
export const DATABASE_PATH =
  process.env.FINAGENT_DATABASE_PATH?.replace(/^~/, homedir()) ||
  join(homedir(), ".finagent", "data.db");