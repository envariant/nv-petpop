<script setup lang="ts">
const emit = defineEmits<{ pick: [string] }>();
function pick(e: PointerEvent) {
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width - 0.5;
  const y = (e.clientY - r.top) / r.height - 0.5;
  const hue = ((Math.atan2(y, x) * 180) / Math.PI + 450) % 360;
  const sat = Math.min(1, Math.hypot(x, y) * 2);
  const l = 0.62 - sat * 0.2;
  const a = sat * Math.min(l, 1 - l);
  const f = (n: number) => {
    const k = (n + hue / 30) % 12;
    return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
  };
  emit('pick', `#${[f(0), f(8), f(4)].map((v) => v.toString(16).padStart(2, '0')).join('')}`.toUpperCase());
}
</script>

<template>
  <div data-testid="colour-wheel" class="h-48 w-48 shrink-0 rounded-full shadow-soft"
    style="background: radial-gradient(circle, #d8cfc6 0%, transparent 70%), conic-gradient(from 90deg, red, yellow, lime, cyan, blue, magenta, red)"
    @pointerdown="pick" />
</template>
