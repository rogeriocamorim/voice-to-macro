"""
gui/macro_tab.py — Macro Editor tab.

View, add, edit, and delete actions in the active game profile.
Changes are written directly to the profile JSON file.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILES_DIR = BASE_DIR / "profiles"

ACTION_TYPES = ["key", "combo", "hold", "sequence"]


# ---------------------------------------------------------------------------
# Add / Edit dialog
# ---------------------------------------------------------------------------

class MacroDialog(QDialog):
    """Dialog for adding or editing a single macro action."""

    def __init__(self, parent=None, action_name: str = "", action_data: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Macro" if action_name else "Add Macro")
        self.setMinimumWidth(420)
        self._build_ui(action_name, action_data or {})

    def _build_ui(self, action_name: str, data: dict) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(action_name)
        self.name_edit.setPlaceholderText("e.g. boost, fsd_jump, throttle_zero")
        form.addRow("Action Name:", self.name_edit)

        self.desc_edit = QLineEdit(data.get("description", ""))
        self.desc_edit.setPlaceholderText("What you'll say to trigger this")
        form.addRow("Description:", self.desc_edit)

        action = data.get("action", {})

        self.type_combo = QComboBox()
        for t in ACTION_TYPES:
            self.type_combo.addItem(t)
        idx = self.type_combo.findText(action.get("type", "key"))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        form.addRow("Type:", self.type_combo)

        # Key (for key, hold)
        self.key_edit = QLineEdit(action.get("key", ""))
        self.key_edit.setPlaceholderText("e.g. j, tab, space, delete")
        form.addRow("Key:", self.key_edit)

        # Keys (for combo)
        self.keys_edit = QLineEdit(", ".join(action.get("keys", [])))
        self.keys_edit.setPlaceholderText("e.g. ctrl, shift, s")
        form.addRow("Keys (comma-sep):", self.keys_edit)

        # Duration (for hold)
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(50, 10000)
        self.duration_spin.setSuffix(" ms")
        self.duration_spin.setValue(action.get("duration_ms", 500))
        form.addRow("Hold Duration:", self.duration_spin)

        # Sequence (as JSON text for simplicity)
        self.sequence_edit = QLineEdit()
        steps = action.get("steps", [])
        if steps:
            self.sequence_edit.setText(json.dumps(steps))
        self.sequence_edit.setPlaceholderText('[{"key": "tab"}, {"delay_ms": 100}, {"key": "x"}]')
        form.addRow("Sequence JSON:", self.sequence_edit)

        layout.addLayout(form)

        # Show/hide fields based on type
        self._on_type_changed(self.type_combo.currentText())

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_type_changed(self, type_name: str) -> None:
        self.key_edit.setVisible(type_name in ("key", "hold"))
        self.keys_edit.setVisible(type_name == "combo")
        self.duration_spin.setVisible(type_name == "hold")
        self.sequence_edit.setVisible(type_name == "sequence")

    def _validate_and_accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Action name is required.")
            return
        # Sanitize name: lowercase, underscores
        name = name.lower().replace(" ", "_").replace("-", "_")
        self.name_edit.setText(name)

        desc = self.desc_edit.text().strip()
        if not desc:
            QMessageBox.warning(self, "Validation", "Description is required (this is what you say).")
            return

        action_type = self.type_combo.currentText()
        if action_type in ("key", "hold") and not self.key_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Key is required for this action type.")
            return
        if action_type == "combo":
            keys = [k.strip() for k in self.keys_edit.text().split(",") if k.strip()]
            if len(keys) < 2:
                QMessageBox.warning(self, "Validation", "Combo needs at least 2 keys (comma-separated).")
                return
        if action_type == "sequence":
            try:
                steps = json.loads(self.sequence_edit.text())
                if not isinstance(steps, list) or len(steps) == 0:
                    raise ValueError
            except (json.JSONDecodeError, ValueError):
                QMessageBox.warning(self, "Validation", "Sequence must be valid JSON array of steps.")
                return

        self.accept()

    def get_result(self) -> tuple[str, dict]:
        """Return (action_name, action_data_dict)."""
        name = self.name_edit.text().strip()
        desc = self.desc_edit.text().strip()
        action_type = self.type_combo.currentText()

        action = {"type": action_type}
        if action_type == "key":
            action["key"] = self.key_edit.text().strip()
        elif action_type == "hold":
            action["key"] = self.key_edit.text().strip()
            action["duration_ms"] = self.duration_spin.value()
        elif action_type == "combo":
            action["keys"] = [k.strip() for k in self.keys_edit.text().split(",") if k.strip()]
        elif action_type == "sequence":
            action["steps"] = json.loads(self.sequence_edit.text())

        return name, {"description": desc, "action": action}


# ---------------------------------------------------------------------------
# Macro Editor tab
# ---------------------------------------------------------------------------

class MacroTab(QWidget):
    """Table-based editor for profile actions."""

    profile_changed = pyqtSignal()  # emitted after add/edit/delete

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_profile: str = "generic"
        self._profile_data: dict = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Profile selector
        top = QHBoxLayout()
        top.addWidget(QLabel("Profile:"))
        self.profile_combo = QComboBox()
        self._populate_profiles()
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        top.addWidget(self.profile_combo, 1)
        layout.addLayout(top)

        # Actions table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Action Name", "Description", "Type", "Detail"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._edit_selected)
        layout.addWidget(self.table)

        # Buttons
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("+ Add Macro")
        self.add_btn.clicked.connect(self._add_macro)
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self._edit_selected)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("deleteBtn")
        self.delete_btn.clicked.connect(self._delete_selected)
        self.dup_btn = QPushButton("Duplicate")
        self.dup_btn.clicked.connect(self._duplicate_selected)

        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.edit_btn)
        btn_row.addWidget(self.dup_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.delete_btn)
        layout.addLayout(btn_row)

        # Load initial
        if self.profile_combo.count() > 0:
            self._on_profile_selected(0)

    def _populate_profiles(self) -> None:
        self.profile_combo.clear()
        if PROFILES_DIR.exists():
            for p in sorted(PROFILES_DIR.glob("*.json")):
                name = p.stem
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    display = data.get("game", name)
                except Exception:
                    display = name
                self.profile_combo.addItem(display, name)

    def _profile_path(self) -> Path:
        return PROFILES_DIR / f"{self._current_profile}.json"

    def _load_profile(self) -> None:
        path = self._profile_path()
        if not path.exists():
            self._profile_data = {"game": self._current_profile, "actions": {}}
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._profile_data = json.load(f)
        except (json.JSONDecodeError, ValueError):
            self._profile_data = {"game": self._current_profile, "actions": {}}

    def _save_profile(self) -> None:
        path = self._profile_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._profile_data, f, indent=2, ensure_ascii=False)
        self.profile_changed.emit()

    def _refresh_table(self) -> None:
        actions = self._profile_data.get("actions", {})
        self.table.setRowCount(len(actions))
        for row, (name, data) in enumerate(actions.items()):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(data.get("description", "")))
            action = data.get("action", {})
            atype = action.get("type", "")
            self.table.setItem(row, 2, QTableWidgetItem(atype))
            # Detail column: show key/keys/steps summary
            if atype == "key":
                detail = action.get("key", "")
            elif atype == "combo":
                detail = " + ".join(action.get("keys", []))
            elif atype == "hold":
                detail = f"{action.get('key', '')} ({action.get('duration_ms', 0)}ms)"
            elif atype == "sequence":
                steps = action.get("steps", [])
                detail = f"{len(steps)} steps"
            else:
                detail = ""
            self.table.setItem(row, 3, QTableWidgetItem(detail))

    def _on_profile_selected(self, index: int) -> None:
        data = self.profile_combo.itemData(index)
        if data:
            self._current_profile = data
            self._load_profile()
            self._refresh_table()

    def _get_selected_action_name(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Select", "Select a row first.")
            return None
        return self.table.item(rows[0].row(), 0).text()

    def _add_macro(self) -> None:
        dlg = MacroDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, data = dlg.get_result()
            actions = self._profile_data.setdefault("actions", {})
            if name in actions:
                reply = QMessageBox.question(
                    self, "Overwrite?",
                    f"Action '{name}' already exists. Overwrite?",
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            actions[name] = data
            self._save_profile()
            self._refresh_table()

    def _edit_selected(self) -> None:
        name = self._get_selected_action_name()
        if not name:
            return
        actions = self._profile_data.get("actions", {})
        data = actions.get(name, {})

        dlg = MacroDialog(self, action_name=name, action_data=data)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_name, new_data = dlg.get_result()
            # If renamed, delete old key
            if new_name != name:
                del actions[name]
            actions[new_name] = new_data
            self._save_profile()
            self._refresh_table()

    def _delete_selected(self) -> None:
        name = self._get_selected_action_name()
        if not name:
            return
        reply = QMessageBox.question(
            self, "Delete Macro",
            f"Delete action '{name}'? This cannot be undone.",
        )
        if reply == QMessageBox.StandardButton.Yes:
            actions = self._profile_data.get("actions", {})
            actions.pop(name, None)
            self._save_profile()
            self._refresh_table()

    def _duplicate_selected(self) -> None:
        name = self._get_selected_action_name()
        if not name:
            return
        actions = self._profile_data.get("actions", {})
        data = actions.get(name)
        if not data:
            return
        import copy
        new_name = f"{name}_copy"
        counter = 1
        while new_name in actions:
            counter += 1
            new_name = f"{name}_copy{counter}"
        actions[new_name] = copy.deepcopy(data)
        self._save_profile()
        self._refresh_table()

    def set_profile(self, profile_name: str) -> None:
        """Programmatically switch to a profile (called from setup tab)."""
        idx = self.profile_combo.findData(profile_name)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
