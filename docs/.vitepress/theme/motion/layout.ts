// A scene drawn for a 16:9 screen is unreadable squeezed onto a phone, so a scene may keep two
// layouts: wide, and narrow for phone width. `useNarrow` says which one applies, and calls
// `changed` -- the scene's `rebuild` -- once the markup has been redrawn for the other one, so
// the timeline is cut again against the new positions.
import { nextTick, onMounted, onUnmounted, ref, type Ref } from 'vue'

export const NARROW = '(max-width: 640px)'

export function useNarrow(changed?: () => void): Ref<boolean> {
  const narrow = ref(false)
  let query: MediaQueryList | undefined
  const listen = () => {
    narrow.value = query!.matches
    if (changed) void nextTick(changed)
  }
  onMounted(() => {
    query = window.matchMedia(NARROW)
    narrow.value = query.matches
    query.addEventListener('change', listen)
  })
  onUnmounted(() => query?.removeEventListener('change', listen))
  return narrow
}
