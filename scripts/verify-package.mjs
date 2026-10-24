#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';

const required = [
  'package/package.json',
  'package/src/index.js',
  'package/lib/client.js',
  'package/cordis.patch.yml',
  'package/work/cli.py',
  'package/scripts/setup.ps1',
  'package/config.example.json',
  'package/README.md',
  'package/LICENSE',
];
const forbidden = [
  /^package\/\.venv\//,
  /^package\/runtime\//,
  /^package\/config\.json$/,
  /^package\/work\/plugin-state\.json$/,
  /^package\/work\/document-cache\//,
  /^package\/work\/review-transactions\//,
  /^package\/outputs\//,
  /^package\/\.translation\.lock$/,
  /^package\/node_modules\//,
  /^package\/\.git\//,
  /\.tgz$/,
];

function text(buffer, start, length) {
  return buffer.subarray(start, start + length).toString('utf8').replace(/\0.*$/, '');
}

function paxPath(data) {
  const fields = data.toString('utf8').split('\n');
  for (const field of fields) {
    const match = /^\d+ path=(.*)$/.exec(field);
    if (match) return match[1];
  }
  return null;
}

function readTar(buffer) {
  const files = new Map();
  let offset = 0;
  let longName = null;
  let extendedPath = null;
  while (offset + 512 <= buffer.length) {
    const header = buffer.subarray(offset, offset + 512);
    if (header.every((byte) => byte === 0)) break;
    let name = text(header, 0, 100);
    const prefix = text(header, 345, 155);
    if (prefix) name = `${prefix}/${name}`;
    const sizeText = text(header, 124, 12).trim();
    const size = sizeText ? parseInt(sizeText, 8) : 0;
    const type = String.fromCharCode(header[156] || 48);
    const start = offset + 512;
    const data = buffer.subarray(start, start + size);
    if (type === 'L') {
      longName = data.toString('utf8').replace(/\0.*$/, '');
    } else if (type === 'x') {
      extendedPath = paxPath(data);
    } else if (type === 'g') {
      // Global pax header: no file content.
    } else {
      if (longName) { name = longName; longName = null; }
      if (extendedPath) { name = extendedPath; extendedPath = null; }
      files.set(name, data);
    }
    offset = start + Math.ceil(size / 512) * 512;
  }
  return files;
}

const archive = process.argv[2];
if (!archive) {
  console.error('Usage: node scripts/verify-package.mjs <package.tgz>');
  process.exit(2);
}
if (!fs.existsSync(archive)) {
  console.error(`Package not found: ${archive}`);
  process.exit(2);
}
const bytes = fs.readFileSync(archive);
const files = readTar(gunzipSync(bytes));
const problems = [];
for (const name of required) if (!files.has(name)) problems.push(`missing required file: ${name}`);
for (const name of files.keys()) {
  if (forbidden.some((pattern) => pattern.test(name))) problems.push(`forbidden file: ${name}`);
}
const manifestEntry = files.get('package/package.json');
if (manifestEntry) {
  try {
    const manifest = JSON.parse(manifestEntry.toString('utf8'));
    if (manifest.name !== 'dsh-pdf-translator') problems.push(`unexpected package name: ${manifest.name}`);
    if (!manifest.version) problems.push('package.json has no version');
    if (manifest.dsh?.bundle?.patch !== './cordis.patch.yml') problems.push('package.json is missing dsh.bundle.patch');
  } catch (error) {
    problems.push(`package.json is not valid JSON: ${error.message}`);
  }
}
if (!files.has('package/lib/client.js') || files.get('package/lib/client.js').length === 0) {
  problems.push('lib/client.js is empty');
}
for (const [name, data] of files) {
  if (data.length > 5 * 1024 * 1024) problems.push(`oversized file: ${name} (${data.length} bytes)`);
}
if (bytes.length > 10 * 1024 * 1024) problems.push(`package is too large: ${bytes.length} bytes`);
if (problems.length) {
  console.error(`Package verification failed for ${path.basename(archive)}:`);
  for (const problem of problems) console.error(`  - ${problem}`);
  process.exit(1);
}
const size = (bytes.length / 1024).toFixed(1);
console.log(`Package OK: ${path.basename(archive)} (${files.size} files, ${size} KiB)`);
for (const name of required.filter((name) => name.endsWith('package.json'))) {
  console.log(`  ${name}: ${JSON.parse(files.get(name).toString('utf8')).version}`);
}
