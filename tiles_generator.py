# -*- coding: utf-8 -*-
"""
/***************************************************************************
 TilesGenerator
                                 A QGIS plugin
 Wtyczka generuje pakiet kafli na podstawie treści mapy
        begin                : 2025-05-03
        git sha              : $Format:%H$
        copyright            : (C) 2025 by GIS Mates
        email                : gis.mates.gm@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os.path
import webbrowser

import qgis
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import *
from .resources.resources import *

from .tiles_generator_dockwidget import TilesGeneratorDockWidget
from .extent_tool import ExtentTool
from .generator_task import GeneratorTask


class TilesGenerator:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)
        self.settings = QSettings()
        locale = self.settings.value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'TilesGenerator_{}.qm'.format(locale))
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&Generator Mapy C-GeoPortal')

        self.pluginIsActive = False
        self.dockwidget = None

    def tr(self, message):
        return QCoreApplication.translate('TilesGenerator', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)
        if whats_this is not None:
            action.setWhatsThis(whats_this)
        if add_to_toolbar:
            self.iface.addToolBarIcon(action)
        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)
        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = ':/plugins/tiles_generator/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Wygeneruj kafle na podstawie treści mapy'),
            callback=self.run,
            parent=self.iface.mainWindow())

    def onClosePlugin(self):
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.pluginIsActive = False

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Generator Mapy C-GeoPortal'),
                action)
            self.iface.removeToolBarIcon(action)

    def logMessage(self, message, message_level=Qgis.Info, mode='quiet'):
        if mode == 'loud':
            self.iface.messageBar().pushMessage('Generator mapy C-GeoPortal', message, level=message_level, duration=3)
        QgsMessageLog.logMessage(message, 'Generator mapy C-GeoPortal', level=message_level)

    def run(self):
        if not self.pluginIsActive:
            self.pluginIsActive = True
            if self.dockwidget is None:
                self.generator_task = GeneratorTask()
                self.generator_task.progress_started.connect(lambda p: self.dockwidget.progress_bar.setMaximum(p))
                self.generator_task.progress_updated.connect(lambda p: self.dockwidget.progress_bar.setValue(p))
                self.generator_task.generation_info.connect(lambda i: self.logMessage(i))
                self.generator_task.finished.connect(self.generationFinihed)
                self.extent_tool = ExtentTool(self.canvas)
                self.dockwidget = TilesGeneratorDockWidget(self.iface, self.settings)
                self.dockwidget.cportal_btn.clicked.connect(lambda: webbrowser.open('https://www.c-geoportal.pl/map'))
                self.dockwidget.draw_extent_btn.clicked.connect(lambda: self.canvas.setMapTool(self.extent_tool))
                self.dockwidget.generate_tiles_btn.clicked.connect(self.callGeneratorTask)
                self.dockwidget.cancel_btn.clicked.connect(self.cancelGeneration)
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()

    def callGeneratorTask(self):
        if self.generator_task.isRunning():
            self.logMessage('Zadanie generowania kafli w toku', mode='loud')
        else:
            tiles_path = self.dockwidget.path_input.text()
            if tiles_path != '':
                params_crs = QgsCoordinateReferenceSystem("EPSG:4326")
                project = QgsProject.instance()
                root = project.layerTreeRoot()
                only_visible = self.dockwidget.visible_layers_btn.isChecked()
                generator_layers = []
                for layer in project.mapLayers().values():
                    if not layer.extent().isEmpty():
                        if only_visible:
                            tree_layer = root.findLayer(layer.id())
                            if tree_layer.isVisible():
                                generator_layers.append(layer)
                        else:
                            generator_layers.append(layer)
                if len(generator_layers) > 0:
                    tiles_extent = QgsRectangle()
                    if self.dockwidget.layers_range_btn.isChecked():
                        for layer in generator_layers:
                            source_crs = layer.crs()
                            transform = QgsCoordinateTransform(source_crs, params_crs, project)
                            if not source_crs.isValid():
                                print(f"Ostrzeżenie: Warstwa '{layer.name()}' ma nieprawidłowy CRS. Pomijanie jej zasięgu.")
                                continue
                            extent_native = layer.extent()
                            if not extent_native.isNull():
                                extent_params_crs = transform.transformBoundingBox(extent_native)
                                if not extent_params_crs.isNull():
                                    tiles_extent.combineExtentWith(extent_params_crs)
                    elif self.dockwidget.map_range_btn.isChecked():
                        transform = QgsCoordinateTransform(project.crs(), params_crs, project)
                        tiles_extent = transform.transformBoundingBox(self.canvas.extent())
                    else:
                        extent = self.extent_tool.rectangle()
                        if extent is not None:
                            transform = QgsCoordinateTransform(project.crs(), params_crs, project)
                            tiles_extent = transform.transformBoundingBox(extent)
                    if not tiles_extent.isNull():
                        self.dockwidget.generate_tiles_btn.setVisible(False)
                        self.dockwidget.cancel_btn.setVisible(True)
                        self.dockwidget.progress_bar.setVisible(True)
                        self.dockwidget.progress_bar.setValue(0)
                        self.generator_task.tiles_path = tiles_path
                        self.generator_task.zip_pack = self.dockwidget.zip_check.isChecked()
                        self.generator_task.layers_to_render = generator_layers
                        self.generator_task.tiles_extent_wgs84 = tiles_extent
                        self.generator_task.zoom_levels = [i for i in range(self.dockwidget.min_slider.value(), self.dockwidget.max_slider.value() + 1)]
                        self.generator_task.start()
                    else:
                        self.logMessage('Zasięg generowania kafli jest pusty', mode='loud')
                else:
                    self.logMessage('Brak warstw do renderowania', mode='loud')
            else:
                self.logMessage('Nie wskazano miejsca zapisu pliku kafli', mode='loud')

    def cancelGeneration(self):
        self.generator_task.terminated = True
        self.generator_task.terminate()

    def generationFinihed(self):
        self.dockwidget.generate_tiles_btn.setVisible(True)
        self.dockwidget.cancel_btn.setVisible(False)
        self.dockwidget.progress_bar.setVisible(False)
        if self.generator_task.terminated:
            self.logMessage('Zadanie generowania kafli przerwane', mode='loud')
        elif len(self.generator_task.errors) > 0:
            nl = '\n'
            self.logMessage(f'Zadanie generowania kafli zakończone z następującymi błędami:{nl}{nl.join(self.generator_task.errors)}', Qgis.Warning, 'loud')
        else:
            tiles_path = self.generator_task.tiles_path
            if self.generator_task.zip_pack:
                tiles_path = tiles_path.replace('.qgisweb', '.zip')
            self.logMessage(f'Zadanie generowania kafli zakończone, wynik zapisany w lokalizacji {tiles_path}', Qgis.Success, 'loud')
