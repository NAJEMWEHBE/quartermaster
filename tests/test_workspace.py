# -*- coding: utf-8 -*-
"""Atomic writes: the new file is on disk before it replaces the old one, and it keeps
normal file permissions."""
import os
import stat
import sys

import pytest

from quartermaster import workspace


def test_the_bytes_reach_the_disk_before_the_swap(tmp_path, monkeypatch):
    """After a power loss NTFS/ext4 can keep the rename but lose unsynced data,
    leaving an empty catalog; fsync before os.replace closes that window."""
    order = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(workspace.os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(workspace.os, "replace", lambda a, b: (order.append("replace"), real_replace(a, b))[1])
    workspace.write_text(tmp_path / "a.txt", "hello")
    assert order == ["fsync", "replace"]
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_written_files_get_the_usual_permissions_not_owner_only(tmp_path):
    umask = os.umask(0o022)
    try:
        workspace.write_text(tmp_path / "a.txt", "x")
    finally:
        os.umask(umask)
    assert stat.S_IMODE(os.stat(tmp_path / "a.txt").st_mode) == 0o644
