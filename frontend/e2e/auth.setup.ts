import { expect, test as setup } from "@playwright/test"

// One reusable account: registered on first run (registration must be open),
// then signed in through the real BFF so the session cookies are genuine.
const account = {
  organization_name: "E2E Tests",
  full_name: "E2E Reviewer",
  email: process.env.E2E_EMAIL ?? "e2e@example.com",
  password: process.env.E2E_PASSWORD ?? "E2e-Test-Password-2026",
}
const STORAGE_STATE = "e2e/.auth/user.json"
const headers = { "X-Requested-With": "docintel" }

setup("sign in", async ({ request }) => {
  const registered = await request.post("/bff/auth/register", {
    data: account,
    headers,
  })
  // 409: the account already exists from an earlier run.
  expect([200, 201, 409]).toContain(registered.status())

  const login = await request.post("/bff/auth/login", {
    data: { email: account.email, password: account.password },
    headers,
  })
  expect(login.ok(), await login.text()).toBeTruthy()
  await request.storageState({ path: STORAGE_STATE })
})
