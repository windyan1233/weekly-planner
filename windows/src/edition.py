"""发布版标记。

``tools/build_release.py`` 在打包「自定义分类版」前会把这里改成 ``True``，
打包「原版」前改回 ``False``。程序内只用来决定是否显示支出分类的编辑入口，
两种版本的数据结构完全相同（六个默认分类始终存在）。
"""

EDITABLE_CATEGORIES = False


def editable_categories() -> bool:
    return bool(EDITABLE_CATEGORIES)
