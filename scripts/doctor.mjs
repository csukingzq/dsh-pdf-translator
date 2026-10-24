import { runPython } from '../src/runner.js';
try { console.log(JSON.stringify(await runPython({ operation: 'doctor' }), null, 2)); }
catch (error) { console.error(error.message); process.exitCode = 1; }
