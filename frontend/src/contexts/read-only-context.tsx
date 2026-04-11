"use client"

import { createContext, useContext, type ReactNode } from "react"
import { useTrial } from "@/hooks/use-trial"

export type ReadOnlyReason = "time" | "cap" | null

interface ReadOnlyState {
  isReadOnly: boolean
  reason: ReadOnlyReason
  blockedAt: string | null
}

export const ReadOnlyContext = createContext<ReadOnlyState>({
  isReadOnly: false,
  reason: null,
  blockedAt: null,
})

export function useReadOnly(): ReadOnlyState {
  return useContext(ReadOnlyContext)
}

/**
 * Provides read-only state derived from the trial hook.
 *
 * isReadOnly when:
 *  - subscription_status === "expired"; OR
 *  - trial is active but trial_blocked_reason is set (cap reached before
 *    the 10-day window elapsed).
 */
export function ReadOnlyProvider({ children }: { children: ReactNode }) {
  const trial = useTrial() as ReturnType<typeof useTrial> & {
    trialBlockedReason?: ReadOnlyReason
    trialBlockedAt?: string | null
  }

  const reason: ReadOnlyReason = trial.trialBlockedReason ?? null
  const blockedAt = trial.trialBlockedAt ?? null

  const timeExpired =
    trial.subscriptionStatus === "expired" ||
    (!trial.trialActive && trial.subscriptionStatus === "trial")

  const isReadOnly = !trial.loading && (timeExpired || reason !== null)

  // If the backend didn't tell us why, infer from state.
  const effectiveReason: ReadOnlyReason = isReadOnly
    ? reason ?? (timeExpired ? "time" : null)
    : null

  return (
    <ReadOnlyContext.Provider
      value={{ isReadOnly, reason: effectiveReason, blockedAt }}
    >
      {children}
    </ReadOnlyContext.Provider>
  )
}
