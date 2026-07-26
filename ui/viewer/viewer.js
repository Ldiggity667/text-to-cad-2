/* Forge3D — Three.js STEP viewer (runs inside QWebEngineView).
 *
 * Qt reads a STEP file and calls window.loadStep(stepFileContent) with the
 * raw file text. We parse it with occt-import-js (OpenCascade -> WASM) into
 * triangle meshes and render them with Three.js.
 */

"use strict";

// ── Scene globals ──────────────────────────────────────────────────────────
let scene, camera, renderer, controls;
let modelGroup;            // holds all loaded model meshes
let gridHelper, axesHelper;
let wireframe = false;
let occtPromise = null;    // memoised occt-import-js module

const DARK_BG = 0x1a1a2e;
const LIGHT_BG = 0xe8e8e0;

// ── DOM helpers ────────────────────────────────────────────────────────────
function $(id) { return document.getElementById(id); }

function setStatus(message) {
  const el = $("status-text");
  if (el) el.textContent = message;
}
window.setStatus = setStatus;

function setLoading(visible, text) {
  const overlay = $("loading-overlay");
  if (!overlay) return;
  if (text) $("loading-text").textContent = text;
  overlay.classList.toggle("hidden", !visible);
}

function showError(msg) {
  setStatus("Error: " + msg);
  setLoading(true, "Error: " + msg);
  console.error("[Forge3D viewer]", msg);
}

// ── Init ───────────────────────────────────────────────────────────────────
function init() {
  const canvas = $("canvas");

  renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled = true;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(DARK_BG);

  camera = new THREE.PerspectiveCamera(
    45, window.innerWidth / window.innerHeight, 0.1, 10000);
  camera.position.set(200, 150, 200);
  camera.lookAt(0, 0, 0);

  // Lights
  const ambient = new THREE.AmbientLight(0xffffff, 0.6);
  scene.add(ambient);

  const dir = new THREE.DirectionalLight(0xffffff, 0.8);
  dir.position.set(300, 400, 300);
  dir.castShadow = true;
  scene.add(dir);

  const hemi = new THREE.HemisphereLight(0x4488ff, 0x774422, 0.3);
  scene.add(hemi);

  // Controls
  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;

  // Helpers
  gridHelper = new THREE.GridHelper(500, 20, 0x333355, 0x222244);
  scene.add(gridHelper);

  axesHelper = new THREE.AxesHelper(50);
  scene.add(axesHelper);

  modelGroup = new THREE.Group();
  scene.add(modelGroup);

  window.addEventListener("resize", onResize);

  animate();
  setStatus("Ready");
}

function onResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

// ── occt-import-js loader ──────────────────────────────────────────────────
// Load the wasm binary ourselves via XHR (reliable over file:// in QWebEngine)
// and hand it to emscripten via wasmBinary, avoiding fetch()/locateFile issues.
function getOcct() {
  if (occtPromise) return occtPromise;
  occtPromise = new Promise((resolve, reject) => {
    if (typeof occtimportjs === "undefined") {
      reject(new Error("occt-import-js library not loaded"));
      return;
    }
    const xhr = new XMLHttpRequest();
    xhr.open("GET", "vendor/occt-import-js.wasm", true);
    xhr.responseType = "arraybuffer";
    xhr.onload = () => {
      if (!xhr.response) { reject(new Error("Could not load wasm binary")); return; }
      occtimportjs({ wasmBinary: new Uint8Array(xhr.response) })
        .then(resolve).catch(reject);
    };
    xhr.onerror = () => reject(new Error("Failed to fetch occt wasm"));
    xhr.send();
  });
  return occtPromise;
}

// ── Model management ───────────────────────────────────────────────────────
function disposeModel() {
  if (!modelGroup) return;
  for (let i = modelGroup.children.length - 1; i >= 0; i--) {
    const child = modelGroup.children[i];
    if (child.geometry) child.geometry.dispose();
    if (child.material) child.material.dispose();
    modelGroup.remove(child);
  }
}

window.clearScene = function () {
  disposeModel();
  setStatus("Ready");
  $("file-info").textContent = "";
  $("triangle-count").textContent = "";
  setLoading(true, "Waiting for model...");
};

window.loadStep = function (stepFileContent) {
  setLoading(true, "Parsing STEP file...");
  setStatus("Parsing STEP file...");

  getOcct().then((occt) => {
    let result;
    try {
      const buf = new TextEncoder().encode(stepFileContent);
      result = occt.ReadStepFile(buf, null);
    } catch (e) {
      showError("STEP parse failed: " + e.message);
      return;
    }

    if (!result || !result.success || !result.meshes || result.meshes.length === 0) {
      showError("No geometry found in STEP file");
      return;
    }

    disposeModel();

    const material = new THREE.MeshPhongMaterial({
      color: 0x7090b0,
      specular: 0x222222,
      shininess: 40,
      side: THREE.DoubleSide,
      wireframe: wireframe,
    });

    let triangleCount = 0;

    result.meshes.forEach((meshData) => {
      const geometry = new THREE.BufferGeometry();
      const pos = meshData.attributes.position.array;
      geometry.setAttribute(
        "position", new THREE.BufferAttribute(new Float32Array(pos), 3));

      if (meshData.attributes.normal && meshData.attributes.normal.array) {
        const norm = meshData.attributes.normal.array;
        geometry.setAttribute(
          "normal", new THREE.BufferAttribute(new Float32Array(norm), 3));
      }

      if (meshData.index && meshData.index.array) {
        const idx = meshData.index.array;
        geometry.setIndex(
          new THREE.BufferAttribute(new Uint32Array(idx), 1));
        triangleCount += idx.length / 3;
      } else {
        triangleCount += pos.length / 9;
      }

      if (!meshData.attributes.normal) geometry.computeVertexNormals();

      const mesh = new THREE.Mesh(geometry, material);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      modelGroup.add(mesh);
    });

    // Centre the model at the origin.
    const box = new THREE.Box3().setFromObject(modelGroup);
    const center = box.getCenter(new THREE.Vector3());
    modelGroup.position.sub(center);

    fitCameraToModel();

    setLoading(false);
    setStatus("Model loaded");
    const size = box.getSize(new THREE.Vector3());
    $("file-info").textContent =
      `${size.x.toFixed(1)} x ${size.y.toFixed(1)} x ${size.z.toFixed(1)} mm`;
    $("triangle-count").textContent =
      `${Math.round(triangleCount).toLocaleString()} triangles`;
  }).catch((e) => {
    showError(e.message || String(e));
  });
};

// ── Camera helpers ─────────────────────────────────────────────────────────
function fitCameraToModel() {
  const box = new THREE.Box3().setFromObject(modelGroup);
  if (box.isEmpty()) return;
  const size = box.getSize(new THREE.Vector3());
  const diag = size.length() || 100;
  const dist = diag * 1.5;

  const dirVec = new THREE.Vector3(1, 0.75, 1).normalize();
  camera.position.copy(dirVec.multiplyScalar(dist));
  camera.near = Math.max(0.1, diag / 1000);
  camera.far = diag * 100;
  camera.updateProjectionMatrix();
  controls.target.set(0, 0, 0);
  controls.update();
}

window.fitToView = function () { fitCameraToModel(); };

window.resetCamera = function () {
  camera.position.set(200, 150, 200);
  camera.near = 0.1;
  camera.far = 10000;
  camera.updateProjectionMatrix();
  controls.target.set(0, 0, 0);
  controls.update();
};

window.toggleWireframe = function () {
  wireframe = !wireframe;
  modelGroup.children.forEach((m) => {
    if (m.material) m.material.wireframe = wireframe;
  });
  return wireframe;
};

window.setBackground = function (dark) {
  scene.background = new THREE.Color(dark ? DARK_BG : LIGHT_BG);
};

// ── Boot ───────────────────────────────────────────────────────────────────
init();
