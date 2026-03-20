import type { MultiLifeCase } from '../types'
import { RAIN_WAREHOUSE_CASE } from './rain-warehouse'

const CASE_MAP: Record<string, MultiLifeCase> = {
  'rain-warehouse': RAIN_WAREHOUSE_CASE,
}

export function getCase(id: string): MultiLifeCase | undefined {
  return CASE_MAP[id]
}

export function listCases(): MultiLifeCase[] {
  return Object.values(CASE_MAP)
}
