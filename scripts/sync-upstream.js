import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');

const NODE_MODULES_DIR = path.join(ROOT_DIR, 'node_modules');
const EDITOR_CLIENT_DIR = path.join(NODE_MODULES_DIR, '@node-red', 'editor-client');
const NODES_MODULE_DIR = path.join(NODE_MODULES_DIR, '@node-red', 'nodes');

const STATIC_DIR = path.join(ROOT_DIR, 'static');
const NODES_DIR = path.join(ROOT_DIR, 'nodes', 'core');

/**
 * Copies files recursively, creating directories as needed
 */
function copyDir(src, dest) {
  if (!fs.existsSync(src)) {
    console.warn(`[sync:skip] Source directory does not exist: ${src}`);
    return;
  }
  fs.mkdirSync(dest, { recursive: true });
  fs.cpSync(src, dest, { recursive: true });
  console.log(`[sync:ok] Copied ${path.relative(ROOT_DIR, src)} -> ${path.relative(ROOT_DIR, dest)}`);
}

function syncEditorClient() {
  console.log('--- Syncing @node-red/editor-client ---');
  if (!fs.existsSync(EDITOR_CLIENT_DIR)) {
    throw new Error(`@node-red/editor-client not found in ${NODE_MODULES_DIR}. Run npm install first.`);
  }

  const clientPkg = JSON.parse(fs.readFileSync(path.join(EDITOR_CLIENT_DIR, 'package.json'), 'utf-8'));
  console.log(`Upstream @node-red/editor-client version: ${clientPkg.version}`);

  // 1. Sync public assets (red, vendor, types, favicon.ico)
  const publicDir = path.join(EDITOR_CLIENT_DIR, 'public');
  if (fs.existsSync(publicDir)) {
    for (const item of fs.readdirSync(publicDir)) {
      const srcItem = path.join(publicDir, item);
      const destItem = path.join(STATIC_DIR, item);
      if (fs.statSync(srcItem).isDirectory()) {
        copyDir(srcItem, destItem);
      } else {
        fs.copyFileSync(srcItem, destItem);
        console.log(`[sync:ok] Copied file: ${item}`);
      }
    }
  }

  // 2. Sync editor locales (locales/*)
  const localesDir = path.join(EDITOR_CLIENT_DIR, 'locales');
  if (fs.existsSync(localesDir)) {
    copyDir(localesDir, path.join(STATIC_DIR, 'locales'));
  }
}

function syncNodes() {
  console.log('--- Syncing @node-red/nodes ---');
  if (!fs.existsSync(NODES_MODULE_DIR)) {
    throw new Error(`@node-red/nodes not found in ${NODE_MODULES_DIR}. Run npm install first.`);
  }

  const nodesPkg = JSON.parse(fs.readFileSync(path.join(NODES_MODULE_DIR, 'package.json'), 'utf-8'));
  console.log(`Upstream @node-red/nodes version: ${nodesPkg.version}`);

  // 1. Sync core node HTML templates
  const coreDir = path.join(NODES_MODULE_DIR, 'core');
  if (fs.existsSync(coreDir)) {
    for (const cat of fs.readdirSync(coreDir)) {
      const catSrc = path.join(coreDir, cat);
      if (fs.statSync(catSrc).isDirectory()) {
        const catDest = path.join(NODES_DIR, cat);
        fs.mkdirSync(catDest, { recursive: true });
        for (const file of fs.readdirSync(catSrc)) {
          if (file.endsWith('.html')) {
            fs.copyFileSync(path.join(catSrc, file), path.join(catDest, file));
          }
        }
        console.log(`[sync:ok] Synced node templates: core/${cat}`);
      }
    }
  }

  // 2. Sync core icons
  const iconsDir = path.join(NODES_MODULE_DIR, 'icons');
  if (fs.existsSync(iconsDir)) {
    copyDir(iconsDir, path.join(STATIC_DIR, 'icons'));
  }

  // 3. Sync node i18n locales if present
  const nodeLocalesDir = path.join(NODES_MODULE_DIR, 'locales');
  if (fs.existsSync(nodeLocalesDir)) {
    copyDir(nodeLocalesDir, path.join(STATIC_DIR, 'locales'));
  }
}

function main() {
  try {
    syncEditorClient();
    syncNodes();
    console.log('--- Upstream Frontend Sync Complete! ---');
  } catch (err) {
    console.error('[sync:error]', err.message);
    process.exit(1);
  }
}

main();

