# -*- coding: utf-8 -*-
"""
/***************************************************************************
 TilesGenerator
                                 A QGIS plugin
 Wtyczka generuje pakiet kafli na podstawie treści mapy
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2025-05-03
        copyright            : (C) 2025 by GIS Mates
        email                : gis.mates.gm@gmail.com
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""
import subprocess
from qgis.core import Qgis

# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load TilesGenerator class from file TilesGenerator.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    try:
        import mercantile
    except ImportError:
        res = subprocess.call(['python3', "-m", "pip", "install", 'mercantile'])
        if res == 0:
            import pandas as pd
        else:
            iface.messageBar().pushMessage('Generator mapy C-GeoPortal',
                                           'Import modułu "mercantile" zakończony niepowodzeniem, zalecamy manualne zainstalowanie zależności',
                                           level=Qgis.Warning, duration=3)
    from .tiles_generator import TilesGenerator
    return TilesGenerator(iface)
