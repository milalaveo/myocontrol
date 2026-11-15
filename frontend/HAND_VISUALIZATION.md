# Procedural hand visualization

`src/components/HandScene.tsx` exports `HandScene` as its default export, accepting
`{ gesture: string; playing?: boolean }`. Import it directly into the preview panel:

```tsx
import HandScene from './components/HandScene';

<div style={{ height: 420 }}>
  <HandScene gesture="finger_spread" playing={true} />
</div>
```

The host application supplies React, React DOM, `three`, `@types/three`, and
`@react-three/fiber`. Match Fiber's major version to the React version used by the
application. No drei, controls, physics, model loader, texture, font, network
request, or externally licensed model asset is needed.

## Gestures and playback

| Gesture | Pose |
| --- | --- |
| `rest` or `neutral` | Relaxed fingers and straight wrist |
| `fist` | All finger joints curl; the thumb folds across the palm |
| `finger_spread` | Straight fingers fan outward and the thumb opens |
| `wrist_flexion` | Hand bends forward at the wrist |
| `wrist_extension` | Hand bends backward at the wrist |

Input is case insensitive; spaces and hyphens become underscores. Unrecognized
values resolve to rest. `playing` defaults to `false`, which holds the selected
pose while smoothly transitioning when the selection changes. `true` demonstrates
the selected gesture by cycling toward rest and back every four seconds. Turning
playback off returns to the selected target pose; it does not freeze mid-cycle.

The initial pose appears immediately. Subsequent joint rotations use `useFrame`
and delta-time-based `MathUtils.damp`, with a capped delta after inactive tabs.
Animation mutates Three.js group refs without setting React state every frame.
Reduced-motion preferences disable repeated playback and snap to the target pose.

## Rendering and accessibility

The hand consists of a flattened capsule palm, rounded thumb base, articulated
three-segment fingers, a two-segment thumb, and a stationary forearm. Child groups
pivot at each joint; the palm and digits pivot together at the wrist. A fixed
perspective camera and cool blue lights make bending visible without controls.
The scene has an alpha-transparent background, designed for a dark blue host panel.
The wrapper fills its parent and has a 320 px minimum height.

Geometry uses modest segment counts and rendering caps the pixel ratio at 1.5.
There are no shadows or postprocessing. This is an illustrative training preview,
not a biomechanical model or a measurement of a user's movement.

A persistent screen-reader status describes the normalized gesture and playback.
The canvas has an accessible image label. Canvas's fallback and an outer React
error boundary provide English text if WebGL initialization fails. A context-loss
listener switches to the same text fallback if an active renderer loses WebGL.
Reloading/remounting the component retries after failure. Browser rendering waits
until mounting, so server rendering does not access `window`.

## Official sources

- [React Three Fiber Canvas](https://r3f.docs.pmnd.rs/api/canvas): camera, renderer,
  pixel ratio, transparent scene setup, and WebGL fallback/error-boundary guidance.
- [React Three Fiber hooks](https://r3f.docs.pmnd.rs/api/hooks): `useFrame` inside
  Canvas and direct updates to scene objects during animation.
- [Three.js CapsuleGeometry](https://threejs.org/docs/pages/CapsuleGeometry.html):
  procedural capsules and configurable tessellation.
- [Three.js MathUtils](https://threejs.org/docs/pages/MathUtils.html): `damp` for
  frame-rate-independent interpolation.

Only this document and `src/components/HandScene.tsx` belong to this implementation.
Package installation and integration are handled by the host application.
