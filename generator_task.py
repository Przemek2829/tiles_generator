import gc
import os
import json
import base64
import io
import math
import time
import mercantile
import traceback
import zipfile

from qgis.PyQt.QtCore import QThread, QSize, QBuffer, QIODevice, pyqtSignal
from qgis.PyQt.QtGui import QImage, QColor
from qgis.core import QgsMapSettings, QgsRectangle, QgsCoordinateReferenceSystem, QgsMapRendererSequentialJob

IMAGE_FORMAT = "PNG"
TILE_CRS_EPSG = 3857
PARAMS_EXTENT_CRS_EPSG = 4326


def format_coord_for_json(coord):
	if coord is None or math.isnan(coord) or math.isinf(coord):
		return "0,00000000"
	formatted = "{:.8f}".format(coord)
	return formatted.replace('.', ',')


class GeneratorTask(QThread):
	progress_started = pyqtSignal(int)
	progress_updated = pyqtSignal(int)
	generation_info = pyqtSignal(str)

	def __init__(self):
		super(GeneratorTask, self).__init__()
		self.tile_width = 256
		self.tile_height = 256
		self.render_margin = 1000

	def run(self):
		self.terminated = False
		self.errors = []
		tiles_processed = 0
		total_tiles_to_process = 0

		try:
			tile_crs = QgsCoordinateReferenceSystem(f"EPSG:{TILE_CRS_EPSG}")
			if not tile_crs.isValid():
				self.errors.append(f"Nieprawidłowy docelowy CRS dla kafli (EPSG:{TILE_CRS_EPSG})")
				self.generation_error.emit()
				return

			tile_ranges_per_zoom = {}
			for z in self.zoom_levels:
				try:
					west = max(-180.0, self.tiles_extent_wgs84.xMinimum())
					south = max(-85.051129, self.tiles_extent_wgs84.yMinimum())
					east = min(180.0, self.tiles_extent_wgs84.xMaximum())
					north = min(85.051129, self.tiles_extent_wgs84.yMaximum())

					if west >= east or south >= north:
						self.generation_info.emit(f"Ostrzeżenie dla Zoom {z}: Nieprawidłowy zasięg WGS84 ({west}, {south}, {east}, {north}).")
						tile_ranges_per_zoom[z] = None
						continue

					tiles_in_extent = list(mercantile.tiles(west, south, east, north, zooms=[z]))
					if tiles_in_extent:
						min_x = min(t.x for t in tiles_in_extent) - 1
						max_x = max(t.x for t in tiles_in_extent) + 1
						min_y = min(t.y for t in tiles_in_extent) - 1
						max_y = max(t.y for t in tiles_in_extent) + 1

						max_tile_index = (1 << z) - 1
						min_x = max(0, min_x)
						max_x = min(max_tile_index, max_x)
						min_y = max(0, min_y)
						max_y = min(max_tile_index, max_y)

						tile_ranges_per_zoom[z] = (min_x, max_x, min_y, max_y)
						count = (max_x - min_x + 1) * (max_y - min_y + 1)
						total_tiles_to_process += count
						self.generation_info.emit(f"Zoom {z}: Zakres X={min_x}-{max_x}, Y={min_y}-{max_y} ({count} kafli)")
					else:
						tile_ranges_per_zoom[z] = None
				except Exception as e:
					self.errors.append(f"Błąd obliczania zakresu dla Z={z}: {e}")
					tile_ranges_per_zoom[z] = None

			if total_tiles_to_process == 0:
				self.generation_info.emit("Brak kafli do wygenerowania")
				return

			self.generation_info.emit(f"Łącznie do przetworzenia: {total_tiles_to_process} kafli.")
			self.progress_started.emit(total_tiles_to_process)

			map_settings = QgsMapSettings()
			map_settings.setLayers(self.layers_to_render)
			map_settings.setBackgroundColor(QColor(0, 0, 0, 0))
			map_settings.setDestinationCrs(tile_crs)
			map_settings.setFlag(QgsMapSettings.Flag.UseAdvancedEffects, False)
			map_settings.setFlag(QgsMapSettings.Flag.Antialiasing, True)

			with open(self.tiles_path, 'w') as output_file:
				output_file.write('{\n')
				output_file.write('  "params": {\n')
				output_file.write('    "extent": {\n')
				output_file.write(
					f'      "lon_min": "{format_coord_for_json(self.tiles_extent_wgs84.xMinimum())}",\n')
				output_file.write(
					f'      "lon_max": "{format_coord_for_json(self.tiles_extent_wgs84.xMaximum())}",\n')
				output_file.write(
					f'      "lat_min": "{format_coord_for_json(self.tiles_extent_wgs84.yMinimum())}",\n')
				output_file.write(
					f'      "lat_max": "{format_coord_for_json(self.tiles_extent_wgs84.yMaximum())}",\n')
				output_file.write(f'      "dxy": "0",\n')
				output_file.write(f'      "dh": "0",\n')
				output_file.write(f'      "epsg": "0"\n')
				output_file.write('    }\n')
				output_file.write('  },\n')
				output_file.write('  "tiles": [\n')

				first_tile_written = False
				self.generation_info.emit("Rozpoczynanie renderowania kafli...")

				for z in self.zoom_levels:
					if tile_ranges_per_zoom.get(z) is None:
						continue
					min_x, max_x, min_y, max_y = tile_ranges_per_zoom[z]
					self.generation_info.emit(f"Przetwarzanie Zoom Level: {z} (Kafle X: {min_x}-{max_x}, Y: {min_y}-{max_y})")

					for x in range(min_x, max_x + 1):
						for y in range(min_y, max_y + 1):
							tiles_processed += 1
							try:
								tile_bounds_mercator = mercantile.xy_bounds(x, y, z)
								tile_extent_mercator_qgs = QgsRectangle(
									tile_bounds_mercator.left, tile_bounds_mercator.bottom,
									tile_bounds_mercator.right, tile_bounds_mercator.top
								)

								if tile_extent_mercator_qgs.width() == 0 or abs(tile_extent_mercator_qgs.height()) == 0:
									self.generation_info.emit(f"Ostrzeżenie: Kafel {z}/{x}/{y} ma zerowy wymiar. Pomijanie.")
									continue

								final_tile_width = self.tile_width
								final_tile_height = self.tile_height

								render_width_px = final_tile_width + self.render_margin
								render_height_px = final_tile_height + self.render_margin

								pixel_res_x = tile_extent_mercator_qgs.width() / final_tile_width
								pixel_res_y = abs(tile_extent_mercator_qgs.height()) / final_tile_height

								if pixel_res_y <= 1e-9:
									self.generation_info.emit(f"Ostrzeżenie: Bardzo mała wysokość piksela dla {z}/{x}/{y}. Pomijanie.")
									continue

								x_offset_map_units = pixel_res_x * (self.render_margin / 2.0)
								y_offset_map_units = pixel_res_y * (self.render_margin / 2.0)

								extent_for_render = QgsRectangle(
									tile_extent_mercator_qgs.xMinimum() - x_offset_map_units,
									tile_extent_mercator_qgs.yMinimum() - y_offset_map_units,
									tile_extent_mercator_qgs.xMaximum() + x_offset_map_units,
									tile_extent_mercator_qgs.yMaximum() + y_offset_map_units
								)

								map_settings.setExtent(extent_for_render)
								map_settings.setOutputSize(QSize(render_width_px, render_height_px))

								job = QgsMapRendererSequentialJob(map_settings)
								job.start()
								job.waitForFinished()

								rendered_large_image = job.renderedImage()

								if rendered_large_image.isNull():
									image_to_save = QImage(QSize(final_tile_width, final_tile_height), QImage.Format_ARGB32_Premultiplied)
									image_to_save.fill(QColor(0, 0, 0, 0))
								elif rendered_large_image.size() != QSize(render_width_px, render_height_px):
									self.errors.append(f"Renderowanie (z marginesem) {z}/{x}/{y} dało zły rozmiar.")
									continue
								else:
									if self.render_margin > 0:
										crop_offset = self.render_margin // 2
										image_to_save = rendered_large_image.copy(crop_offset, crop_offset,
																				  final_tile_width, final_tile_height)
									else:
										image_to_save = rendered_large_image

								if image_to_save.isNull() or image_to_save.size() != QSize(final_tile_width,
																						   final_tile_height):
									self.errors.append(f"Obraz do zapisu dla {z}/{x}/{y} jest nieprawidłowy po cięciu/przypisaniu.")
									continue

								buffer = QBuffer()
								buffer.open(QIODevice.ReadWrite)
								image_to_save.save(buffer, IMAGE_FORMAT)
								image_bytes = buffer.data()
								buffer.close()

								if not image_bytes:
									self.errors.append(f"Konwersja obrazu kafla {z}/{x}/{y} do {IMAGE_FORMAT} nie dała danych.")
									continue

								base64_string = base64.b64encode(image_bytes).decode('utf-8')

								tile_entry = {'x': str(x), 'y': str(y), 'z': str(z), 't': base64_string}

								if first_tile_written:
									output_file.write(',\n    ')
								else:
									output_file.write('    ')
									first_tile_written = True

								json.dump(tile_entry, output_file)

							except mercantile.TileArgParsingError as tae:
								self.errors.append(f"Błąd mercantile dla {z}/{x}/{y}: {tae}.")
							except Exception as e_tile:
								self.errors.append(f"Błąd podczas przetwarzania kafla {z}/{x}/{y}: {e_tile}")

							if tiles_processed % 20 == 0 or tiles_processed == total_tiles_to_process:
								self.progress_updated.emit(tiles_processed)

				if first_tile_written:
					output_file.write('\n  ')
				output_file.write(']\n')
				output_file.write('}\n')
			with open(self.tiles_path, "r", encoding="utf-8") as f:
				data = json.load(f)
			with open(self.tiles_path, "w", encoding="utf-8") as file:
				file.write(base64.b64encode(json.dumps(data).encode("utf-8")).decode("utf-8"))
			if self.zip_pack:
				with zipfile.ZipFile(self.tiles_path.replace('.qgisweb', '.zip'), 'w', compression=zipfile.ZIP_DEFLATED) as arch:
					arch.write(self.tiles_path, arcname=os.path.basename(self.tiles_path))
				try:
					os.remove(self.tiles_path)
				except:
					pass
		except Exception as e_main:
			self.errors.append(f"Krytyczny błąd w wątku generowania: {e_main}\n{traceback.format_exc()}")
		finally:
			gc.collect()
