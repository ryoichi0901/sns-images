import { Composition } from 'remotion';
import { ShortVideo } from './ShortVideo';

export const Root = () => (
  <Composition
    id="ShortVideo"
    component={ShortVideo}
    durationInFrames={1800}
    fps={30}
    width={1080}
    height={1920}
    defaultProps={{
      title: '',
      thumbnail: '',
      scenes: [],
      fps: 30,
      account: '@ryo_money_fp',
      cta_text: '続きはプロフィールから',
    }}
  />
);
