import sys
import os
import json
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QCheckBox, QSpinBox, QTableWidget, QTableWidgetItem, QDialog, QFileDialog, QMessageBox, QSlider, QFormLayout, QStatusBar
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QIcon


class ConfigEditor(QMainWindow):
    def __init__(self, config_path):
        super().__init__()
        self.config_path = config_path
        self.config_data = None
        self.modified = False
        self.setWindowTitle("配置编辑器")

        # 设置窗口大小
        self.setFixedSize(560, 360)  # 固定窗口大小为560x360
        
        # 将窗口移动到屏幕中央
        qr = self.frameGeometry()
        cp = QApplication.primaryScreen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

        # 设置图标
        self.setWindowIcon(QIcon("logo.ico"))

        self.load_config()
        self.create_ui()

        # 使用状态栏代替状态标签
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("配置未修改")

    def load_config(self):
        """加载配置文件"""
        try:
            if not os.path.exists(self.config_path):
                # 创建默认配置
                self.config_data = {
                    "enabled": True,
                    "scan_interval": 3,
                    "targets": []
                }
            else:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法加载配置文件：{e}")

    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=4)
            self.modified = False
            self.statusBar.showMessage("配置已保存")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法保存配置文件：{e}")

    def create_ui(self):
        """创建UI界面"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)  # 设置控件间距
        layout.setContentsMargins(15, 15, 15, 15)  # 设置边距

        # 全局设置，使用QFormLayout以更好地对齐
        global_form = QFormLayout()
        global_form.setSpacing(8)  # 设置表单行间距
        global_form.setContentsMargins(0, 0, 0, 5)  # 设置表单边距
        self.enabled_check = QCheckBox("启用系统", self)
        self.enabled_check.setChecked(self.config_data.get('enabled', True))
        self.enabled_check.toggled.connect(self.on_modified)

        self.scan_interval_spin = QSpinBox(self)
        self.scan_interval_spin.setValue(self.config_data.get('scan_interval', 3))
        self.scan_interval_spin.valueChanged.connect(self.on_modified)

        global_form.addRow("扫描间隔:", self.scan_interval_spin)
        global_form.addRow(self.enabled_check)  # 复选框单独一行
        layout.addLayout(global_form)

        # 目标应用列表
        self.target_table = QTableWidget(self)
        self.target_table.setColumnCount(7)
        self.target_table.setHorizontalHeaderLabels(["应用名称", "关键词", "背景图片", "透明度", "亮度", "对比度", "饱和度"])
        self.target_table.setStyleSheet("QTableWidget { font-size: 12px; background-color: #f7f7f7; border: 1px solid #ddd; gridline-color: #e0e0e0; } QTableWidget::item { padding: 3px; }")
        self.target_table.horizontalHeader().setStretchLastSection(True)
        self.target_table.verticalHeader().setVisible(False)  # 隐藏垂直头
        self.target_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.target_table.setSelectionMode(QTableWidget.SingleSelection)
        # 设置各列的固定宽度，适应560x360窗口，总宽度调整为约500以适应边距
        column_widths = [70, 90, 110, 55, 55, 55, 55]  # 总和约490
        for col, width in enumerate(column_widths):
            self.target_table.setColumnWidth(col, width)
        self.refresh_targets()
        layout.addWidget(self.target_table)

        # 操作按钮
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("添加应用", self)
        self.add_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; border-radius: 6px; padding: 8px 12px; font-size: 11pt; }")
        self.add_button.clicked.connect(self.add_target)
        button_layout.addWidget(self.add_button)

        self.edit_button = QPushButton("编辑应用", self)
        self.edit_button.setStyleSheet("QPushButton { background-color: #FFC107; color: white; font-weight: bold; border-radius: 6px; padding: 8px 12px; font-size: 11pt; }")
        self.edit_button.clicked.connect(self.edit_target)
        button_layout.addWidget(self.edit_button)

        self.remove_button = QPushButton("删除应用", self)
        self.remove_button.setStyleSheet("QPushButton { background-color: #F44336; color: white; font-weight: bold; border-radius: 6px; padding: 8px 12px; font-size: 11pt; }")
        self.remove_button.clicked.connect(self.remove_target)
        button_layout.addWidget(self.remove_button)

        button_layout.addStretch()  # 添加伸展以右对齐保存和应用按钮

        self.apply_button = QPushButton("应用", self)
        self.apply_button.setStyleSheet("QPushButton { background-color: #008CBA; color: white; font-weight: bold; border-radius: 6px; padding: 8px 12px; font-size: 11pt; }")
        self.apply_button.clicked.connect(self.apply_config)
        button_layout.addWidget(self.apply_button)

        self.save_button = QPushButton("保存并关闭", self)
        self.save_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; border-radius: 6px; padding: 8px 12px; font-size: 11pt; }")
        self.save_button.clicked.connect(self.save_and_close)
        button_layout.addWidget(self.save_button)

        layout.addLayout(button_layout)

    def on_modified(self):
        """配置被修改"""
        self.modified = True
        self.statusBar.showMessage("配置已修改")

    def refresh_targets(self):
        """刷新目标列表显示"""
        self.target_table.setRowCount(len(self.config_data.get('targets', [])))
        for row, target in enumerate(self.config_data.get('targets', [])):
            self.target_table.setItem(row, 0, QTableWidgetItem(target.get('name', '')))
            self.target_table.setItem(row, 1, QTableWidgetItem(", ".join(target.get('keywords', []))))
            self.target_table.setItem(row, 2, QTableWidgetItem(target.get('image_path', '')))
            self.target_table.setItem(row, 3, QTableWidgetItem(str(target.get('alpha', 40)) + "%"))
            self.target_table.setItem(row, 4, QTableWidgetItem(str(target.get('brightness', 1.0))))
            self.target_table.setItem(row, 5, QTableWidgetItem(str(target.get('contrast', 1.0))))
            self.target_table.setItem(row, 6, QTableWidgetItem(str(target.get('saturation', 1.0))))

    def save_and_close(self):
        """保存并关闭"""
        self.apply_config()
        self.save_config()
        self.close()

    def apply_config(self):
        """应用配置（保存但不关闭）"""
        self.config_data['enabled'] = self.enabled_check.isChecked()
        self.config_data['scan_interval'] = self.scan_interval_spin.value()
        self.save_config()

    def add_target(self):
        """弹出对话框添加新目标应用"""
        dialog = TargetDialog(self)
        if dialog.exec_() and dialog.target_data:
            self.config_data['targets'].append(dialog.target_data)
            self.refresh_targets()
            self.on_modified()

    def edit_target(self):
        """编辑选中的目标应用"""
        selected = self.target_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "警告", "请选择一个应用进行编辑")
            return
        row = selected[0].row()
        target = self.config_data['targets'][row]
        dialog = TargetDialog(self, target)
        if dialog.exec_() and dialog.target_data:
            self.config_data['targets'][row] = dialog.target_data
            self.refresh_targets()
            self.on_modified()

    def remove_target(self):
        """删除选中的目标应用"""
        selected = self.target_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "警告", "请选择一个应用进行删除")
            return
        row = selected[0].row()
        reply = QMessageBox.question(self, "确认删除", "确定要删除此应用吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.config_data['targets'][row]
            self.refresh_targets()
            self.on_modified()

    def closeEvent(self, event):
        """关闭事件"""
        if self.modified:
            reply = self.ask_save_changes()
            if reply == QMessageBox.Cancel:
                event.ignore()
            elif reply == QMessageBox.Save:
                self.save_config()
                event.accept()
            else:
                event.accept()
        else:
            event.accept()

    def ask_save_changes(self):
        """询问是否保存修改"""
        return QMessageBox.question(self, '保存修改', '配置已修改，是否保存？',
                                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                    QMessageBox.Save)


class TargetDialog(QDialog):
    """目标编辑对话框"""
    def __init__(self, parent, target_data=None):
        super().__init__(parent)
        self.setWindowTitle("编辑目标应用")
        self.setFixedSize(350, 250)  # 增加高度以防止溢出

        # 设置图标
        self.setWindowIcon(QIcon("logo.ico"))

        self.target_data = target_data if target_data else {}
        self.create_ui()

    def create_ui(self):
        """创建UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(6)  # 减小布局间距
        layout.setContentsMargins(12, 12, 12, 12)  # 设置边距
        form_layout = QFormLayout()
        form_layout.setSpacing(4)  # 减小表单行间距
        form_layout.setContentsMargins(0, 0, 0, 5)  # 设置表单边距

        self.name_edit = QLineEdit(self)
        self.name_edit.setText(self.target_data.get('name', ''))
        form_layout.addRow("应用名称:", self.name_edit)

        self.keywords_edit = QLineEdit(self)
        self.keywords_edit.setText(", ".join(self.target_data.get('keywords', [])))
        form_layout.addRow("关键词 (逗号分隔):", self.keywords_edit)

        # 背景图片选择
        image_hbox = QHBoxLayout()
        image_hbox.setSpacing(5)  # 设置水平布局间距
        self.image_edit = QLineEdit(self)
        self.image_edit.setText(self.target_data.get('image_path', ''))
        self.image_button = QPushButton("选择文件", self)
        self.image_button.clicked.connect(self.select_image_file)
        image_hbox.addWidget(self.image_edit)
        image_hbox.addWidget(self.image_button)
        form_layout.addRow("背景图片:", image_hbox)

        self.alpha_spin = QSpinBox(self)
        self.alpha_spin.setRange(0, 100)
        self.alpha_spin.setValue(self.target_data.get('alpha', 40))
        form_layout.addRow("透明度 (%):", self.alpha_spin)

        # 亮度滑块和数值显示
        brightness_hbox = QHBoxLayout()
        brightness_hbox.setSpacing(8)  # 设置水平布局间距
        self.brightness_slider = QSlider(Qt.Horizontal, self)
        self.brightness_slider.setRange(0, 200)
        self.brightness_slider.setValue(int(self.target_data.get('brightness', 1.0) * 100))
        self.brightness_slider.setFixedWidth(120)  # 设置滑块宽度
        self.brightness_label = QLabel(f"{self.brightness_slider.value() / 100:.2f}")
        self.brightness_label.setFixedWidth(40)  # 设置标签宽度
        self.brightness_slider.valueChanged.connect(self.update_brightness_label)
        brightness_hbox.addWidget(self.brightness_slider)
        brightness_hbox.addWidget(self.brightness_label)
        form_layout.addRow("亮度:", brightness_hbox)

        # 对比度滑块和数值显示
        contrast_hbox = QHBoxLayout()
        contrast_hbox.setSpacing(8)  # 设置水平布局间距
        self.contrast_slider = QSlider(Qt.Horizontal, self)
        self.contrast_slider.setRange(0, 200)
        self.contrast_slider.setValue(int(self.target_data.get('contrast', 1.0) * 100))
        self.contrast_slider.setFixedWidth(120)  # 设置滑块宽度
        self.contrast_label = QLabel(f"{self.contrast_slider.value() / 100:.2f}")
        self.contrast_label.setFixedWidth(40)  # 设置标签宽度
        self.contrast_slider.valueChanged.connect(self.update_contrast_label)
        contrast_hbox.addWidget(self.contrast_slider)
        contrast_hbox.addWidget(self.contrast_label)
        form_layout.addRow("对比度:", contrast_hbox)

        # 饱和度滑块和数值显示
        saturation_hbox = QHBoxLayout()
        saturation_hbox.setSpacing(8)  # 设置水平布局间距
        self.saturation_slider = QSlider(Qt.Horizontal, self)
        self.saturation_slider.setRange(0, 200)
        self.saturation_slider.setValue(int(self.target_data.get('saturation', 1.0) * 100))
        self.saturation_slider.setFixedWidth(120)  # 设置滑块宽度
        self.saturation_label = QLabel(f"{self.saturation_slider.value() / 100:.2f}")
        self.saturation_label.setFixedWidth(40)  # 设置标签宽度
        self.saturation_slider.valueChanged.connect(self.update_saturation_label)
        saturation_hbox.addWidget(self.saturation_slider)
        saturation_hbox.addWidget(self.saturation_label)
        form_layout.addRow("饱和度:", saturation_hbox)

        layout.addLayout(form_layout)

        # 操作按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)  # 设置按钮间距
        button_layout.addStretch()
        self.save_button = QPushButton("保存", self)
        self.save_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; border-radius: 6px; padding: 8px 16px; font-size: 11pt; }")
        self.save_button.clicked.connect(self.save_data)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("取消", self)
        self.cancel_button.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-weight: bold; border-radius: 6px; padding: 8px 16px; font-size: 11pt; }")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def update_brightness_label(self, value):
        """更新亮度标签显示"""
        self.brightness_label.setText(f"{value / 100:.2f}")

    def update_contrast_label(self, value):
        """更新对比度标签显示"""
        self.contrast_label.setText(f"{value / 100:.2f}")

    def update_saturation_label(self, value):
        """更新饱和度标签显示"""
        self.saturation_label.setText(f"{value / 100:.2f}")

    def select_image_file(self):
        """选择背景图片文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择背景图片", 
            "", 
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tiff)"
        )
        if file_path:
            self.image_edit.setText(file_path)

    def save_data(self):
        """保存目标数据"""
        name = self.name_edit.text().strip()
        keywords_str = self.keywords_edit.text().strip()
        keywords = [keyword.strip() for keyword in keywords_str.split(",") if keyword.strip()]
        image_path = self.image_edit.text().strip()
        alpha = self.alpha_spin.value()
        brightness = self.brightness_slider.value() / 100.0
        contrast = self.contrast_slider.value() / 100.0
        saturation = self.saturation_slider.value() / 100.0

        if not name or not keywords or not image_path:
            QMessageBox.warning(self, "输入错误", "请填写完整的目标应用信息（应用名称、关键词和背景图片不能为空）。")
            return

        self.target_data = {
            "name": name,
            "keywords": keywords,
            "image_path": image_path,
            "alpha": alpha,
            "brightness": brightness,
            "contrast": contrast,
            "saturation": saturation
        }
        self.accept()


def main(config_path="config.json"):
    app = QApplication(sys.argv)
    editor = ConfigEditor(config_path)
    editor.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()