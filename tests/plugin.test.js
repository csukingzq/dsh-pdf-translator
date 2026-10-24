import test from 'node:test';
import assert from 'node:assert/strict';
import { Context } from '@deepseek-ai/cordis';
import { ToolRuntime } from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import Registry from '@deepseek-ai/dsh-typert-registry';
import * as plugin from '../src/index.js';
import { runPython, root } from '../src/runner.js';
import path from 'node:path';

test('Cordis registers native tools, validates inputs and disposes registrations', async () => {
  const ctx = new Context();
  ctx.plugin(SystemPrompt);
  ctx.plugin(ToolRuntime);
  ctx.plugin(Registry);
  const fiber = ctx.plugin(plugin);
  await new Promise(resolve => setTimeout(resolve, 30));
  const registry = ctx.get('tools');
  assert.ok(registry.get('pdf_translate'));
  assert.ok(ctx.get('pdfTranslator'));
  assert.ok(ctx.typert.local.get('pdfTranslator/call'));
  const signal = new AbortController().signal;
  const doctor = await registry.execute({ callId: 'doctor-1', name: 'pdf_translator_doctor', arguments: {}, signal });
  assert.equal(doctor.isError, false, JSON.stringify(doctor));
  assert.equal(doctor.value.local_ocr, false);
  const inspect = await registry.execute({ callId: 'inspect-1', name: 'pdf_inspect',
    arguments: { pdf: path.join(root, 'tests/fixtures/vision-sample.pdf') }, signal });
  assert.equal(inspect.isError, false, JSON.stringify(inspect));
  assert.equal(inspect.value.pages, 1);
  const invalid = await registry.execute({ callId: 'invalid-1', name: 'pdf_translate', arguments: { pdf: 'x', workers: 0 }, signal });
  assert.equal(invalid.isError, true);
  await fiber.dispose();
  assert.equal(registry.get('pdf_translate'), undefined);
  await ctx.fiber.dispose();
});

test('pre-aborted requests do not launch Python', async () => {
  const controller = new AbortController(); controller.abort();
  assert.throws(() => runPython({ operation: 'doctor' }, {}, controller.signal), /abort/i);
});

test('bridge returns useful failure for nonexistent PDF', async () => {
  await assert.rejects(runPython({ operation: 'inspect', pdf: path.join(root, 'missing.pdf') }), /PDF/);
});

test('bridge cancellation stops a running process', async () => {
  const controller = new AbortController();
  const result = runPython({ operation: 'doctor' }, {}, controller.signal);
  controller.abort();
  await assert.rejects(result, /取消/);
});
