"""「作者的话」弹窗：关于页面的作者自述。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# TODO: windyan1233@qq.com
AUTHOR_EMAIL = "windyan1233@qq.com"

AUTHOR_NOTE = (
    "大家好，我是这个项目的作者，目前是一名大一新生。",
    "您点开这个项目时，可能会发现代码有些稚嫩，甚至带有明显的 AI 痕迹。没错，这个“日程 + 记账”二合一的小软件，是我全程借助 AI（dsh）辅助开发出来的。",
    "我的最初就是想做个软件供自己用，顺便学习使用 AI，做出来发现效果还不错，所以想分享出来。我甚至不是计算机专业的学生，而是一个被誉为天坑的药学生。可能有人问我会转专业吗？不会，我现在还是挺喜欢这个专业的。不过这也让我看到了一种可能，那就是 AI 时代，普通人也可以凭自己喜好创作了。我也有点期待未来 AI 的发展了。",
    "我实在是没有扎实的代码基础，但我能保证的是：",
    "这个软件完全免费、无广告、不联网（数据全在本地，不收集任何隐私）。",
    "如果您在使用中遇到闪退或 Bug，我会尽我所能，把错误信息喂给 AI，让它帮我一起修复。我就是扮演纯包工头的角色来了，不过我也会进行学习，多个手艺多个路嘛。",
    "欢迎各位前辈、大佬多提 Issue 和优化建议，我会虚心学习。如果实在是不喜欢我这种做法，请不要骂我，您提的所有建议我都会看，并学习改正的。",
)


class AuthorNoteDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("作者的话")
        self.setModal(True)
        self.resize(600, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        title = QLabel("作者的话")
        title.setObjectName("Title")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 8, 0)
        body_layout.setSpacing(10)
        for paragraph in AUTHOR_NOTE:
            label = QLabel(paragraph)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            body_layout.addWidget(label)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        email = QLabel(f"联系邮箱：{AUTHOR_EMAIL}")
        email.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        footer.addWidget(email, 1)

        copy_button = QPushButton("复制邮箱")
        copy_button.setCursor(Qt.CursorShape.PointingHandCursor)

        def copy_email() -> None:
            QApplication.clipboard().setText(AUTHOR_EMAIL)
            copy_button.setText("已复制")

        copy_button.clicked.connect(copy_email)
        footer.addWidget(copy_button)

        close_button = QPushButton("关闭")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        root.addLayout(footer)
