// A lofi "late night desk" drawn with the five brand colours only.
export function HeroScene() {
  return (
    <svg className="scene" viewBox="0 0 480 400" role="img" aria-label="A cozy desk by a night window">
      <rect width="480" height="400" rx="26" fill="var(--scene-bg)" />
      {/* window */}
      <rect x="60" y="34" width="220" height="190" rx="14" fill="var(--c-deep-teal)" stroke="var(--c-cream)" strokeWidth="5" />
      <path d="M170 34v190M60 129h220" stroke="var(--c-cream)" strokeWidth="4" />
      <circle cx="226" cy="82" r="22" fill="var(--c-cream)" />
      <circle cx="237" cy="75" r="19" fill="var(--c-deep-teal)" />
      {[
        [96, 70], [128, 100], [100, 168], [206, 160], [250, 118], [140, 58],
      ].map(([x, y]) => (
        <circle key={`${x}-${y}`} className="scene__star" cx={x} cy={y} r="2.2" fill="var(--c-cream)" />
      ))}
      <path d="M62 224v-40l34-30 28 20 40-44 48 52 24-18v60z" fill="var(--c-plum)" opacity=".75" />
      {/* lamp glow + lamp */}
      <circle cx="400" cy="150" r="90" fill="var(--c-pink)" opacity=".16" />
      <path d="M372 112l36-18 14 28-36 18z" fill="var(--c-pink)" stroke="var(--c-cream)" strokeWidth="3" />
      <path d="M396 130l-14 70M382 200h40" stroke="var(--c-cream)" strokeWidth="5" strokeLinecap="round" />
      {/* desk */}
      <rect x="20" y="288" width="440" height="22" rx="8" fill="var(--c-plum)" />
      <rect x="44" y="310" width="14" height="70" fill="var(--c-plum)" />
      <rect x="422" y="310" width="14" height="70" fill="var(--c-plum)" />
      {/* books */}
      <rect x="62" y="238" width="86" height="22" rx="4" fill="var(--c-teal)" stroke="var(--c-cream)" strokeWidth="3" />
      <rect x="70" y="262" width="96" height="26" rx="4" fill="var(--c-pink)" stroke="var(--c-cream)" strokeWidth="3" />
      {/* laptop */}
      <rect x="196" y="204" width="150" height="84" rx="8" fill="var(--scene-screen)" stroke="var(--c-cream)" strokeWidth="4" />
      <rect x="206" y="214" width="130" height="64" rx="4" fill="var(--c-deep-teal)" />
      <path d="M216 228h70M216 242h96M216 256h54" stroke="var(--c-cream)" strokeWidth="4" strokeLinecap="round" opacity=".85" />
      <path className="scene__cursor" d="M276 256h10" stroke="var(--c-pink)" strokeWidth="4" strokeLinecap="round" />
      <path d="M180 288h182l-10 8H190z" fill="var(--c-cream)" />
      {/* mug */}
      <rect x="378" y="256" width="34" height="32" rx="6" fill="var(--c-cream)" />
      <path d="M412 264h8a8 8 0 0 1 0 16h-8" fill="none" stroke="var(--c-cream)" strokeWidth="4" />
      <path className="scene__steam" d="M388 246c-6-8 6-12 0-20M400 246c-6-8 6-12 0-20" fill="none" stroke="var(--c-cream)" strokeWidth="3" strokeLinecap="round" opacity=".6" />
    </svg>
  )
}
