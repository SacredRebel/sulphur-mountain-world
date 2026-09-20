// Rebuild committed massing models from their scripts.
//
//   node scripts/build-models.mjs
//
//   Each entry in MODELS is one generator. The script is the source of truth; the GLB under
//   models/ is the artifact and is committed with the pack (static hosting — no deploy build).
//   Needs python3 with numpy and scipy; if they are missing it makes a small virtual environment.
import { spawnSync } from 'node:child_process';
import { mkdirSync, existsSync, statSync } from 'node:fs';
import { join } from 'node:path';

const MODELS = [
  { script: 'scripts/oak-leaf.py', out: 'models/oak-leaf-massing.glb' },
  { script: 'scripts/example-box.py', out: 'models/example-box.glb' },
  { script: 'scripts/retreat-village.py', out: 'models/retreat-village.glb' },
  { script: 'scripts/glamping-creek.py', out: 'models/glamping-creek.glb' },
  { script: 'scripts/the-barn.py', out: 'models/the-barn.glb' },
  { script: 'scripts/agricultural-hub.py', out: 'models/agricultural-hub.glb' },
  { script: 'scripts/tropical-dome.py', out: 'models/tropical-dome.glb' },
];
const VENV = '.venv-models';

const run = (cmd, args) => spawnSync(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf8' });
const has = py => run(py, ['-c', 'import numpy, scipy']).status === 0;

let python = ['python3', 'python'].find(p => run(p, ['--version']).status === 0);
if (!python) { console.warn('[models] no python3 on this machine — the massing models are not built'); process.exit(0); }

if (!has(python)) {
  const venvPy = join(VENV, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  if (!(existsSync(venvPy) && has(venvPy))) {
    console.log('[models] numpy and scipy are missing — making a virtual environment for them…');
    const mk = run(python, ['-m', 'venv', VENV]);
    const pip = mk.status === 0 ? run(venvPy, ['-m', 'pip', 'install', '--quiet', 'numpy', 'scipy']) : mk;
    if (pip.status !== 0 || !has(venvPy)) {
      console.warn('[models] could not get numpy/scipy — the massing models are not built\n' + (pip.stderr || '').slice(-600));
      process.exit(0);
    }
  }
  python = venvPy;
}

mkdirSync('models', { recursive: true });
for (const m of MODELS) {
  const r = run(python, [m.script, m.out]);
  if (r.status !== 0 || !existsSync(m.out)) {
    console.warn(`[models] ${m.script} failed — ${m.out} not built\n` + (r.stderr || r.stdout || '').slice(-600));
    continue;
  }
  console.log(`[models] ${m.out} ${(statSync(m.out).size / 1024).toFixed(0)} KB ${r.stdout.trim()}`);
  const v = run(python, ['scripts/validate-model.py', m.out]);
  if (v.status !== 0) {
    console.warn(`[models] validate failed for ${m.out}\n` + (v.stdout || v.stderr || '').slice(-800));
  } else {
    console.log(`[models] validate ok ${m.out}`);
  }
}
