<script setup lang="ts">
// A recorded screen, played where it is read. Nothing is fetched until the video is near the
// window (`preload="none"` and a poster), it plays muted while it is on screen and pauses when it
// leaves, and a reader who asked for less motion gets the poster and the play button instead.
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps<{ src: string; poster: string; title: string; caption?: string }>()

const video = ref<HTMLVideoElement | null>(null)
let io: IntersectionObserver | null = null
onMounted(() => {
  const el = video.value
  if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  io = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting) el.play().catch(() => {})
      else el.pause()
    },
    { threshold: 0.5 },
  )
  io.observe(el)
})
onBeforeUnmount(() => io?.disconnect())
</script>

<template>
  <figure class="demo">
    <div class="demo-frame">
      <video
        ref="video"
        :src="src"
        :poster="poster"
        :aria-label="title"
        preload="none"
        muted
        loop
        playsinline
        controls
        width="996"
        height="670"
      />
    </div>
    <figcaption v-if="caption">{{ caption }}</figcaption>
  </figure>
</template>

<style scoped>
.demo {
  margin: 24px 0;
}
.demo-frame {
  border: 2px solid var(--vp-c-text-1);
  box-shadow: 6px 6px 0 var(--hf-cyan);
  background: #0f1418;
  line-height: 0;
}
.demo video {
  width: 100%;
  height: auto;
  aspect-ratio: 996 / 670;
  display: block;
}
.demo figcaption {
  margin-top: 12px;
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--vp-c-text-2);
}
</style>
