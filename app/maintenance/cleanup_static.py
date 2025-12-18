from pathlib import Path
import shutil

from app.config.constants import BASE_DIR
from app import models
from app.database import SessionLocal


def cleanup_covers(dry_run: bool = True) -> None:
    """
    清理 /static/uploads/covers 目录下未被数据库引用的封面图片。

    通过对比文件名是否出现在 Game.image_url / Resource.cover_image 中来判断是否为孤立文件。
    """
    covers_dir = BASE_DIR / "app" / "static" / "uploads" / "covers"
    if not covers_dir.exists():
        print("[covers] 目录不存在，跳过")
        return

    db = SessionLocal()
    try:
        used_paths = set()

        # 收集游戏封面
        for (url,) in db.query(models.Game.image_url).filter(models.Game.image_url.isnot(None)):
            used_paths.add(url)

        # 收集资源封面
        for (url,) in db.query(models.Resource.cover_image).filter(models.Resource.cover_image.isnot(None)):
            used_paths.add(url)

        used_filenames = {
            Path(p).name
            for p in used_paths
            if isinstance(p, str) and p.startswith("/static/uploads/covers/")
        }

        total = 0
        deletable = 0

        for file in covers_dir.iterdir():
            if not file.is_file():
                continue
            total += 1
            if file.name not in used_filenames:
                deletable += 1
                print(f"[covers] Orphan file: {file}")
                if not dry_run:
                    try:
                        file.unlink()
                    except Exception as exc:
                        print(f"[covers] 删除失败: {file} ({exc})")

        print(f"[covers] 共扫描 {total} 个文件，可删除 {deletable} 个孤立封面（dry_run={dry_run}）。")
    finally:
        db.close()


def cleanup_article_statics(dry_run: bool = True) -> None:
    """
    清理 /static/articles 下未被任何 Article.slug 引用的静态目录。
    """
    articles_root = BASE_DIR / "app" / "static" / "articles"
    if not articles_root.exists():
        print("[articles] 目录不存在，跳过")
        return

    db = SessionLocal()
    try:
        alive_slugs = {slug for (slug,) in db.query(models.Article.slug).all()}

        total = 0
        deletable = 0

        for sub in articles_root.iterdir():
            if not sub.is_dir():
                continue
            total += 1
            slug = sub.name
            if slug not in alive_slugs:
                deletable += 1
                print(f"[articles] Orphan static dir: {sub}")
                if not dry_run:
                    try:
                        shutil.rmtree(sub)
                    except Exception as exc:
                        print(f"[articles] 删除失败: {sub} ({exc})")

        print(f"[articles] 共扫描 {total} 个静态目录，可删除 {deletable} 个孤立目录（dry_run={dry_run}）。")
    finally:
        db.close()


if __name__ == "__main__":
    # 默认使用 dry_run 模式，先观察输出结果是否符合预期。
    cleanup_covers(dry_run=True)
    cleanup_article_statics(dry_run=True)


