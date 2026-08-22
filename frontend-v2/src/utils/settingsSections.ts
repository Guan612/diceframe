export type SettingsSectionId = 'api' | 'models' | 'network' | 'sharing' | 'botapi' | 'appearance' | 'access' | 'advanced' | 'about'

const SETTINGS_SECTION_IDS = new Set<SettingsSectionId>([
  'api',
  'models',
  'network',
  'sharing',
  'botapi',
  'appearance',
  'access',
  'advanced',
  'about',
])

export function normalizeSettingsSection(value: string): SettingsSectionId | null {
  if (value === 'memory') return 'models'
  return SETTINGS_SECTION_IDS.has(value as SettingsSectionId) ? value as SettingsSectionId : null
}
