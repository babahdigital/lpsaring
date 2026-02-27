import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

import { resolveAccessStatusFromUser } from '../utils/authAccess'

type ContractCase = {
  name: string
  user: Record<string, unknown>
  expected_frontend: 'ok' | 'blocked' | 'inactive' | 'expired' | 'habis' | 'fup'
}

function loadContractCases(): ContractCase[] {
  const thisFile = fileURLToPath(import.meta.url)
  const thisDir = dirname(thisFile)
  const contractPath = resolve(thisDir, '../../contracts/access_status_parity_cases.json')
  const content = readFileSync(contractPath, 'utf-8')
  const parsed = JSON.parse(content)

  if (!Array.isArray(parsed))
    throw new Error('Parity contract must be an array')

  return parsed as ContractCase[]
}

describe('access-status parity contract', () => {
  const cases = loadContractCases()

  it('contract must contain cases', () => {
    expect(cases.length).toBeGreaterThan(0)
  })

  for (const testCase of cases) {
    it(`matches frontend status for case: ${testCase.name}`, () => {
      const actual = resolveAccessStatusFromUser(testCase.user as any)
      expect(actual).toBe(testCase.expected_frontend)
    })
  }
})
