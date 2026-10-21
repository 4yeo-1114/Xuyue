# -*- coding: utf-8 -*-
"""留痕图定期清理单测——1016 不花钱项②。

验证：①过期 marks_only_/annotated_ 删掉且计字节 ②新图留着
③original_/上传件/记录/其他文件一律不碰 ④保留天数 0=关闭 ⑤只认图片后缀。
"""
import os
import time

import pytest

from app.services import marks_cleanup


@pytest.fixture()
def fake_tree(tmp_path, monkeypatch):
    """伪造 grading_data_all/grading_data_u1/{modify,home_img} 目录树。"""
    root = tmp_path / "grading_data_all"
    for sub in ("modify", "home_img"):
        d = root / "grading_data_u1" / sub
        d.mkdir(parents=True)
    monkeypatch.setattr(
        "app.grading.user_paths.grading_data_all_root", lambda: root
    )
    return root


def _touch(path, size=1024, age_days=0):
    path.write_bytes(b"x" * size)
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
    return path


def test_expired_marks_images_removed_and_bytes_counted(fake_tree):
    mod = fake_tree / "grading_data_u1" / "modify"
    old_mark = _touch(mod / "marks_only_张三_1.jpg", size=2048, age_days=120)
    old_ann = _touch(mod / "annotated_张三_1.jpg", size=4096, age_days=120)
    home = fake_tree / "grading_data_u1" / "home_img"
    old_home = _touch(home / "marks_only_essay_李四.png", size=1024, age_days=100)

    r = marks_cleanup.cleanup_old_marks_images(older_than_days=90)
    assert r["removed"] == 3
    assert r["freed_bytes"] == 2048 + 4096 + 1024
    assert not old_mark.exists() and not old_ann.exists() and not old_home.exists()
    assert r["errors"] == 0


def test_recent_images_kept(fake_tree):
    mod = fake_tree / "grading_data_u1" / "modify"
    fresh = _touch(mod / "marks_only_王五_1.jpg", size=2048, age_days=10)
    r = marks_cleanup.cleanup_old_marks_images(older_than_days=90)
    assert r["removed"] == 0
    assert fresh.exists()


def test_untouchable_files_survive(fake_tree):
    """原卷 original_*、上传件、记录 JSON、非目标前缀、非图片后缀都不能删。"""
    mod = fake_tree / "grading_data_u1" / "modify"
    keepers = [
        _touch(mod / "original_张三_1.jpg", size=512, age_days=200),
        _touch(mod / "ref_cls1_张三_1.jpg", size=512, age_days=200),
        _touch(mod / "marks_only_张三_1.jpg.txt", size=512, age_days=200),
        _touch(mod / "grading_history.json", size=512, age_days=200),
    ]
    test_dir = fake_tree / "grading_data_u1" / "test"
    test_dir.mkdir()
    upload = _touch(test_dir / "marks_only_不该扫到.jpg", size=512, age_days=200)

    r = marks_cleanup.cleanup_old_marks_images(older_than_days=90)
    assert r["removed"] == 0
    for k in keepers:
        assert k.exists(), f"{k.name} 不能删"
    assert upload.exists(), "test/ 不在清理范围"


def test_retention_zero_disables(fake_tree):
    mod = fake_tree / "grading_data_u1" / "modify"
    _touch(mod / "marks_only_x.jpg", size=512, age_days=200)
    r = marks_cleanup.cleanup_old_marks_images(older_than_days=0)
    assert r["removed"] == 0
    assert (mod / "marks_only_x.jpg").exists()


def test_retention_days_from_env(monkeypatch):
    monkeypatch.setenv("MARKS_IMAGE_RETENTION_DAYS", "30")
    assert marks_cleanup.retention_days() == 30
    monkeypatch.setenv("MARKS_IMAGE_RETENTION_DAYS", "0")
    assert marks_cleanup.retention_days() == 0
    monkeypatch.setenv("MARKS_IMAGE_RETENTION_DAYS", "abc")
    assert marks_cleanup.retention_days() == 0
    monkeypatch.delenv("MARKS_IMAGE_RETENTION_DAYS")
    assert marks_cleanup.retention_days() == 90, "默认保留 90 天"


def test_cleanup_loop_wired_in_main():
    """防回归：main 启动段必须挂上清理线程。"""
    import inspect

    from app import main

    assert "marks_cleanup" in inspect.getsource(main), "main 启动段必须引用 marks_cleanup"
