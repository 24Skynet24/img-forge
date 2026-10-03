"""Dialog asked when the destination already contains an item with the same name."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.saver import ConflictAction


class ConflictDialog(QDialog):
    """Overwrite / Rename / Skip, optionally for every further conflict of the same kind."""

    def __init__(self, path: Path, is_folder: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Файл уже существует" if not is_folder else "Папка уже существует")
        self.setModal(True)
        self.action = ConflictAction.SKIP  # closing the dialog = skip
        kind = "Папка" if is_folder else "Файл"
        text = QLabel(
            f"{kind} «{path.name}» уже есть в выбранном месте.\n{path.parent}\n\nЧто сделать?"
        )
        text.setWordWrap(True)
        overwrite = QPushButton("Перезаписать")
        overwrite.setToolTip(
            "Файлы с одинаковыми именами будут заменены, остальное содержимое папки останется"
            if is_folder
            else "Существующий файл будет заменён"
        )
        rename = QPushButton("Переименовать (_1)")
        rename.setToolTip("Сохранить рядом под новым именем, добавив суффикс _1, _2, …")
        skip = QPushButton("Пропустить")
        skip.setDefault(True)
        self._all = QCheckBox("Применить ко всем следующим")
        for button, action in (
            (overwrite, ConflictAction.OVERWRITE),
            (rename, ConflictAction.RENAME),
            (skip, ConflictAction.SKIP),
        ):
            button.clicked.connect(lambda _=False, a=action: self._choose(a))
        row = QHBoxLayout()
        row.addStretch()
        for button in (overwrite, rename, skip):
            row.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(self._all)
        layout.addLayout(row)
        self.setMinimumWidth(460)

    @property
    def apply_to_all(self) -> bool:
        return self._all.isChecked()

    def _choose(self, action: ConflictAction) -> None:
        self.action = action
        self.accept()
