"""
KOTOBA·AI — 用户数据目录统一管理

所有用户可写数据（config / progress / learned_content / wrong_book / vocabulary /
pending_knowledge / knowledge_index / history / output / cache）一律存放于统一数据目录，
默认 %APPDATA%\\KOTOBA-AI，可在设置页更改为任意绝对路径。

自定义目录指针存于默认目录内的 data_dir.txt（无需注册表，卸载/外部工具也能读到）。
get_data_dir() 每次实时解析（不缓存），保证更改后立即生效。
"""

import os
import shutil

APP_NAME = "KOTOBA-AI"
PTR_NAME = "data_dir.txt"          # 自定义目录指针，位于默认目录内

_packaged = None


def is_packaged():
    """MSIX 打包环境检测：GetCurrentPackageFullName 能取到包名即处于商店版沙箱。结果缓存。

    商店版（沙箱重定向 APPDATA）与 GitHub 版（自由路径）共用同一份逻辑，
    仅数据目录自定义能力按 PACK-2 / DIR-1~3 降级。非 Windows 环境恒为 False。
    """
    global _packaged
    if _packaged is None:
        _packaged = _detect_packaged()
    return _packaged


def _detect_packaged():
    try:
        import ctypes
        GetCurrentPackageFullName = ctypes.windll.kernel32.GetCurrentPackageFullName
        GetCurrentPackageFullName.restype = ctypes.c_long
        GetCurrentPackageFullName.argtypes = [
            ctypes.POINTER(ctypes.c_int), ctypes.c_wchar_p,
        ]
        size = ctypes.c_int(0)
        # 传空缓冲：若处于包内，返回 ERROR_INSUFFICIENT_BUFFER 并写入所需长度；
        # 非包内返回 APPMODEL_ERROR_NO_PACKAGE，size 保持 0。
        GetCurrentPackageFullName(ctypes.byref(size), None)
        return size.value > 0
    except Exception:
        return False

# 旧版本遗留数据（相对 cwd 路径），首次启动迁移到数据目录
LEGACY_ITEMS = [
    "config.json", "progress.json", "learned_content.json",
    "wrong_book.json", "vocabulary.json", "pending_knowledge.json",
    "knowledge_index.json", "history", "output", "cache",
]


def get_default_data_dir():
    """固定默认数据目录 %APPDATA%\\KOTOBA-AI（永不只读）。"""
    ap = os.environ.get("APPDATA") or os.path.join(
        os.environ.get("USERPROFILE", ""), "AppData", "Roaming"
    )
    return os.path.join(ap, APP_NAME)


def _ptr_path():
    """自定义目录指针文件路径（固定位于默认目录内）。"""
    return os.path.join(get_default_data_dir(), PTR_NAME)


def get_data_dir():
    """解析当前数据目录：优先读自定义指针，否则用默认。实时解析不缓存。

    打包环境（商店版沙箱）直接返回默认目录，忽略指针（DIR-3：不触发自定义）。"""
    if is_packaged():
        return get_default_data_dir()
    try:
        with open(_ptr_path(), "r", encoding="utf-8") as f:
            p = f.read().strip()
        if p and os.path.isabs(p):
            return p
    except OSError:
        pass
    return get_default_data_dir()


def data_path(*parts):
    """数据目录下的相对路径 → 绝对路径。"""
    return os.path.join(get_data_dir(), *parts)


def resolve(path):
    """相对路径 → 数据目录绝对路径；绝对路径原样返回（如内置只读资源）。"""
    if os.path.isabs(path):
        return path
    return os.path.join(get_data_dir(), path)


def get_data_dir_info():
    """返回 {dir, customized, default, packaged}，供设置页展示 / 判定降级。"""
    d = get_data_dir()
    return {
        "dir": d,
        "customized": d != get_default_data_dir(),
        "default": get_default_data_dir(),
        "packaged": is_packaged(),
    }


def _copy_tree_merge(src, dst):
    """合并复制文件或目录（dst 已存在则跳过），返回复制的文件数。幂等安全。"""
    if not os.path.exists(src):
        return 0
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        count = 0
        for name in os.listdir(src):
            count += _copy_tree_merge(os.path.join(src, name), os.path.join(dst, name))
        return count
    if not os.path.exists(dst):
        try:
            shutil.copy2(src, dst)
            return 1
        except OSError:
            pass
    return 0


def set_data_dir(new_dir, migrate=True):
    """更改数据目录：先把旧目录数据迁移到新目录，再写指针。返回迁移文件数。"""
    if is_packaged():
        raise ValueError("商店版不支持修改数据目录，如需自定义请使用 GitHub 版")
    new_dir = os.path.expanduser((new_dir or "").strip())
    if not os.path.isabs(new_dir):
        raise ValueError("数据目录必须是绝对路径")
    new_dir = os.path.normpath(new_dir)
    old_dir = get_data_dir()
    if os.path.normcase(old_dir) == os.path.normcase(new_dir):
        return 0

    os.makedirs(new_dir, exist_ok=True)
    # 可写性探测，避免指针写了却写不进数据
    probe = os.path.join(new_dir, ".kotoba_write_test")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        raise ValueError(f"目标目录不可写：{e}")

    migrated = 0
    if migrate and os.path.isdir(old_dir):
        for name in os.listdir(old_dir):
            if name == PTR_NAME:
                continue
            migrated += _copy_tree_merge(
                os.path.join(old_dir, name), os.path.join(new_dir, name)
            )
    os.makedirs(get_default_data_dir(), exist_ok=True)
    with open(_ptr_path(), "w", encoding="utf-8") as f:
        f.write(new_dir)
    return migrated


def reset_data_dir():
    """删除自定义指针，回到默认数据目录（不迁移数据）。"""
    try:
        os.remove(_ptr_path())
    except OSError:
        pass


def migrate_legacy_data():
    """首次启动：若数据目录为空，把 cwd 遗留数据复制进去（复制不移动，幂等安全）。"""
    data_dir = get_data_dir()
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    if os.listdir(data_dir):
        return 0  # 已有数据 → 已迁移过，跳过
    n = 0
    for name in LEGACY_ITEMS:
        src = os.path.join(os.getcwd(), name)
        if os.path.exists(src):
            n += _copy_tree_merge(src, os.path.join(data_dir, name))
    return n
