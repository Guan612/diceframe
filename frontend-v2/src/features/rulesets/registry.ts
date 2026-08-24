import { defineAsyncComponent, type Component } from 'vue'

type ExperienceLoader = () => Promise<{ default: Component }>

const loaders: Record<string, ExperienceLoader> = {
  dnd2024: () => import('./dnd2024/create/Dnd2024CharacterBuilder.vue'),
}
const components = new Map<string, Component>()

export function resolveRulesetExperience(profile: string): Component | null {
  const loader = loaders[profile]
  if (!loader) return null
  const cached = components.get(profile)
  if (cached) return cached
  const component = defineAsyncComponent(loader)
  components.set(profile, component)
  return component
}
