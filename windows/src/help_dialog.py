"""内置使用说明与课表导出说明。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

HELP_TABS: list[tuple[str, str]] = [
    (
        "快速开始",
        """
        <h2>快速开始</h2>
        <p>一周日程把「日程」和「记账」放在同一个窗口，数据都保存在本机。</p>
        <h3>新建任务</h3>
        <ol>
          <li>点右上角「新建任务」。</li>
          <li>填名称，选分类和优先级。</li>
          <li>「计划时间」可以加一个或多个，每个都会单独提醒。</li>
          <li>「截止时间」用于截止前一天提醒。</li>
          <li>保存。</li>
        </ol>
        <h3>看日程</h3>
        <ul>
          <li>默认周视图，左侧是时间轴，课程显示为背景块。</li>
          <li>点任务可以完成、编辑、删除。</li>
          <li>上方可以按分类、状态、优先级筛选，也可以搜索。</li>
        </ul>
        <h3>提醒</h3>
        <ul>
          <li>计划时间：默认提前 10 分钟，可在设置里改。</li>
          <li>截止时间：默认前一天提醒，时间可改。</li>
          <li>程序最小化到托盘后，提醒仍由后台调度器执行。</li>
        </ul>
        """,
    ),
    (
        "日程与提醒",
        """
        <h2>日程与提醒</h2>
        <h3>一个任务多个计划时间</h3>
        <p>同一个任务可以有几个「准备/出发/开始」时间，每个时间独立提醒，不会互相覆盖。</p>
        <h3>截止时间</h3>
        <p>截止时间只用于「截止前一天」的提醒；它不会自动把任务标成完成。</p>
        <h3>稍后提醒</h3>
        <p>提醒弹出后可以选「稍后提醒」，稍后再次弹出；错过的提醒会在下次启动时补发。</p>
        <h3>托盘与开机启动</h3>
        <ul>
          <li>关闭窗口默认最小化到托盘，不退出。</li>
          <li>设置里可以打开「开机启动」；如果没有反应，检查托盘菜单或重新登录 Windows。</li>
          <li>不要从聊天窗口/文件卡片里直接点 exe，那种方式可能没有写权限。</li>
        </ul>
        """,
    ),
    (
        "课表导入 / 导出",
        """
        <h2>课表导入 / 导出</h2>
        <h3>导入</h3>
        <ol>
          <li>点「导入课表」。</li>
          <li>支持 <code>.xls</code>、<code>.xlsx</code>、<code>.csv</code>、文字版 <code>.pdf</code>，也可以「从文本粘贴」。</li>
          <li>选「使用课表时间」或「自定义每节时间」。</li>
          <li>填第 1 周星期一，预览后导入。</li>
        </ol>
        <h3>从教务系统导出：有「导出」键</h3>
        <ol>
          <li>用电脑浏览器登录教务系统，打开「课表查询」。</li>
          <li>点「导出 / 输出 / 下载」，格式优先 <code>.xlsx</code>，其次 <code>.xls</code>、<code>.csv</code>。</li>
          <li>不要选图片或扫描 PDF；文字版 PDF 也可以。</li>
          <li>打开导出的文件，确认有「星期一…星期日」或「课程名称/星期/节次」表头。</li>
        </ol>
        <h3>导出键叫「打印」怎么办</h3>
        <ul>
          <li><b>打印预览能选中文字</b>：拖选表格 → <code>Ctrl+C</code> → 粘到 Excel → 另存为 <code>.xlsx</code>；或直接用本程序的「从文本粘贴」。</li>
          <li><b>只能打印成 PDF</b>：打印机选「Microsoft Print to PDF」，保存后直接导入；失败就用「从文本粘贴」。</li>
          <li><b>打印出来是图片/扫描件</b>：程序不能识别，需要先 OCR，或按模板手工录入。</li>
        </ul>
        <h3>从本程序导出</h3>
        <p>目前没有单独的「导出课表」按钮。设置 → 数据 → 导出 JSON，会导出包含课程、任务、记账在内的全部数据。</p>
        <p>只想保存课表时，建议同时保留教务系统导出的原始 Excel。</p>
        """,
    ),
    (
        "记账",
        """
        <h2>记账</h2>
        <h3>记一笔</h3>
        <ol>
          <li>点「记一笔支出」或「记一笔收入」。</li>
          <li>填金额，选分类和资金分区。</li>
          <li>日期默认今天，可以改。</li>
          <li>保存。</li>
        </ol>
        <h3>资金分区与转账</h3>
        <ul>
          <li>资金分区用来区分饭卡、生活费、现金等。</li>
          <li>「资金调动」是分区之间转账，不计入收入/支出。</li>
          <li>所有分区余额之和 = 当前总余额。</li>
        </ul>
        <h3>分类</h3>
        <p>默认六类：吃饭、生活、文具、游戏、周边、科技。自定义分类版可以新增、改名、隐藏分类；原版固定六类。</p>
        <h3>月报与结转</h3>
        <ul>
          <li>月报按真实账目自动生成，分类合计 = 本月总支出。</li>
          <li>月末余额会自动结转到下月，不需要手工改初始余额。</li>
        </ul>
        """,
    ),
    (
        "数据与备份",
        """
        <h2>数据与备份</h2>
        <h3>数据在哪</h3>
        <ul>
          <li>数据库：<code>%APPDATA%\\WeeklyPlanner\\planner.db</code>、<code>finance.db</code>。</li>
          <li>卸载程序不会删除数据；重装后仍会读取原数据。</li>
          <li>数据是明文 SQLite，备份文件请自己保管。</li>
        </ul>
        <h3>备份 / 恢复</h3>
        <ol>
          <li>设置 → 数据 → 导出 JSON。</li>
          <li>恢复时选「导入 JSON」，会整体替换当前的任务、账目和月报。</li>
          <li>导入前建议先导出一份当前备份。</li>
        </ol>
        <h3>与 Android 互通</h3>
        <p>两端使用同一套 JSON 格式，手动导出/导入即可；没有自动同步，也不会上传服务器。</p>
        <h3>隐私</h3>
        <p>程序不联网、不需要账号、不收集数据。Windows 包目前未做商业代码签名，SmartScreen 可能提示「未知发布者」。</p>
        """,
    ),
]


class HelpDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("使用说明")
        self.setModal(True)
        self.resize(760, 680)

        palette = self.palette()
        text_color = palette.color(QPalette.ColorRole.WindowText).name()
        muted_color = palette.color(QPalette.ColorRole.PlaceholderText).name()
        code_bg = palette.color(QPalette.ColorRole.AlternateBase).name()

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 14)
        root.setSpacing(10)

        title = QLabel("使用说明")
        title.setObjectName("Title")
        root.addWidget(title)
        subtitle = QLabel("日程、提醒、课表导入/导出、记账、备份；断网也能看。")
        subtitle.setStyleSheet(f"color: {muted_color};")
        root.addWidget(subtitle)

        tabs = QTabWidget()
        for name, body in HELP_TABS:
            browser = QTextBrowser()
            browser.setOpenExternalLinks(False)
            browser.setFrameShape(QFrame.Shape.NoFrame)
            browser.setStyleSheet("QTextBrowser { background: transparent; border: none; }")
            browser.document().setDocumentMargin(10)
            browser.setHtml(
                f"""
                <style>
                  body {{ color: {text_color}; font-size: 14px; line-height: 1.65; }}
                  h2 {{ font-size: 19px; margin: 0 0 10px 0; }}
                  h3 {{ font-size: 15px; margin: 16px 0 6px 0; }}
                  p, li {{ color: {text_color}; }}
                  ul, ol {{ margin: 4px 0 8px 18px; padding: 0; }}
                  code {{ background: {code_bg}; padding: 1px 4px; }}
                  b {{ color: {text_color}; }}
                </style>
                {body}
                """
            )
            tabs.addTab(browser, name)
        root.addWidget(tabs, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close_button = QPushButton("关闭")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        root.addLayout(footer)
