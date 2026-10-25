package com.weeklyplanner

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.weeklyplanner.ui.MainScreen
import com.weeklyplanner.ui.MainViewModel
import com.weeklyplanner.ui.theme.WeeklyTheme

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels { MainViewModel.Factory(application as WeeklyApp) }

    private val permissionLauncher = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleIntent(intent)
        setContent {
            val settings by viewModel.settings.collectAsStateWithLifecycle()
            WeeklyTheme(theme = settings.theme) {
                MainScreen(viewModel)
            }
        }
        requestNotificationPermission()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        val taskId = intent?.getLongExtra(EXTRA_TASK_ID, 0L) ?: 0L
        if (taskId > 0L) {
            viewModel.openTask(taskId)
            intent?.removeExtra(EXTRA_TASK_ID)
        }

        when (intent?.action) {
            Intent.ACTION_VIEW -> intent.data?.let { readExternalJson(it) }
            Intent.ACTION_SEND -> {
                @Suppress("DEPRECATION")
                val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
                if (uri != null) {
                    readExternalJson(uri)
                } else {
                    intent.getStringExtra(Intent.EXTRA_TEXT)
                        ?.takeIf { it.isNotBlank() }
                        ?.let { viewModel.offerImport(it) }
                }
            }
        }
        // 处理完清掉，避免旋转/重建时重复导入
        intent?.action = null
        intent?.data = null
        intent?.removeExtra(Intent.EXTRA_STREAM)
        intent?.removeExtra(Intent.EXTRA_TEXT)
    }

    private fun readExternalJson(uri: Uri) {
        Thread {
            val text = runCatching {
                contentResolver.openInputStream(uri)?.bufferedReader()?.use { reader ->
                    val buffer = CharArray(8192)
                    val builder = StringBuilder()
                    var total = 0
                    while (true) {
                        val read = reader.read(buffer)
                        if (read <= 0) break
                        total += read
                        if (total > MAX_JSON_CHARS) {
                            throw IllegalStateException("文件太大（超过 20 MB）")
                        }
                        builder.append(buffer, 0, read)
                    }
                    builder.toString()
                }
            }.getOrElse { error ->
                runOnUiThread {
                    Toast.makeText(this, "读取文件失败：${error.message}", Toast.LENGTH_LONG).show()
                }
                null
            }
            if (text != null) {
                Handler(Looper.getMainLooper()).post {
                    if (text.isBlank()) {
                        Toast.makeText(this, "文件是空的", Toast.LENGTH_LONG).show()
                    } else {
                        viewModel.offerImport(text)
                    }
                }
            }
        }.start()
    }

    private fun requestNotificationPermission() {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    companion object {
        const val EXTRA_TASK_ID = "task_id"
        private const val MAX_JSON_CHARS = 20 * 1024 * 1024
    }
}
