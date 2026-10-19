import { getDb } from "../src/lib/db";

// getDb() connects and applies migrations/*.sql (idempotent).
getDb().then(() => {
  console.log("migrations applied");
  process.exit(0);
}, (e) => {
  console.error(e);
  process.exit(1);
});
