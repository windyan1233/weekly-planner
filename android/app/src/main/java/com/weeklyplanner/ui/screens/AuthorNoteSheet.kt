package com.weeklyplanner.ui.screens

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// TODO: windyan1233@qq.com
private const val AUTHOR_EMAIL = "windyan1233@qq.com"

private val paragraphs = listOf(
    "大家好，我是这个项目的作者，目前是一名大一新生。",
    "您点开这个项目时，可能会发现代码有些稚嫩，甚至带有明显的 AI 痕迹。没错，这个“日程 + 记账”二合一的小软件，是我全程借助 AI（dsh）辅助开发出来的。",
    "我的最初就是想做个软件供自己用，顺便学习使用 AI，做出来发现效果还不错，所以想分享出来。我甚至不是计算机专业的学生，而是一个被誉为天坑的药学生。可能有人问我会转专业吗？不会，我现在还是挺喜欢这个专业的。不过这也让我看到了一种可能，那就是 AI 时代，普通人也可以凭自己喜好创作了。我也有点期待未来 AI 的发展了。",
    "我实在是没有扎实的代码基础，但我能保证的是：",
    "这个软件完全免费、无广告、不联网（数据全在本地，不收集任何隐私）。",
    "如果您在使用中遇到闪退或 Bug，我会尽我所能，把错误信息喂给 AI，让它帮我一起修复。我就是扮演纯包工头的角色来了，不过我也会进行学习，多个手艺多个路嘛。",
    "欢迎各位前辈、大佬多提 Issue 和优化建议，我会虚心学习。如果实在是不喜欢我这种做法，请不要骂我，您提的所有建议我都会看，并学习改正的。"
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AuthorNoteSheet(onDismiss: () -> Unit) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val context = LocalContext.current
    var copied by remember { mutableStateOf(false) }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp)
                .padding(bottom = 28.dp)
        ) {
            Text("作者的话", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(14.dp))

            SelectionContainer {
                Column {
                    paragraphs.forEach { paragraph ->
                        Text(
                            paragraph,
                            style = MaterialTheme.typography.bodyMedium,
                            lineHeight = 23.sp,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        Spacer(Modifier.height(10.dp))
                    }
                }
            }

            Spacer(Modifier.height(4.dp))
            Text(
                "联系邮箱：$AUTHOR_EMAIL",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(Modifier.height(10.dp))
            OutlinedButton(onClick = {
                val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("作者邮箱", AUTHOR_EMAIL))
                copied = true
            }) {
                Text(if (copied) "已复制邮箱" else "复制邮箱")
            }
            Spacer(Modifier.height(6.dp))
            Text(
                "感谢你愿意花时间了解这个小项目。",
                style = MaterialTheme.typography.bodySmall,
                color = Color(0xFF8A8F9C)
            )
        }
    }
}
