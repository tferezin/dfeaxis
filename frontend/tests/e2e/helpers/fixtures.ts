/**
 * Test fixtures for trial flow E2E.
 *
 * Talks directly to Supabase REST + Auth Admin API to seed and tear down
 * test users in any trial state we want to validate.
 *
 * The service role key is hardcoded for the dev project — these tests
 * are NEVER meant to run against production.
 */

const SUPABASE_URL = process.env.SUPABASE_URL || "https://kmiooqyasvhglszcioow.supabase.co"
const SR_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || (() => {
  throw new Error(
    "SUPABASE_SERVICE_ROLE_KEY env var is required for E2E tests. " +
    "Set it in your shell or in frontend/.env.local"
  )
})()

const REST = `${SUPABASE_URL}/rest/v1`
const AUTH_ADMIN = `${SUPABASE_URL}/auth/v1/admin`

const HEADERS = {
  apikey: SR_KEY,
  Authorization: `Bearer ${SR_KEY}`,
  "Content-Type": "application/json",
  Prefer: "return=representation",
}

export interface TestUserOptions {
  /** subscription_status to set (default 'trial') */
  status?: "trial" | "active" | "cancelled" | "expired"
  /** Days remaining on the trial (default 10). Sets trial_expires_at = now + X days. */
  daysRemaining?: number
  /** Docs already consumed against trial cap (default 0) */
  docsConsumed?: number
  /** Trial cap (default 500) */
  trialCap?: number
  /** Force trial blocked with reason (sets trial_blocked_at = now) */
  blockedReason?: "cap" | "time" | null
  /** Optional cert seed: clone admin cert under this tenant for capture tests */
  withCert?: boolean
  /** CNPJ override (default generates a random valid one) */
  cnpj?: string
}

export interface TestUser {
  id: string
  tenantId: string
  email: string
  password: string
  cnpj: string
  certId?: string
}

/** Generates a unique 14-digit valid CNPJ with correct mod-11 check digits. */
function generateTestCnpj(): string {
  // Generate 8 random base digits + fixed branch "0001"
  const base = Math.floor(Math.random() * 100_000_000)
    .toString()
    .padStart(8, "0")
  const digits = (base + "0001").split("").map(Number) // 12 digits

  // First check digit (position 13)
  const w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
  let sum = digits.reduce((s, d, i) => s + d * w1[i], 0)
  let rem = sum % 11
  const d1 = rem < 2 ? 0 : 11 - rem
  digits.push(d1)

  // Second check digit (position 14)
  const w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
  sum = digits.reduce((s, d, i) => s + d * w2[i], 0)
  rem = sum % 11
  const d2 = rem < 2 ? 0 : 11 - rem
  digits.push(d2)

  return digits.join("")
}

/**
 * Creates a fresh test user + tenant in the specified trial state.
 * Email is unique per call (timestamp + random suffix).
 */
export async function createTestUser(
  opts: TestUserOptions = {}
): Promise<TestUser> {
  const {
    status = "trial",
    daysRemaining = 10,
    docsConsumed = 0,
    trialCap = 500,
    blockedReason = null,
    withCert = false,
    cnpj = generateTestCnpj(),
  } = opts

  const stamp = Date.now()
  const random = Math.random().toString(36).slice(2, 8)
  const email = `e2e-${stamp}-${random}@dfeaxis-test.com`
  const password = "E2eTestPassword123!"

  // Step 1: create auth user (email pre-confirmed)
  const authRes = await fetch(`${AUTH_ADMIN}/users`, {
    method: "POST",
    headers: HEADERS,
    body: JSON.stringify({
      email,
      password,
      email_confirm: true,
    }),
  })
  if (!authRes.ok) {
    const text = await authRes.text()
    throw new Error(`createAuthUser failed: ${authRes.status} ${text}`)
  }
  const authData = await authRes.json()
  const userId: string = authData.id

  // Step 2: create tenant
  const trialExpires = new Date(
    Date.now() + daysRemaining * 24 * 60 * 60 * 1000
  ).toISOString()

  const tenantPayload: Record<string, unknown> = {
    user_id: userId,
    company_name: `E2E Test ${random}`,
    email,
    plan: "starter",
    credits: 100,
    subscription_status: status,
    trial_active: status === "trial" && !blockedReason,
    trial_expires_at: trialExpires,
    trial_cap: trialCap,
    docs_consumidos_trial: docsConsumed,
    cnpj,
    phone: "11999999999",
  }

  if (blockedReason) {
    tenantPayload.trial_blocked_reason = blockedReason
    tenantPayload.trial_blocked_at = new Date().toISOString()
    tenantPayload.trial_active = false
  }

  const tenantRes = await fetch(`${REST}/tenants`, {
    method: "POST",
    headers: HEADERS,
    body: JSON.stringify(tenantPayload),
  })
  if (!tenantRes.ok) {
    const text = await tenantRes.text()
    // Cleanup orphan auth user
    await fetch(`${AUTH_ADMIN}/users/${userId}`, {
      method: "DELETE",
      headers: HEADERS,
    })
    throw new Error(`createTenant failed: ${tenantRes.status} ${text}`)
  }
  const tenantData = await tenantRes.json()
  const tenantId: string = tenantData[0].id

  // Step 3 (optional): seed a certificate (cloned from admin's real cert)
  let certId: string | undefined
  if (withCert) {
    const adminCertRes = await fetch(
      `${REST}/certificates?select=*&tenant_id=eq.dfe11fdb-fa54-403e-b563-24aef3b7b406&limit=1`,
      { headers: HEADERS }
    )
    const adminCerts = (await adminCertRes.json()) as Array<{
      pfx_encrypted: string
      pfx_password_encrypted: string
      pfx_iv: string | null
    }>
    if (adminCerts.length === 0) {
      throw new Error("admin cert not found — required for withCert=true")
    }
    const seed = adminCerts[0]

    const certPayload = {
      tenant_id: tenantId,
      cnpj,
      company_name: `E2E Test Cert ${random}`,
      pfx_encrypted: seed.pfx_encrypted, // shared blob — won't decrypt for this tenant but exists
      pfx_iv: seed.pfx_iv,
      pfx_password_encrypted: seed.pfx_password_encrypted,
      valid_from: "2026-01-01",
      valid_until: "2027-01-01",
      is_active: true,
    }

    const certRes = await fetch(`${REST}/certificates`, {
      method: "POST",
      headers: HEADERS,
      body: JSON.stringify(certPayload),
    })
    if (!certRes.ok) {
      const text = await certRes.text()
      throw new Error(`createCert failed: ${certRes.status} ${text}`)
    }
    const certData = await certRes.json()
    certId = certData[0].id
  }

  return { id: userId, tenantId, email, password, cnpj, certId }
}

/** Updates a tenant's state mid-test (e.g., simulate cap reached, payment, etc). */
export async function updateTenant(
  tenantId: string,
  patch: Record<string, unknown>
): Promise<void> {
  const res = await fetch(`${REST}/tenants?id=eq.${tenantId}`, {
    method: "PATCH",
    headers: HEADERS,
    body: JSON.stringify(patch),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`updateTenant failed: ${res.status} ${text}`)
  }
}

/** Simulates a successful payment: tenant becomes 'active' and unblocked. */
export async function simulatePaymentSuccess(tenantId: string): Promise<void> {
  await updateTenant(tenantId, {
    subscription_status: "active",
    trial_active: false,
    trial_blocked_reason: null,
    trial_blocked_at: null,
  })
}

/** Simulates trial time expiration: trial_expires_at moves to past. */
export async function simulateTimeExpired(tenantId: string): Promise<void> {
  const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
  await updateTenant(tenantId, {
    trial_expires_at: yesterday,
    trial_active: false,
    subscription_status: "expired",
    trial_blocked_reason: "time",
    trial_blocked_at: new Date().toISOString(),
  })
}

/** Simulates cap reached: docs_consumidos_trial = trial_cap, blocked. */
export async function simulateCapReached(
  tenantId: string,
  cap: number = 500
): Promise<void> {
  await updateTenant(tenantId, {
    docs_consumidos_trial: cap,
    trial_blocked_reason: "cap",
    trial_blocked_at: new Date().toISOString(),
    trial_active: false,
  })
}

/** Tears down a test user (deletes tenant, related rows, and auth user). */
export async function deleteTestUser(user: TestUser): Promise<void> {
  // Delete child tables first (FK NO ACTION)
  for (const table of [
    "audit_log",
    "credit_transactions",
    "polling_log",
    "manifestacao_events",
    "documents",
    "api_keys",
    "certificates",
  ]) {
    await fetch(`${REST}/${table}?tenant_id=eq.${user.tenantId}`, {
      method: "DELETE",
      headers: HEADERS,
    })
  }
  await fetch(`${REST}/tenants?id=eq.${user.tenantId}`, {
    method: "DELETE",
    headers: HEADERS,
  })
  await fetch(`${AUTH_ADMIN}/users/${user.id}`, {
    method: "DELETE",
    headers: HEADERS,
  })
}

/** Reads tenant state (for assertions on what the backend now sees). */
export async function getTenant(
  tenantId: string
): Promise<Record<string, unknown>> {
  const res = await fetch(
    `${REST}/tenants?id=eq.${tenantId}&select=*`,
    { headers: HEADERS }
  )
  const rows = (await res.json()) as Record<string, unknown>[]
  return rows[0]
}

/** Seeds a document row for manifestation tests. Returns the document ID. */
export async function seedDocument(
  tenantId: string,
  cnpj: string,
  overrides: Record<string, unknown> = {}
): Promise<string> {
  const payload = {
    tenant_id: tenantId,
    cnpj,
    tipo: "NFE",
    chave_acesso:
      overrides.chave_acesso ||
      `3526${cnpj}55001${Math.floor(Math.random() * 1e9)
        .toString()
        .padStart(9, "0")}1${Math.floor(Math.random() * 1e9)
        .toString()
        .padStart(9, "0")}`.slice(0, 44),
    nsu: overrides.nsu || "000000000000001",
    xml_content: overrides.xml_content || null,
    status: overrides.status || "pending_manifestacao",
    is_resumo: overrides.is_resumo ?? true,
    manifestacao_status: overrides.manifestacao_status || "pendente",
    fetched_at: overrides.fetched_at || new Date().toISOString(),
    ...overrides,
  }

  const res = await fetch(`${REST}/documents`, {
    method: "POST",
    headers: HEADERS,
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`seedDocument failed: ${res.status} ${text}`)
  }
  const data = await res.json()
  return data[0].id
}

/** Reads a document by ID (for assertions on manifestacao_status). */
export async function getDocument(
  docId: string
): Promise<Record<string, unknown>> {
  const res = await fetch(
    `${REST}/documents?id=eq.${docId}&select=*`,
    { headers: HEADERS }
  )
  const rows = (await res.json()) as Record<string, unknown>[]
  return rows[0]
}
