package com.weeklyplanner.domain

import java.math.BigDecimal
import java.math.RoundingMode
import java.text.DecimalFormat

/** 金额统一用「分」存整数，避免浮点误差。 */
object Money {
    private val allowed = Regex("""^\d{1,9}(\.\d{1,2})?$""")

    fun parseToCents(input: String): Long? {
        val text = input.trim()
            .replace("¥", "")
            .replace("￥", "")
            .replace(",", "")
            .replace("，", "")
        if (!allowed.matches(text)) return null
        return try {
            BigDecimal(text).movePointRight(2).setScale(0, RoundingMode.HALF_UP).longValueExact()
        } catch (e: ArithmeticException) {
            null
        }
    }

    fun format(cents: Long): String {
        val formatter = DecimalFormat("#,##0.00")
        val value = BigDecimal(cents).movePointLeft(2)
        return "¥" + formatter.format(value)
    }

    fun formatPlain(cents: Long): String {
        return BigDecimal(cents).movePointLeft(2).setScale(2, RoundingMode.HALF_UP).toPlainString()
    }

    fun formatSigned(cents: Long): String = (if (cents >= 0) "+" else "-") + format(Math.abs(cents))
}
