# =============================================================================
# 01_descriptive.R
# 写真・動画撮影と体験に関するアンケート：全体像の記述統計・グラフ作成
#
# 使い方（RStudio）:
#   1. claude-test.Rproj を開く（作業ディレクトリがプロジェクト直下になる）
#   2. Googleフォームの回答 xlsx を data/survey.xlsx として置く
#   3. このファイルを開いて「Source」
#   -> analysis/output/tables/ に集計表（CSV, Excelで開ける）
#      analysis/output/figures/ にグラフ（PNG）が出力される
#
# 必要パッケージ: readxl, dplyr, tidyr, stringr, purrr, readr, ggplot2, scales
#   （任意）ragg … 日本語フォントの描画が安定するので推奨
# =============================================================================

pkgs <- c("readxl", "dplyr", "tidyr", "stringr", "purrr", "readr", "ggplot2", "scales")
missing_pkgs <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_pkgs) > 0) install.packages(missing_pkgs)

suppressPackageStartupMessages({
  library(readxl)
  library(dplyr)
  library(tidyr)
  library(stringr)
  library(purrr)
  library(readr)
  library(ggplot2)
})

# ---- 設定 -------------------------------------------------------------------

data_path <- "data/survey.xlsx"
out_dir   <- "analysis/output"
tab_dir   <- file.path(out_dir, "tables")
fig_dir   <- file.path(out_dir, "figures")
for (d in c(tab_dir, file.path(fig_dir, c("single", "multi")))) {
  dir.create(d, recursive = TRUE, showWarnings = FALSE)
}

# 体験タイプ（4-1）の T1〜T4 割り当て。番号の付け方が違う場合はここを書き換える。
type_map <- c(
  "観客型"                   = "T1",
  "鑑賞回遊型"               = "T2",
  "演出空間で仲間と過ごす型" = "T3",
  "機能的な場での活動型"     = "T4"
)
group_levels <- c("全体", "T1", "T2", "T3", "T4")

# 順序のある選択肢（ここに無い項目は度数の多い順に並べる）
ordinal_levels <- list(
  "2-1"  = c("ほとんどない", "月に数回", "週1回くらい", "週に数回", "ほぼ毎日"),
  "4-4"  = c("1時間未満", "1〜2時間", "2〜3時間", "3〜5時間", "5時間以上"),
  "4-12" = c("なかった", "1〜2回", "3〜5回", "6回以上"),
  "4-29" = c("見返していない", "1〜2回見返した", "何度も見返した")
)

# 1人しか選んでいない選択肢（=「その他」欄の自由記述）はまとめる
other_label <- "その他（自由記述）"

# ---- フォント・配色・テーマ ---------------------------------------------------

jp_font <- switch(Sys.info()[["sysname"]],
  Windows = "Yu Gothic",
  Darwin  = "Hiragino Sans",
  "Noto Sans CJK JP"
)
use_ragg <- requireNamespace("ragg", quietly = TRUE)
if (!use_ragg && Sys.info()[["sysname"]] == "Windows") {
  windowsFonts(`Yu Gothic` = windowsFont("Yu Gothic"))
}

ink       <- "#0b0b0b"
ink_2     <- "#52514e"
ink_muted <- "#898781"
grid_col  <- "#e1e0d9"
surface   <- "#fcfcfb"

# 全体＝グレー、T1〜T4＝カテゴリカル配色（固定順）
group_cols <- c("全体" = "#52514e", "T1" = "#2a78d6", "T2" = "#eb6834",
                "T3" = "#1baf7a", "T4" = "#eda100")
cat_cols <- c("#2a78d6", "#eb6834", "#1baf7a", "#eda100",
              "#e87ba4", "#008300", "#6250d6", "#e34948")
seq_cols <- c("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")
# −3〜+3 用の発散配色（赤←グレー→青）
likert_cols <- c("-3" = "#b8302f", "-2" = "#e66767", "-1" = "#f4b3b2", "0" = "#e1e0d9",
                 "1" = "#9ec5f4", "2" = "#5598e7", "3" = "#1c5cab")

theme_survey <- function(base_size = 11) {
  theme_minimal(base_size = base_size, base_family = jp_font) +
    theme(
      plot.background    = element_rect(fill = surface, colour = NA),
      panel.grid.major.y = element_blank(),
      panel.grid.minor   = element_blank(),
      panel.grid.major.x = element_line(colour = grid_col, linewidth = 0.3),
      axis.text          = element_text(colour = ink_2),
      axis.title         = element_text(colour = ink_muted),
      plot.title         = element_text(colour = ink, face = "bold", size = base_size + 2),
      plot.subtitle      = element_text(colour = ink_2),
      plot.caption       = element_text(colour = ink_muted, hjust = 0),
      legend.text        = element_text(colour = ink_2),
      legend.title       = element_text(colour = ink_muted),
      legend.position    = "top",
      strip.text         = element_text(colour = ink, face = "bold", hjust = 0),
      plot.title.position = "plot"
    )
}

save_plot <- function(p, file, width = 8, height = 5) {
  if (use_ragg) {
    ggsave(file, p, width = width, height = height, dpi = 200, device = ragg::agg_png)
  } else {
    ggsave(file, p, width = width, height = height, dpi = 200)
  }
}

write_table <- function(df, name) {
  write_excel_csv(df, file.path(tab_dir, paste0(name, ".csv")), na = "")
}

wrap <- function(x, width = 24) str_wrap(x, width = width)

# ---- 読み込みと項目メタ情報 -------------------------------------------------

raw <- read_excel(data_path, .name_repair = "minimal")
raw <- raw[, names(raw) != "" & !str_detect(names(raw), "^Column")]

# 個人情報・自由記述・タイムスタンプは集計対象外
drop_pattern <- str_c(
  "Timestamp", "メールアドレス", "インタビュー", "どんな場面でしたか",
  "きっかけを教えてください", "自由に書いて", sep = "|"
)
keep <- !str_detect(names(raw), drop_pattern)
dat  <- raw[, keep]

likert_values <- -3:3

meta <- tibble(header = names(dat)) |>
  mutate(
    col_id  = row_number(),
    qnum    = str_extract(header, "^\\d+-\\d+"),
    # 番号のない「次の項目は…」ブロックは撮影態度（3-x）として扱う
    qnum    = if_else(is.na(qnum) & str_detect(header, "次の項目は"), "3", qnum),
    bracket = str_match(header, "\\[(.+)\\]\\s*$")[, 2],
    question = header |>
      str_remove("\\s*\\[.+\\]\\s*$") |>
      str_remove("^\\d+-\\d+\\.\\s*") |>
      str_replace_all("\\s+", " "),
    label = coalesce(bracket, question),
    type = case_when(
      str_detect(header, "すべて選んで") ~ "multi",
      qnum %in% c("1-1", "4-3") ~ "numeric",
      !is.na(bracket) ~ "likert",
      TRUE ~ "single"
    )
  ) |>
  group_by(qnum) |>
  mutate(code = if (n() > 1) str_c(qnum, "_", row_number()) else qnum) |>
  ungroup() |>
  mutate(code = if_else(code == "4-1", "type", code))

# 4-23 は2箇所に分かれて出力されているため、通し番号は列順になる
names(dat) <- meta$code

# Likert 項目は数値に
likert_codes <- meta$code[meta$type == "likert"]
dat <- dat |> mutate(across(all_of(likert_codes), ~ suppressWarnings(as.numeric(.x))))
stopifnot(all(unlist(dat[likert_codes]) %in% c(likert_values, NA)))

# 体験タイプ
dat <- dat |>
  mutate(
    type_label = str_remove(type, "（.*$"),
    group      = unname(type_map[type_label]),
    group      = factor(group, levels = group_levels[-1])
  )

# 「全体」行を足した縦持ちデータ（全体＋T1〜T4 の比較用）
with_total <- function(df) {
  bind_rows(
    df |> mutate(group = "全体"),
    df |> filter(!is.na(group)) |> mutate(group = as.character(group))
  ) |>
    mutate(group = factor(group, levels = group_levels))
}

block_of <- function(code) {
  case_when(
    str_starts(code, "3_")                        ~ "3 撮影に対する態度",
    str_starts(code, "(4-5|4-8|4-9)")               ~ "4-5〜4-9 体験全体の評価",
    str_starts(code, "4-23")                      ~ "4-23 撮影の目的",
    str_starts(code, "(4-24|4-25)")                 ~ "4-24・4-25 撮影中・撮影直後",
    str_starts(code, "(4-30|4-33)")                 ~ "4-30・4-33 見返し・共有"
  )
}

# ---- 0. 回答者の概要 ---------------------------------------------------------

type_tab <- dat |>
  count(type_label, group) |>
  mutate(pct = n / sum(n) * 100) |>
  arrange(group)
write_table(type_tab, "00_type_counts")

demo_tab <- dat |>
  select(group, gender = `1-2`, job = `1-3`) |>
  with_total() |>
  pivot_longer(c(gender, job), names_to = "item", values_to = "option") |>
  count(item, option, group) |>
  group_by(item, group) |>
  mutate(pct = n / sum(n) * 100) |>
  ungroup()
write_table(demo_tab, "00_demographics")

# ---- 1. 数値項目（年齢・人数） ----------------------------------------------

num_summary <- function(x) {
  tibble(n = sum(!is.na(x)), mean = mean(x, na.rm = TRUE), sd = sd(x, na.rm = TRUE),
         min = min(x, na.rm = TRUE), q1 = quantile(x, .25, na.rm = TRUE),
         median = median(x, na.rm = TRUE), q3 = quantile(x, .75, na.rm = TRUE),
         max = max(x, na.rm = TRUE))
}

numeric_tab <- dat |>
  transmute(group, `年齢` = as.numeric(`1-1`), `体験の人数（自分含む）` = as.numeric(`4-3`)) |>
  with_total() |>
  pivot_longer(-group, names_to = "item", values_to = "value") |>
  group_by(item, group) |>
  summarise(num_summary(value), .groups = "drop") |>
  mutate(across(where(is.double), ~ round(.x, 2)))
write_table(numeric_tab, "01_numeric_summary")

# ---- 2. 単一選択項目 ---------------------------------------------------------

single_codes <- meta |>
  filter(type == "single", !code %in% c("type")) |>
  pull(code)

lump_rare <- function(x) {
  counts <- table(x)
  if_else(!is.na(x) & x %in% names(counts)[counts == 1], other_label, x)
}

single_long <- dat |>
  select(group, all_of(single_codes)) |>
  mutate(across(all_of(single_codes), ~ lump_rare(as.character(.x)))) |>
  with_total() |>
  pivot_longer(all_of(single_codes), names_to = "code", values_to = "option") |>
  filter(!is.na(option))

single_tab <- single_long |>
  count(code, group, option) |>
  group_by(code, group) |>
  mutate(n_valid = sum(n), pct = round(n / n_valid * 100, 1)) |>
  ungroup() |>
  left_join(meta |> select(code, question), by = "code") |>
  relocate(question, .after = code)

write_table(single_tab |> filter(group == "全体") |> select(-group), "02_single_overall")
write_table(single_tab, "02_single_by_type")

# 項目ごとに、全体＋T1〜T4 の100%積み上げ棒グラフ
option_order <- function(code, options, counts) {
  lv <- ordinal_levels[[code]]
  if (!is.null(lv)) return(c(lv, setdiff(options, lv)))
  ord <- options[order(-counts)]
  c(setdiff(ord, other_label), intersect(ord, other_label))
}

plot_single <- function(cd) {
  d  <- single_tab |> filter(code == cd)
  tot <- d |> filter(group == "全体")
  lv <- option_order(cd, tot$option, tot$n)
  d <- d |> mutate(option = factor(option, levels = rev(lv)),
                   group  = factor(group, levels = rev(group_levels)))
  k <- length(lv)
  cols <- if (!is.null(ordinal_levels[[cd]])) {
    seq_cols[round(seq(2, 7, length.out = k))]
  } else if (k <= length(cat_cols)) {
    cat_cols[seq_len(k)]
  } else {
    colorRampPalette(cat_cols)(k)
  }
  names(cols) <- lv
  if (other_label %in% lv) cols[other_label] <- "#c3c2b7"
  n_lab <- d |> distinct(group, n_valid)

  p <- ggplot(d, aes(x = pct, y = group, fill = option)) +
    geom_col(width = 0.7, colour = surface, linewidth = 0.5) +
    geom_text(aes(label = if_else(pct >= 8, str_c(round(pct), "%"), "")),
              position = position_stack(vjust = 0.5), size = 3,
              family = jp_font, colour = "white") +
    geom_text(data = n_lab, aes(x = 101, y = group, label = str_c("n=", n_valid)),
              inherit.aes = FALSE, hjust = 0, size = 3, family = jp_font, colour = ink_muted) +
    scale_fill_manual(values = cols, breaks = lv, labels = wrap(lv, 20), name = NULL) +
    scale_x_continuous(limits = c(0, 110), breaks = seq(0, 100, 25),
                       labels = function(x) str_c(x, "%"), expand = c(0, 0)) +
    labs(title = str_c(cd, ". ", wrap(meta$question[meta$code == cd], 32)),
         x = NULL, y = NULL) +
    guides(fill = guide_legend(nrow = ceiling(k / 3), byrow = TRUE)) +
    theme_survey()
  save_plot(p, file.path(fig_dir, "single", str_c(cd, ".png")),
            width = 8, height = 3.6 + 0.3 * ceiling(k / 3))
}
walk(single_codes, plot_single)

# ---- 3. 複数選択項目 ---------------------------------------------------------

multi_codes <- meta$code[meta$type == "multi"]

multi_long <- dat |>
  mutate(id = row_number()) |>
  select(id, group, all_of(multi_codes)) |>
  pivot_longer(all_of(multi_codes), names_to = "code", values_to = "answer") |>
  filter(!is.na(answer)) |>
  separate_rows(answer, sep = ",\\s*") |>
  mutate(answer = str_trim(answer)) |>
  group_by(code) |>
  mutate(answer = lump_rare(answer)) |>
  ungroup() |>
  distinct()

# 分母 = その設問に回答した人数
multi_denom <- dat |>
  select(group, all_of(multi_codes)) |>
  with_total() |>
  pivot_longer(all_of(multi_codes), names_to = "code", values_to = "answer") |>
  filter(!is.na(answer)) |>
  count(code, group, name = "n_resp")

multi_tab <- multi_long |>
  with_total() |>
  distinct(id, group, code, answer) |>
  count(code, group, answer, name = "n_selected") |>
  complete(nesting(code, answer), group, fill = list(n_selected = 0)) |>
  left_join(multi_denom, by = c("code", "group")) |>
  mutate(pct = round(n_selected / n_resp * 100, 1)) |>
  left_join(meta |> select(code, question), by = "code") |>
  relocate(question, .after = code) |>
  arrange(code, group, desc(n_selected))

write_table(multi_tab |> filter(group == "全体") |> select(-group), "03_multi_overall")
write_table(multi_tab, "03_multi_by_type")

plot_multi <- function(cd) {
  d <- multi_tab |> filter(code == cd, !is.na(n_resp))
  tot <- d |> filter(group == "全体") |> arrange(n_selected)
  lv <- c(intersect(other_label, tot$answer), setdiff(tot$answer, other_label))
  d <- d |> mutate(answer = factor(answer, levels = lv),
                   facet  = str_c(group, "（n=", n_resp, "）"),
                   facet  = factor(facet, levels = unique(facet[order(group)])))
  p <- ggplot(d, aes(x = pct, y = answer, fill = group)) +
    geom_col(width = 0.7) +
    geom_text(aes(label = str_c(round(pct), "%")), hjust = -0.15, size = 2.8,
              family = jp_font, colour = ink_2) +
    facet_wrap(~facet, nrow = 1) +
    scale_fill_manual(values = group_cols, guide = "none") +
    scale_y_discrete(labels = function(x) wrap(x, 18)) +
    scale_x_continuous(limits = c(0, 125), breaks = c(0, 50, 100),
                       labels = function(x) str_c(x, "%"), expand = c(0, 0)) +
    labs(title = str_c(cd, ". ", wrap(meta$question[meta$code == cd], 50)),
         subtitle = "各グループで、その選択肢を選んだ人の割合（複数回答）",
         x = NULL, y = NULL) +
    theme_survey(10)
  save_plot(p, file.path(fig_dir, "multi", str_c(cd, ".png")),
            width = 12, height = 2 + 0.35 * length(lv))
}
walk(multi_codes, plot_multi)

# ---- 4. −3〜+3 の評定項目 ----------------------------------------------------

likert_long <- dat |>
  select(group, all_of(likert_codes)) |>
  with_total() |>
  pivot_longer(all_of(likert_codes), names_to = "code", values_to = "value") |>
  filter(!is.na(value)) |>
  left_join(meta |> select(code, label), by = "code") |>
  mutate(block = block_of(code))

likert_summary <- likert_long |>
  group_by(block, code, label, group) |>
  summarise(
    n        = n(),
    mean     = mean(value),
    sd       = sd(value),
    se       = sd / sqrt(n),
    median   = median(value),
    pct_agree    = mean(value > 0) * 100,
    pct_neutral  = mean(value == 0) * 100,
    pct_disagree = mean(value < 0) * 100,
    .groups = "drop"
  ) |>
  mutate(across(c(mean, sd, se, median, starts_with("pct")), ~ round(.x, 2))) |>
  arrange(code, group)

write_table(likert_summary |> filter(group == "全体") |> select(-group), "04_likert_overall")
write_table(likert_summary, "04_likert_by_type")

likert_dist <- likert_long |>
  filter(group == "全体") |>
  count(block, code, label, value) |>
  complete(nesting(block, code, label), value = likert_values, fill = list(n = 0)) |>
  group_by(code) |>
  mutate(pct = round(n / sum(n) * 100, 1)) |>
  ungroup()
write_table(likert_dist |> pivot_wider(id_cols = c(block, code, label), names_from = value,
                                       values_from = n, names_prefix = "n_"),
            "04_likert_distribution")

# 4a. 回答分布（全体）：0 を中央にそろえた発散型の積み上げ棒
plot_likert_dist <- function(blk) {
  d <- likert_dist |> filter(block == blk) |>
    mutate(item = str_c(code, " ", label),
           value = factor(value, levels = likert_values))
  item_order <- likert_summary |> filter(block == blk, group == "全体") |>
    arrange(mean) |> mutate(item = str_c(code, " ", label)) |> pull(item)
  d <- d |> mutate(item = factor(item, levels = item_order))

  # 0 の半分を左右に振り分けて中央をそろえる
  neg <- d |> filter(as.integer(as.character(value)) <= 0) |>
    mutate(pct = if_else(value == "0", pct / 2, pct), pct = -pct,
           value = factor(value, levels = c("-3", "-2", "-1", "0")))
  pos <- d |> filter(as.integer(as.character(value)) >= 0) |>
    mutate(pct = if_else(value == "0", pct / 2, pct),
           value = factor(value, levels = c("3", "2", "1", "0")))
  n_lab <- likert_summary |> filter(block == blk, group == "全体") |>
    mutate(item = factor(str_c(code, " ", label), levels = item_order))

  p <- ggplot(mapping = aes(y = item, x = pct, fill = value)) +
    geom_col(data = neg, width = 0.7) +
    geom_col(data = pos, width = 0.7) +
    geom_vline(xintercept = 0, colour = ink_muted, linewidth = 0.3) +
    geom_text(data = n_lab, aes(x = 102, y = item,
                                label = sprintf("M=%.2f  n=%d", mean, n)),
              inherit.aes = FALSE, hjust = 0, size = 2.8, family = jp_font,
              colour = ink_2) +
    scale_fill_manual(values = likert_cols, breaks = as.character(likert_values),
                      labels = c("−3 全く当てはまらない", "−2", "−1", "0", "+1", "+2",
                                 "+3 とても当てはまる"),
                      name = NULL) +
    scale_x_continuous(limits = c(-100, 135), breaks = seq(-100, 100, 50),
                       labels = function(x) str_c(abs(x), "%")) +
    scale_y_discrete(labels = function(x) wrap(x, 28)) +
    guides(fill = guide_legend(nrow = 1)) +
    labs(title = str_c(blk, "：回答分布（全体）"),
         subtitle = "左＝当てはまらない側、右＝当てはまる側（0 は左右に半分ずつ）。平均値の高い順",
         x = NULL, y = NULL) +
    theme_survey(10)
  save_plot(p, file.path(fig_dir, str_c("likert_dist_", str_extract(blk, "^[0-9-]+"), ".png")),
            width = 11, height = 1.8 + 0.45 * n_distinct(d$item))
}

# 4b. タイプ別の平均値（ドットプロット、エラーバー＝±1SE）
plot_likert_means <- function(blk) {
  d <- likert_summary |> filter(block == blk) |>
    mutate(item = str_c(code, " ", label))
  item_order <- d |> filter(group == "全体") |> arrange(mean) |> pull(item)
  d <- d |> mutate(item = factor(item, levels = item_order))
  pd <- position_dodge(width = 0.6)

  p <- ggplot(d, aes(x = mean, y = item, colour = group)) +
    geom_vline(xintercept = 0, colour = ink_muted, linewidth = 0.3) +
    geom_errorbarh(aes(xmin = mean - se, xmax = mean + se), height = 0,
                   position = pd, linewidth = 0.5, alpha = 0.6) +
    geom_point(aes(shape = group), position = pd, size = 2.6) +
    scale_colour_manual(values = group_cols, name = NULL) +
    scale_shape_manual(values = c(18, 16, 16, 16, 16), name = NULL) +
    scale_x_continuous(limits = c(-3, 3), breaks = -3:3) +
    scale_y_discrete(labels = function(x) wrap(x, 28)) +
    labs(title = str_c(blk, "：平均値（全体・T1〜T4）"),
         subtitle = "点＝平均、横線＝±1標準誤差",
         x = "平均（−3〜+3）", y = NULL) +
    theme_survey(10)
  save_plot(p, file.path(fig_dir, str_c("likert_mean_", str_extract(blk, "^[0-9-]+"), ".png")),
            width = 9, height = 1.8 + 0.6 * n_distinct(d$item))
}

blocks <- unique(na.omit(likert_summary$block))
walk(blocks, plot_likert_dist)
walk(blocks, plot_likert_means)

# ---- 5. 体験タイプの人数 -----------------------------------------------------

p_type <- type_tab |>
  mutate(lab = if_else(is.na(group), type_label, str_c(group, " ", type_label)),
         lab = factor(lab, levels = rev(lab))) |>
  ggplot(aes(x = n, y = lab, fill = group)) +
  geom_col(width = 0.65) +
  geom_text(aes(label = sprintf("%d人（%.0f%%）", n, pct)), hjust = -0.1, size = 3.2,
            family = jp_font, colour = ink_2) +
  scale_fill_manual(values = group_cols, na.value = "#c3c2b7", guide = "none") +
  scale_x_continuous(expand = expansion(mult = c(0, 0.25))) +
  labs(title = "4-1. ここ1ヶ月で一番記憶に残っている体験のタイプ",
       subtitle = str_c("回答者 N=", nrow(dat)), x = "人数", y = NULL) +
  theme_survey()
save_plot(p_type, file.path(fig_dir, "00_type_counts.png"), width = 8, height = 3.5)

# ---- 項目一覧（コード表） ----------------------------------------------------

write_table(meta |> select(code, type, question, label), "99_codebook")

message("完了: ", normalizePath(out_dir))
