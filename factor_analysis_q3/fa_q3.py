"""設問3（写真を撮ることへの意識・8項目）の探索的因子分析.
使い方: python fa_q3.py <回答データ.xlsx> <出力ディレクトリ>
"""
import sys, warnings
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from factor_analyzer import FactorAnalyzer
from factor_analyzer.factor_analyzer import calculate_kmo, calculate_bartlett_sphericity
warnings.filterwarnings('ignore')

src, out = sys.argv[1], sys.argv[2]
df = pd.read_excel(src, 'Form Responses 1')
cols = [k for k in df.columns if str(k).startswith('次の項目は')]
labels = [k.split('[')[-1].rstrip(']') for k in cols]
X = df[cols].dropna()
X.columns = [f'Q3-{i+1}' for i in range(len(cols))]
lab = dict(zip(X.columns, labels))
n, p = X.shape

def alpha(Z):
    Z = np.asarray(Z); k = Z.shape[1]
    return k / (k - 1) * (1 - Z.var(0, ddof=1).sum() / Z.sum(1).var(ddof=1))

# 記述統計・相関
desc = X.describe().T[['count', 'mean', 'std', 'min', 'max']]
desc['skew'] = X.skew(); desc.insert(0, '項目', [lab[c] for c in X.columns])
corr = X.corr()

# 適合性
chi_b, p_b = calculate_bartlett_sphericity(X)
kmo_i, kmo_t = calculate_kmo(X)

# 因子数: 固有値と平行分析(95%ile, 2000回)
ev = np.linalg.eigvalsh(corr.values)[::-1]
rng = np.random.default_rng(0)
sims = np.array([np.linalg.eigvalsh(np.corrcoef(rng.standard_normal((n, p)), rowvar=False))[::-1] for _ in range(2000)])
pa = np.percentile(sims, 95, axis=0)
eig = pd.DataFrame({'固有値': ev, '平行分析95%': pa}, index=range(1, p + 1))

# 2因子・最尤法・プロマックス回転
fa = FactorAnalyzer(n_factors=2, rotation='promax', method='ml'); fa.fit(X)
L = pd.DataFrame(fa.loadings_, index=X.columns, columns=['F1 撮影への肯定的価値づけ', 'F2 撮影による体験阻害の意識'])
L['共通性'] = fa.get_communalities(); L.insert(0, '項目', [lab[c] for c in X.columns])
L = L.sort_values(['F1 撮影への肯定的価値づけ'], key=lambda s: -s.abs())
var = fa.get_factor_variance()
phi = pd.DataFrame(fa.phi_, index=['F1', 'F2'], columns=['F1', 'F2'])

F1 = ['Q3-1', 'Q3-3', 'Q3-4', 'Q3-5', 'Q3-6', 'Q3-8']; F2 = ['Q3-2', 'Q3-7']
rel = pd.DataFrame({'項目数': [6, 2], 'α係数': [alpha(X[F1]), alpha(X[F2])],
                    '尺度得点平均': [X[F1].mean(1).mean(), X[F2].mean(1).mean()],
                    '尺度得点SD': [X[F1].mean(1).std(), X[F2].mean(1).std()]}, index=['F1', 'F2'])
summary = pd.DataFrame({'値': [len(df), n, kmo_t, chi_b, p_b, var[1][0], var[1][1], var[2][1]]},
    index=['回答者数', '分析対象(欠測除外)', 'KMO', 'Bartlett χ²', 'Bartlett p', 'F1 寄与率', 'F2 寄与率', '累積寄与率'])

with pd.ExcelWriter(f'{out}/fa_q3_results.xlsx') as w:
    summary.to_excel(w, sheet_name='概要'); desc.round(2).to_excel(w, sheet_name='記述統計'); corr.round(3).to_excel(w, sheet_name='相関行列')
    pd.DataFrame({'項目': labels, 'KMO(MSA)': kmo_i}, index=X.columns).round(3).to_excel(w, sheet_name='項目別KMO')
    eig.round(3).to_excel(w, sheet_name='固有値_平行分析'); L.round(3).to_excel(w, sheet_name='因子負荷量')
    phi.round(3).to_excel(w, sheet_name='因子間相関'); rel.round(3).to_excel(w, sheet_name='信頼性')

jp = [f for f in font_manager.findSystemFonts() if 'wqy' in f.lower() or 'noto' in f.lower() and 'cjk' in f.lower()]
if jp:
    font_manager.fontManager.addfont(jp[0]); plt.rcParams['font.family'] = font_manager.FontProperties(fname=jp[0]).get_name()
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(eig.index, ev, 'o-', label='実データの固有値')
ax.plot(eig.index, pa, 's--', color='gray', label='平行分析（乱数95%点）')
ax.axhline(1, color='lightgray', lw=0.8)
ax.set_xlabel('因子番号'); ax.set_ylabel('固有値'); ax.set_title(f'設問3 スクリープロット (n={n})'); ax.legend()
fig.tight_layout(); fig.savefig(f'{out}/scree_q3.png', dpi=150)
print(summary.round(3)); print(L.round(3).to_string())
