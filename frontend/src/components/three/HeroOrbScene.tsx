import { useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Float, MeshDistortMaterial, Icosahedron } from '@react-three/drei';
import type { Mesh } from 'three';

/**
 * The scene itself, code-split from HeroOrb.tsx so the three.js/fiber/drei
 * bundle (not small) never loads for a visitor who has reduced motion set,
 * a narrow viewport, or no WebGL — HeroOrb decides whether this module is
 * even requested.
 */

function DistortIcosahedron() {
  const meshRef = useRef<Mesh>(null);

  // Slow, deliberate rotation — decoration, not distraction. A hero element
  // spinning fast enough to catch the eye competes with the headline it
  // sits behind rather than supporting it.
  useFrame((_, delta) => {
    if (!meshRef.current) return;
    meshRef.current.rotation.x += delta * 0.08;
    meshRef.current.rotation.y += delta * 0.12;
  });

  return (
    <Float speed={1.4} rotationIntensity={0.4} floatIntensity={0.8}>
      <Icosahedron ref={meshRef} args={[1.6, 4]}>
        <MeshDistortMaterial
          color="#22d3ee"
          attach="material"
          distort={0.45}
          speed={2}
          roughness={0.05}
          metalness={0.85}
          emissive="#8b5cf6"
          emissiveIntensity={0.6}
          toneMapped={false}
        />
      </Icosahedron>
    </Float>
  );
}

export default function HeroOrbScene() {
  return (
    <Canvas
      dpr={[1, 1.5]}
      camera={{ position: [0, 0, 6], fov: 40 }}
      gl={{ alpha: true, antialias: true, powerPreference: 'low-power' }}
      style={{ width: '100%', height: '100%' }}
    >
      <ambientLight intensity={0.35} />
      <pointLight position={[5, 5, 5]} intensity={3} color="#22d3ee" />
      <pointLight position={[-5, -3, 3]} intensity={2.5} color="#a78bfa" />
      <pointLight position={[0, -4, 4]} intensity={1.5} color="#ffffff" />
      <DistortIcosahedron />
    </Canvas>
  );
}
