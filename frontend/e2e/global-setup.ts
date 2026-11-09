import { request, type FullConfig } from "@playwright/test";
import { ADMIN, PASSWORD, USERS } from "./helpers";

/** Create one account per role through the API, signed in as the bootstrap administrator. */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL!;
  const ctx = await request.newContext({ baseURL });
  const login = await ctx.post("/api/auth/login", { data: ADMIN });
  if (!login.ok()) throw new Error(`Bootstrap admin sign-in failed: ${login.status()} ${await login.text()}`);
  for (const [role, u] of Object.entries(USERS)) {
    const r = await ctx.post("/api/users", { data: { email: u.email, full_name: u.name, role, password: PASSWORD } });
    if (!r.ok() && r.status() !== 422) throw new Error(`Could not create ${role}: ${r.status()} ${await r.text()}`);
  }
  await ctx.dispose();
}
