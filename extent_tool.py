from qgis.gui import QgsMapTool, QgsRubberBand, QgsMapMouseEvent
from qgis.core import QgsRectangle, QgsWkbTypes, QgsGeometry
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor


class ExtentTool(QgsMapTool):
    extentSelected = pyqtSignal(QgsRectangle)

    def __init__(self, canvas):
        QgsMapTool.__init__(self, canvas)
        self.canvas = canvas
        self.rubber_band = None
        self.start_point = None
        self.end_point = None
        self.dragging = False

        self.fill_color = QColor(5, 151, 49, 50)
        self.stroke_color = QColor(5, 151, 49)
        self.stroke_width = 1

    def createRubberBand(self):
        if not self.rubber_band:
            self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
            self.rubber_band.setColor(self.fill_color)
            self.rubber_band.setStrokeColor(self.stroke_color)
            self.rubber_band.setWidth(self.stroke_width)
            self.rubber_band.reset()

    def canvasPressEvent(self, e):
        self.createRubberBand()
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        if e.button() == Qt.MouseButton.LeftButton:
            self.start_point = self.toMapCoordinates(e.pos())
            self.end_point = self.start_point
            self.dragging = True

    def canvasMoveEvent(self, e):
        if not self.dragging:
            return
        self.end_point = self.toMapCoordinates(e.pos())
        self.showRect(self.start_point, self.end_point)

    def canvasReleaseEvent(self, e):
        if self.dragging:
            self.dragging = False
            final_rect = self.rectangle()
            if final_rect:
                self.extentSelected.emit(final_rect)

    def showRect(self, start_point, end_point):
        if not self.rubber_band:
            return

        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        if start_point is None or end_point is None or start_point == end_point:
            return

        rect = QgsRectangle(start_point, end_point)
        geom = QgsGeometry.fromRect(rect)
        if geom:
            self.rubber_band.setToGeometry(geom, None)
            self.rubber_band.show()

    def rectangle(self):
        if self.start_point is None or self.end_point is None:
            return None
        if self.start_point == self.end_point:
            return None
        return QgsRectangle(self.start_point, self.end_point)

    def deactivate(self):
        if self.rubber_band:
            self.rubber_band.reset()
            self.rubber_band = None
        self.start_point = None
        self.end_point = None
        self.dragging = False
        QgsMapTool.deactivate(self)

    def activate(self):
        QgsMapTool.activate(self)
