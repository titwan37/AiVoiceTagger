import * as THREE from 'three';

export const SemanticDeformationShader = {
  uniforms: {
    uTime: { value: 0 },
    uAttractorPos: { value: new THREE.Vector3(0, 0, 0) },
    uAttractorStrength: { value: 0.0 },
    uIntensity: { value: 1.0 },
  },
  vertexShader: `
    uniform float uTime;
    uniform vec3 uAttractorPos;
    uniform float uAttractorStrength;
    uniform float uIntensity;

    varying vec2 vUv;
    varying float vElevation;
    varying vec3 vWorldPosition;

    void main() {
      vUv = uv;
      vec3 pos = position;

      // 1. RMS / Conversational Agitation Wave Simulation
      float wave = sin(pos.x * 2.0 + uTime * 3.0) * cos(pos.y * 2.0 + uTime * 2.0) * (0.15 * uIntensity);
      pos.z += wave;

      // 2. Gravitational Vortex / Obsessive Lexical Loop Deformation
      float distToAttractor = distance(pos.xy, uAttractorPos.xy);
      float vortexPull = exp(-distToAttractor * 1.5) * uAttractorStrength;
      pos.z -= vortexPull * 1.8;

      vElevation = pos.z;
      vWorldPosition = (modelMatrix * vec4(pos, 1.0)).xyz;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
    }
  `,
  fragmentShader: `
    uniform float uTime;
    varying vec2 vUv;
    varying float vElevation;
    varying vec3 vWorldPosition;

    void main() {
      // Heatmap palette: Deep Cyan (Regulated) -> Amber (Friction) -> Crimson (Acute Crisis)
      vec3 colorCalm = vec3(0.05, 0.4, 0.65);
      vec3 colorAlert = vec3(0.95, 0.65, 0.1);
      vec3 colorCrisis = vec3(0.95, 0.15, 0.25);

      float normElevation = clamp((vElevation + 0.8) / 1.6, 0.0, 1.0);
      vec3 finalColor = mix(colorCalm, colorAlert, smoothstep(0.2, 0.6, normElevation));
      finalColor = mix(finalColor, colorCrisis, smoothstep(0.6, 1.0, normElevation));

      // Grid line overlay
      vec2 grid = abs(fract(vUv * 40.0 - 0.5) - 0.5) / fwidth(vUv * 40.0);
      float line = min(grid.x, grid.y);
      float gridAlpha = 1.0 - min(line, 1.0);

      gl_FragColor = vec4(finalColor + vec3(gridAlpha * 0.15), 0.75);
    }
  `,
};
