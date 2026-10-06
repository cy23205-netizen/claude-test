/**
 * Googleフォームの「4つのタイプ」を聞く設問を、
 * 「その体験について（概要）」の直前に移動するスクリプト。
 *
 * 使い方:
 *   1. https://script.google.com で新しいプロジェクトを作成
 *   2. このコードを貼り付けて保存
 *   3. まず listItems を実行して設問一覧（ログ）を確認
 *   4. 必要なら TYPE_KEYWORD / ANCHOR_KEYWORD を調整して moveTypeQuestion を実行
 */
const FORM_ID = '1c2XNzvoX9ZtYsMnRfUjcN2-xEnDrM5XSlFmU14M5bmQ';
const TYPE_KEYWORD = 'タイプ';            // 移動したい設問のタイトルに含まれる語
const ANCHOR_KEYWORD = 'その体験について'; // この項目の直前に置く

function listItems() {
  const form = FormApp.openById(FORM_ID);
  form.getItems().forEach((item, i) => {
    Logger.log(`${i}: [${item.getType()}] ${item.getTitle()}`);
  });
}

function moveTypeQuestion() {
  const form = FormApp.openById(FORM_ID);
  const items = form.getItems();

  const typeItems = items.filter(it => it.getTitle().includes(TYPE_KEYWORD));
  const anchors = items.filter(it => it.getTitle().includes(ANCHOR_KEYWORD));
  if (typeItems.length !== 1) {
    throw new Error(`「${TYPE_KEYWORD}」を含む項目が ${typeItems.length} 件あります。listItems で確認し TYPE_KEYWORD を絞ってください。`);
  }
  if (anchors.length !== 1) {
    throw new Error(`「${ANCHOR_KEYWORD}」を含む項目が ${anchors.length} 件あります。listItems で確認し ANCHOR_KEYWORD を絞ってください。`);
  }

  const typeItem = typeItems[0];
  const anchorIndex = anchors[0].getIndex();
  const fromIndex = typeItem.getIndex();
  // 前方から後方へ移動する場合は、自身が抜けた分インデックスが1つずれる
  const toIndex = fromIndex < anchorIndex ? anchorIndex - 1 : anchorIndex;

  form.moveItem(fromIndex, toIndex);
  Logger.log(`「${typeItem.getTitle()}」を ${fromIndex} → ${toIndex} に移動しました。`);
  listItems();
}
