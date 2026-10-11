import { useMemo } from 'react'
import type { Animal } from './animal'

// 16 columns, one letter per pixel. K outline, O orange, W cream, P pink (corgi);
// B brown, D dark brown, L light brown (capybara).
const FACES: Record<Animal, { rows: string[]; palette: Record<string, string> }> = {
  corgi: {
    palette: { K: '#1a1220', O: '#e2913d', W: '#f6e3c6', P: '#e58fa8' },
    rows: [
      '................',
      '.KK..........KK.',
      'KOOK........KOOK',
      'KOPOK......KOPOK',
      'KOPOKKKKKKKKOPOK',
      '.KOOOOOOOOOOOOK.',
      '.KOOOOOWWOOOOOK.',
      '.KOOKOOWWOOKOOK.',
      '.KOOOOWWWWOOOOK.',
      '.KOOOWWWWWWOOOK.',
      '..KOWWWWWWWWOK..',
      '..KKWWWKKWWWKK..',
      '..KWWWWPPWWWWK..',
      '..KKKKKKKKKKKK..',
    ],
  },
  capybara: {
    palette: { K: '#1a1220', B: '#a9744f', D: '#7d5236', L: '#cfa27a' },
    rows: [
      '................',
      '................',
      '..KKK......KKK..',
      '.KDDDK....KDDDK.',
      '.KDDDKKKKKKDDDK.',
      '..KKBBBBBBBBKK..',
      '.KBBBBBBBBBBBBK.',
      '.KBBKBBBBBBKBBK.',
      '.KBBBBBBBBBBBBK.',
      '.KBBLLLLLLLLBBK.',
      '.KBLLLLLLLLLLBK.',
      '.KBLLKKLLKKLLBK.',
      '.KBLLLLLLLLLLBK.',
      '..KBLLLLLLLLBK..',
      '...KKKKKKKKKK...',
    ],
  },
}

/** A pixel-art face. `busy` makes it bob while it is working on an answer. */
export function PixelAnimal({ animal, busy = false }: { animal: Animal; busy?: boolean }) {
  const { rows, palette } = FACES[animal]
  const cells = useMemo(
    () =>
      rows.flatMap((row, y) =>
        [...row].flatMap((ch, x) => (palette[ch] ? [<rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill={palette[ch]} />] : [])),
      ),
    [rows, palette],
  )
  return (
    <svg
      className={`pixel-animal ${busy ? 'pixel-animal--busy' : ''}`}
      viewBox={`0 0 16 ${rows.length}`}
      shapeRendering="crispEdges"
      aria-hidden="true"
    >
      {cells}
    </svg>
  )
}
