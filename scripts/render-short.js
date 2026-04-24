#!/usr/bin/env node
/**
 * Remotionを使って短台本JSONからMP4（縦型1080x1920）を生成する。
 * 台本JSONはshort-video-scripterが出力したファイルを想定。
 *
 * Usage:
 *   node scripts/render-short.js --script logs/script_YYYYMMDD.json [--out output/short_YYYYMMDD.mp4]
 *
 * 台本JSON形式（short-video-scripterの出力）:
 * {
 *   "title": "タイトル案",
 *   "thumbnail": "サムネイル文字案",
 *   "scenes": [
 *     { "id": "hook",   "start": 0,  "end": 3,  "voice": "...", "telop": "..." },
 *     { "id": "issue",  "start": 3,  "end": 10, "voice": "...", "telop": "..." },
 *     ...
 *     { "id": "cta",    "start": 50, "end": 60, "voice": "...", "telop": "..." }
 *   ],
 *   "hashtags": { "youtube": [...], "tiktok": [...], "reels": [...] }
 * }
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// ─── CLI 引数パース ────────────────────────────────────────────────────────────

const args = process.argv.slice(2);

function getArg(flag) {
  const idx = args.indexOf(flag);
  return idx !== -1 ? args[idx + 1] : null;
}

const scriptPath = getArg('--script');
const dryRun = args.includes('--dry-run');

if (!scriptPath) {
  console.error('Error: --script <path> が必要です');
  console.error('例: node scripts/render-short.js --script logs/script_20260422.json');
  process.exit(1);
}

if (!fs.existsSync(scriptPath)) {
  console.error(`Error: 台本ファイルが見つかりません: ${scriptPath}`);
  process.exit(1);
}

// ─── 台本読み込み ─────────────────────────────────────────────────────────────

const script = JSON.parse(fs.readFileSync(scriptPath, 'utf8'));
const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
const defaultOut = path.join('output', `short_${dateStr}.mp4`);
const outPath = getArg('--out') || defaultOut;

// ─── 出力ディレクトリを確保 ───────────────────────────────────────────────────

const outDir = path.dirname(outPath);
if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

// ─── Remotion コンポジション設定を生成 ───────────────────────────────────────

const FPS = 30;
const WIDTH = 1080;
const HEIGHT = 1920;

// シーン総尺（秒）は最後のシーンの end を使用
const totalSeconds = script.scenes
  ? Math.max(...script.scenes.map(s => s.end))
  : 60;
const totalFrames = totalSeconds * FPS;

// Remotion がレンダリングに使う入力プロップをJSONで書き出す
const propsPath = path.join('output', `props_${dateStr}.json`);
const props = {
  title:    script.title    || '',
  thumbnail:script.thumbnail|| '',
  hook_sub: script.hook_sub || '',
  scenes:   script.scenes   || [],
  fps:      FPS,
  account:  script.account  || '@ryo_money_fp',
  cta_text: script.cta_text || '続きはプロフィールから',
};
fs.writeFileSync(propsPath, JSON.stringify(props, null, 2));

// ─── ローカルコンポジションファイルを生成（Remotion Lambda不使用のローカルレンダー）──

const compositionDir = path.join('remotion');
if (!fs.existsSync(compositionDir)) {
  fs.mkdirSync(compositionDir, { recursive: true });
}

// index.jsx: Remotionエントリポイント
const indexPath = path.join(compositionDir, 'index.jsx');
if (!fs.existsSync(indexPath)) {
  fs.writeFileSync(indexPath, generateRemotionIndex());
}

// Root.jsx: コンポジション定義
const rootPath = path.join(compositionDir, 'Root.jsx');
fs.writeFileSync(rootPath, generateRoot(totalFrames, FPS, WIDTH, HEIGHT));

// ShortVideo.jsx: 縦型動画コンポーネント
const componentPath = path.join(compositionDir, 'ShortVideo.jsx');
if (!fs.existsSync(componentPath)) {
  fs.writeFileSync(componentPath, generateShortVideoComponent());
}

// ─── ドライランモード ─────────────────────────────────────────────────────────

if (dryRun) {
  console.log('[DRY RUN] render-short.js');
  console.log('  台本:', scriptPath);
  console.log('  出力先:', outPath);
  console.log('  総尺:', totalSeconds, '秒 /', totalFrames, 'フレーム');
  console.log('  解像度:', `${WIDTH}x${HEIGHT} @${FPS}fps`);
  console.log('  シーン数:', props.scenes.length);
  console.log('  プロップスJSON:', propsPath);
  console.log('  Remotion構成ファイル:');
  console.log('    -', indexPath);
  console.log('    -', rootPath);
  console.log('    -', componentPath);
  console.log('[DRY RUN] 実際のレンダリングはスキップされました');
  process.exit(0);
}

// ─── Remotion でレンダリング ─────────────────────────────────────────────────

console.log(`[render-short] 台本: ${scriptPath}`);
console.log(`[render-short] 出力: ${outPath}`);
console.log(`[render-short] 尺: ${totalSeconds}秒 (${totalFrames}フレーム)`);

const npxBin = process.env.NPM_EXECPATH
  ? `node "${process.env.NPM_EXECPATH}" exec remotion`
  : 'npx remotion';

const renderCmd = [
  npxBin,
  'render',
  'remotion/index.jsx',        // エントリポイント
  'ShortVideo',                // コンポジションID
  outPath,
  `--props="${propsPath}"`,
  `--width=${WIDTH}`,
  `--height=${HEIGHT}`,
  `--fps=${FPS}`,
  '--codec=h264',
  '--log=verbose',
].join(' ');

console.log(`[render-short] 実行: ${renderCmd}`);

try {
  execSync(renderCmd, { stdio: 'inherit' });
  console.log(`[render-short] 完了: ${outPath}`);

  // 台本JSONにレンダー結果のパスを記録
  const result = { ...script, renderedAt: new Date().toISOString(), outputPath: outPath };
  fs.writeFileSync(scriptPath, JSON.stringify(result, null, 2));
} catch (err) {
  console.error('[render-short] レンダリング失敗:', err.message);
  process.exit(1);
}

// ─── Remotion ファイル生成ヘルパー ────────────────────────────────────────────

function generateRemotionIndex() {
  return `import { registerRoot } from 'remotion';
import { Root } from './Root';
registerRoot(Root);
`;
}

function generateRoot(durationFrames, fps, width, height) {
  return `import { Composition } from 'remotion';
import { ShortVideo } from './ShortVideo';

export const Root = () => (
  <Composition
    id="ShortVideo"
    component={ShortVideo}
    durationInFrames={${durationFrames}}
    fps={${fps}}
    width={${width}}
    height={${height}}
    defaultProps={{
      title: '',
      thumbnail: '',
      hook_sub: '',
      scenes: [],
      fps: ${fps},
      account: '@ryo_money_fp',
      cta_text: '続きはプロフィールから',
    }}
  />
);
`;
}

function generateShortVideoComponent() {
  return `import { useCurrentFrame, useVideoConfig, spring } from 'remotion';

const ACCOUNT_DEFAULT = '@ryo_money_fp';
const GOLD    = '#c9a227';
const GOLD_BG = 'rgba(201,162,39,0.15)';
const GOLD_BD = 'rgba(201,162,39,0.5)';
const NUMBER_RE   = /([\d,]+[万億千兆円%年ヶ月回倍]+)/g;
const NUMBER_TEST = /^[\d,]+[万億千兆円%年ヶ月回倍]+$/;
const STORY_FLOW = { story1: 'していた', story2: '損をした', story3: 'だから話す' };

// 数字を金色・大きく・強いグローで強調
function EmphasisText({ text }) {
  const parts = text.split(NUMBER_RE);
  return (
    <>
      {parts.map((part, i) =>
        NUMBER_TEST.test(part) ? (
          <span key={i} style={{
            color: GOLD,
            fontSize: '1.8em',
            fontWeight: '900',
            display: 'inline-block',
            textShadow: '0 0 30px rgba(201,162,39,1), 0 0 60px rgba(201,162,39,0.6), 0 4px 12px rgba(0,0,0,0.9)',
            letterSpacing: '-0.01em',
          }}>{part}</span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

export const ShortVideo = ({ scenes = [], title = '', hook_sub = '', fps = 30, account = ACCOUNT_DEFAULT, cta_text = '続きはプロフィールから' }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const currentSec  = frame / fps;
  const activeScene = scenes.findLast(s => currentSec >= s.start) || scenes[0] || null;
  const activeIndex = scenes.reduce((acc, s, i) => (currentSec >= s.start ? i : acc), 0);
  const isHook  = activeIndex === 0;
  const isStory = activeScene && activeScene.id && activeScene.id.startsWith('story');
  const isCta   = activeScene && activeScene.id === 'cta';
  const flowLabel = isStory ? (STORY_FLOW[activeScene.id] || '') : '';

  const sceneStartFrame = activeScene ? activeScene.start * fps : 0;
  const frameInScene    = Math.max(0, frame - sceneStartFrame);
  const opacity = spring({ frame: frameInScene, fps, config: { damping: 14, stiffness: 80 } });

  // 冒頭3秒のフックアニメーション: 0.3倍から等倍へ劇的ズームイン
  const hookScale = isHook
    ? spring({ frame, fps, config: { damping: 12, stiffness: 40 }, from: 0.3, to: 1 })
    : 1;
  // Y軸: 60px下から滑り上がる
  const hookY = isHook
    ? spring({ frame, fps, config: { damping: 14, stiffness: 45 }, from: 60, to: 0 })
    : 0;

  const sceneDuration = activeScene ? (activeScene.end - activeScene.start) * fps : 1;
  const sceneProgress = Math.min(
    (activeIndex + frameInScene / Math.max(sceneDuration, 1)) / Math.max(scenes.length, 1), 1
  );
  const ctaLines = cta_text.split('\\n');

  return (
    <div style={{
      width: '100%', height: '100%',
      background: 'linear-gradient(180deg, #0d1b3e 0%, #0b1835 40%, #060c20 100%)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      position: 'relative',
      fontFamily: '"Noto Sans JP", "Hiragino Kaku Gothic ProN", sans-serif',
      overflow: 'hidden',
    }}>
      {/* 背景装飾 */}
      <div style={{ position: 'absolute', top: '35%', left: '50%', transform: 'translateX(-50%)', width: '700px', height: '700px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(13,27,62,0.5) 0%, transparent 70%)', pointerEvents: 'none' }} />
      {/* タイトル */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, padding: '60px 40px 20px', background: 'linear-gradient(180deg, rgba(0,0,0,0.8) 0%, transparent 100%)', textAlign: 'center' }}>
        <div style={{ fontSize: '30px', fontWeight: '700', color: GOLD, lineHeight: 1.3, letterSpacing: '0.02em' }}>{title}</div>
      </div>
      {/* フックシーン */}
      {activeScene && isHook && (
        <>
          {/* フックテキスト背景グロー（楕円形オーラ） */}
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: '960px', height: '640px', borderRadius: '50%', background: \`radial-gradient(ellipse, rgba(201,162,39,\${0.13 * opacity}) 0%, transparent 68%)\`, pointerEvents: 'none' }} />
          {/* バッジ */}
          <div style={{ position: 'absolute', top: '22%', left: '50%', transform: 'translateX(-50%)', backgroundColor: GOLD, color: '#060c20', fontSize: '28px', fontWeight: '900', letterSpacing: '0.06em', padding: '10px 32px', borderRadius: '100px', whiteSpace: 'nowrap', opacity }}>元銀行員が言います</div>
          {/* hook_sub */}
          {hook_sub ? <div style={{ position: 'absolute', top: '34%', left: '50%', transform: 'translateX(-50%)', backgroundColor: GOLD_BG, border: \`1px solid \${GOLD_BD}\`, color: GOLD, fontSize: '22px', fontWeight: '700', padding: '5px 20px', borderRadius: '6px', whiteSpace: 'nowrap', opacity }}>{hook_sub}</div> : null}
          {/* メインフックテキスト: 冒頭3秒のズームイン＋スライドアップ */}
          <div style={{ position: 'absolute', top: '50%', left: '50px', right: '50px', transform: \`translateY(calc(-50% + \${hookY}px)) scale(\${hookScale})\`, textAlign: 'center', fontSize: '96px', fontWeight: '900', color: '#ffffff', lineHeight: 1.2, opacity, textShadow: '0 0 60px rgba(201,162,39,0.7), 0 0 120px rgba(201,162,39,0.3), 0 4px 20px rgba(0,0,0,0.9)', letterSpacing: '-0.02em' }}>
            <EmphasisText text={activeScene.telop || activeScene.voice} />
          </div>
        </>
      )}
      {/* ストーリーシーン */}
      {activeScene && isStory && (
        <>
          {flowLabel ? <div style={{ position: 'absolute', bottom: '300px', left: '40px', backgroundColor: GOLD_BG, border: \`1px solid \${GOLD_BD}\`, color: GOLD, fontSize: '26px', fontWeight: '700', padding: '8px 24px', borderRadius: '6px', letterSpacing: '0.05em', opacity }}>{flowLabel}</div> : null}
          <div style={{ position: 'absolute', bottom: '200px', left: '36px', right: '36px', textAlign: 'center', fontSize: '64px', fontWeight: '900', color: '#ffffff', lineHeight: 1.35, opacity, textShadow: '0 4px 16px rgba(0,0,0,0.9)', backgroundColor: 'rgba(10,22,40,0.85)', borderRadius: '20px', padding: '28px 28px', borderLeft: '8px solid ' + GOLD }}>
            <EmphasisText text={activeScene.telop || activeScene.voice} />
          </div>
        </>
      )}
      {/* CTAシーン */}
      {activeScene && isCta && (
        <div style={{ position: 'absolute', bottom: '200px', left: '36px', right: '36px', textAlign: 'center', fontSize: '56px', fontWeight: '900', color: '#ffffff', lineHeight: 1.5, opacity, textShadow: '0 4px 16px rgba(0,0,0,0.9)', backgroundColor: 'rgba(10,22,40,0.85)', borderRadius: '20px', padding: '32px 28px', borderLeft: '8px solid ' + GOLD }}>
          {ctaLines.map((line, i) => <div key={i}>{line}</div>)}
        </div>
      )}
      {/* その他シーン */}
      {activeScene && !isHook && !isStory && !isCta && (
        <div style={{ position: 'absolute', bottom: '200px', left: '36px', right: '36px', textAlign: 'center', fontSize: '64px', fontWeight: '900', color: '#ffffff', lineHeight: 1.35, opacity, textShadow: '0 4px 16px rgba(0,0,0,0.9)', backgroundColor: 'rgba(10,22,40,0.85)', borderRadius: '20px', padding: '28px 28px', borderLeft: '8px solid ' + GOLD }}>
          <EmphasisText text={activeScene.telop || activeScene.voice} />
        </div>
      )}
      {/* シーンインジケーター */}
      <div style={{ position: 'absolute', bottom: '148px', left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: '12px', alignItems: 'center' }}>
        {scenes.map((s, i) => <div key={s.id} style={{ width: i === activeIndex ? '28px' : '10px', height: '10px', borderRadius: '5px', backgroundColor: i === activeIndex ? GOLD : 'rgba(255,255,255,0.3)' }} />)}
      </div>
      {/* プログレスバー */}
      <div style={{ position: 'absolute', bottom: '108px', left: '40px', right: '40px', height: '8px', backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: '4px', overflow: 'hidden' }}>
        <div style={{ width: (sceneProgress * 100) + '%', height: '100%', background: 'linear-gradient(90deg, ' + GOLD + ', #e8b830)', borderRadius: '4px', boxShadow: '0 0 10px rgba(201,162,39,0.7)' }} />
      </div>
      {/* アカウント名 */}
      <div style={{ position: 'absolute', bottom: '52px', left: 0, right: 0, textAlign: 'center', fontSize: '28px', fontWeight: '700', color: 'rgba(255,255,255,0.8)', letterSpacing: '0.08em' }}>{account}</div>
    </div>
  );
};
`;
}
