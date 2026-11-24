import { Component, useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode, RefObject } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Group, MathUtils } from 'three'

export interface HandSceneProps {
  gesture: string
  playing?: boolean
}

type Gesture = 'rest' | 'fist' | 'finger_spread' | 'wrist_flexion' | 'wrist_extension'

const LABELS: Record<Gesture, string> = {
  rest: 'Relaxed hand',
  fist: 'Closed fist',
  finger_spread: 'Fingers spread',
  wrist_flexion: 'Wrist flexion',
  wrist_extension: 'Wrist extension',
}

const FINGERS = [
  { x: -0.48, y: 0.91, length: 0.97, radius: 0.13, spread: 0.26 },
  { x: -0.16, y: 0.99, length: 1.11, radius: 0.14, spread: 0.08 },
  { x: 0.17, y: 0.95, length: 1.03, radius: 0.13, spread: -0.12 },
  { x: 0.47, y: 0.82, length: 0.79, radius: 0.115, spread: -0.32 },
]

const hiddenText: CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clipPath: 'inset(50%)',
  whiteSpace: 'nowrap',
  border: 0,
}

function normalizeGesture(value: string): Gesture {
  const key = value
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
  return Object.prototype.hasOwnProperty.call(LABELS, key) ? (key as Gesture) : 'rest'
}

function Fallback({ label }: { label: string }) {
  return (
    <div
      role="status"
      style={{
        display: 'grid',
        placeContent: 'center',
        minHeight: '100%',
        height: '100%',
        textAlign: 'center',
        color: '#b9d4ef',
        padding: 24,
        boxSizing: 'border-box',
      }}
    >
      <strong>{label}</strong>
      <span style={{ marginTop: 8, fontSize: 13 }}>
        3D preview unavailable. Gesture selection remains available.
      </span>
    </div>
  )
}

class SceneBoundary extends Component<{ children: ReactNode; label: string }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    return this.state.failed ? <Fallback label={this.props.label} /> : this.props.children
  }
}

function Segment({ length, radius }: { length: number; radius: number }) {
  return (
    <>
      <mesh position={[0, length / 2, 0]}>
        <capsuleGeometry args={[radius, Math.max(0.01, length - radius * 2), 4, 12]} />
        <meshStandardMaterial color="#76b5df" metalness={0.28} roughness={0.36} />
      </mesh>
      <mesh>
        <sphereGeometry args={[radius * 1.03, 12, 8]} />
        <meshStandardMaterial color="#346587" metalness={0.35} roughness={0.4} />
      </mesh>
    </>
  )
}

function Finger({ index, joints }: { index: number; joints: RefObject<(Group | null)[]> }) {
  const finger = FINGERS[index]!
  const proximal = finger.length * 0.45
  const middle = finger.length * 0.31
  const distal = finger.length * 0.24
  return (
    <group
      position={[finger.x, finger.y, 0]}
      ref={(node) => {
        joints.current[index * 3] = node
      }}
    >
      <Segment length={proximal} radius={finger.radius} />
      <group
        position={[0, proximal, 0]}
        ref={(node) => {
          joints.current[index * 3 + 1] = node
        }}
      >
        <Segment length={middle} radius={finger.radius * 0.88} />
        <group
          position={[0, middle, 0]}
          ref={(node) => {
            joints.current[index * 3 + 2] = node
          }}
        >
          <Segment length={distal} radius={finger.radius * 0.76} />
        </group>
      </group>
    </group>
  )
}

function ContextMonitor({ onLost }: { onLost: () => void }) {
  const canvas = useThree((state) => state.gl.domElement)
  useEffect(() => {
    const lost = (event: Event) => {
      event.preventDefault()
      onLost()
    }
    canvas.addEventListener('webglcontextlost', lost)
    return () => canvas.removeEventListener('webglcontextlost', lost)
  }, [canvas, onLost])
  return null
}

function Hand({
  gesture,
  playing,
  reducedMotion,
}: {
  gesture: Gesture
  playing: boolean
  reducedMotion: boolean
}) {
  const wrist = useRef<Group>(null)
  const joints = useRef<(Group | null)[]>([])
  const thumb = useRef<Group>(null)
  const thumbTip = useRef<Group>(null)
  const elapsed = useRef(0)
  const initialized = useRef(false)

  useEffect(() => {
    elapsed.current = 0
  }, [gesture, playing])

  useFrame((_, frameDelta) => {
    const dt = Math.min(frameDelta, 0.05)
    if (playing && !reducedMotion) elapsed.current += dt
    // Playback cycles between the selected gesture and rest every four seconds.
    const amount =
      playing && !reducedMotion ? 0.5 + 0.5 * Math.cos((elapsed.current * Math.PI) / 2) : 1
    const move = (current: number, target: number) =>
      reducedMotion || !initialized.current ? target : MathUtils.damp(current, target, 9, dt)
    const curl = gesture === 'fist' ? amount : 0
    const spread = gesture === 'finger_spread' ? amount : 0
    if (wrist.current) {
      const bend = gesture === 'wrist_flexion' ? 0.82 : gesture === 'wrist_extension' ? -0.72 : 0
      wrist.current.rotation.x = move(wrist.current.rotation.x, bend * amount)
    }
    FINGERS.forEach((finger, index) => {
      for (let joint = 0; joint < 3; joint += 1) {
        const node = joints.current[index * 3 + joint]
        if (!node) continue
        const relaxed = joint === 0 ? 0.12 : 0.18
        const closed = joint === 0 ? 1.35 : joint === 1 ? 1.55 : 1.1
        node.rotation.x = move(node.rotation.x, relaxed * (1 - spread) + curl * (closed - relaxed))
        if (joint === 0)
          node.rotation.z = move(
            node.rotation.z,
            finger.spread * (0.22 + spread * 0.78) * (1 - curl),
          )
      }
    })
    if (thumb.current) {
      thumb.current.rotation.z = move(thumb.current.rotation.z, 0.72 + spread * 0.32 - curl * 1.05)
      thumb.current.rotation.x = move(thumb.current.rotation.x, 0.14 + curl * 0.85)
      thumb.current.rotation.y = move(thumb.current.rotation.y, -0.2 - curl * 0.55)
    }
    if (thumbTip.current)
      thumbTip.current.rotation.x = move(thumbTip.current.rotation.x, 0.12 + curl * 0.95)
    initialized.current = true
  })

  return (
    <group position={[0.12, -0.8, 0]} rotation={[0.06, -0.42, -0.12]}>
      <mesh position={[0, -0.55, 0]}>
        <capsuleGeometry args={[0.29, 0.75, 5, 16]} />
        <meshStandardMaterial color="#375b7d" metalness={0.4} roughness={0.4} />
      </mesh>
      <mesh position={[0, -0.22, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.29, 0.035, 8, 32]} />
        <meshStandardMaterial color="#56d5eb" emissive="#167eab" emissiveIntensity={0.8} />
      </mesh>
      <group ref={wrist}>
        <mesh position={[0, 0.42, 0]} scale={[1, 1, 0.43]}>
          <capsuleGeometry args={[0.6, 0.48, 6, 20]} />
          <meshStandardMaterial color="#639fca" metalness={0.32} roughness={0.38} />
        </mesh>
        <mesh position={[-0.4, 0.29, 0.05]} scale={[0.27, 0.43, 0.22]}>
          <sphereGeometry args={[1, 16, 12]} />
          <meshStandardMaterial color="#76b5df" metalness={0.28} roughness={0.36} />
        </mesh>
        {FINGERS.map((_, index) => (
          <Finger key={index} index={index} joints={joints} />
        ))}
        <group position={[-0.48, 0.22, 0.06]} ref={thumb}>
          <Segment length={0.52} radius={0.17} />
          <group position={[0, 0.52, 0]} ref={thumbTip}>
            <Segment length={0.4} radius={0.14} />
          </group>
        </group>
      </group>
    </group>
  )
}

export default function HandScene({ gesture, playing = false }: HandSceneProps) {
  const normalized = normalizeGesture(gesture)
  const label = LABELS[normalized]
  const [ready, setReady] = useState(false)
  const [contextLost, setContextLost] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const handleContextLost = useCallback(() => setContextLost(true), [])

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReducedMotion(query.matches)
    update()
    setReady(true)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  return (
    <div className="hand-preview">
      <span role="status" aria-live="polite" style={hiddenText}>
        {label}.{' '}
        {playing && !reducedMotion ? 'Gesture demonstration playing.' : 'Static gesture preview.'}
      </span>
      {!ready ? (
        <div style={{ height: '100%' }} aria-hidden="true" />
      ) : contextLost ? (
        <Fallback label={label} />
      ) : (
        <SceneBoundary label={label}>
          <Canvas
            aria-label={`3D hand showing ${label.toLowerCase()}`}
            role="img"
            camera={{ position: [0, 0.25, 8], fov: 39, near: 0.1, far: 30 }}
            dpr={[1, 1.5]}
            gl={{ alpha: true, antialias: true, powerPreference: 'low-power' }}
            style={{ background: 'transparent' }}
            fallback={<Fallback label={label} />}
            onCreated={({ gl }) => gl.setClearColor('#071526', 0)}
          >
            <ambientLight intensity={0.85} />
            <hemisphereLight args={['#bee8ff', '#10243b', 1.5]} />
            <directionalLight position={[-3, 5, 5]} intensity={2.5} color="#d0ecff" />
            <directionalLight position={[4, 1, -3]} intensity={3} color="#369cd9" />
            <pointLight position={[-2, -1, 2]} intensity={4} color="#47d7e8" />
            <ContextMonitor onLost={handleContextLost} />
            <Hand gesture={normalized} playing={playing} reducedMotion={reducedMotion} />
          </Canvas>
        </SceneBoundary>
      )}
    </div>
  )
}
