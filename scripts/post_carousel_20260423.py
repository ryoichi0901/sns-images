"""
2026-04-23 カルーセル投稿スクリプト
7枚の画像をCloudinaryへアップロードしてからInstagramにカルーセル投稿する。
"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.post_agent import upload_to_cloudinary, publish_carousel_to_instagram

CLOUD_NAME = "dw6iu8dn9"
API_KEY = "751867497883922"
API_SECRET = "KfUBWeGm1gIzWEHpjATc_Gvqb3w"

IG_USER_ID = "17841433555586625"
ACCESS_TOKEN = (
    "EAAXN41AOpWsBRAcrQ3Any2j6p6aRchhStQFOeaUxaJZBZC6pp5QwNJ3bQf5WpfRLbqzJmC0ZBJ29fUWfPpasVxuVBl8V8PJKRrxFcDFAPaJ5mgdZAfF3r2rQzKjKV1CHh05ZAoW3KzCRJLh0mOs9ZBYIt74RYEjADOKCXMji71fgKVg6S5pKFxiylgQ72O1tqH"
)

IMAGES_DIR = PROJECT_ROOT / "images"
IMAGE_FILES = [
    IMAGES_DIR / "post_20260423_slide1.jpg",
    IMAGES_DIR / "post_20260423_slide2.jpg",
    IMAGES_DIR / "post_20260423_slide3.jpg",
    IMAGES_DIR / "post_20260423_slide4.jpg",
    IMAGES_DIR / "post_20260423_slide5.jpg",
    IMAGES_DIR / "post_20260423_slide6.jpg",
    IMAGES_DIR / "post_20260423_slide7.jpg",
]

CAPTION = """AI副業って危ない？全部、誤解でした😅

銀行員として20年、毎日お客様のお金の相談を受けてきた私が正直に言います。

「AI副業は怪しい」「詐欺が多い」「稼げるのは一部の人だけ」

…これ、全部間違いだったんです。

私も最初は怖かった。でも実際に試してみて気づいたこと、体験談としてまとめました。

今から始めても全然遅くないし、ハードルは思ってたより全然低かったです。

詳細はプロフィールリンクから👇

#AI副業 #資産形成 #副業収入 #金融リテラシー #元銀行員"""


def main() -> None:
    # 全ファイルの存在確認
    for path in IMAGE_FILES:
        if not path.exists():
            raise FileNotFoundError(f"画像ファイルが見つかりません: {path}")

    print(f"[main] {len(IMAGE_FILES)}枚の画像をCloudinaryにアップロードします...")
    image_urls: list[str] = []
    for i, image_path in enumerate(IMAGE_FILES, 1):
        print(f"[main] スライド{i} アップロード中: {image_path.name}")
        url = upload_to_cloudinary(image_path, CLOUD_NAME, API_KEY, API_SECRET)
        image_urls.append(url)

    print(f"\n[main] Cloudinaryアップロード完了。カルーセル投稿を開始します...")
    post_id = publish_carousel_to_instagram(image_urls, CAPTION, IG_USER_ID, ACCESS_TOKEN)
    print(f"\n[main] 投稿成功。投稿ID: {post_id}")


if __name__ == "__main__":
    main()
