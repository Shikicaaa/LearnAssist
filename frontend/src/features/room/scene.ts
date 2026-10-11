import {
  AmbientLight,
  BackSide,
  BoxGeometry,
  CanvasTexture,
  CircleGeometry,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DataTexture,
  DirectionalLight,
  Group,
  Mesh,
  MeshBasicMaterial,
  MeshToonMaterial,
  NearestFilter,
  OrthographicCamera,
  PCFShadowMap,
  PointLight,
  RedFormat,
  Scene,
  SRGBColorSpace,
  Vector3,
  WebGLRenderer,
} from 'three'
import { onTyping } from './typing'

/**
 * A small isometric lofi room: a corgi on a cushion types on a laptop.
 * Everything is built from boxes and cylinders, so no model files are needed.
 *
 * The room faces -x (the corgi looks at the laptop on the left wall); the camera looks from
 * the front-right, a little more from the front than a true 45 degrees, so the corgi is seen
 * in profile and the laptop screen stays visible.
 */

const PALETTE = {
  floor: 0x5a3f5e,
  rug: 0xc9786a,
  rugInner: 0xe8b88a,
  wallBack: 0x3c2f55,
  wallLeft: 0x483a66,
  wood: 0x8a5a3c,
  woodDark: 0x5e3b27,
  metal: 0xb9b2c8,
  keys: 0x2c2a3a,
  cushion: 0x6fb3a3,
  fur: 0xe2913d,
  furLight: 0xf6e3c6,
  furDark: 0xb86a24,
  black: 0x1d1620,
  pink: 0xe58fa8,
  lamp: 0xffc873,
  plant: 0x4f9a6b,
  pot: 0xc0674f,
  mug: 0xf3ede0,
  book1: 0xd4605a,
  book2: 0x5f8fd0,
  book3: 0xe7c35c,
}

export type RoomTheme = 'light' | 'dark'

/** Everything that differs between day and night. */
const LOOK = {
  dark: {
    ambient: [0x6c6cb0, 0.62],
    sun: [0x8c98ff, 0.5],
    lamp: 16,
    glow: 2.2,
    sky: 0x151545,
    disc: 0xfff1c9,
    discScale: 1,
    stars: true,
    floor: 0x4a3550,
    wallBack: 0x2f2548,
    wallLeft: 0x382d58,
    lampShade: 0xffc873,
  },
  light: {
    ambient: [0xfff4e2, 1.35],
    sun: [0xfff0cc, 2.1],
    lamp: 0,
    glow: 0.35,
    sky: 0x86cdf5,
    disc: 0xffd75e,
    discScale: 1.5,
    stars: false,
    floor: 0xc99c6c,
    wallBack: 0xf4dcc2,
    wallLeft: 0xebcfb2,
    lampShade: 0xe3cfa6,
  },
} as const

// Three flat light steps: the cel-shaded look of a small indie game.
const TOON_STEPS = new DataTexture(new Uint8Array([95, 175, 255]), 3, 1, RedFormat)
TOON_STEPS.minFilter = NearestFilter
TOON_STEPS.magFilter = NearestFilter
TOON_STEPS.needsUpdate = true

const OUTLINE = new MeshBasicMaterial({ color: 0x1a1220, side: BackSide })

const SCREEN_W = 256
const SCREEN_H = 160
const CODE_COLORS = ['#7fe3c1', '#f6c177', '#c4a7e7', '#9ccfd8', '#eb6f92']

const toon = (color: number) => new MeshToonMaterial({ color, gradientMap: TOON_STEPS })

/** A dark rim around a mesh: its back faces, grown by `t` on every side. */
function outlined<T extends Mesh>(mesh: T, t = 0.045): T {
  mesh.geometry.computeBoundingBox()
  const size = mesh.geometry.boundingBox!.getSize(new Vector3())
  const rim = new Mesh(mesh.geometry, OUTLINE)
  rim.scale.set(1 + (2 * t) / (size.x || 1), 1 + (2 * t) / (size.y || 1), 1 + (2 * t) / (size.z || 1))
  mesh.add(rim)
  return mesh
}

function box(w: number, h: number, d: number, color: number, x = 0, y = 0, z = 0, rim = true): Mesh {
  const mesh = new Mesh(new BoxGeometry(w, h, d), toon(color))
  mesh.position.set(x, y, z)
  mesh.castShadow = true
  mesh.receiveShadow = true
  return rim ? outlined(mesh) : mesh
}

function cylinder(rTop: number, rBottom: number, h: number, color: number, segments = 16, rim = true): Mesh {
  const mesh = new Mesh(new CylinderGeometry(rTop, rBottom, h, segments), toon(color))
  mesh.castShadow = true
  mesh.receiveShadow = true
  return rim ? outlined(mesh) : mesh
}

function cone(r: number, h: number, color: number, x: number, y: number, z: number): Mesh {
  const mesh = new Mesh(new ConeGeometry(r, h, 4), toon(color))
  mesh.position.set(x, y, z)
  mesh.rotation.y = Math.PI / 4
  mesh.castShadow = true
  return outlined(mesh)
}

// --- the laptop screen: tiny code that scrolls when you type ------------------------------------

class Screen {
  readonly texture: CanvasTexture
  private readonly canvas = document.createElement('canvas')
  private readonly ctx: CanvasRenderingContext2D
  private lines: { width: number; indent: number; color: string }[] = []

  constructor() {
    this.canvas.width = SCREEN_W
    this.canvas.height = SCREEN_H
    this.ctx = this.canvas.getContext('2d')!
    this.texture = new CanvasTexture(this.canvas)
    this.texture.colorSpace = SRGBColorSpace
    this.texture.magFilter = NearestFilter
    for (let i = 0; i < 9; i++) this.addLine()
    this.draw()
  }

  addLine() {
    this.lines.push({
      width: 30 + Math.random() * 130,
      indent: Math.floor(Math.random() * 3) * 16,
      color: CODE_COLORS[Math.floor(Math.random() * CODE_COLORS.length)],
    })
    if (this.lines.length > 9) this.lines.shift()
    this.draw()
  }

  private draw() {
    const { ctx } = this
    ctx.fillStyle = '#1b1830'
    ctx.fillRect(0, 0, SCREEN_W, SCREEN_H)
    ctx.fillStyle = '#2a2644'
    ctx.fillRect(0, 0, SCREEN_W, 14)
    ;['#eb6f92', '#f6c177', '#7fe3c1'].forEach((c, i) => {
      ctx.fillStyle = c
      ctx.fillRect(8 + i * 12, 4, 6, 6)
    })
    this.lines.forEach((line, i) => {
      ctx.fillStyle = line.color
      ctx.fillRect(14 + line.indent, 24 + i * 15, line.width, 7)
    })
    this.texture.needsUpdate = true
  }
}

// --- sparkles that float up from the keyboard ------------------------------------------------

interface Spark {
  mesh: Mesh
  age: number
  life: number
  vx: number
  vz: number
}

// --- the room ---------------------------------------------------------------------------------

export interface Room {
  setTheme: (theme: RoomTheme) => void
  dispose: () => void
}

export interface RoomOptions {
  /** 'room': the whole isometric room. 'corner': just the corgi, its desk and laptop on a small slab. */
  view?: 'room' | 'corner'
  reducedMotion: boolean
  theme: RoomTheme
  /** Called when the corgi's head moves on screen (CSS pixels, relative to the host). */
  onHead?: (point: { x: number; y: number }) => void
}

// The camera looks at the room from the front-right. The target sits above the room's middle, so
// the room lands in the lower part of the frame and leaves headroom for the speech bubble.
const CAMERA_OFFSET = new Vector3(7.6, 5.7, 11.2)
const FRAMES = {
  room: { target: new Vector3(-0.6, 2.7, -0.2), halfHeight: 5.2, minHalfWidth: 6.4 },
  corner: { target: new Vector3(-2.1, 1.2, 0.1), halfHeight: 2.05, minHalfWidth: 2.6 },
}

export function createRoom(
  host: HTMLElement,
  { view = 'room', reducedMotion, theme: initialTheme, onHead }: RoomOptions,
): Room {
  const frameOf = FRAMES[view]
  // No antialiasing and a canvas rendered smaller than it is shown: the chunky pixels are the look.
  const renderer = new WebGLRenderer({ antialias: false, alpha: true, powerPreference: 'low-power' })
  renderer.setPixelRatio(1)
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = PCFShadowMap
  renderer.outputColorSpace = SRGBColorSpace
  host.appendChild(renderer.domElement)
  renderer.domElement.style.display = 'block'

  const scene = new Scene()
  const camera = new OrthographicCamera(-5, 5, frameOf.halfHeight, -frameOf.halfHeight, 0.1, 80)
  camera.position.copy(frameOf.target).add(CAMERA_OFFSET)
  camera.lookAt(frameOf.target)

  const ambient = new AmbientLight(0xffffff, 1)
  scene.add(ambient)
  const sun = new DirectionalLight(0xffffff, 1)
  sun.position.set(4, 8, 5)
  sun.castShadow = true
  sun.shadow.mapSize.set(1024, 1024)
  Object.assign(sun.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6 })
  scene.add(sun)
  const lampLight = new PointLight(PALETTE.lamp, 16, 7, 1.6)
  lampLight.position.set(-2.3, 2.6, -2.3)
  scene.add(lampLight)

  const world = new Group()
  scene.add(world)

  // shell: floor and two walls
  const floor = box(7, 0.3, 7, PALETTE.floor, 0, -0.15, 0)
  const wallBack = box(7, 4, 0.3, PALETTE.wallBack, 0, 2, -3.65)
  const wallLeft = box(0.3, 4, 7, PALETTE.wallLeft, -3.65, 2, 0)
  world.add(floor, wallBack, wallLeft)
  const rug = cylinder(2.1, 2.1, 0.04, PALETTE.rug, 40, false)
  rug.position.set(0.2, 0.02, 0.2)
  const rugInner = cylinder(1.3, 1.3, 0.05, PALETTE.rugInner, 40, false)
  rugInner.position.set(0.2, 0.03, 0.2)
  world.add(rug, rugInner)

  // window on the back wall: night sky with a moon, or a day sky with a sun
  const windowFrame = box(2.2, 1.6, 0.12, PALETTE.woodDark, 0.4, 2.5, -3.45)
  const sky = new Mesh(new BoxGeometry(1.9, 1.3, 0.05), new MeshBasicMaterial({ color: 0x1a1a4a }))
  sky.position.set(0.4, 2.5, -3.38)
  const moon = new Mesh(new CircleGeometry(0.22, 24), new MeshBasicMaterial({ color: 0xfff1c9 }))
  moon.position.set(0.9, 2.75, -3.34)
  world.add(windowFrame, sky, moon)
  const stars: Mesh[] = []
  for (const [sx, sy] of [[-0.2, 2.9], [0.1, 2.35], [0.55, 2.95], [-0.3, 2.2], [1.1, 2.3]]) {
    const star = new Mesh(new CircleGeometry(0.045, 6), new MeshBasicMaterial({ color: 0xffffff }))
    star.position.set(sx, sy, -3.34)
    stars.push(star)
    world.add(star)
  }

  // shelf with books on the back wall
  const shelf = [
    box(1.5, 0.08, 0.5, PALETTE.wood, -1.9, 2.1, -3.35),
    box(0.18, 0.6, 0.36, PALETTE.book1, -2.4, 2.42, -3.35),
    box(0.16, 0.5, 0.36, PALETTE.book2, -2.2, 2.38, -3.35),
    box(0.2, 0.66, 0.36, PALETTE.book3, -2.0, 2.45, -3.35),
  ]
  world.add(...shelf)
  const pot = cylinder(0.2, 0.15, 0.28, PALETTE.pot)
  pot.position.set(-1.4, 2.28, -3.35)
  const plant = new Mesh(new ConeGeometry(0.3, 0.55, 6), toon(PALETTE.plant))
  plant.position.set(-1.4, 2.68, -3.35)
  plant.castShadow = true
  outlined(plant)
  world.add(pot, plant)

  // The corner view keeps only the corgi's corner: no walls, window, shelf or rug, and a small slab.
  if (view === 'corner') {
    for (const hidden of [wallBack, wallLeft, rug, rugInner, windowFrame, sky, moon, pot, plant, ...shelf, ...stars]) {
      hidden.visible = false
    }
    floor.visible = false
  }

  // desk against the left wall, with a mug and a lamp
  const DESK_Y = 1.05
  world.add(box(1.1, 0.12, 3.4, PALETTE.wood, -2.95, DESK_Y, -0.3))
  for (const lz of [-1.85, 1.25]) {
    world.add(box(0.12, DESK_Y, 0.12, PALETTE.woodDark, -2.5, DESK_Y / 2, lz))
    world.add(box(0.12, DESK_Y, 0.12, PALETTE.woodDark, -3.35, DESK_Y / 2, lz))
  }
  const mug = cylinder(0.11, 0.1, 0.2, PALETTE.mug)
  mug.position.set(-3.1, DESK_Y + 0.16, 1.0)
  world.add(mug)
  const lampBase = cylinder(0.2, 0.24, 0.06, PALETTE.woodDark)
  lampBase.position.set(-3.3, DESK_Y + 0.09, -1.6)
  const lampArm = box(0.05, 0.9, 0.05, PALETTE.metal, -3.3, DESK_Y + 0.55, -1.6)
  const lampHead = new Mesh(
    new ConeGeometry(0.28, 0.3, 14, 1, true),
    new MeshBasicMaterial({ color: PALETTE.lamp, side: 2 }),
  )
  lampHead.position.set(-3.1, DESK_Y + 1.05, -1.6)
  lampHead.rotation.z = -0.35
  const lampMaterial = lampHead.material as MeshBasicMaterial
  world.add(lampBase, lampArm, lampHead)

  // laptop: base on the desk, screen at the wall side, facing +x (towards the corgi)
  const laptop = new Group()
  laptop.position.set(-2.85, DESK_Y + 0.06, 0.1)
  laptop.add(box(0.75, 0.05, 1.15, PALETTE.metal, 0, 0.025, 0))
  const keysGroup = new Group()
  const keyMeshes: Mesh[] = []
  for (let r = 0; r < 4; r++) {
    for (let c = 0; c < 7; c++) {
      const key = box(0.1, 0.03, 0.11, PALETTE.keys, -0.2 + r * 0.13, 0.065, -0.46 + c * 0.155)
      keyMeshes.push(key)
      keysGroup.add(key)
    }
  }
  laptop.add(keysGroup)
  const lid = new Group()
  lid.position.set(-0.36, 0.05, 0)
  lid.rotation.z = -0.32 // leans back, away from the corgi
  lid.add(box(0.05, 0.72, 1.15, PALETTE.metal, 0, 0.36, 0))
  const screen = new Screen()
  const display = new Mesh(new BoxGeometry(0.01, 0.62, 1.03), new MeshBasicMaterial({ map: screen.texture }))
  display.position.set(0.03, 0.36, 0)
  lid.add(display)
  laptop.add(lid)
  const glow = new PointLight(0x9fe8ff, 1.6, 3.5, 1.5)
  glow.position.set(0.6, 0.6, 0)
  laptop.add(glow)
  world.add(laptop)

  // cushion and the corgi
  const cushion = cylinder(0.8, 0.85, 0.5, PALETTE.cushion, 24)
  cushion.position.set(-1.7, 0.25, 0.1)
  world.add(cushion)

  if (view === 'corner') {
    // no room and no cushion: the corgi sits on a plain chair at the desk
    cushion.visible = false
    const seat = box(1.1, 0.1, 1.1, PALETTE.wood, -1.7, 0.45, 0.1)
    const back = box(0.1, 0.8, 1.1, PALETTE.wood, -1.2, 0.9, 0.1)
    world.add(seat, back)
    for (const [lx, lz] of [[-2.2, -0.4], [-2.2, 0.6], [-1.2, -0.4], [-1.2, 0.6]]) {
      world.add(box(0.1, 0.45, 0.1, PALETTE.woodDark, lx, 0.225, lz))
    }
  }

  const corgi = new Group()
  corgi.position.set(-1.7, 0.5, 0.1)
  world.add(corgi)

  // sitting: haunches low at the back, torso leaning up and forward (towards -x)
  const torso = new Group()
  torso.position.set(0.1, 0.3, 0)
  torso.rotation.z = 0.32
  corgi.add(torso)
  torso.add(box(0.74, 0.78, 0.7, PALETTE.fur, 0, 0.34, 0))
  torso.add(box(0.1, 0.6, 0.5, PALETTE.furLight, -0.37, 0.34, 0)) // chest
  const haunch = box(0.7, 0.34, 0.68, PALETTE.furDark, 0.28, 0.05, 0)
  corgi.add(haunch)
  const tail = box(0.16, 0.16, 0.16, PALETTE.furLight, 0.7, 0.2, 0)
  corgi.add(tail)

  const head = new Group()
  head.position.set(-0.32, 1.2, 0)
  head.rotation.y = 0.45 // glances at whoever is looking
  corgi.add(head)
  head.add(box(0.7, 0.58, 0.76, PALETTE.fur, 0, 0, 0))
  head.add(box(0.1, 0.3, 0.4, PALETTE.furLight, -0.36, -0.05, 0)) // muzzle blaze
  head.add(box(0.34, 0.22, 0.3, PALETTE.furLight, -0.46, -0.12, 0)) // snout
  head.add(box(0.07, 0.08, 0.12, PALETTE.black, -0.64, -0.03, 0)) // nose
  const eyes = new Group()
  eyes.add(box(0.05, 0.08, 0.08, PALETTE.black, -0.37, 0.1, 0.22))
  eyes.add(box(0.05, 0.08, 0.08, PALETTE.black, -0.37, 0.1, -0.22))
  head.add(eyes)
  const earL = cone(0.19, 0.5, PALETTE.fur, 0.0, 0.5, 0.26)
  const earR = cone(0.19, 0.5, PALETTE.fur, 0.0, 0.5, -0.26)
  const innerL = cone(0.1, 0.34, PALETTE.pink, -0.04, 0.48, 0.26)
  const innerR = cone(0.1, 0.34, PALETTE.pink, -0.04, 0.48, -0.26)
  head.add(earL, earR, innerL, innerR)
  head.add(box(0.14, 0.05, 0.2, PALETTE.pink, -0.56, -0.26, 0)) // tongue

  // front paws, resting on the keyboard
  const pawL = new Group()
  const pawR = new Group()
  for (const [paw, z] of [[pawL, 0.24], [pawR, -0.24]] as const) {
    paw.position.set(-0.78, 0.8, z)
    paw.add(box(0.7, 0.2, 0.2, PALETTE.fur, 0.05, 0.1, 0))
    paw.add(box(0.2, 0.16, 0.22, PALETTE.furLight, -0.33, 0.02, 0))
    corgi.add(paw)
  }

  // --- sparkles -------------------------------------------------------------------------------
  const sparks: Spark[] = []
  const sparkColors = [0x7fe3c1, 0xf6c177, 0xc4a7e7, 0xeb6f92]
  function spawnSpark() {
    if (view === 'corner') return // there the thoughts are drawn by the page, floating to the chat bar
    const mesh = new Mesh(
      new BoxGeometry(0.09, 0.09, 0.09),
      new MeshBasicMaterial({
        color: sparkColors[Math.floor(Math.random() * sparkColors.length)],
        transparent: true,
      }),
    )
    mesh.position.set(-2.4 + Math.random() * 0.3, DESK_Y + 0.9, 0.1 + (Math.random() - 0.5) * 0.9)
    world.add(mesh)
    sparks.push({
      mesh,
      age: 0,
      life: 0.9 + Math.random() * 0.5,
      vx: 0.5 + Math.random() * 0.7,
      vz: (Math.random() - 0.5) * 0.7,
    })
  }

  // --- day and night ----------------------------------------------------------------------------
  let currentTheme = initialTheme
  const look = () => LOOK[currentTheme]

  function applyTheme(next: RoomTheme) {
    currentTheme = next
    const l = look()
    ambient.color.set(l.ambient[0])
    ambient.intensity = l.ambient[1]
    sun.color.set(l.sun[0])
    sun.intensity = l.sun[1]
    lampLight.intensity = l.lamp
    glow.intensity = l.glow
    ;(floor.material as MeshToonMaterial).color.set(l.floor)
    ;(wallBack.material as MeshToonMaterial).color.set(l.wallBack)
    ;(wallLeft.material as MeshToonMaterial).color.set(l.wallLeft)
    ;(sky.material as MeshBasicMaterial).color.set(l.sky)
    ;(moon.material as MeshBasicMaterial).color.set(l.disc)
    moon.scale.setScalar(l.discScale)
    lampMaterial.color = new Color(l.lampShade)
    if (view === 'room') for (const star of stars) star.visible = l.stars
  }
  applyTheme(initialTheme)

  // --- where the head is on screen (for the speech bubble) ----------------------------------------
  const headPoint = new Vector3()
  let hostW = 0
  let hostH = 0
  let lastX = -1
  let lastY = -1
  function reportHead() {
    if (!onHead || !hostW) return
    head.getWorldPosition(headPoint)
    headPoint.y += 0.55
    headPoint.project(camera)
    const x = (headPoint.x * 0.5 + 0.5) * hostW
    const y = (-headPoint.y * 0.5 + 0.5) * hostH
    if (Math.abs(x - lastX) < 0.5 && Math.abs(y - lastY) < 0.5) return
    lastX = x
    lastY = y
    onHead({ x, y })
  }

  // --- animation ------------------------------------------------------------------------------
  let typingUntil = 0
  let lastLine = 0
  const offTyping = onTyping(() => {
    const now = performance.now()
    typingUntil = now + 320
    if (now - lastLine > 90) {
      lastLine = now
      screen.addLine()
      spawnSpark()
      const key = keyMeshes[Math.floor(Math.random() * keyMeshes.length)]
      key.userData.pressedUntil = now + 120
    }
    if (reducedMotion) frame()
  })

  const clock = { last: performance.now() }
  let blinkAt = performance.now() + 2500
  let raf = 0
  let running = true
  let lastDraw = 0

  function frame() {
    const now = performance.now()
    const dt = Math.min((now - clock.last) / 1000, 0.1)
    clock.last = now
    const t = now / 1000
    const typing = now < typingUntil

    // paws: quick alternating taps while typing, resting otherwise
    const tapL = typing ? Math.max(0, Math.sin(t * 28)) * 0.1 : 0
    const tapR = typing ? Math.max(0, Math.sin(t * 28 + Math.PI)) * 0.1 : 0
    pawL.position.y = 0.8 + tapL
    pawR.position.y = 0.8 + tapR

    for (const key of keyMeshes) {
      const pressed = (key.userData.pressedUntil ?? 0) > now
      key.position.y = pressed ? 0.045 : 0.065
      ;(key.material as MeshToonMaterial).color.set(pressed ? 0x9fe8ff : PALETTE.keys)
    }

    if (!reducedMotion) {
      const breathe = Math.sin(t * 1.8) * 0.012
      torso.scale.set(1 + breathe, 1 + breathe * 1.5, 1)
      tail.position.z = Math.sin(t * (typing ? 12 : 3)) * (typing ? 0.2 : 0.1)
      head.rotation.z = typing ? Math.sin(t * 9) * 0.03 - 0.04 : Math.sin(t * 1.1) * 0.015
      earL.rotation.z = Math.sin(t * 0.7) > 0.96 ? 0.25 : 0
      lampLight.intensity = look().lamp + (look().lamp ? Math.sin(t * 2.3) * 0.6 : 0)
    }
    glow.intensity = look().glow * (typing ? 1.5 : 1)

    // blink
    if (now > blinkAt) {
      eyes.scale.y = 0.1
      if (now > blinkAt + 120) {
        eyes.scale.y = 1
        blinkAt = now + 2500 + Math.random() * 3000
      }
    }

    for (let i = sparks.length - 1; i >= 0; i--) {
      const s = sparks[i]
      s.age += dt
      const k = s.age / s.life
      s.mesh.position.x += s.vx * dt
      s.mesh.position.z += s.vz * dt
      s.mesh.position.y += (0.9 - k) * dt
      s.mesh.rotation.y += dt * 4
      ;(s.mesh.material as MeshBasicMaterial).opacity = Math.max(0, 1 - k)
      if (k >= 1) {
        world.remove(s.mesh)
        s.mesh.geometry.dispose()
        ;(s.mesh.material as MeshBasicMaterial).dispose()
        sparks.splice(i, 1)
      }
    }

    renderer.render(scene, camera)
    reportHead()
  }

  function loop(now: number) {
    if (!running) return
    raf = requestAnimationFrame(loop)
    if (document.hidden || now - lastDraw < 33) return // 30 fps is plenty for a background
    lastDraw = now
    frame()
  }
  if (reducedMotion) frame()
  else raf = requestAnimationFrame(loop)

  function resize() {
    const { clientWidth: w, clientHeight: h } = host
    if (!w || !h) return
    hostW = w
    hostH = h
    const pixel = h > 520 ? 3 : 2 // CSS pixels per rendered pixel
    renderer.setSize(Math.ceil(w / pixel), Math.ceil(h / pixel), false)
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    const aspect = w / h
    // Wide stages show more of the sides; narrow ones (phones) zoom out so the room still fits.
    const halfHeight = Math.max(frameOf.halfHeight, frameOf.minHalfWidth / aspect)
    camera.left = -halfHeight * aspect
    camera.right = halfHeight * aspect
    camera.top = halfHeight
    camera.bottom = -halfHeight
    camera.updateProjectionMatrix()
    lastX = -1
    frame()
  }
  const observer = new ResizeObserver(resize)
  observer.observe(host)
  resize()

  return {
    setTheme(next) {
      applyTheme(next)
      frame()
    },
    dispose() {
      running = false
      cancelAnimationFrame(raf)
      offTyping()
      observer.disconnect()
      scene.traverse((object) => {
        if (object instanceof Mesh) {
          object.geometry.dispose()
          const materials = Array.isArray(object.material) ? object.material : [object.material]
          for (const m of materials) {
            ;(m as MeshBasicMaterial).map?.dispose()
            m.dispose()
          }
        }
      })
      renderer.dispose()
      renderer.domElement.remove()
    },
  }
}
