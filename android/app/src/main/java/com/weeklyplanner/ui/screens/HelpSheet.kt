package com.weeklyplanner.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

private data class HelpSection(
    val title: String,
    val paragraphs: List<String>
)

private val helpSections = listOf(
    HelpSection(
        "快速开始",
        listOf(
            "新建任务：点右下角「新建任务」，填名称，选分类和优先级。",
            "计划时间：可以只填开始，也可以设结束；开始/结束提醒可各自开关（开始默认提前 10 分钟）。",
            "截止时间：打开「截止时间」开关，程序会在截止前一天提醒。",
            "看日程：默认周视图，左右滑动切换上一周/下一周；想用列表去「我的 → 日程视图」。"
        )
    ),
    HelpSection(
        "日程与提醒",
        listOf(
            "一个任务多个计划时间：每个时间独立提醒，不会互相覆盖。",
            "截止时间只负责「截止前一天」提醒，不会自动把任务标成完成。",
            "提醒弹出后可以「稍后提醒」；错过的提醒会在下次打开时补发。",
            "Android 12 及以上建议允许「闹钟和提醒」，否则提醒可能延迟。"
        )
    ),
    HelpSection(
        "课表导入 / 导出",
        listOf(
            "导入：我的 → 课表 → 导入课表，支持 .xls / .xlsx / .csv；不支持 PDF。",
            "有「导出」键：用电脑登录教务系统 → 课表查询 → 导出，格式优先 xlsx，其次 xls / csv。",
            "只有「打印」键：如果打印预览能选中文字，拖选表格复制到 Excel，另存为 xlsx。",
            "只能打印成 PDF：Android 不能直接导入 PDF，需要先在电脑上转成 xlsx / csv。",
            "打印成图片/扫描件：程序不能识别，需要 OCR 或按模板手工录入。",
            "本程序目前没有单独的「导出课表」按钮；「我的 → 数据 → 导出备份」会导出含课程在内的 JSON 全量数据。"
        )
    ),
    HelpSection(
        "记账",
        listOf(
            "记一笔：点「记一笔支出/收入」，填金额、分类、资金分区和日期。",
            "资金分区：饭卡、生活费分开记；「资金调动」是分区之间转账，不计收支。",
            "分类：默认六类，可在「我的 → 支出分类」改名、新增或删除。",
            "月报：按真实账目自动生成，分类合计 = 本月总支出；月末余额自动结转到下月。"
        )
    ),
    HelpSection(
        "备份与隐私",
        listOf(
            "数据只在本机（Room 数据库），不联网、不需要账号。",
            "备份：我的 → 数据 → 导出备份，生成 JSON；恢复会整体替换当前数据。",
            "两端互通：Windows 和 Android 用同一套 JSON 手动导入/导出，没有自动同步。",
            "卸载应用通常会删除应用私有目录里的数据，换机前先导出备份。"
        )
    )
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HelpSheet(onDismiss: () -> Unit) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 28.dp)
        ) {
            Text(
                "使用说明",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(4.dp))
            Text(
                "日程、提醒、课表导入/导出、记账、备份；断网也能看。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(Modifier.height(14.dp))

            helpSections.forEachIndexed { index, section ->
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f),
                    shape = MaterialTheme.shapes.large,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(Modifier.padding(14.dp)) {
                        Text(
                            section.title,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                        Spacer(Modifier.height(6.dp))
                        section.paragraphs.forEach { paragraph ->
                            Text(
                                "· $paragraph",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(Modifier.height(5.dp))
                        }
                    }
                }
                if (index != helpSections.lastIndex) {
                    Spacer(Modifier.height(10.dp))
                }
            }

            Spacer(Modifier.height(16.dp))
            HorizontalDivider()
            Spacer(Modifier.height(12.dp))
            Text(
                "完整图文说明在仓库 docs/ 目录；Release 里也有 PDF。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}
