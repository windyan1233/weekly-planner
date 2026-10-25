package com.weeklyplanner.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CategoriesTest {
    @Test
    fun encode_decode_roundtrip() {
        val custom = listOf(
            Category("food", "吃饭", 0xFFE57373),
            Category("custom_1", "奶茶", 0xFF64B5F6)
        )
        val decoded = Categories.decode(Categories.encode(custom))
        assertEquals(custom, decoded)
    }

    @Test
    fun blank_uses_defaults() {
        assertEquals(Categories.defaults, Categories.decode(""))
        assertEquals(Categories.defaults, Categories.decode(null))
    }

    @Test
    fun unknown_key_falls_back_to_other() {
        assertEquals("其他", Categories.label("missing", Categories.defaults))
        assertEquals("其他", Categories.category("missing", Categories.defaults).label)
    }

    @Test
    fun custom_label_is_used() {
        val custom = Categories.defaults + Category("custom_1", "奶茶", 0xFF64B5F6)
        assertEquals("奶茶", Categories.label("custom_1", custom))
        assertTrue(custom.any { it.key == "custom_1" })
    }
}
