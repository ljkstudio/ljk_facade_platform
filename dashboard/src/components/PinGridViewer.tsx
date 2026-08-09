import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { AdaptiveMoldResult } from "../api/client";

interface Props {
  result: AdaptiveMoldResult | null;
  maxHeight: number;
}

function PinGrid({ result, maxHeight }: Props) {
  const pins = useMemo(() => {
    if (!result || result.pin_heights.length === 0) return [];
    const { nx, ny, pin_heights, grid_pts, clamp_flags, extension_flags } =
      result;
    return pin_heights.map((h, i) => {
      const pt = grid_pts[i] || { x: 0, y: 0, z: 0 };
      const t = maxHeight > 0 ? h / maxHeight : 0;
      const r = clamp_flags[i] ? 1 : extension_flags[i] ? 0.9 : 0.2;
      const g = extension_flags[i] ? 0.7 : 0.6 + t * 0.4;
      const b = clamp_flags[i] ? 0.2 : 0.8 - t * 0.5;
      return {
        x: pt.x,
        y: h / 2,
        z: -pt.y,
        h: Math.max(h, 1),
        color: `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`,
        nx,
        ny,
      };
    });
  }, [result, maxHeight]);

  if (pins.length === 0) {
    return (
      <mesh>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#334155" wireframe />
      </mesh>
    );
  }

  return (
    <group>
      {pins.map((pin, i) => (
        <mesh key={i} position={[pin.x, pin.y, pin.z]}>
          <boxGeometry args={[18, pin.h, 18]} />
          <meshStandardMaterial color={pin.color} />
        </mesh>
      ))}
      <gridHelper args={[1200, 20, "#334155", "#1e2733"]} position={[500, 0, -500]} />
    </group>
  );
}

export function PinGridViewer({ result, maxHeight }: Props) {
  return (
    <div className="viewer-wrap">
      <Canvas camera={{ position: [800, 600, 800], fov: 45 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[500, 800, 300]} intensity={0.9} />
        <PinGrid result={result} maxHeight={maxHeight} />
        <OrbitControls makeDefault />
      </Canvas>
    </div>
  );
}
