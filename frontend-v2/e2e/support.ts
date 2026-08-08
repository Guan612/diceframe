import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

export const accessToken = () => {
  const dataDir = process.env.DICEFRAME_E2E_DATA_DIR
  if (!dataDir) throw new Error('DICEFRAME_E2E_DATA_DIR is required; run E2E through npm run test:e2e')
  return readFileSync(resolve(dataDir, 'access_token.txt'), 'utf8').trim()
}
