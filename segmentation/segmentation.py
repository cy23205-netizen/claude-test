"""設問1〜3による撮影ユーザーセグメンテーション.

Step1 撮影頻度「ほとんどない」層を先に分離
Step2 考え方8項目の因子分析（最尤法・プロマックス）→ 因子得点
Step3 非日常の撮影目的（9選択肢）の数量化III類 → サンプルスコア
Step4 標準化した変数でウォード法 → シルエット値でクラスター数決定 → k-meansで微調整
Step5 セグメント × 体験タイプ・性別・職業・年齢層のクロス集計（フィッシャーの正確確率検定, R が必要）

使い方: python segmentation.py <回答データ.xlsx> <出力ディレクトリ>
"""
import sys, warnings, subprocess
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap
from factor_analyzer import FactorAnalyzer
from factor_analyzer.factor_analyzer import calculate_kmo, calculate_bartlett_sphericity
from scipy.cluster.hierarchy import linkage, fcluster, dendrogram, set_link_color_palette
from scipy.stats import chi2_contingency
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, silhouette_samples
warnings.filterwarnings('ignore')

SRC, OUT = sys.argv[1], sys.argv[2]
N_AXES, K = 2, 5          # 採用した目的軸数・クラスター数（silhouette表参照）
RNG = np.random.default_rng(0)

df = pd.read_excel(SRC, '分析用')
col = lambda prefix: next(k for k in df.columns if str(k).startswith(prefix))
FREQ, PURP = col('2-1'), col('2-3')
Q3 = [k for k in df.columns if str(k).startswith('次の項目は')]
Q3_LAB = [k.split('[')[-1].rstrip(']') for k in Q3]
OPTS = ['記念・思い出として残すため', 'あとで自分で見返すため', 'SNSに投稿するため', '人に見せたり送ったりするため',
        '撮ること自体が楽しいから', 'メモや情報として残すため（看板・資料など）', '一緒にいる人との会話やノリのため',
        '周りが撮っているから', 'なんとなく・癖で']
OPT_S = ['記念・思い出', '自分で見返す', 'SNS投稿', '人に見せる・送る', '撮ること自体が楽しい',
         'メモ・情報', '会話やノリ', '周りが撮っている', 'なんとなく・癖']
FMAP = {'月に数回': 1, '週1回くらい': 2, '週に数回': 3, 'ほぼ毎日': 4}

# ---------- Step1 ----------
rare = df[FREQ] == 'ほとんどない'
d = df[~rare].copy()
assert d[Q3].notna().all().all()
n = len(d)

# ---------- Step2 因子分析 ----------
X = d[Q3]
bart = calculate_bartlett_sphericity(X); kmo_i, kmo_t = calculate_kmo(X)
ev = np.linalg.eigvalsh(X.corr().values)[::-1]
pa = np.percentile([np.linalg.eigvalsh(np.corrcoef(RNG.standard_normal((n, 8)), rowvar=False))[::-1]
                    for _ in range(2000)], 95, axis=0)
fa = FactorAnalyzer(n_factors=2, rotation='promax', method='ml').fit(X)
FNAME = ['F1 撮影への肯定的価値づけ', 'F2 撮影による体験阻害の意識']
load = pd.DataFrame(fa.loadings_, index=Q3_LAB, columns=FNAME); load['共通性'] = fa.get_communalities()
FS = fa.transform(X)
def alpha(Z):
    Z = np.asarray(Z, float); k = Z.shape[1]
    return k / (k - 1) * (1 - Z.var(0, ddof=1).sum() / Z.sum(1).var(ddof=1))
F1_IT, F2_IT = [0, 2, 3, 4, 5, 7], [1, 6]
fa_tab = pd.DataFrame({
    '値': [n, kmo_t, bart[0], bart[1], *ev[:3], *pa[:3], alpha(X.iloc[:, F1_IT]), alpha(X.iloc[:, F2_IT]), fa.phi_[0, 1]]},
    index=['n', 'KMO', 'Bartlett χ²', 'Bartlett p', '固有値1', '固有値2', '固有値3',
           '平行分析95% 1', '平行分析95% 2', '平行分析95% 3', 'α F1(6項目)', 'α F2(2項目)', '因子間相関'])

# ---------- Step3 数量化III類 ----------
def purpose_matrix(frame):
    s = frame[PURP].fillna('')
    return np.array([[int(o in v) for o in OPTS] for v in s])
Bm = purpose_matrix(d)
P = Bm / Bm.sum(); r = P.sum(1); c = P.sum(0)
U, sv, Vt = np.linalg.svd((P - np.outer(r, c)) / np.sqrt(np.outer(r, c)), full_matrices=False)
sv, U, Vt = sv[:-1], U[:, :-1], Vt[:-1]             # 最後の自明解(固有値0)を除く
ROW = U / np.sqrt(r)[:, None]                        # サンプルスコア（重み付き分散1）
COL = Vt.T / np.sqrt(c)[:, None]                     # カテゴリースコア
q3_eig = pd.DataFrame({'相関係数': sv, '固有値': sv ** 2, '寄与率': sv ** 2 / (sv ** 2).sum(),
                       '累積寄与率': np.cumsum(sv ** 2) / (sv ** 2).sum()}, index=[f'軸{i+1}' for i in range(len(sv))])
q3_cat = pd.DataFrame(COL[:, :3], index=OPT_S, columns=['軸1', '軸2', '軸3']); q3_cat.insert(0, '選択数', Bm.sum(0))
AXNAME = ['目的軸1 なんとなく(−)⇔意図的(+)', '目的軸2 自分の記録(−)⇔その場・共有の楽しみ(+)']

# ---------- Step4 クラスター分析 ----------
V = np.column_stack([FS, ROW[:, :N_AXES], d[FREQ].map(FMAP).values])
VNAME = ['F1 肯定的価値づけ', 'F2 体験阻害の意識', '目的軸1 意図的', '目的軸2 共有・楽しみ', '撮影頻度']
Z = (V - V.mean(0)) / V.std(0)
L = linkage(Z, 'ward')
sil_rows = []
for k in range(2, 9):
    w = fcluster(L, k, 'maxclust')
    km = KMeans(k, init=np.array([Z[w == g].mean(0) for g in range(1, k + 1)]), n_init=1).fit(Z).labels_
    sil_rows.append({'k': k, 'ウォード法 シルエット': silhouette_score(Z, w), 'ウォード法 最小群n': np.bincount(w)[1:].min(),
                     'k-means後 シルエット': silhouette_score(Z, km), 'k-means後 最小群n': np.bincount(km).min()})
sil = pd.DataFrame(sil_rows).set_index('k')
ward = fcluster(L, K, 'maxclust')
lab = KMeans(K, init=np.array([Z[ward == g].mean(0) for g in range(1, K + 1)]), n_init=1).fit(Z).labels_
agree = pd.crosstab(pd.Series(ward, name='ウォード法'), pd.Series(lab, name='k-means'))

# 命名（クラスターの平均プロフィールから規則で割り当て）
zprof = pd.DataFrame(Z, columns=VNAME).groupby(lab).mean()
nanto = pd.DataFrame(Bm, columns=OPT_S).groupby(lab).mean()['なんとなく・癖']
names = {}
names[nanto.idxmax()] = 'なんとなく撮影型'
rest = [g for g in zprof.index if g not in names]
for key, nm, f in [('F2 体験阻害の意識', '体験優先型', 'max'), ('目的軸2 共有・楽しみ', '共有・楽しみ志向型', 'max'),
                   ('撮影頻度', '記録重視型', 'min')]:
    g = getattr(zprof.loc[rest, key], 'idx' + f)(); names[g] = nm; rest.remove(g)
names[rest[0]] = '低関与型'
ORDER = ['記録重視型', '共有・楽しみ志向型', '体験優先型', '低関与型', 'なんとなく撮影型', 'ほとんど撮らない層']

seg = pd.Series('ほとんど撮らない層', index=df.index)
seg[d.index] = [names[g] for g in lab]
seg = pd.Categorical(seg, ORDER, ordered=True)
df['セグメント'] = seg

# プロフィール（元の尺度）
d['セグメント'] = df.loc[d.index, 'セグメント']
prof = pd.DataFrame(index=ORDER)
prof['n'] = df['セグメント'].value_counts().reindex(ORDER)
prof['割合'] = prof['n'] / len(df)
prof['F1 尺度得点(−3〜3)'] = d.groupby('セグメント')[[Q3[i] for i in F1_IT]].mean().mean(1)
prof['F2 尺度得点(−3〜3)'] = d.groupby('セグメント')[[Q3[i] for i in F2_IT]].mean().mean(1)
for nm, z in zip(VNAME, Z.T):
    prof[f'{nm} (z)'] = pd.Series(z, index=d.index).groupby(d['セグメント']).mean()
freq_tab = pd.crosstab(df['セグメント'], df[FREQ], normalize='index')[['ほとんどない', '月に数回', '週1回くらい', '週に数回', 'ほぼ毎日']]
purp_all = pd.DataFrame(purpose_matrix(df), columns=OPT_S, index=df.index).groupby(df['セグメント']).mean()
item_tab = d.groupby('セグメント')[Q3].mean(); item_tab.columns = Q3_LAB

# ---------- Step5 クロス集計 ----------
age = df[col('1-1')]
df['年齢層'] = pd.cut(age, [0, 20, 21, 22, 200], labels=['20歳以下', '21歳', '22歳', '23歳以上'])
df['体験タイプ'] = df['タイプ'].replace({'不明': 'どれも行っていない'})
df['性別'] = df[col('1-2')]; df['職業'] = df[col('1-3')]
df['撮影頻度'] = pd.Categorical(df[FREQ], ['ほとんどない', '月に数回', '週1回くらい', '週に数回', 'ほぼ毎日'], ordered=True)

def r_fisher(tabs):
    """R の fisher.test（ネットワークアルゴリズムによる正確検定, Freeman-Halton 拡張）で p 値を返す."""
    code = 'x <- scan("stdin", quiet=TRUE); out <- c(); i <- 1\n' \
           'while (i <= length(x)) { r <- x[i]; k <- x[i+1]; m <- matrix(x[(i+2):(i+1+r*k)], r, k, byrow=TRUE)\n' \
           '  out <- c(out, fisher.test(m, workspace=2e8)$p.value); i <- i + 2 + r*k }\n' \
           'cat(sprintf("%.10g", out), sep="\\n")'
    inp = ' '.join(' '.join(map(str, [t.shape[0], t.shape[1], *t.astype(int).ravel()])) for t in tabs)
    res = subprocess.run(['Rscript', '-e', code], input=inp, capture_output=True, text=True, check=True)
    return [float(v) for v in res.stdout.split()]

def holm(p):
    p = np.asarray(p); o = np.argsort(p); m = len(p); adj = np.empty(m)
    adj[o] = np.minimum(1, np.maximum.accumulate((m - np.arange(m)) * p[o]))
    return adj

def cross(var, keep_cols=None, drop_rows=(), row='セグメント'):
    t = pd.crosstab(df[row], df[var])
    full = t.copy(); full['合計'] = full.sum(1)
    tt = t.drop(index=list(drop_rows), errors='ignore')
    if keep_cols is not None: tt = tt[keep_cols]
    tt = tt.loc[tt.sum(1) > 0, tt.sum(0) > 0]
    a = tt.values.astype(float)
    chi, _, dof, ex = chi2_contingency(a, correction=False)
    N = a.sum(); rs = a.sum(1, keepdims=True) / N; cs = a.sum(0, keepdims=True) / N
    adj = (a - ex) / np.sqrt(ex * (1 - rs) * (1 - cs))
    res = pd.DataFrame(adj, index=tt.index, columns=tt.columns)
    # 下位検定: 各セル「そのセグメントか否か × そのカテゴリーか否か」の 2×2 フィッシャー検定（Holm 補正）
    cells = [(i, j) for i in range(a.shape[0]) for j in range(a.shape[1])]
    sub = [np.array([[a[i, j], a[i].sum() - a[i, j]], [a[:, j].sum() - a[i, j], N - a[i].sum() - a[:, j].sum() + a[i, j]]])
           for i, j in cells]
    ps = r_fisher([a] + sub)
    post = pd.DataFrame(np.nan, index=tt.index, columns=tt.columns)
    for (i, j), q in zip(cells, holm(ps[1:])): post.iat[i, j] = q
    stat = {'検定対象n': int(N), 'フィッシャーの正確確率検定 p': ps[0], "Cramér's V": np.sqrt(chi / (N * (min(a.shape) - 1))),
            '（参考）χ²': chi, '（参考）df': dof, '期待度数<5のセル割合': (ex < 5).mean()}
    return full, (t.T / t.sum(1)).T, res, post, stat

crosses = {
    '体験タイプ': cross('体験タイプ', ['T1', 'T2', 'T3', 'T4']),
    '性別': cross('性別', ['男性', '女性']),
    '職業': cross('職業'),
    '年齢層': cross('年齢層'),
    # 撮影頻度はクラスタリングの投入変数・Step1の分割基準なので、関連が出るのは当然（記述用）
    '撮影頻度': cross('撮影頻度', ['月に数回', '週1回くらい', '週に数回', 'ほぼ毎日'], drop_rows=['ほとんど撮らない層']),
}
# セグメントを介さない、撮影頻度 × 属性のクロス集計
freq_crosses = {
    '体験タイプ': cross('体験タイプ', ['T1', 'T2', 'T3', 'T4'], row='撮影頻度'),
    '性別': cross('性別', ['男性', '女性'], row='撮影頻度'),
    '職業': cross('職業', row='撮影頻度'),
    '年齢層': cross('年齢層', row='撮影頻度'),
}

# ---------- 出力 ----------
with pd.ExcelWriter(f'{OUT}/segmentation_results.xlsx', engine='xlsxwriter') as w:
    prof.round(3).to_excel(w, sheet_name='セグメント概要')
    freq_tab.round(3).to_excel(w, sheet_name='撮影頻度構成')
    purp_all.round(3).to_excel(w, sheet_name='非日常の目的 選択率')
    item_tab.round(2).to_excel(w, sheet_name='考え方8項目 平均')
    fa_tab.round(3).to_excel(w, sheet_name='S2 因子分析 指標')
    load.round(3).to_excel(w, sheet_name='S2 因子負荷量')
    q3_eig.round(3).to_excel(w, sheet_name='S3 数量化III類 固有値')
    q3_cat.round(3).to_excel(w, sheet_name='S3 カテゴリースコア')
    sil.round(3).to_excel(w, sheet_name='S4 シルエット')
    agree.to_excel(w, sheet_name='S4 ウォード×kmeans')
    r0 = 0
    for nm, (full, pct, res, post, stat) in [*crosses.items(), *[(f'頻度×{k}', v) for k, v in freq_crosses.items()]]:
        sh = f'S5 {nm}' if not nm.startswith('頻度×') else f'S6 {nm}'
        pd.DataFrame({'値': stat}).round(4).to_excel(w, sheet_name=sh, startrow=0)
        full.to_excel(w, sheet_name=sh, startrow=10); pct.round(3).to_excel(w, sheet_name=sh, startrow=20)
        res.round(2).to_excel(w, sheet_name=sh, startrow=30); post.round(4).to_excel(w, sheet_name=sh, startrow=40)
        ws = w.sheets[sh]
        for rr, t in [(9, '度数'), (19, '行%（セグメント内の構成比）'), (29, '調整済み残差（記述用）'),
                      (39, '下位検定: セルごとの2×2フィッシャー検定 p（Holm補正）')]: ws.write(rr, 0, t)
    out_ids = pd.DataFrame({'回答No': df.index + 1, 'セグメント': df['セグメント'], '体験タイプ': df['体験タイプ']})
    for nm, z in zip(VNAME, V.T): out_ids.loc[d.index, nm] = z
    out_ids.to_excel(w, sheet_name='回答者別 所属', index=False)

# ---------- 図 ----------
font = next((f for f in font_manager.findSystemFonts() if 'wqy-zenhei' in f.lower()), None)
if font:
    font_manager.fontManager.addfont(font); plt.rcParams['font.family'] = font_manager.FontProperties(fname=font).get_name()
INK, INK2, GRID, SURF = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
SER = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300']
plt.rcParams.update({'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2, 'ytick.color': INK2,
                     'figure.facecolor': SURF, 'axes.facecolor': SURF, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.unicode_minus': False})

fig, ax = plt.subplots(figsize=(9, 4.5))
cut = (L[-K, 2] + L[-K + 1, 2]) / 2
set_link_color_palette(SER[:K]); dendrogram(L, ax=ax, color_threshold=cut, above_threshold_color=INK2, no_labels=True)
ax.axhline(cut, color=INK2, ls='--', lw=1); ax.text(ax.get_xlim()[1], cut, f' k={K}', va='bottom', ha='right', color=INK2)
ax.set_ylabel('結合距離（ウォード法）'); ax.set_title(f'デンドログラム（n={n}）', color=INK, loc='left')
fig.tight_layout(); fig.savefig(f'{OUT}/fig1_dendrogram.png', dpi=150); plt.close(fig)

fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(sil.index, sil['ウォード法 シルエット'], 'o-', color=SER[0], lw=2, ms=8, label='ウォード法')
ax.plot(sil.index, sil['k-means後 シルエット'], 's-', color=SER[1], lw=2, ms=8, label='k-means で微調整後')
ax.axvline(K, color=GRID, lw=6, zorder=0)
ax.set_xlabel('クラスター数 k'); ax.set_ylabel('平均シルエット値'); ax.grid(axis='y', color=GRID)
ax.set_title('クラスター数とシルエット値', color=INK, loc='left'); ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(f'{OUT}/fig2_silhouette.png', dpi=150); plt.close(fig)

fig, ax = plt.subplots(figsize=(7, 5.5))
ax.axhline(0, color=GRID); ax.axvline(0, color=GRID)
ax.scatter(COL[:, 0], COL[:, 1], s=40 + Bm.sum(0) * 1.5, color=SER[0], edgecolor=SURF, lw=2, zorder=3)
OFF = {'周りが撮っている': (-6, 6, 'right'), '人に見せる・送る': (-8, -3, 'right'), '自分で見返す': (8, -12, 'left'), '記念・思い出': (8, 4, 'left')}
for x, y, t, k in zip(COL[:, 0], COL[:, 1], OPT_S, Bm.sum(0)):
    dx, dy, ha = OFF.get(t, (8, 4, 'left'))
    ax.annotate(f'{t}（{k}）', (x, y), xytext=(dx, dy), textcoords='offset points', ha=ha, color=INK, fontsize=9)
ax.set_xlabel(f'軸1（寄与率 {q3_eig.iloc[0, 2]:.1%}）  なんとなく ⇔ 意図的')
ax.set_ylabel(f'軸2（寄与率 {q3_eig.iloc[1, 2]:.1%}）  自分の記録 ⇔ その場・共有の楽しみ')
ax.set_title('非日常の撮影目的：数量化III類 カテゴリースコア（括弧内は選択数）', color=INK, loc='left', fontsize=10)
fig.tight_layout(); fig.savefig(f'{OUT}/fig3_quant3.png', dpi=150); plt.close(fig)

cm = LinearSegmentedColormap.from_list('div', ['#2a78d6', '#f0efec', '#e34948'])
zp = prof.loc[ORDER[:-1], [f'{v} (z)' for v in VNAME]]
fig, ax = plt.subplots(figsize=(8, 3.8))
ax.imshow(zp.values, cmap=cm, vmin=-2, vmax=2, aspect='auto')
ax.set_xticks(range(len(VNAME)), VNAME, rotation=20, ha='right'); ax.set_yticks(range(len(zp)), [f'{s}（n={prof.loc[s, "n"]}）' for s in zp.index])
for i in range(zp.shape[0]):
    for j in range(zp.shape[1]):
        ax.text(j, i, f'{zp.values[i, j]:+.2f}', ha='center', va='center', color=INK, fontsize=9)
ax.spines[:].set_visible(False); ax.tick_params(length=0)
ax.set_title('クラスター別の平均（標準化得点 z、青＝低い／赤＝高い）', color=INK, loc='left', fontsize=10)
fig.tight_layout(); fig.savefig(f'{OUT}/fig4_profile.png', dpi=150); plt.close(fig)

t = crosses['体験タイプ'][0].drop(columns='合計')[['T1', 'T2', 'T3', 'T4']]
pct = (t.T / t.sum(1)).T
fig, ax = plt.subplots(figsize=(8, 3.6)); left = np.zeros(len(pct))
TN = {'T1': 'T1 観客型', 'T2': 'T2 鑑賞回遊型', 'T3': 'T3 演出空間で仲間と過ごす型', 'T4': 'T4 機能的な場での活動型'}
for j, cc in enumerate(pct.columns):
    ax.barh(range(len(pct)), pct[cc], left=left, color=SER[j], edgecolor=SURF, lw=2, label=TN[cc])
    for i, (v, l0) in enumerate(zip(pct[cc], left)):
        if v >= .1: ax.text(l0 + v / 2, i, f'{v:.0%}', ha='center', va='center', color=INK, fontsize=8)
    left += pct[cc].values
ax.set_yticks(range(len(pct)), [f'{s}（n={int(t.loc[s].sum())}）' for s in pct.index]); ax.invert_yaxis()
ax.set_xlim(0, 1); ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
ax.legend(ncol=2, frameon=False, loc='upper center', bbox_to_anchor=(.5, -.12), fontsize=8)
ax.set_title('セグメント別の体験タイプ構成', color=INK, loc='left')
fig.tight_layout(); fig.savefig(f'{OUT}/fig5_type_by_segment.png', dpi=150); plt.close(fig)

# ---------- コンソール要約 ----------
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
print(fa_tab.round(3).T.to_string()); print(load.round(2)); print(q3_eig.round(3).head(4)); print(q3_cat.round(2))
print(sil.round(3)); print(agree); print(prof.round(2).to_string()); print(purp_all.round(2).to_string()); print(freq_tab.round(2).to_string())
for nm, (full, pct, res, post, stat) in [*crosses.items(), *[(f'頻度×{k}', v) for k, v in freq_crosses.items()]]:
    print(full.to_string()) if nm.startswith('頻度×') else None
    print('\n##', nm, {k: round(float(v), 4) for k, v in stat.items()}); print(res.round(2).to_string()); print(post.round(3).to_string())
