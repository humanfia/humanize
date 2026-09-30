<script setup lang="ts">
// A card's picture of a flow: its own scene, in the same grammar as its page, without words.
// At rest it is the whole run; while the card is hovered or focused it plays, quickly, and
// never under reduced motion.
import { gsap } from 'gsap'
import { computed, onUnmounted, reactive, ref } from 'vue'

import { SCENES } from '../../flows'
import FlowScene from './FlowScene.vue'
import { card, cardHeight, lay } from './stage'

const props = defineProps<{ scene: string }>()

const layout = computed(() => lay(SCENES[props.scene]))
const view = computed(() => ({ w: 300, h: cardHeight(layout.value) }))
const cam = computed(() => card(layout.value, view.value))
const clock = reactive({ t: 0 })
const moving = ref(false)
let tween: gsap.core.Tween | null = null

function play() {
  if (moving.value || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const L = layout.value
  moving.value = true
  tween = gsap.fromTo(
    clock,
    { t: -0.2 },
    { t: L.firedAt + 0.8, duration: (L.firedAt + 1) * 0.75, ease: 'none', repeat: -1, repeatDelay: 0.4 },
  )
}

function stop() {
  tween?.kill()
  tween = null
  moving.value = false
}

defineExpose({ play, stop })
onUnmounted(stop)
</script>

<template>
  <FlowScene
    class="thumb"
    :lay="layout"
    :view="view"
    :cam="cam"
    :t="moving ? clock.t : layout.firedAt + 1"
    :mode="moving ? 'play' : 'still'"
    bare
  />
</template>
