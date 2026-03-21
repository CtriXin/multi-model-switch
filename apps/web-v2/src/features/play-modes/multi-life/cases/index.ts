import type { MultiLifeCase } from '../types'
import { RAIN_WAREHOUSE_CASE } from './rain-warehouse'
import { MISSING_PAINTER_CASE } from './missing-painter'
import { SNOW_MANSION_CASE } from './snow-mansion'
import { FINAL_FLIGHT_CASE } from './final-flight'
import { ANTIQUE_DEALER_CASE } from './antique-dealer'
import { LAB_ACCIDENT_CASE } from './lab-accident'

const CASE_MAP: Record<string, MultiLifeCase> = {
  'rain-warehouse': RAIN_WAREHOUSE_CASE,
  'missing-painter': MISSING_PAINTER_CASE,
  'snow-mansion': SNOW_MANSION_CASE,
  'final-flight': FINAL_FLIGHT_CASE,
  'antique-dealer': ANTIQUE_DEALER_CASE,
  'lab-accident': LAB_ACCIDENT_CASE,
}

export function getCase(id: string): MultiLifeCase | undefined {
  return CASE_MAP[id]
}

export function listCases(): MultiLifeCase[] {
  return Object.values(CASE_MAP)
}
