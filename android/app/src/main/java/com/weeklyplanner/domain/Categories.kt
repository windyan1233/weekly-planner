package com.weeklyplanner.domain

/** 支出分类：key 稳定不变，改的只是显示名和颜色。 */
data class Category(val key: String, val label: String, val argb: Long)

object Categories {
    val defaults = listOf(
        Category("food", "吃饭", 0xFFE57373),
        Category("life", "生活", 0xFF64B5F6),
        Category("stationery", "文具", 0xFF81C784),
        Category("game", "游戏", 0xFFFFB74D),
        Category("merch", "周边", 0xFFBA68C8),
        Category("tech", "科技", 0xFF4DB6AC)
    )

    /** 兼容旧代码的默认列表。 */
    val all: List<Category> get() = defaults

    fun label(key: String, list: List<Category> = defaults): String =
        list.firstOrNull { it.key == key }?.label ?: "其他"

    fun category(key: String, list: List<Category> = defaults): Category =
        list.firstOrNull { it.key == key } ?: Category("other", "其他", 0xFF90A4AE)

    fun encode(list: List<Category>): String =
        list.joinToString("\n") { "${it.key}|${it.label}|${it.argb}" }

    fun decode(raw: String?): List<Category> {
        if (raw.isNullOrBlank()) return defaults
        val parsed = raw.lines().mapNotNull { line ->
            val parts = line.split('|', limit = 3)
            if (parts.size != 3 || parts[0].isBlank() || parts[1].isBlank()) return@mapNotNull null
            Category(parts[0].trim(), parts[1].trim(), parts[2].trim().toLongOrNull() ?: 0xFF90A4AE)
        }
        return parsed.ifEmpty { defaults }
    }
}
