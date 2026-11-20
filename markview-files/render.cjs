// Crossnote bridge. One JSON request on stdin, one JSON response on stdout.
// Source text is supplied in memory; rendering never saves the user's document.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { fileURLToPath, pathToFileURL } = require('node:url');
const { randomBytes } = require('node:crypto');
const { Notebook, setBuildDirectory, defaultConfig, loadHTML } = require('./vendor/crossnote/engine.cjs');

setBuildDirectory(path.join(__dirname, 'vendor', 'crossnote', 'assets'));

const IMAGE_EXT_RE = /\.(?:png|jpe?g|gif|svg|webp|bmp|ico|avif)(?:[?#].*)?$/i;

function normalizeImageMarkdownLine(line) {
  // Split around inline code spans so code examples stay untouched.
  const parts = line.split(/(`+(?:[^`]|`(?!\1))*?`+)/);
  for (let i = 0; i < parts.length; i += 2) {
    parts[i] = parts[i].replace(/!\[([^\]]*)\]\(([^)\n]+)\)/g, (full, alt, rawDest) => {
      const dest = rawDest.trim();
      if (!dest || dest.startsWith('<')) return full;
      if (/^file:\/\//i.test(dest)) {
        try {
          let localPath = fileURLToPath(dest);
          if (/^\/[a-zA-Z]:[\\/]/.test(localPath)) localPath = localPath.slice(1);
          localPath = localPath.replace(/\\/g, '/');
          return `![${alt}](<${localPath}>)`;
        } catch {
          return full;
        }
      }
      if (/^(?:https?:|data:|blob:)/i.test(dest)) return full;
      if (/["']/.test(dest)) return full;
      if (dest.includes('\\')) {
        const posix = dest.replace(/\\/g, '/');
        return /\s/.test(posix) ? `![${alt}](<${posix}>)` : `![${alt}](${posix})`;
      }
      if (/\s/.test(dest) && IMAGE_EXT_RE.test(dest)) {
        return `![${alt}](<${dest}>)`;
      }
      return full;
    });
  }
  return parts.join('');
}

function preprocessImageLinks(markdown) {
  const lines = markdown.split('\n');
  let fenceChar = '';
  let fenceLen = 0;
  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(/^\s*(`{3,}|~{3,})/);
    if (match) {
      const marker = match[1];
      if (!fenceChar) {
        fenceChar = marker[0];
        fenceLen = marker.length;
      } else if (marker[0] === fenceChar && marker.length >= fenceLen && lines[i].trim().length === marker.length) {
        fenceChar = '';
        fenceLen = 0;
      }
      continue;
    }
    if (!fenceChar && lines[i].includes('![')) {
      lines[i] = normalizeImageMarkdownLine(lines[i]);
    }
  }
  return lines.join('\n');
}

function toFileHref(localPath, suffix = '') {
  if (/^[a-zA-Z]:[\\/]/.test(localPath) && process.platform !== 'win32') {
    return 'file:///' + encodeURI(localPath.replace(/\\/g, '/')) + suffix;
  }
  return pathToFileURL(localPath).href + suffix;
}

function resolveMediaSrc(src, docDir, docBaseUrl) {
  if (!src) return src;
  const trimmed = src.trim();
  if (/^(?:https?:|data:|blob:)/i.test(trimmed)) return trimmed;

  if (trimmed.startsWith(docBaseUrl)) {
    const tail = trimmed.slice(docBaseUrl.length);
    const match = tail.match(/^([^?#]*)(.*)$/);
    const rawPath = match ? match[1] : tail;
    const suffix = match ? match[2] : '';
    let rel;
    try {
      rel = decodeURIComponent(rawPath);
    } catch {
      rel = rawPath;
    }
    if (rel.startsWith('~/') || rel.startsWith('~\\')) {
      return toFileHref(path.join(os.homedir(), rel.slice(2)), suffix);
    }
    if (/^[a-zA-Z]:[\\/]/.test(rel)) {
      return toFileHref(rel, suffix);
    }
    if (!fs.existsSync(path.join(docDir, rel))) {
      if (rel.startsWith('/') && fs.existsSync(rel)) {
        return toFileHref(rel, suffix);
      }
      if (path.sep === '/' && fs.existsSync('/' + rel)) {
        return toFileHref('/' + rel, suffix);
      }
    }
    return trimmed;
  }

  if (/^file:\/\//i.test(trimmed)) return trimmed;
  const match = trimmed.match(/^([^?#]*)(.*)$/);
  const rawPath = match ? match[1] : trimmed;
  const suffix = match ? match[2] : '';
  if (rawPath.startsWith('~/') || rawPath.startsWith('~\\')) {
    return toFileHref(path.join(os.homedir(), rawPath.slice(2)), suffix);
  }
  if (/^[a-zA-Z]:[\\/]/.test(rawPath)) {
    return toFileHref(rawPath, suffix);
  }
  if (path.isAbsolute(rawPath)) {
    return toFileHref(rawPath, suffix);
  }
  return toFileHref(path.resolve(docDir, rawPath), suffix);
}

async function render(request) {
  const filename = path.resolve(request.filename);
  const docDir = path.dirname(filename);
  const docBaseUrl = pathToFileURL(docDir + path.sep).href;
  const light = request.theme === 'light';
  const notebook = new Notebook();
  // Keep preview configuration independent of executable workspace config files.
  notebook.initConfig = async (config) => { notebook.config = { ...defaultConfig(), ...config }; };
  await notebook.init({ notebookPath: docDir, config: {
    previewTheme: light ? 'github-light.css' : 'github-dark.css',
    codeBlockTheme: light ? 'github.css' : 'github-dark.css',
    mathRenderingOption: 'KaTeX',
    enableExtendedTableSyntax: true,
    enableCriticMarkupSyntax: true,
    enableScriptExecution: false,
    plantumlServer: '', krokiServer: '', webSequenceDiagramsServer: '',
    mermaidConfig: { startOnLoad: false, securityLevel: 'strict', theme: light ? 'default' : 'dark' },
  }});
  const engine = notebook.getNoteMarkdownEngine(path.basename(filename));
  const source = request.markdown ? preprocessImageLinks(request.markdown) : '\n';
  // Crossnote treats an empty string as a request to read the file from disk.
  const result = await engine.parseMD(source, {
    useRelativeFilePath: false, hideFrontMatter: true, isForPreview: false,
    runAllCodeChunks: false, triggeredBySave: false,
  });
  const dom = loadHTML(result.html);
  dom('script, iframe, object, embed, base, meta, link').remove();
  dom('*').each((_, element) => {
    for (const name of Object.keys(element.attribs || {})) {
      if (/^on/i.test(name) || name === 'srcdoc') dom(element).removeAttr(name);
    }
  });
  dom('img[src], video[src], audio[src], source[src]').each((_, element) => {
    const src = dom(element).attr('src');
    const resolved = resolveMediaSrc(src, docDir, docBaseUrl);
    if (resolved !== src) dom(element).attr('src', resolved);
  });
  const body = (dom('head').html() || '') + (dom('body').html() || '');
  let html = await engine.generateHTMLTemplateForExport(body, result.yamlConfig, {
    offline: true, isForPrint: false, isForPrince: false, embedLocalImages: false,
  });
  const nonce = randomBytes(18).toString('base64');
  // Crossnote's export template assigns its own Mermaid theme after the config.
  html = html.replace(/MERMAID_CONFIG\.theme = "[^"]*"/g,
                      `MERMAID_CONFIG.theme = "${light ? 'default' : 'dark'}"`);
  html = html.replace(/<head>/i, `<head><meta name="color-scheme" content="${light ? 'light' : 'dark'}">`);
  html = html.replace(/<script\b/g, `<script nonce="${nonce}"`);
  // Scripts generated by Crossnote may run; scripts from Markdown may not.
  const policy = `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline' file:; img-src file: data: https: http: blob:; font-src file: data:; media-src file: data: https: http: blob:; connect-src 'none'; object-src 'none'; base-uri file:; form-action 'none'`;
  let fontCss = '';
  const fontRules = [];
  if (typeof request.fontFamily === 'string' && request.fontFamily.trim()) {
    const safeFamily = request.fontFamily.replace(/["'\\<>{};]/g, '').trim();
    if (safeFamily) fontRules.push(`font-family: "${safeFamily}", sans-serif;`);
  }
  const fontSize = Number(request.fontSize);
  if (Number.isFinite(fontSize) && fontSize >= 9 && fontSize <= 28 && fontSize !== 12) {
    fontRules.push(`font-size: ${Math.round(fontSize)}pt;`);
  }
  if (fontRules.length) {
    fontCss = `<style>.markdown-preview, .markdown-preview p, .markdown-preview li, .markdown-preview td, .markdown-preview th { ${fontRules.join(' ')} }</style>`;
  }
  html = html.replace(/<head>/i, `<head><meta http-equiv="Content-Security-Policy" content="${policy}"><base href="${docBaseUrl}">`);
  if (fontCss) {
    html = html.replace(/<\/head>/i, `${fontCss}</head>`);
  }
  return { html };
}

if (require.main === module) {
  let input = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => { input += chunk; });
  process.stdin.on('end', async () => {
    try {
      const result = await render(JSON.parse(input));
      process.stdout.write(JSON.stringify(result));
    } catch (error) {
      process.stdout.write(JSON.stringify({ error: String(error.message || error) }));
      process.exitCode = 1;
    }
  });
}
module.exports = { render };
