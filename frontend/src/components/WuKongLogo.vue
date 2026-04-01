<script setup>
import { computed } from 'vue'

const props = defineProps({
  size: {
    type: [Number, String],
    default: 36
  }
})

const iconSize = computed(() => {
  return typeof props.size === 'number' ? `${props.size}px` : props.size
})
</script>

<template>
  <div class="wukong-logo" :style="{ width: iconSize, height: iconSize }">
    <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bgGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:#1f2937"/>
          <stop offset="100%" style="stop-color:#111827"/>
        </linearGradient>
        <linearGradient id="goldGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" style="stop-color:#fbbf24"/>
          <stop offset="50%" style="stop-color:#fcd34d"/>
          <stop offset="100%" style="stop-color:#fbbf24"/>
        </linearGradient>
        <linearGradient id="redCandleGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" style="stop-color:#dc2626"/>
          <stop offset="50%" style="stop-color:#ef4444"/>
          <stop offset="100%" style="stop-color:#dc2626"/>
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="0.8" result="coloredBlur"/>
          <feMerge>
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>
      
      <rect x="2" y="2" width="44" height="44" rx="10" fill="url(#bgGradient)"/>
      <rect x="2" y="2" width="44" height="44" rx="10" stroke="#374151" stroke-width="1"/>
      
      <g filter="url(#glow)">
        <line x1="5" y1="8" x2="5" y2="40" stroke="url(#goldGradient)" stroke-width="2" stroke-linecap="round"/>
        <rect x="3" y="12" width="4" height="8" rx="1" fill="url(#goldGradient)"/>
        <rect x="3" y="28" width="4" height="8" rx="1" fill="url(#goldGradient)"/>
        
        <line x1="11" y1="8" x2="11" y2="40" stroke="url(#goldGradient)" stroke-width="2" stroke-linecap="round"/>
        <rect x="9" y="10" width="4" height="10" rx="1" fill="url(#goldGradient)"/>
        
        <line x1="17" y1="8" x2="17" y2="40" stroke="url(#goldGradient)" stroke-width="2" stroke-linecap="round"/>
        <rect x="15" y="14" width="4" height="8" rx="1" fill="url(#goldGradient)"/>
        <rect x="15" y="28" width="4" height="8" rx="1" fill="url(#goldGradient)"/>
        
        <line x1="23" y1="8" x2="23" y2="40" stroke="url(#goldGradient)" stroke-width="2" stroke-linecap="round"/>
        <rect x="21" y="10" width="4" height="10" rx="1" fill="url(#goldGradient)"/>
      </g>
      
      <g filter="url(#glow)">
        <line x1="30" y1="6" x2="30" y2="42" stroke="url(#redCandleGradient)" stroke-width="2.5" stroke-linecap="round"/>
        <rect x="27" y="14" width="6" height="18" rx="1.5" fill="url(#redCandleGradient)"/>
        
        <path d="M36 14L44 14" stroke="#22c55e" stroke-width="2.5" stroke-linecap="round"/>
        <path d="M40 10L44 14L40 18" stroke="#22c55e" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
        
        <path d="M36 34L44 34" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round"/>
        <path d="M40 30L44 34L40 38" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.wukong-logo {
  display: flex;
  align-items: center;
  justify-content: center;
}

.wukong-logo svg {
  width: 100%;
  height: 100%;
}
</style>
