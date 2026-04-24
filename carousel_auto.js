#!/usr/bin/env node
/**
 * carousel_auto.js
 *
 * 自動カルーセル生成・投稿パイプライン
 *   1. Claude API でテーマ決定 → 7枚スライドのコンテンツ生成
 *   2. Puppeteer で HTML テンプレートをスライドごとにスクリーンショット
 *   3. carousel_post.py を呼び出して Instagram カルーセル投稿
 *
 * Usage:
 *   node carousel_auto.js                  # 本番実行
 *   node carousel_auto.js --dry-run        # スクリーンショットのみ（投稿しない）
 *   node carousel_auto.js --weekday 3      # 曜日を手動指定（0=月〜6=日）
 */

const fs   = require('fs');
const path = require('path');
const os   = require('os');
const { execSync, spawnSync } = require('child_process');
const Anthropic = require('@anthropic-ai/sdk');
const puppeteer = require('puppeteer');

// ─── 環境変数 ─────────────────────────────────────────────────────────────────

const ENV_PATH = path.join(os.homedir(), 'Documents/Obsidian Vault/.env');
if (fs.existsSync(ENV_PATH)) {
  fs.readFileSync(ENV_PATH, 'utf8').split('\n').forEach(line => {
    const [k, ...rest] = line.split('=');
    if (k && rest.length && !k.startsWith('#')) {
      process.env[k.trim()] = rest.join('=').trim();
    }
  });
}

const ROOT        = __dirname;
const IMAGES_DIR  = path.join(ROOT, 'images');
const LOGS_DIR    = path.join(ROOT, 'logs');
const TMPL_PATH   = path.join(ROOT, 'templates', 'carousel_template.json');
const POST_SCRIPT = path.join(ROOT, 'scripts', 'carousel_post.py');

fs.mkdirSync(IMAGES_DIR, { recursive: true });
fs.mkdirSync(LOGS_DIR,   { recursive: true });

// ─── CLI 引数 ─────────────────────────────────────────────────────────────────

const args    = process.argv.slice(2);
const DRY_RUN = args.includes('--dry-run');
const wdIdx   = args.indexOf('--weekday');
const WEEKDAY = wdIdx !== -1 ? parseInt(args[wdIdx + 1]) : new Date().getDay() === 0 ? 6 : new Date().getDay() - 1;

const DAY_NAMES   = ['月', '火', '水', '木', '金', '土', '日'];
const DAY_THEMES  = [
  '積立NISA・長期投資の基礎と実践',
  'ChatGPT・AI副業で収入を増やす具体的な方法',
  '副業収入の仕組み化・自動化',
  '投資信託・ETF・米国株の選び方',
  '金融リテラシー・複利・節税',
  'AI副業実績レポートと学び',
  'ライフプラン・FIRE・老後資金',
];

// ─── Claude API でスライドコンテンツ生成 ─────────────────────────────────────

async function generateSlides(weekday) {
  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const theme  = DAY_THEMES[weekday];

  console.log(`[carousel_auto] テーマ: ${DAY_NAMES[weekday]}曜日 — ${theme}`);

  const prompt = `あなたは金融機関20年勤務の元バンカー・FP資格保持のインフルエンサーです。

テーマ：${theme}
トーン：等身大の語りかけ口調（「〜なんです」「実は私も〜」「私の場合は〜だった」）
構成：共感→ストーリー→CTA

Instagram カルーセル 7枚分のスライドコンテンツを JSON で返してください。
コンプライアンス：「月○万円稼げる」「必ず儲かる」等の収益約束・投資断定は禁止。体験談ベースで。

JSON形式（コードブロック不要）：
{
  "caption": "Instagram キャプション（500字以内・等身大トーン・ハッシュタグ5個末尾）",
  "slides": [
    {
      "num": 1,
      "role": "hook",
      "headline": "見出し（20字以内・2行可）",
      "subtext": "サブテキスト（30字以内・金色で表示）",
      "body": "本文（60字以内・改行\\nで区切る）"
    }
  ]
}

role は hook / problem / step / proof / cta のいずれか。
slide 1=hook, 2=problem, 3〜5=step, 6=proof, 7=cta。`;

  const msg = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 2000,
    messages:   [{ role: 'user', content: prompt }],
  });

  const text = msg.content[0].text.replace(/```json|```/g, '').trim();
  const data = JSON.parse(text);
  console.log(`[carousel_auto] スライド生成完了: ${data.slides.length}枚`);
  return data;
}

// ─── HTML テンプレートロード ───────────────────────────────────────────────────

function loadTemplate() {
  if (!fs.existsSync(TMPL_PATH)) {
    throw new Error(`テンプレートが見つかりません: ${TMPL_PATH}`);
  }
  return JSON.parse(fs.readFileSync(TMPL_PATH, 'utf8'));
}

// ─── スライド HTML 生成 ────────────────────────────────────────────────────────

function buildSlideHtml(tmpl, slide, totalSlides, account) {
  let html = tmpl.html_template;
  html = html
    .replace(/\{\{HEADLINE\}\}/g,   slide.headline  || '')
    .replace(/\{\{SUBTEXT\}\}/g,    slide.subtext   || '')
    .replace(/\{\{BODY\}\}/g,       (slide.body || '').replace(/\\n/g, '<br>'))
    .replace(/\{\{SLIDE_NUM\}\}/g,  String(slide.num))
    .replace(/\{\{TOTAL\}\}/g,      String(totalSlides))
    .replace(/\{\{ACCOUNT\}\}/g,    account || '@ryo_finance_ai')
    .replace(/\{\{ROLE\}\}/g,       slide.role || 'step');
  return html;
}

// ─── Puppeteer でスクリーンショット ─────────────────────────────────────────────

async function screenshotSlides(slides, tmpl, dateStr, account) {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();

  const { width, height } = tmpl.viewport || { width: 1080, height: 1350 };
  await page.setViewport({ width, height, deviceScaleFactor: 2 });

  const imagePaths = [];

  for (const slide of slides) {
    const html    = buildSlideHtml(tmpl, slide, slides.length, account);
    const tmpFile = path.join(os.tmpdir(), `carousel_slide_${slide.num}.html`);
    fs.writeFileSync(tmpFile, html, 'utf8');

    await page.goto(`file://${tmpFile}`, { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 200));

    const outPath = path.join(IMAGES_DIR, `post_${dateStr}_slide${slide.num}.jpg`);
    await page.screenshot({
      path:    outPath,
      type:    'jpeg',
      quality: 92,
      clip:    { x: 0, y: 0, width, height },
    });

    fs.unlinkSync(tmpFile);
    console.log(`[carousel_auto] ✓ slide${slide.num}: ${path.basename(outPath)}`);
    imagePaths.push(outPath);
  }

  await browser.close();
  return imagePaths;
}

// ─── carousel_post.py 呼び出し ───────────────────────────────────────────────

function postToInstagram(imagePaths, caption, dateStr) {
  const resultPath = path.join(LOGS_DIR, `carousel_result_${dateStr}.json`);
  const imagesArg  = imagePaths.map(p => `"${p}"`).join(' ');
  const captionArg = caption.replace(/"/g, '\\"');

  const cmd = `python3 "${POST_SCRIPT}" --images ${imagesArg} --caption "${captionArg}" --out "${resultPath}"`;
  console.log('\n[carousel_auto] Instagram投稿開始...');

  const result = spawnSync('python3', [
    POST_SCRIPT,
    '--images', ...imagePaths,
    '--caption', caption,
    '--out', resultPath,
  ], { stdio: 'inherit', encoding: 'utf8' });

  if (result.status !== 0) {
    throw new Error(`carousel_post.py が失敗しました (exit code: ${result.status})`);
  }

  if (fs.existsSync(resultPath)) {
    return JSON.parse(fs.readFileSync(resultPath, 'utf8'));
  }
  return { status: 'success' };
}

// ─── ログ記録 ─────────────────────────────────────────────────────────────────

function saveLog(dateStr, weekday, slides, imagePaths, postResult) {
  const entry = {
    date:        dateStr,
    weekday:     DAY_NAMES[weekday],
    theme:       DAY_THEMES[weekday],
    slide_count: slides.length,
    images:      imagePaths.map(p => path.basename(p)),
    post_result: postResult,
    dry_run:     DRY_RUN,
  };
  const logPath = path.join(LOGS_DIR, 'carousel_auto.jsonl');
  fs.appendFileSync(logPath, JSON.stringify(entry) + '\n', 'utf8');
  console.log(`[carousel_auto] ログ保存: ${logPath}`);
}

// ─── メイン ───────────────────────────────────────────────────────────────────

async function main() {
  const now     = new Date();
  const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
  const account = process.env.IG_ACCOUNT_NAME || '@ryo_finance_ai';

  console.log(`\n=== carousel_auto.js ===`);
  console.log(`日付: ${dateStr}  曜日: ${DAY_NAMES[WEEKDAY]}曜日`);
  console.log(`モード: ${DRY_RUN ? 'DRY RUN（投稿しない）' : '本番'}\n`);

  // Step1: スライドコンテンツ生成
  const { caption, slides } = await generateSlides(WEEKDAY);

  // Step2: テンプレートロード
  const tmpl = loadTemplate();

  // Step3: スクリーンショット
  console.log('\n--- スクリーンショット生成 ---');
  const imagePaths = await screenshotSlides(slides, tmpl, dateStr, account);

  if (DRY_RUN) {
    console.log('\n[DRY RUN] 投稿をスキップしました。');
    console.log('生成画像:');
    imagePaths.forEach(p => console.log('  ' + path.basename(p)));
    saveLog(dateStr, WEEKDAY, slides, imagePaths, { status: 'dry_run' });
    return;
  }

  // Step4: Instagram投稿
  const postResult = postToInstagram(imagePaths, caption, dateStr);
  saveLog(dateStr, WEEKDAY, slides, imagePaths, postResult);

  console.log('\n=== 完了 ===');
  console.log(`投稿ID: ${postResult.post_id || '(不明)'}`);
}

main().catch(err => {
  console.error('[carousel_auto] エラー:', err.message);
  process.exit(1);
});
