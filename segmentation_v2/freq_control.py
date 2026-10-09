"""撮影頻度を統制してもセグメントと撮影目的の関連が残るかの検討.

- 目的の選択（2-2 日常, 2-3 非日常; 選択/非選択）: ロジスティック回帰
    目的 ~ セグメント + 撮影頻度  と  目的 ~ 撮影頻度  の尤度比検定でセグメントの効果を評価
- 評定項目（4-5, 4-23; −3〜+3）: 線形回帰（共分散分析）, 同様に F 検定（Type II）
- 撮影頻度は 1=月に数回〜4=ほぼ毎日 の数値（線形）で投入。感度分析としてカテゴリー投入も実施。
- 補正なしモデル（セグメントのみ）の p と並べて比較する。p は Benjamini-Hochberg で FDR 補正。

使い方: python freq_control.py <回答データ.xlsx> <segmentation_v2_results.xlsx> <出力ディレクトリ>
"""
import sys, warnings
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm
from scipy.stats import chi2
warnings.filterwarnings('ignore')

SRC, SEG, OUT = sys.argv[1:4]
df = pd.read_excel(SRC, '分析用')
seg = pd.read_excel(SEG, '回答者別 所属')
df['seg'] = seg['セグメント'].values
d = df[df['seg'] != 'ほとんど撮らない層'].copy()
col = lambda p: next(k for k in df.columns if str(k).startswith(p))
FMAP = {'月に数回': 1, '週1回くらい': 2, '週に数回': 3, 'ほぼ毎日': 4}
d['freq'] = d[col('2-1')].map(FMAP); d['freq_c'] = d['freq'].astype(str)
d['seg'] = pd.Categorical(d['seg'], ['撮影積極型', '両立型', '体験優先型'])
OPTS = ['記念・思い出として残すため', 'あとで自分で見返すため', 'SNSに投稿するため', '人に見せたり送ったりするため',
        '撮ること自体が楽しいから', 'メモや情報として残すため（看板・資料など）', '一緒にいる人との会話やノリのため',
        '周りが撮っているから', 'なんとなく・癖で']
OPT_S = ['記念・思い出', '自分で見返す', 'SNS投稿', '人に見せる・送る', '撮ること自体が楽しい',
         'メモ・情報', '会話やノリ', '周りが撮っている', 'なんとなく・癖']
short = lambda c: str(c).split('[')[-1].rstrip(']')

def bh(p):
    p = np.asarray(p, float); o = np.argsort(p); m = len(p); q = np.empty(m)
    q[o] = np.minimum(1, np.minimum.accumulate((p[o] * m / np.arange(1, m + 1))[::-1])[::-1]); return q

def lr_logit(y, data, cov):
    """セグメント効果の尤度比検定 p。分離などで推定できない場合は NaN."""
    try:
        full = smf.logit(f'y ~ C(seg) + {cov}' if cov else 'y ~ C(seg)', data.assign(y=y)).fit(disp=0, maxiter=200)
        red = smf.logit(f'y ~ {cov}' if cov else 'y ~ 1', data.assign(y=y)).fit(disp=0, maxiter=200)
        if not (full.mle_retvals['converged'] and red.mle_retvals['converged']) or np.any(np.abs(full.params) > 15):
            return np.nan, np.nan
        return chi2.sf(2 * (full.llf - red.llf), 2), full
    except Exception:
        return np.nan, np.nan

rows = []
for tag, c in [('日常', col('2-2')), ('非日常', col('2-3'))]:
    s = d[c].fillna('')
    for o, so in zip(OPTS, OPT_S):
        y = s.apply(lambda v: int(o in v))
        p0, _ = lr_logit(y, d, None); p1, m1 = lr_logit(y, d, 'freq'); p2, _ = lr_logit(y, d, 'C(freq_c)')
        fr = m1.pvalues.get('freq', np.nan) if m1 is not np.nan else np.nan
        orr = np.exp(m1.params) if m1 is not np.nan else None
        rows.append({'変数': f'{tag}の目的: {so}', '分析': 'ロジスティック', 'n': len(y), '該当数': int(y.sum()),
                     **{f'{g} 選択率': y[d['seg'] == g].mean() for g in d['seg'].cat.categories},
                     'セグメント p（統制なし）': p0, 'セグメント p（頻度を統制）': p1, 'セグメント p（頻度カテゴリー統制）': p2,
                     '撮影頻度の効果 p': fr,
                     'OR 両立型/積極型（統制後）': orr['C(seg)[T.両立型]'] if orr is not None else np.nan,
                     'OR 体験優先型/積極型（統制後）': orr['C(seg)[T.体験優先型]'] if orr is not None else np.nan,
                     'OR 頻度1段階あたり': orr['freq'] if orr is not None else np.nan})

num_cols = [col('4-5')] + [k for k in df.columns if str(k).startswith('4-23')]
for c in num_cols:
    x = d[[c, 'seg', 'freq', 'freq_c']].dropna().rename(columns={c: 'y'})
    p0 = anova_lm(smf.ols('y ~ C(seg)', x).fit(), typ=2).loc['C(seg)', 'PR(>F)']
    m1 = smf.ols('y ~ C(seg) + freq', x).fit(); a1 = anova_lm(m1, typ=2)
    p2 = anova_lm(smf.ols('y ~ C(seg) + C(freq_c)', x).fit(), typ=2).loc['C(seg)', 'PR(>F)']
    ss = a1['sum_sq']; eta = ss['C(seg)'] / (ss['C(seg)'] + ss['Residual'])
    adj = {g: m1.predict(pd.DataFrame({'seg': [g], 'freq': [x['freq'].mean()]}))[0] for g in d['seg'].cat.categories}
    rows.append({'変数': f'{str(c)[:4]} {short(c)}', '分析': '線形（共分散分析）', 'n': len(x),
                 **{f'{g} 平均': x.loc[x['seg'] == g, 'y'].mean() for g in d['seg'].cat.categories},
                 **{f'{g} 調整平均': v for g, v in adj.items()},
                 'セグメント p（統制なし）': p0, 'セグメント p（頻度を統制）': a1.loc['C(seg)', 'PR(>F)'],
                 'セグメント p（頻度カテゴリー統制）': p2, '撮影頻度の効果 p': a1.loc['freq', 'PR(>F)'], '偏η²（セグメント）': eta})

res = pd.DataFrame(rows)
ok = res['セグメント p（頻度を統制）'].notna()
res.loc[ok, 'q（統制後, BH補正）'] = bh(res.loc[ok, 'セグメント p（頻度を統制）'])
res.to_excel(f'{OUT}/freq_control_results.xlsx', index=False)

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
print(pd.crosstab(d['seg'], d['freq'], margins=True))
show = ['変数', 'n', 'セグメント p（統制なし）', 'セグメント p（頻度を統制）', 'セグメント p（頻度カテゴリー統制）', '撮影頻度の効果 p', 'q（統制後, BH補正）']
print(res[show].round(3).to_string())
print(res[['変数', 'OR 両立型/積極型（統制後）', 'OR 体験優先型/積極型（統制後）', 'OR 頻度1段階あたり']].dropna().round(2).to_string())
print(res[['変数'] + [c for c in res.columns if '平均' in c]].dropna().round(2).to_string())
