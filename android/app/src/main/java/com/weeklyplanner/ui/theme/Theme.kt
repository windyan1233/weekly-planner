package com.weeklyplanner.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val LightColors = lightColorScheme(
    primary = Color(0xFF4F6BED),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFDFE5FF),
    onPrimaryContainer = Color(0xFF12235C),
    secondary = Color(0xFF5B6B8C),
    onSecondary = Color.White,
    background = Color(0xFFF6F7FB),
    surface = Color.White,
    surfaceVariant = Color(0xFFEDEFF7),
    onSurfaceVariant = Color(0xFF5A6173),
    outline = Color(0xFFD5D9E6),
    error = Color(0xFFC0392B)
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF9DB1FF),
    onPrimary = Color(0xFF12235C),
    primaryContainer = Color(0xFF2A3A6E),
    onPrimaryContainer = Color(0xFFDFE5FF),
    secondary = Color(0xFFAFB9D4),
    background = Color(0xFF10131A),
    surface = Color(0xFF181C25),
    surfaceVariant = Color(0xFF232936),
    onSurfaceVariant = Color(0xFFB6BDCD),
    outline = Color(0xFF3A4152),
    error = Color(0xFFFFB4AB)
)

@Composable
fun WeeklyTheme(theme: String, content: @Composable () -> Unit) {
    val dark = when (theme) {
        "dark" -> true
        "light" -> false
        else -> isSystemInDarkTheme()
    }
    val colors = if (dark) DarkColors else LightColors
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = Color.Transparent.toArgb()
            window.navigationBarColor = Color.Transparent.toArgb()
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = !dark
                isAppearanceLightNavigationBars = !dark
            }
        }
    }
    MaterialTheme(colorScheme = colors, typography = Typography(), content = content)
}
