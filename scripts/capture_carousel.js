#!/usr/bin/env node
/**
 * capture_carousel.js
 *
 * carousel_redesign_v4.html の {{PLACEHOLDER}} を書き換えて
 * Puppeteer で各スライドを 1080×1350 PNG に撮影する。
 * carousel_agent.py から subprocess で呼び出される。
 *
 * Usage:
 *   node scripts/capture_carousel.js \
 *     --content '{"slides":[...]}' \
 *     --out logs/carousel_images/YYYYMMDD
 *
 * stdout: JSON 配列 ["/abs/path/slide_1.png", ..., "slide_7.png"]
 * stderr: 進捗ログ
 */

const fs        = require('fs');
const path      = require('path');
const os        = require('os');
const puppeteer = require('puppeteer');

const ROOT = path.join(__dirname, '..');

// ─── 設定読み込み ─────────────────────────────────────────────────────────────

function loadConfig(configPath) {
  const defaults = {
    html_file:         'templates/carousel_redesign_v4.html',
    viewport:          { width: 1080, height: 1350 },
    device_scale_factor: 2,
    wait_ms:           300,
    account:           '@ryo_finance_ai',
    role_colors: {
      hook:    '#f0c040',
      problem: '#e05040',
      step:    '#f0c040',
      proof:   '#40c080',
      cta:     '#f0c040',
    },
  };
  if (!fs.existsSync(configPath)) return defaults;
  try {
    return { ...defaults, ...JSON.parse(fs.readFileSync(configPath, 'utf8')) };
  } catch {
    return defaults;
  }
}

// ─── 引数パース ───────────────────────────────────────────────────────────────

function parseArgs() {
  const argv = process.argv.slice(2);
  const get  = (flag) => { const i = argv.indexOf(flag); return i !== -1 ? argv[i + 1] : null; };

  const contentArg = get('--content');
  const outDir     = get('--out') || path.join(ROOT, 'logs', 'carousel_images');
  const configPath = get('--config') || path.join(ROOT, 'config', 'carousel_html_config.json');

  if (!contentArg) {
    console.error('Usage: node capture_carousel.js --content <json> [--out <dir>]');
    process.exit(1);
  }

  return {
    content: JSON.parse(contentArg),
    outDir,
    config: loadConfig(configPath),
  };
}

// ─── スライドごとの HTML 生成（プレースホルダー置換）────────────────────────

function buildHtml(template, slide, totalSlides, config) {
  const role      = slide.role || 'step';
  const roleColor = (config.role_colors || {})[role] || '#f0c040';

  return template
    .replace(/\{\{HEADLINE\}\}/g,  slide.headline  || '')
    .replace(/\{\{SUBTEXT\}\}/g,   slide.subtext   || '')
    .replace(/\{\{BODY\}\}/g,      (slide.body || '').replace(/\\n/g, '<br>').replace(/\n/g, '<br>'))
    .replace(/\{\{SLIDE_NUM\}\}/g, String(slide.num || 1))
    .replace(/\{\{TOTAL\}\}/g,     String(totalSlides))
    .replace(/\{\{ACCOUNT\}\}/g,   config.account  || '@ryo_finance_ai')
    .replace(/\{\{ROLE\}\}/g,      role)
    .replace(/\{\{ROLE_COLOR\}\}/g, roleColor);
}

// ─── メイン ───────────────────────────────────────────────────────────────────

(async () => {
  const { content, outDir, config } = parseArgs();
  const slides  = content.slides || [];
  const vp      = config.viewport || { width: 1080, height: 1350 };
  const scale   = config.device_scale_factor || 2;
  const waitMs  = config.wait_ms || 300;

  // HTML テンプレート読み込み
  const htmlPath = path.resolve(ROOT, config.html_file || 'templates/carousel_redesign_v4.html');
  if (!fs.existsSync(htmlPath)) {
    console.error(`[capture_carousel] HTML が見つかりません: ${htmlPath}`);
    process.exit(1);
  }
  const template = fs.readFileSync(htmlPath, 'utf8');

  fs.mkdirSync(outDir, { recursive: true });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: vp.width, height: vp.height, deviceScaleFactor: scale });

  const outputPaths = [];

  for (const slide of slides) {
    const num     = slide.num || (slides.indexOf(slide) + 1);
    const html    = buildHtml(template, slide, slides.length, config);
    const tmpFile = path.join(os.tmpdir(), `carousel_slide_${num}.html`);
    fs.writeFileSync(tmpFile, html, 'utf8');

    await page.goto(`file://${tmpFile}`, { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, waitMs));

    const outPath = path.join(outDir, `slide_${num}.png`);
    await page.screenshot({
      path: outPath,
      type: 'png',
      clip: { x: 0, y: 0, width: vp.width, height: vp.height },
    });

    fs.unlinkSync(tmpFile);
    outputPaths.push(outPath);
    console.error(`[capture_carousel] ✓ slide_${num}.png`);
  }

  await browser.close();
  process.stdout.write(JSON.stringify(outputPaths) + '\n');
})().catch(err => {
  console.error('[capture_carousel] ERROR:', err.message);
  process.exit(1);
});
