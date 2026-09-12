import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { minify as minifyHtml } from 'html-minifier-terser';
import * as esbuild from 'esbuild';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');
const STATIC_DIR = path.join(ROOT_DIR, 'static');
const DIST_DIR = path.join(ROOT_DIR, 'dist');
const NODES_DIR = path.join(ROOT_DIR, 'nodes', 'core');
const DIST_NODES_DIR = path.join(DIST_DIR, 'nodes', 'core');

/**
 * Minifies JavaScript inside script tags using esbuild
 */
async function minifyJsContent(code) {
  try {
    const res = await esbuild.transform(code, {
      loader: 'js',
      minify: true,
      target: 'es2020',
    });
    return res.code;
  } catch (err) {
    console.warn(`[warn] JS minification error: ${err.message}. Preserving original code.`);
    return code;
  }
}

/**
 * Compiles a single Node-RED .html node file into an optimized, modular chunk
 */
async function compileNodeFile(srcFile, destFile) {
  const content = fs.readFileSync(srcFile, 'utf-8');

  // 1. Process and minify <script type="text/javascript"> blocks
  const jsRegex = /<script\b([^>]*type=["']text\/javascript["'][^>]*)>([\s\S]*?)<\/script>/gi;
  let transformed = await replaceAsync(content, jsRegex, async (match, attrs, code) => {
    if (!code.trim()) return match;
    const minified = await minifyJsContent(code);
    return `<script${attrs}>${minified}</script>`;
  });

  // 2. Minify HTML form templates and help text
  try {
    transformed = await minifyHtml(transformed, {
      collapseWhitespace: true,
      removeComments: true,
      preserveLineBreaks: false,
      minifyCSS: true,
    });
  } catch (err) {
    console.warn(`[warn] HTML minification error on ${path.basename(srcFile)}: ${err.message}`);
  }

  // Ensure destination directory exists
  fs.mkdirSync(path.dirname(destFile), { recursive: true });
  fs.writeFileSync(destFile, transformed, 'utf-8');
}

/**
 * Helper for async String.replace
 */
async function replaceAsync(str, regex, asyncFn) {
  const promises = [];
  str.replace(regex, (match, ...args) => {
    promises.push(asyncFn(match, ...args));
    return match;
  });
  const data = await Promise.all(promises);
  return str.replace(regex, () => data.shift());
}

/**
 * Recursively scans and compiles all .html files in nodes/
 */
async function buildAllNodes(srcDir, outDir) {
  if (!fs.existsSync(srcDir)) {
    console.warn(`Directory not found: ${srcDir}`);
    return;
  }

  const entries = fs.readdirSync(srcDir, { withFileTypes: true });
  for (const entry of entries) {
    const fullSrc = path.join(srcDir, entry.name);
    const fullDest = path.join(outDir, entry.name);

    if (entry.isDirectory()) {
      await buildAllNodes(fullSrc, fullDest);
    } else if (entry.isFile() && entry.name.endsWith('.html')) {
      await compileNodeFile(fullSrc, fullDest);
      console.log(`Compiled: ${path.relative(ROOT_DIR, fullSrc)} -> ${path.relative(ROOT_DIR, fullDest)}`);
    }
  }
}

/**
 * Copies static assets (vendor, locales, red, icons) into dist to ensure complete standalone serving
 */
function copyStaticAssets() {
  const dirsToCopy = ['vendor', 'locales', 'red', 'icons', 'types', 'debug'];
  for (const dir of dirsToCopy) {
    const src = path.join(STATIC_DIR, dir);
    const dest = path.join(DIST_DIR, dir);
    if (fs.existsSync(src)) {
      fs.cpSync(src, dest, { recursive: true });
      console.log(`Copied static directory: ${dir} -> dist/${dir}`);
    }
  }
}

async function main() {
  console.log('--- Compiling Node-RED Modular Node Chunks ---');
  await buildAllNodes(NODES_DIR, DIST_NODES_DIR);
  console.log('--- Copying Standalone Static Resources ---');
  copyStaticAssets();
  console.log('--- Modular Nodes & Static Assets Build Complete ---');
}

main().catch(err => {
  console.error('Build nodes error:', err);
  process.exit(1);
});

