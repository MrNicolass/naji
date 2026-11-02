"""Settings dialog for the tray-first desktop application."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from naji.config import DEFAULT_INSTRUCTIONS, Config
from naji.i18n import Translator
from naji.ui.theme.tokens import SPACE


class SettingsDialog(QDialog):
    """Edit settings that can be safely applied while Naji is running."""

    saved = Signal()

    def __init__(
        self,
        config: Config,
        translator: Translator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._t = translator
        self.setWindowTitle(self._t.t("settings.title"))
        self.setModal(False)
        self.setMinimumWidth(SPACE["xxl"] * 15)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE["xl"], SPACE["xl"], SPACE["xl"], SPACE["xl"])
        layout.setSpacing(SPACE["lg"])

        description = QLabel(self._t.t("settings.description"), self)
        description.setWordWrap(True)
        description.setProperty("role", "secondary")
        layout.addWidget(description)

        form = QFormLayout()
        form.setSpacing(SPACE["md"])

        self._theme = QComboBox(self)
        self._add_options(
            self._theme,
            (
                ("system", "settings.theme.system"),
                ("dark", "settings.theme.dark"),
                ("light", "settings.theme.light"),
            ),
            self._config.ui.theme,
        )
        self._theme.setAccessibleName(self._t.t("settings.theme"))
        form.addRow(self._t.t("settings.theme"), self._theme)

        self._locale = QComboBox(self)
        self._add_options(
            self._locale,
            (
                ("system", "settings.locale.system"),
                ("pt-BR", "settings.locale.pt_br"),
                ("en", "settings.locale.en"),
            ),
            self._config.ui.locale,
        )
        self._locale.setAccessibleName(self._t.t("settings.locale"))
        form.addRow(self._t.t("settings.locale"), self._locale)

        self._speech_mode = QComboBox(self)
        self._add_options(
            self._speech_mode,
            (
                ("ptt", "settings.speech_mode.ptt"),
                ("toggle", "settings.speech_mode.toggle"),
                ("vad", "settings.speech_mode.vad"),
            ),
            self._config.ui.speech_mode,
        )
        self._speech_mode.setAccessibleName(self._t.t("settings.speech_mode"))
        form.addRow(self._t.t("settings.speech_mode"), self._speech_mode)

        self._auto_hide = QSpinBox(self)
        self._auto_hide.setRange(1000, 60000)
        self._auto_hide.setSingleStep(1000)
        self._auto_hide.setSuffix(self._t.t("settings.milliseconds"))
        self._auto_hide.setValue(self._config.ui.auto_hide_ms)
        self._auto_hide.setAccessibleName(self._t.t("settings.auto_hide"))
        form.addRow(self._t.t("settings.auto_hide"), self._auto_hide)

        self._follow_up = QSpinBox(self)
        self._follow_up.setRange(1000, 60000)
        self._follow_up.setSingleStep(1000)
        self._follow_up.setSuffix(self._t.t("settings.milliseconds"))
        self._follow_up.setValue(self._config.ui.follow_up_ms)
        self._follow_up.setAccessibleName(self._t.t("settings.follow_up"))
        form.addRow(self._t.t("settings.follow_up"), self._follow_up)

        self._reduced_motion = QCheckBox(self._t.t("settings.reduced_motion"), self)
        self._reduced_motion.setChecked(self._config.ui.reduced_motion)
        form.addRow("", self._reduced_motion)

        self._autostart = QCheckBox(self._t.t("settings.autostart"), self)
        self._autostart.setChecked(self._config.ui.start_with_windows)
        form.addRow("", self._autostart)

        self._instructions = QPlainTextEdit(self)
        self._instructions.setPlainText(self._config.models.instructions)
        self._instructions.setAccessibleName(self._t.t("settings.instructions"))
        self._instructions.setFixedHeight(SPACE["xxl"] * 4)
        self._instructions.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        form.addRow(self._t.t("settings.instructions"), self._instructions)

        layout.addLayout(form)
        layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.Save).setText(self._t.t("settings.save"))
        buttons.button(QDialogButtonBox.Cancel).setText(self._t.t("settings.cancel"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_options(
        self,
        combo: QComboBox,
        options: tuple[tuple[str, str], ...],
        selected: str,
    ) -> None:
        for value, label_key in options:
            combo.addItem(self._t.t(label_key), value)
        combo.setCurrentIndex(max(0, combo.findData(selected)))

    def _save(self) -> None:
        self._config.ui.theme = self._theme.currentData()
        self._config.ui.locale = self._locale.currentData()
        self._config.ui.speech_mode = self._speech_mode.currentData()
        self._config.ui.auto_hide_ms = self._auto_hide.value()
        self._config.ui.follow_up_ms = self._follow_up.value()
        self._config.ui.reduced_motion = self._reduced_motion.isChecked()
        self._config.ui.start_with_windows = self._autostart.isChecked()
        instructions = self._instructions.toPlainText().strip()
        self._config.models.instructions = instructions or DEFAULT_INSTRUCTIONS
        self.saved.emit()
        self.accept()
