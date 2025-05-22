import os
import sys

from qgis.PyQt import QtGui, QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QFileDialog

sys.path.append(os.path.dirname(__file__))

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'tiles_generator_dockwidget_base.ui'), resource_suffix='')


class TilesGeneratorDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, iface, settings):
        super(TilesGeneratorDockWidget, self).__init__()
        self.iface = iface
        self.settings = settings
        self.setupUi(self)
        self.draw_extent_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.loadSettings()
        self.zip_check.stateChanged.connect(self.saveSettings)
        self.all_layers_btn.clicked.connect(self.saveSettings)
        self.visible_layers_btn.clicked.connect(self.saveSettings)
        self.layers_range_btn.clicked.connect(lambda: self.saveSettings(True))
        self.map_range_btn.clicked.connect(lambda: self.saveSettings(True))
        self.user_range_btn.clicked.connect(self.saveSettings)
        self.min_slider.valueChanged.connect(self.updateZoomRange)
        self.max_slider.valueChanged.connect(self.updateZoomRange)
        self.show_path_btn.clicked.connect(self.tilesPath)

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()

    def loadSettings(self):
        zip_pack = self.settings.value('zip_pack')
        layers_option = self.settings.value('tiles_layers')
        range_option = self.settings.value('tiles_range')
        zoom_min = self.settings.value('tiles_zoom_min')
        zoom_max = self.settings.value('tiles_zoom_max')
        if zip_pack:
            self.zip_check.setChecked(int(zip_pack) == 1)
        if layers_option:
            if layers_option == 'all_layers':
                self.all_layers_btn.setChecked(True)
            else:
                self.visible_layers_btn.setChecked(True)
        if range_option:
            if range_option == 'layers_range':
                self.layers_range_btn.setChecked(True)
            elif range_option == 'map_range':
                self.map_range_btn.setChecked(True)
            else:
                self.user_range_btn.setChecked(True)
                self.draw_extent_btn.setVisible(True)
        if zoom_min:
            self.min_slider.setValue(int(zoom_min))
        if zoom_max:
            self.max_slider.setValue(int(zoom_max))
        self.updateDisplayLabels()

    def saveSettings(self, clear_extent_tool=False):
        if clear_extent_tool:
            if self.iface.mapCanvas().mapTool().__class__.__name__ == 'ExtentTool':
                self.iface.actionPan().trigger()
        self.draw_extent_btn.setVisible(False)
        layers_option = 'all_layers'
        range_option = 'layers_range'
        zip_check = 1 if self.zip_check.isChecked() else 0
        if self.visible_layers_btn.isChecked():
            layers_option = 'visible_layers'
        if self.map_range_btn.isChecked():
            range_option = 'map_range'
        if self.user_range_btn.isChecked():
            range_option = 'user_range'
            self.draw_extent_btn.setVisible(True)
        self.settings.setValue('zip_pack', zip_check)
        self.settings.setValue('tiles_layers', layers_option)
        self.settings.setValue('tiles_range', range_option)
        self.settings.setValue('tiles_zoom_min', self.min_slider.value())
        self.settings.setValue('tiles_zoom_max', self.max_slider.value())

    def updateZoomRange(self, value):
        sender = self.sender()
        current_min = self.min_slider.value()
        current_max = self.max_slider.value()
        if sender == self.min_slider:
            if current_min > current_max:
                self.max_slider.blockSignals(True)
                self.max_slider.setValue(current_min)
                self.max_slider.blockSignals(False)
        elif sender == self.max_slider:
            if current_max < current_min:
                self.min_slider.blockSignals(True)
                self.min_slider.setValue(current_max)
                self.min_slider.blockSignals(False)
        self.saveSettings()
        self.updateDisplayLabels()

    def updateDisplayLabels(self):
        self.min_display_label.setText(f"Min: {self.min_slider.value()}")
        self.max_display_label.setText(f"Max: {self.max_slider.value()}")

    def tilesPath(self):
        tiles_file = QFileDialog.getSaveFileName(self, "Wskaż miejsce zapisu", '', "QGIS Web (*.qgisweb)")[0]
        if tiles_file != "":
            self.path_input.setText(tiles_file)
