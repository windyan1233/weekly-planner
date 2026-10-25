package com.weeklyplanner.ui.screens

import androidx.compose.ui.graphics.Color
import org.junit.Assert.assertEquals
import org.junit.Test

class ScheduleLayoutTest {
    private fun block(start: Int, end: Int) = WeekBlock(
        dayIndex = 0,
        startMinutes = start,
        endMinutes = end,
        title = "t",
        subtitle = "",
        color = Color.Red
    )

    @Test
    fun non_overlapping_blocks_stay_at_level_zero() {
        val placed = placeBlocks(listOf(block(600, 660), block(700, 760)))
        assertEquals(listOf(0, 0), placed.map { it.level })
    }

    @Test
    fun overlapping_blocks_get_stacked_levels() {
        val placed = placeBlocks(listOf(block(600, 700), block(650, 720)))
        assertEquals(listOf(0, 1), placed.map { it.level })
    }

    @Test
    fun later_block_reuses_level_after_overlap_ends() {
        val placed = placeBlocks(listOf(block(600, 700), block(650, 720), block(730, 780)))
        assertEquals(listOf(0, 1, 0), placed.map { it.level })
    }
}
