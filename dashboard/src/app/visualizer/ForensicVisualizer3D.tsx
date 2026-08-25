import React, { useRef, useMemo, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Text, Float, Line } from '@react-three/drei';
import * as THREE from 'three';
import { SemanticDeformationShader } from './shaders';

export type ProjectionMode = 'SEMANTIC' | 'LEGAL_STATUTORY' | 'PSYCHODYNAMIC';

export interface DialogueSegmentNode {
  id: string;
  speaker: string;
  timestamp: string;
  text: string;
  rmsIntensity: number;
  umapX: number;
  umapY: number;
  statuteCategory?: 'ART_180' | 'ART_181' | 'ART_177' | 'ART_186' | 'ART_28B';
  severity: number; // 0.0 to 1.0
  yearOffset: number; // 0.0 (2015) to 1.0 (2026)
}

// ---------------------------------------------------------------------------
// 1. Semantic Manifold Projection
// ---------------------------------------------------------------------------
const SemanticManifoldLayer: React.FC<{
  nodes: DialogueSegmentNode[];
  onSelectNode: (node: DialogueSegmentNode) => void;
}> = ({ nodes, onSelectNode }) => {
  const meshRef = useRef<THREE.Mesh>(null!);
  const shaderMatRef = useRef<THREE.ShaderMaterial>(null!);

  useFrame((state) => {
    if (shaderMatRef.current) {
      shaderMatRef.current.uniforms['uTime'].value = state.clock.getElapsedTime();
      shaderMatRef.current.uniforms['uAttractorStrength'].value = 1.2;
    }
  });

  const trajectoryPoints = useMemo(() => {
    return nodes.map((n) => new THREE.Vector3(n.umapX * 6, n.umapY * 6, n.rmsIntensity * 2));
  }, [nodes]);

  return (
    <group>
      {/* Dynamic Deformable Base Plane */}
      <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.5, 0]}>
        <planeGeometry args={[12, 12, 64, 64]} />
        <shaderMaterial
          ref={shaderMatRef}
          args={[SemanticDeformationShader]}
          transparent
          side={THREE.DoubleSide}
          wireframe={false}
        />
      </mesh>

      {/* Trajectory Spline Ribbon */}
      {trajectoryPoints.length > 1 && (
        <Line
          points={trajectoryPoints}
          color="#38bdf8"
          lineWidth={2.5}
          dashed={false}
          transparent
          opacity={0.8}
        />
      )}

      {/* Instanced Dialogue Utterance Particles */}
      {nodes.map((node) => (
        <mesh
          key={node.id}
          position={[node.umapX * 6, node.umapY * 6, node.rmsIntensity * 2]}
          onClick={(e) => {
            e.stopPropagation();
            onSelectNode(node);
          }}
        >
          <sphereGeometry args={[0.08 + node.severity * 0.12, 16, 16]} />
          <meshStandardMaterial
            color={node.speaker === 'SPEAKER_01' ? '#f43f5e' : '#0ea5e9'}
            emissive={node.speaker === 'SPEAKER_01' ? '#881337' : '#0369a1'}
            emissiveIntensity={0.6}
            roughness={0.2}
          />
        </mesh>
      ))}
    </group>
  );
};

// ---------------------------------------------------------------------------
// 2. Swiss Legal Evidence Constellation
// ---------------------------------------------------------------------------
const LegalConstellationLayer: React.FC<{
  nodes: DialogueSegmentNode[];
  onSelectNode: (node: DialogueSegmentNode) => void;
}> = ({ nodes, onSelectNode }) => {
  const getStatuteAngle = (cat?: string) => {
    switch (cat) {
      case 'ART_180': return 0;
      case 'ART_181': return (Math.PI * 2) / 5;
      case 'ART_177': return (Math.PI * 4) / 5;
      case 'ART_186': return (Math.PI * 6) / 5;
      case 'ART_28B': return (Math.PI * 8) / 5;
      default: return 0;
    }
  };

  return (
    <group>
      {/* Statutory Sector Guidelines */}
      {[0, 1, 2, 3, 4].map((idx) => {
        const angle = (idx * Math.PI * 2) / 5;
        const x = Math.cos(angle) * 5;
        const z = Math.sin(angle) * 5;
        return (
          <group key={idx}>
            <Line points={[[0, 0, 0], [x, 0, z]]} color="#475569" lineWidth={1} />
            <Text
              position={[x * 1.15, 0.2, z * 1.15]}
              fontSize={0.25}
              color="#cbd5e1"
              anchorX="center"
              anchorY="middle"
            >
              {['Art. 180 CP', 'Art. 181 CP', 'Art. 177 CP', 'Art. 186 CP', 'Art. 28b CC'][idx]}
            </Text>
          </group>
        );
      })}

      {/* Timeline Cylindrical Grid Base */}
      <gridHelper args={[10, 10, '#334155', '#1e293b']} position={[0, -2, 0]} />

      {/* Evidence Nodes Placed in Cylindrical Coordinates (r, theta, z) */}
      {nodes.map((node) => {
        const theta = getStatuteAngle(node.statuteCategory) + (Math.random() - 0.5) * 0.3;
        const radius = 1.0 + node.severity * 3.5;
        const x = Math.cos(theta) * radius;
        const z = Math.sin(theta) * radius;
        const y = -2 + node.yearOffset * 4.0; // Timeline vertical height

        return (
          <mesh
            key={node.id}
            position={[x, y, z]}
            onClick={(e) => {
              e.stopPropagation();
              onSelectNode(node);
            }}
          >
            <octahedronGeometry args={[0.12 + node.severity * 0.15, 0]} />
            <meshStandardMaterial
              color={node.severity > 0.7 ? '#ef4444' : '#f59e0b'}
              emissive={node.severity > 0.7 ? '#991b1b' : '#b45309'}
              wireframe={node.severity < 0.4}
            />
          </mesh>
        );
      })}
    </group>
  );
};

// ---------------------------------------------------------------------------
// 3. Psychodynamic Tensor Field & Triangulation Topology
// ---------------------------------------------------------------------------
const PsychodynamicTopologyLayer: React.FC<{
  onSelectNode: (node: DialogueSegmentNode) => void;
}> = () => {
  const agents = useMemo(
    () => ({
      father: new THREE.Vector3(-3, 1, 0),
      mother: new THREE.Vector3(3, 1, 0),
      child: new THREE.Vector3(0, -1.5, 1.5),
      court: new THREE.Vector3(0, 3, -2),
    }),
    []
  );

  return (
    <group>
      {/* Agent Nodes */}
      <Float speed={1.5} rotationIntensity={0.2} floatIntensity={0.3}>
        <mesh position={agents.father}>
          <dodecahedronGeometry args={[0.4]} />
          <meshStandardMaterial color="#0284c7" emissive="#0369a1" />
        </mesh>
        <Text position={[-3, 1.7, 0]} fontSize={0.25} color="#38bdf8">
          Target Parent
        </Text>

        <mesh position={agents.mother}>
          <dodecahedronGeometry args={[0.4]} />
          <meshStandardMaterial color="#e11d48" emissive="#be123c" />
        </mesh>
        <Text position={[3, 1.7, 0]} fontSize={0.25} color="#fb7185">
          Aggressive Vector
        </Text>

        <mesh position={agents.child}>
          <sphereGeometry args={[0.3, 32, 32]} />
          <meshStandardMaterial color="#fbbf24" emissive="#d97706" />
        </mesh>
        <Text position={[0, -2.1, 1.5]} fontSize={0.25} color="#fde68a">
          Triangulated Minor
        </Text>
      </Float>

      {/* Interpersonal Tension Vector Beams */}
      <Line
        points={[agents.mother, agents.child]}
        color="#e11d48"
        lineWidth={3}
        dashed
        dashScale={5}
      />
      <Line
        points={[agents.father, agents.child]}
        color="#38bdf8"
        lineWidth={2}
      />
      <Line
        points={[agents.mother, agents.father]}
        color="#a855f7"
        lineWidth={4}
      />
    </group>
  );
};

// ---------------------------------------------------------------------------
// Master Canvas Component with Mode HUD
// ---------------------------------------------------------------------------
export const ForensicVisualizer3D: React.FC<{ data: DialogueSegmentNode[] }> = ({ data }) => {
  const [mode, setMode] = useState<ProjectionMode>('SEMANTIC');
  const [selectedNode, setSelectedNode] = useState<DialogueSegmentNode | null>(null);

  return (
    <div className="relative w-full h-[800px] bg-slate-950 rounded-xl overflow-hidden border border-slate-800">
      {/* Mode Control Bar */}
      <div className="absolute top-4 left-4 z-10 flex gap-2 bg-slate-900/80 backdrop-blur p-1.5 rounded-lg border border-slate-700">
        {(['SEMANTIC', 'LEGAL_STATUTORY', 'PSYCHODYNAMIC'] as ProjectionMode[]).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`px-3 py-1.5 rounded text-xs font-semibold tracking-wider transition ${
              mode === m
                ? 'bg-sky-600 text-white shadow-lg'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {m.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Selected Node HUD Card */}
      {selectedNode && (
        <div className="absolute bottom-4 left-4 z-10 max-w-md bg-slate-900/90 backdrop-blur-md border border-slate-700 rounded-lg p-4 text-slate-200 shadow-2xl">
          <div className="flex justify-between items-start mb-2">
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800">
              {selectedNode.timestamp}
            </span>
            <span className="text-xs font-bold text-rose-400">{selectedNode.speaker}</span>
          </div>
          <p className="text-sm italic mb-2 text-slate-100">"{selectedNode.text}"</p>
          <div className="flex gap-4 text-xs font-mono text-slate-400">
            <span>RMS: {(selectedNode.rmsIntensity * 100).toFixed(0)}%</span>
            <span>Severity: {(selectedNode.severity * 10).toFixed(1)}/10</span>
            {selectedNode.statuteCategory && (
              <span className="text-amber-400">{selectedNode.statuteCategory}</span>
            )}
          </div>
        </div>
      )}

      {/* 3D WebGL Canvas */}
      <Canvas camera={{ position: [0, 6, 8], fov: 45 }}>
        <ambientLight intensity={0.4} />
        <pointLight position={[10, 10, 10]} intensity={1.2} />
        <directionalLight position={[-5, 5, -5]} intensity={0.5} />

        {mode === 'SEMANTIC' && (
          <SemanticManifoldLayer nodes={data} onSelectNode={setSelectedNode} />
        )}
        {mode === 'LEGAL_STATUTORY' && (
          <LegalConstellationLayer nodes={data} onSelectNode={setSelectedNode} />
        )}
        {mode === 'PSYCHODYNAMIC' && (
          <PsychodynamicTopologyLayer onSelectNode={setSelectedNode} />
        )}

        <OrbitControls makeDefault maxPolarAngle={Math.PI / 2 + 0.1} />
      </Canvas>
    </div>
  );
};
