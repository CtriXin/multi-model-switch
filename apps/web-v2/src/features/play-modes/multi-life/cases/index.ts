import type { MultiLifeCase } from '../types'
import { RAIN_WAREHOUSE_CASE } from './rain-warehouse'
import { MISSING_PAINTER_CASE } from './missing-painter'
import { SNOW_MANSION_CASE } from './snow-mansion'
import { FINAL_FLIGHT_CASE } from './final-flight'
import { ANTIQUE_DEALER_CASE } from './antique-dealer'
import { LAB_ACCIDENT_CASE } from './lab-accident'
import { ENDLESS_AUTUMN_CASE } from './endless-autumn'
import { HIDDEN_CORNER_CASE } from './hidden-corner'
import { RESET_LOOP_CASE } from './reset-loop'
import { SILENT_TRUTH_CASE } from './silent-truth'
import { CRIMINAL_RISE_CASE } from './criminal-rise'

const CASE_MAP: Record<string, MultiLifeCase> = {
  'rain-warehouse': RAIN_WAREHOUSE_CASE,
  'missing-painter': MISSING_PAINTER_CASE,
  'snow-mansion': SNOW_MANSION_CASE,
  'final-flight': FINAL_FLIGHT_CASE,
  'antique-dealer': ANTIQUE_DEALER_CASE,
  'lab-accident': LAB_ACCIDENT_CASE,
  'endless-autumn': ENDLESS_AUTUMN_CASE,
  'hidden-corner': HIDDEN_CORNER_CASE,
  'reset-loop': RESET_LOOP_CASE,
  'silent-truth': SILENT_TRUTH_CASE,
  'criminal-rise': CRIMINAL_RISE_CASE,
}

export function getCase(id: string): MultiLifeCase | undefined {
  return CASE_MAP[id]
}

export function listCases(): MultiLifeCase[] {
  return Object.values(CASE_MAP)
}
