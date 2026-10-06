/**
 * Googleフォーム編集スクリプト
 *   1. 性別の設問から「答えない」系の選択肢を削除
 *   2. セクション「1. あなたについて教えてください」を用意し、その中に 性別・年齢・職業 を入れる
 *   3. 「4つのタイプ」を聞く設問を「その体験について（概要）」の直前に移動
 *
 * 使い方:
 *   1. 念のためフォームを複製してバックアップ（︙ → コピーを作成）
 *   2. https://script.google.com で新しいプロジェクトを作成し、このコードを貼り付けて保存
 *   3. listItems を実行して設問一覧（ログ）を確認
 *   4. 必要なら下のキーワードを調整し、run を実行
 */
const FORM_ID = '1YVBN8OWO9f6ViWxNY2iQqxpVkMoMJMJ_JsKW-WbAM9E';

const TYPE_KEYWORD = 'タイプ';             // 移動したい設問のタイトルに含まれる語
const ANCHOR_KEYWORD = 'その体験について';  // この項目の直前に置く
const GENDER_KEYWORD = '性別';
const AGE_KEYWORD = '年齢';
const JOB_KEYWORD = '職業';
const PROFILE_SECTION_KEYWORD = 'あなたについて';
const PROFILE_SECTION_TITLE = '1. あなたについて教えてください';
const NO_ANSWER_PATTERN = /答え(ない|たくない)|回答(しない|したくない)/;

function listItems() {
  const form = FormApp.openById(FORM_ID);
  form.getItems().forEach((item, i) => {
    Logger.log(`${i}: [${item.getType()}] ${item.getTitle()}`);
  });
}

function run() {
  const form = FormApp.openById(FORM_ID);
  removeNoAnswerChoice(form);
  buildProfileSection(form);
  moveTypeQuestion(form);
  Logger.log('--- 完了後の並び ---');
  listItems();
}

function findOne(form, keyword, type) {
  const hits = form.getItems(type).filter(it => it.getTitle().includes(keyword));
  if (hits.length !== 1) {
    throw new Error(`「${keyword}」を含む項目が ${hits.length} 件あります。listItems で確認しキーワードを調整してください。`);
  }
  return hits[0];
}

// item を anchor の直前（offset=0）または直後（offset=1）に置く
function placeRelative(form, item, anchor, offset) {
  const from = item.getIndex();
  let to = anchor.getIndex() + offset;
  if (from < to) to -= 1; // 自身が抜けた分ずれる
  if (from !== to) form.moveItem(from, to);
}

function removeNoAnswerChoice(form) {
  const item = findOne(form, GENDER_KEYWORD);
  let q;
  switch (item.getType()) {
    case FormApp.ItemType.MULTIPLE_CHOICE: q = item.asMultipleChoiceItem(); break;
    case FormApp.ItemType.LIST: q = item.asListItem(); break;
    case FormApp.ItemType.CHECKBOX: q = item.asCheckboxItem(); break;
    default: throw new Error(`性別の設問の形式（${item.getType()}）は選択肢を持ちません。`);
  }
  const choices = q.getChoices();
  const kept = choices.filter(c => !NO_ANSWER_PATTERN.test(c.getValue()));
  if (kept.length === choices.length) {
    Logger.log('性別: 「答えない」系の選択肢は見つかりませんでした。');
    return;
  }
  // getChoices() の Choice をそのまま渡すと分岐設定（ページ移動）も保持される
  q.setChoices(kept);
  Logger.log(`性別: ${choices.length - kept.length} 件の選択肢を削除しました。`);
}

function buildProfileSection(form) {
  const breaks = form.getItems(FormApp.ItemType.PAGE_BREAK)
    .filter(it => it.getTitle().includes(PROFILE_SECTION_KEYWORD));
  let section;
  if (breaks.length === 1) {
    section = breaks[0];
  } else if (breaks.length === 0) {
    section = form.addPageBreakItem();
    form.moveItem(section.getIndex(), 0);
    Logger.log('セクション「あなたについて」が無かったため先頭に作成しました。');
  } else {
    throw new Error('「あなたについて」を含むセクションが複数あります。');
  }
  section.setTitle(PROFILE_SECTION_TITLE);

  // セクション直後に 性別 → 年齢 → 職業 の順で並べる
  let prev = section;
  [GENDER_KEYWORD, AGE_KEYWORD, JOB_KEYWORD].forEach(kw => {
    const item = findOne(form, kw);
    placeRelative(form, item, prev, 1);
    prev = item;
  });
  Logger.log('セクション1に 性別・年齢・職業 を配置しました。');
}

function moveTypeQuestion(form) {
  const typeItem = findOne(form, TYPE_KEYWORD);
  const anchor = findOne(form, ANCHOR_KEYWORD);
  placeRelative(form, typeItem, anchor, 0);
  Logger.log(`「${typeItem.getTitle()}」を「${anchor.getTitle()}」の直前に移動しました。`);
}
