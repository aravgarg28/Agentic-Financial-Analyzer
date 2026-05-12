"use client";

import { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, Environment, Sparkles } from "@react-three/drei";
import * as THREE from "three";

function FinancialMesh() {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.getElapsedTime() * 0.15;
      groupRef.current.position.y = Math.sin(state.clock.getElapsedTime() * 0.5) * 0.2;
    }
  });

  return (
    <group ref={groupRef}>
      {/* Sleek metallic bar charts rising up */}
      <mesh position={[-1.8, -1.2, 0]}>
        <boxGeometry args={[0.6, 1.2, 0.6]} />
        <meshStandardMaterial color="#cca35e" metalness={0.9} roughness={0.15} />
      </mesh>
      <mesh position={[-0.6, -0.6, 0]}>
        <boxGeometry args={[0.6, 2.4, 0.6]} />
        <meshStandardMaterial color="#cca35e" metalness={0.9} roughness={0.15} />
      </mesh>
      <mesh position={[0.6, 0.2, 0]}>
        <boxGeometry args={[0.6, 4.0, 0.6]} />
        <meshStandardMaterial color="#cca35e" metalness={0.9} roughness={0.15} />
      </mesh>
      <mesh position={[1.8, 1.0, 0]}>
        <boxGeometry args={[0.6, 5.6, 0.6]} />
        <meshStandardMaterial color="#cca35e" metalness={0.9} roughness={0.15} />
      </mesh>

      {/* Floating glossy coins/tokens */}
      <Float speed={2.5} rotationIntensity={1.5} floatIntensity={1.5} position={[-2, 1, 1.5]}>
        <mesh rotation={[Math.PI / 2, 0, 0.5]}>
          <cylinderGeometry args={[0.6, 0.6, 0.1, 64]} />
          <meshStandardMaterial color="#ffffff" metalness={1} roughness={0.1} />
        </mesh>
      </Float>

      <Float speed={2} rotationIntensity={2} floatIntensity={1.5} position={[2, -1.5, 1.5]}>
        <mesh rotation={[Math.PI / 2, 0, -0.5]}>
          <cylinderGeometry args={[0.8, 0.8, 0.12, 64]} />
          <meshStandardMaterial color="#cca35e" metalness={1} roughness={0.1} />
        </mesh>
      </Float>
    </group>
  );
}

export default function Hero3DBackground() {
  return (
    <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", zIndex: 0, pointerEvents: "none", background: "radial-gradient(circle at 50% 50%, #111111 0%, #030303 100%)" }}>
      <Canvas camera={{ position: [0, 0, 8], fov: 45 }}>
        <ambientLight intensity={0.4} />
        <directionalLight position={[10, 10, 5]} intensity={1.5} color="#ffffff" />
        <directionalLight position={[-10, -10, -5]} intensity={2.5} color="#cca35e" />
        <pointLight position={[0, 0, 5]} intensity={1} color="#cca35e" />
        
        <FinancialMesh />
        
        <Sparkles count={200} scale={15} size={2} speed={0.3} opacity={0.4} color="#cca35e" />
        <Environment preset="city" />
      </Canvas>
    </div>
  );
}
