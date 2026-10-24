import { runPython } from '../src/runner.js';
const [pdf, pages = 'all', mode] = process.argv.slice(2);
if (!pdf) {
  console.error('Usage: node scripts/translate.mjs "D:/book.pdf" [all|1,3-5] [--render-only]');
  process.exitCode = 1;
} else {
  const controller = new AbortController();
  process.once('SIGINT', () => controller.abort());
  try {
    console.log(JSON.stringify(await runPython({ operation: 'translate', pdf, pages,
      renderOnly: mode === '--render-only' }, {}, controller.signal), null, 2));
  } catch (error) {
    console.error(error.message); process.exitCode = 1;
  }
}
