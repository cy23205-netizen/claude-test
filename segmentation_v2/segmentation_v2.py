"""撮影ユーザーセグメンテーション 改訂版（考え方2因子のみで分類 + 安定性・外部妥当性の検証）.

Step1 撮影頻度「ほとんどない」層を先に分離
Step2 考え方8項目の因子分析（最尤法・プロマックス, 2因子）→ 因子得点
Step3 F1・F2 を標準化してウォード法 → k-means で微調整（k=2〜5 を比較）
Step4 安定性: ブートストラップ（500回）でクラスターごとの Jaccard 係数
Step5 外部妥当性: 分類に使っていない変数（撮影頻度・目的・設問4の体験）で群間差を検定
Step6 属性・体験タイプとのクロス集計
検定: カテゴリー変数はフィッシャーの正確確率検定（R fisher.test）、順序・数値変数は Kruskal-Wallis 検定。
外部妥当性の検定群には Benjamini-Hochberg 法で FDR 補正をかける。

使い方: python segmentation_v2.py <回答データ.xlsx> <出力ディレクトリ>
"""
import sys, warnings, subprocess
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from factor_analyzer import FactorAnalyzer
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.stats import kruskal, chi2_contingency
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
warnings.filterwarnings('ignore')

SRC, OUT = sys.argv[1], sys.argv[2]
K, N_BOOT = 3, 500
df = pd.read_excel(SRC, '分析用')
col = lambda prefix: next(k for k in df.columns if str(k).startswith(prefix))
FREQ = col('2-1')
Q3 = [k for k in df.columns if str(k).startswith('次の項目は')]
OPTS = ['記念・思い出として残すため', 'あとで自分で見返すため', 'SNSに投稿するため', '人に見せたり送ったりするため',
        '撮ること自体が楽しいから', 'メモや情報として残すため（看板・資料など）', '一緒にいる人との会話やノリのため',
        '周りが撮っているから', 'なんとなく・癖で']
OPT_S = ['記念・思い出', '自分で見返す', 'SNS投稿', '人に見せる・送る', '撮ること自体が楽しい',
         'メモ・情報', '会話やノリ', '周りが撮っている', 'なんとなく・癖']
FREQ_LV = ['ほとんどない', '月に数回', '週1回くらい', '週に数回', 'ほぼ毎日']
short = lambda c: str(c).split('[')[-1].rstrip(']') if '[' in str(c) else str(c).split('. ', 1)[-1]

# ---------- Step1・2 ----------
rare = df[FREQ] == 'ほとんどない'
d = df[~rare].copy(); n = len(d)
fa = FactorAnalyzer(n_factors=2, rotation='promax', method='ml').fit(d[Q3])
FS = fa.transform(d[Q3])
Z = (FS - FS.mean(0)) / FS.std(0)

# ---------- Step3 ----------
def fit(Z, k):
    w = fcluster(linkage(Z, 'ward'), k, 'maxclust')
    return KMeans(k, init=np.array([Z[w == g].mean(0) for g in range(1, k + 1)]), n_init=1).fit(Z).labels_

def boot_jaccard(Z, k, B, seed=1):
    lab0 = fit(Z, k); rng = np.random.default_rng(seed); J = {g: [] for g in range(k)}
    for _ in range(B):
        idx = rng.choice(len(Z), len(Z)); u = np.unique(idx)
        lb = pd.Series(fit(Z[idx], k), index=idx).groupby(level=0).first().reindex(u).values
        for g in range(k):
            A = set(u[lab0[u] == g])
            if A: J[g].append(max(len(A & set(u[lb == h])) / len(A | set(u[lb == h])) for h in range(k)))
    return lab0, np.array([np.mean(J[g]) for g in range(k)])

comp = []
for k in range(2, 6):
    lab_k, J = boot_jaccard(Z, k, N_BOOT)
    comp.append({'k': k, 'シルエット': silhouette_score(Z, lab_k), '最小群n': np.bincount(lab_k).min(),
                 'Jaccard 平均': J.mean(), 'Jaccard 最小': J.min()})
comp = pd.DataFrame(comp).set_index('k')
lab, JAC = boot_jaccard(Z, K, N_BOOT)

# 命名: F1最小 → 体験優先型 / 残りで F2 が低い方 → 両立型（撮影と体験を両立） / もう一方 → 撮影積極型
zp = pd.DataFrame(Z, columns=['F1', 'F2']).groupby(lab).mean()
g_exp = zp['F1'].idxmin(); rest = zp.drop(g_exp)
g_nat = rest['F2'].idxmin(); g_act = rest.drop(g_nat).index[0]
NAMES = {g_act: '撮影積極型', g_nat: '両立型', g_exp: '体験優先型'}
ORDER = ['撮影積極型', '両立型', '体験優先型', 'ほとんど撮らない層']
df['セグメント'] = 'ほとんど撮らない層'
df.loc[d.index, 'セグメント'] = [NAMES[g] for g in lab]
df['セグメント'] = pd.Categorical(df['セグメント'], ORDER, ordered=True)
d['セグメント'] = df.loc[d.index, 'セグメント']
stab = pd.DataFrame({'n': [int((lab == g).sum()) for g in NAMES], 'Jaccard 平均': [JAC[g] for g in NAMES]},
                    index=[NAMES[g] for g in NAMES]).reindex(ORDER[:-1])

# プロフィール（分類に使った変数）
prof = pd.DataFrame(index=ORDER)
prof['n'] = df['セグメント'].value_counts().reindex(ORDER); prof['割合'] = prof['n'] / len(df)
prof['F1 因子得点(z)'] = pd.Series(Z[:, 0], index=d.index).groupby(d['セグメント']).mean()
prof['F2 因子得点(z)'] = pd.Series(Z[:, 1], index=d.index).groupby(d['セグメント']).mean()
item = d.groupby('セグメント')[Q3].mean(); item.columns = [short(c) for c in Q3]

# ---------- R fisher ----------
def r_fisher(tabs):
    code = ('x <- scan("stdin", quiet=TRUE); out <- c(); i <- 1\n'
            'while (i <= length(x)) { r <- x[i]; k <- x[i+1]; m <- matrix(x[(i+2):(i+1+r*k)], r, k, byrow=TRUE)\n'
            '  out <- c(out, fisher.test(m, workspace=2e8)$p.value); i <- i + 2 + r*k }\n'
            'cat(sprintf("%.10g", out), sep="\\n")')
    inp = ' '.join(' '.join(map(str, [t.shape[0], t.shape[1], *np.asarray(t).astype(int).ravel()])) for t in tabs)
    return [float(v) for v in subprocess.run(['Rscript', '-e', code], input=inp, capture_output=True, text=True, check=True).stdout.split()]

def bh(p):
    p = np.asarray(p, float); o = np.argsort(p); m = len(p); q = np.empty(m)
    q[o] = np.minimum(1, np.minimum.accumulate((p[o] * m / np.arange(1, m + 1))[::-1])[::-1]); return q

def holm(p):
    p = np.asarray(p); o = np.argsort(p); m = len(p); a = np.empty(m)
    a[o] = np.minimum(1, np.maximum.accumulate((m - np.arange(m)) * p[o])); return a

# ---------- Step5 外部妥当性（クラスター化した108人, 3群）----------
segs = ORDER[:-1]
num_vars, cat_vars = {}, {}
num_vars['撮影頻度（1=月に数回〜4=ほぼ毎日）'] = ('頻度', d[FREQ].map({v: i for i, v in enumerate(FREQ_LV)}))
for tag, c in [('日常', col('2-2')), ('非日常', col('2-3'))]:
    s = d[c].fillna('')
    for o, so in zip(OPTS, OPT_S): cat_vars[f'{tag}の目的: {so}'] = (f'設問2 {tag}の目的', s.apply(lambda v: '選択' if o in v else '非選択'))
for p in ['4-5', '4-8', '4-9', '4-23', '4-24', '4-25', '4-30', '4-33']:
    for c in [k for k in df.columns if str(k).startswith(p)]: num_vars[f'{p} {short(c)}'] = (f'設問{p}', d[c])
for p in ['4-10', '4-12', '4-14', '4-27', '4-28', '4-29', '4-31', '4-34']:
    c = col(p); cat_vars[f'{p} {short(c)}'] = (f'設問{p}', d[c])

rows, cat_tabs = [], []
for nm, (grp, x) in num_vars.items():
    ok = x.notna(); g = [x[ok & (d['セグメント'] == s)] for s in segs]
    H, p = kruskal(*g); N = sum(map(len, g))
    rows.append({'変数': nm, '区分': grp, '種類': '数値・順序', 'n': N, '検定': 'Kruskal-Wallis', '統計量': H, 'p': p,
                 '効果量': (H - len(segs) + 1) / (N - len(segs)), '効果量の種類': 'ε²',
                 **{f'{s} 平均': gg.mean() for s, gg in zip(segs, g)}})
for nm, (grp, x) in cat_vars.items():
    ok = x.notna(); t = pd.crosstab(d.loc[ok, 'セグメント'], x[ok]).reindex(segs).fillna(0)
    t = t.loc[:, t.sum() > 0]; cat_tabs.append((nm, grp, t))
pf = r_fisher([t.values for _, _, t in cat_tabs])
for (nm, grp, t), p in zip(cat_tabs, pf):
    chi = chi2_contingency(t.values, correction=False)[0]; N = t.values.sum()
    pct = (t.T / t.sum(1)).T
    key = '選択' if '選択' in t.columns else None
    rows.append({'変数': nm, '区分': grp, '種類': 'カテゴリー', 'n': N, '検定': 'Fisher 正確確率', '統計量': np.nan, 'p': p,
                 '効果量': np.sqrt(chi / (N * (min(t.shape) - 1))), '効果量の種類': "Cramér's V",
                 **({f'{s} 選択率': pct.loc[s, key] for s in segs} if key else {})})
ext = pd.DataFrame(rows)
ext['q (BH補正)'] = bh(ext['p'])
ext = ext.sort_values('p')

# ---------- Step6 属性クロス集計（116人, 4セグメント）----------
df['年齢層'] = pd.cut(df[col('1-1')], [0, 20, 21, 22, 200], labels=['20歳以下', '21歳', '22歳', '23歳以上'])
df['体験タイプ'] = df['タイプ'].replace({'不明': 'どれも行っていない'})
df['性別'] = df[col('1-2')]; df['職業'] = df[col('1-3')]
def cross(var, keep=None):
    t = pd.crosstab(df['セグメント'], df[var]); full = t.copy(); full['合計'] = full.sum(1)
    tt = t[keep] if keep else t; tt = tt.loc[tt.sum(1) > 0, tt.sum(0) > 0]; a = tt.values.astype(float); N = a.sum()
    chi, _, _, ex = chi2_contingency(a, correction=False)
    cells = [(i, j) for i in range(a.shape[0]) for j in range(a.shape[1])]
    sub = [np.array([[a[i, j], a[i].sum() - a[i, j]], [a[:, j].sum() - a[i, j], N - a[i].sum() - a[:, j].sum() + a[i, j]]]) for i, j in cells]
    ps = r_fisher([a] + sub); post = pd.DataFrame(np.nan, index=tt.index, columns=tt.columns)
    for (i, j), q in zip(cells, holm(ps[1:])): post.iat[i, j] = q
    stat = {'検定対象n': int(N), 'フィッシャー p': ps[0], "Cramér's V": np.sqrt(chi / (N * (min(a.shape) - 1))), '期待度数<5の割合': (ex < 5).mean()}
    return full, (t.T / t.sum(1)).T, post, stat
crosses = {'体験タイプ': cross('体験タイプ', ['T1', 'T2', 'T3', 'T4']), '性別': cross('性別', ['男性', '女性']),
           '職業': cross('職業'), '年齢層': cross('年齢層')}
cross_sum = pd.DataFrame({k: v[3] for k, v in crosses.items()}).T

# ---------- 出力 ----------
with pd.ExcelWriter(f'{OUT}/segmentation_v2_results.xlsx', engine='xlsxwriter') as w:
    prof.round(3).to_excel(w, sheet_name='セグメント概要')
    item.round(2).to_excel(w, sheet_name='考え方8項目 平均')
    comp.round(3).to_excel(w, sheet_name='クラスター数比較')
    stab.round(3).to_excel(w, sheet_name='安定性 Jaccard')
    ext.round(4).to_excel(w, sheet_name='外部妥当性', index=False)
    r0 = 0
    for nm, grp, t in cat_tabs:
        pd.concat({nm: t.assign(合計=t.sum(1))}, axis=1).to_excel(w, sheet_name='外部妥当性 度数表', startrow=r0); r0 += len(t) + 4
    cross_sum.round(4).to_excel(w, sheet_name='属性クロス 検定')
    for nm, (full, pct, post, stat) in crosses.items():
        sh = f'属性 {nm}'
        full.to_excel(w, sheet_name=sh, startrow=1); pct.round(3).to_excel(w, sheet_name=sh, startrow=9)
        post.round(4).to_excel(w, sheet_name=sh, startrow=17)
        ws = w.sheets[sh]
        for rr, tx in [(0, '度数'), (8, '行%'), (16, 'セルごとの2×2フィッシャー p（Holm補正）')]: ws.write(rr, 0, tx)
    pd.DataFrame({'回答No': df.index + 1, 'セグメント': df['セグメント']}).assign(
        **{'F1(z)': pd.Series(Z[:, 0], index=d.index), 'F2(z)': pd.Series(Z[:, 1], index=d.index)}).to_excel(w, sheet_name='回答者別 所属', index=False)

# ---------- 図 ----------
font = next((f for f in font_manager.findSystemFonts() if 'wqy-zenhei' in f.lower()), None)
if font:
    font_manager.fontManager.addfont(font); plt.rcParams['font.family'] = font_manager.FontProperties(fname=font).get_name()
INK, INK2, GRID, SURF = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
SER = {'撮影積極型': '#2a78d6', '両立型': '#eb6834', '体験優先型': '#1baf7a'}
MRK = {'撮影積極型': 'o', '両立型': 's', '体験優先型': '^'}
plt.rcParams.update({'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2, 'ytick.color': INK2, 'figure.facecolor': SURF,
                     'axes.facecolor': SURF, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.unicode_minus': False})

fig, ax = plt.subplots(figsize=(6.5, 5.5))
ax.axhline(0, color=GRID); ax.axvline(0, color=GRID)
for s in segs:
    mk = (d['セグメント'] == s).values
    ax.scatter(Z[mk, 0], Z[mk, 1], s=50, marker=MRK[s], color=SER[s], edgecolor=SURF, lw=1.5, label=f'{s}（n={mk.sum()}）', zorder=3)
    cx, cy = Z[mk].mean(0)
    ax.annotate(s, (cx, cy), xytext=(0, 0), textcoords='offset points', ha='center', va='center', fontsize=11, color=INK,
                bbox=dict(boxstyle='round,pad=0.3', fc=SURF, ec=SER[s], lw=1.5), zorder=4)
ax.set_xlabel('F1 撮影への肯定的価値づけ（標準化因子得点）'); ax.set_ylabel('F2 撮影による体験阻害の意識（標準化因子得点）')
ax.legend(frameon=False, loc='upper left', fontsize=9, bbox_to_anchor=(0, -0.12), ncol=3)
ax.set_title(f'考え方2因子による3タイプ（n={n}）', color=INK, loc='left')
fig.tight_layout(); fig.savefig(f'{OUT}/fig1_factor_map.png', dpi=150); plt.close(fig)

fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(comp.index, comp['シルエット'], 'o-', color='#2a78d6', lw=2, ms=8, label='平均シルエット値')
ax.plot(comp.index, comp['Jaccard 最小'], 's-', color='#eb6834', lw=2, ms=8, label='Jaccard 最小値（最も不安定な群）')
ax.axhline(.75, color=INK2, ls=':', lw=1); ax.text(5.05, .75, '安定の目安 .75', va='center', fontsize=8, color=INK2)
ax.axvline(K, color=GRID, lw=6, zorder=0); ax.set_xticks(comp.index); ax.set_ylim(0.3, 0.95)
ax.set_xlabel('クラスター数 k'); ax.grid(axis='y', color=GRID); ax.legend(frameon=False, fontsize=9)
ax.set_title('クラスター数の比較（分離度と安定性）', color=INK, loc='left')
fig.tight_layout(); fig.savefig(f'{OUT}/fig2_k_comparison.png', dpi=150); plt.close(fig)

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30); pd.set_option('display.max_colwidth', 40)
print(comp.round(3)); print(stab.round(3)); print(prof.round(2)); print(item.round(2).T)
print(ext[['変数', 'n', 'p', 'q (BH補正)', '効果量'] + [c for c in ext.columns if c.endswith(('平均', '選択率'))]].round(3).head(25).to_string())
print(cross_sum.round(3))
for nm, (full, pct, post, stat) in crosses.items(): print(nm); print(full.to_string()); print(post.round(3).to_string())
