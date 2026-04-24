import { useCurrentFrame, useVideoConfig, spring } from 'remotion';

const ACCOUNT_DEFAULT = '@ryo_money_fp';
const GOLD    = '#c9a227';
const GOLD_BG = 'rgba(201,162,39,0.15)';
const GOLD_BD = 'rgba(201,162,39,0.5)';
const NUMBER_RE   = /([\d,]+[万億千兆円%年ヶ月回倍]+)/g;
const NUMBER_TEST = /^[\d,]+[万億千兆円%年ヶ月回倍]+$/;

// story シーンの narrative flow ラベル
const STORY_FLOW = { story1: 'していた', story2: '損をした', story3: 'だから話す' };

function EmphasisText({ text }) {
  const parts = text.split(NUMBER_RE);
  return (
    <>
      {parts.map((part, i) =>
        NUMBER_TEST.test(part) ? (
          <span key={i} style={{
            color: GOLD,
            fontSize: '1.3em',
            fontWeight: '900',
            textShadow: `0 0 20px rgba(201,162,39,0.8)`,
          }}>{part}</span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

export const ShortVideo = ({
  scenes   = [],
  title    = '',
  fps      = 30,
  account  = ACCOUNT_DEFAULT,
  cta_text = '続きはプロフィールから',
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const currentSec  = frame / fps;
  const activeScene = scenes.findLast(s => currentSec >= s.start) || scenes[0] || null;

  const activeIndex = scenes.reduce((acc, s, i) => (currentSec >= s.start ? i : acc), 0);
  const isHook  = activeIndex === 0;
  const isStory = activeScene?.id?.startsWith('story');
  const isCta   = activeScene?.id === 'cta';
  const flowLabel = isStory ? (STORY_FLOW[activeScene.id] || '') : '';

  const sceneStartFrame = activeScene ? activeScene.start * fps : 0;
  const frameInScene    = Math.max(0, frame - sceneStartFrame);
  const opacity = spring({ frame: frameInScene, fps, config: { damping: 14, stiffness: 80 } });
  const scale   = isHook
    ? spring({ frame, fps, config: { damping: 10, stiffness: 60 }, from: 0.75, to: 1 })
    : 1;

  const sceneDuration = activeScene ? (activeScene.end - activeScene.start) * fps : 1;
  const sceneProgress = Math.min(
    (activeIndex + frameInScene / Math.max(sceneDuration, 1)) / Math.max(scenes.length, 1),
    1
  );

  // CTA テキストを改行で分割
  const ctaLines = cta_text.split('\n');

  return (
    <div style={{
      width: '100%', height: '100%',
      background: 'linear-gradient(180deg, #0d1b3e 0%, #0b1835 40%, #060c20 100%)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      position: 'relative',
      fontFamily: '"Noto Sans JP", "Hiragino Kaku Gothic ProN", sans-serif',
      overflow: 'hidden',
    }}>

      {/* 背景グロー */}
      <div style={{
        position: 'absolute', top: '35%', left: '50%',
        transform: 'translateX(-50%)',
        width: '700px', height: '700px', borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(13,27,62,0.5) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* タイトルバー（上部） */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0,
        padding: '60px 40px 20px',
        background: 'linear-gradient(180deg, rgba(0,0,0,0.8) 0%, transparent 100%)',
        textAlign: 'center',
      }}>
        <div style={{
          fontSize: '30px', fontWeight: '700', color: GOLD,
          lineHeight: 1.3, letterSpacing: '0.02em',
        }}>{title}</div>
      </div>

      {/* ── フックシーン（index 0） ────────────────────────────────────────── */}
      {activeScene && isHook && (
        <>
          {/* 「元銀行員が言います」バッジ */}
          <div style={{
            position: 'absolute', top: '22%', left: '50%',
            transform: 'translateX(-50%)',
            backgroundColor: GOLD, color: '#060c20',
            fontSize: '28px', fontWeight: '900', letterSpacing: '0.06em',
            padding: '10px 32px', borderRadius: '100px',
            whiteSpace: 'nowrap', opacity,
          }}>
            元銀行員が言います
          </div>

          {/* 月7万 実績バッジ */}
          <div style={{
            position: 'absolute', top: '34%', left: '50%',
            transform: 'translateX(-50%)',
            backgroundColor: GOLD_BG, border: `1px solid ${GOLD_BD}`,
            color: GOLD, fontSize: '22px', fontWeight: '700',
            padding: '5px 20px', borderRadius: '6px',
            whiteSpace: 'nowrap', opacity,
          }}>
            副業解禁3ヶ月→月5万 / 6ヶ月→月7万
          </div>

          {/* メイン大テキスト（画面60%以上） */}
          <div style={{
            position: 'absolute', top: '50%',
            left: '50px', right: '50px',
            transform: 'translateY(-50%) scale(' + scale + ')',
            textAlign: 'center',
            fontSize: '88px', fontWeight: '900', color: '#ffffff',
            lineHeight: 1.2, opacity,
            textShadow: '0 0 40px rgba(201,162,39,0.5), 0 4px 20px rgba(0,0,0,0.9)',
            letterSpacing: '-0.02em',
          }}>
            <EmphasisText text={activeScene.telop || activeScene.voice} />
          </div>
        </>
      )}

      {/* ── ストーリーシーン ────────────────────────────────────────────────── */}
      {activeScene && isStory && (
        <>
          {/* narrative flow ラベル（していた / 損をした / だから話す） */}
          {flowLabel && (
            <div style={{
              position: 'absolute', bottom: '300px', left: '40px',
              backgroundColor: GOLD_BG, border: `1px solid ${GOLD_BD}`,
              color: GOLD, fontSize: '26px', fontWeight: '700',
              padding: '8px 24px', borderRadius: '6px',
              letterSpacing: '0.05em', opacity,
            }}>
              {flowLabel}
            </div>
          )}

          {/* テロップ（画面60%以上の大きさ） */}
          <div style={{
            position: 'absolute', bottom: '200px',
            left: '36px', right: '36px',
            textAlign: 'center',
            fontSize: '64px', fontWeight: '900', color: '#ffffff',
            lineHeight: 1.35, opacity,
            textShadow: '0 4px 16px rgba(0,0,0,0.9)',
            backgroundColor: 'rgba(10,22,40,0.85)',
            borderRadius: '20px', padding: '28px 28px',
            borderLeft: '8px solid ' + GOLD,
          }}>
            <EmphasisText text={activeScene.telop || activeScene.voice} />
          </div>
        </>
      )}

      {/* ── CTA シーン（テーマ別テキスト差し替え） ─────────────────────────── */}
      {activeScene && isCta && (
        <div style={{
          position: 'absolute', bottom: '200px',
          left: '36px', right: '36px',
          textAlign: 'center',
          fontSize: '56px', fontWeight: '900', color: '#ffffff',
          lineHeight: 1.5, opacity,
          textShadow: '0 4px 16px rgba(0,0,0,0.9)',
          backgroundColor: 'rgba(10,22,40,0.85)',
          borderRadius: '20px', padding: '32px 28px',
          borderLeft: '8px solid ' + GOLD,
        }}>
          {ctaLines.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </div>
      )}

      {/* ── その他シーン（problem / proof 等） ──────────────────────────────── */}
      {activeScene && !isHook && !isStory && !isCta && (
        <div style={{
          position: 'absolute', bottom: '200px',
          left: '36px', right: '36px',
          textAlign: 'center',
          fontSize: '64px', fontWeight: '900', color: '#ffffff',
          lineHeight: 1.35, opacity,
          textShadow: '0 4px 16px rgba(0,0,0,0.9)',
          backgroundColor: 'rgba(10,22,40,0.85)',
          borderRadius: '20px', padding: '28px 28px',
          borderLeft: '8px solid ' + GOLD,
        }}>
          <EmphasisText text={activeScene.telop || activeScene.voice} />
        </div>
      )}

      {/* シーンドット */}
      <div style={{
        position: 'absolute', bottom: '148px', left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex', gap: '12px', alignItems: 'center',
      }}>
        {scenes.map((s, i) => (
          <div key={s.id} style={{
            width: i === activeIndex ? '28px' : '10px',
            height: '10px', borderRadius: '5px',
            backgroundColor: i === activeIndex ? GOLD : 'rgba(255,255,255,0.3)',
          }} />
        ))}
      </div>

      {/* プログレスバー */}
      <div style={{
        position: 'absolute', bottom: '108px',
        left: '40px', right: '40px',
        height: '8px', backgroundColor: 'rgba(255,255,255,0.15)',
        borderRadius: '4px', overflow: 'hidden',
      }}>
        <div style={{
          width: (sceneProgress * 100) + '%', height: '100%',
          background: `linear-gradient(90deg, ${GOLD}, #e8b830)`,
          borderRadius: '4px',
          boxShadow: '0 0 10px rgba(201,162,39,0.7)',
        }} />
      </div>

      {/* アカウント名 */}
      <div style={{
        position: 'absolute', bottom: '52px',
        left: 0, right: 0, textAlign: 'center',
        fontSize: '28px', fontWeight: '700',
        color: 'rgba(255,255,255,0.8)', letterSpacing: '0.08em',
      }}>{account}</div>

    </div>
  );
};
