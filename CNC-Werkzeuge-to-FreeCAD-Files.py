#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 
# CNC Werkzeuge und Werkzeugbibliotheken für FreeCAD aus einer Exceldatei
# 
# Dieses Skript liest CNC-Werkzeugdaten aus einer Excel-Datei und generiert individuelle .fctb-Dateien für jedes Werkzeug,
# sowie eine .fctl-Bibliotheksdatei zur Verwendung in FreeCAD. Es beinhaltet Funktionalitäten, um Werkzeugtypen
# spezifischen FreeCAD-Shape-Dateien zuzuordnen.
#
# Konfigurierbare Parameter wie Dateipfade und Präfixe werden in einer separaten Konfigurationsdatei (config.json) festgelegt.
#
# Autor: Josef Spitzlberger, https://github.com/spitzlbergerj
# Datum: Aktuelles Datum
# Version: 1.0
# FreeCAD-Version: 0.21.2
# Python-Version: 3.10.8
#
# Nutzung:
# - Stellen Sie sicher, dass die Pakete 'pandas' und 'openpyxl' in Ihrer Python-Umgebung installiert sind.
# - Aktualisieren Sie die 'config.json'-Datei mit den korrekten Pfaden und Einstellungen für Ihr System.
# - Führen Sie dieses Skript in einer Python-Umgebung aus, in der die FreeCAD Python-Bibliotheken zugänglich sind.
#
# Hinweis:
# - Das Skript erwartet, dass die Excel-Datei eine spezifische Struktur hat, siehe Beispiel Excel Datei.
# - Dateipfade, die Sonderzeichen enthalten, werden unter Verwendung der UTF-8-Kodierung behandelt.
#
# Haftungsausschluss:
# - Sie nutzen das Skript auf eigene Gefahr. Sichern Sie ihre Daten vor der Ausführung.
#

import pandas as pd
import xml.etree.ElementTree as ET
import logging
import json
import re
import os
import sys
import argparse
from datetime import datetime


# -----------------------------------------------------------------------------------------------------
#
# setup_logging
#
# Bereinige den Dateinamen, der aus der Spalte Bezeichnung gebildet wird.
# ° wird durch ein G ersetzt
# - durch einen _
# sonstge unzulässige zeichen werden durch '' ersetzt
# -----------------------------------------------------------------------------------------------------

def setup_logging(log_file_path='cnc_tools.log', log_level='DEBUG'):
	try:
		# Überprüfe, ob eine Log-Datei bereits existiert
		if os.path.exists(log_file_path):
			# Erstelle einen Zeitstempel für den Dateinamen
			timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
			# Erstelle einen neuen Dateinamen für das alte Log-File
			backup_log_file_path = f"{log_file_path}.{timestamp}.backup"
			# Benenne die alte Log-Datei um
			os.rename(log_file_path, backup_log_file_path)
			logging.info(f"Alte Log-Datei gesichert als: {backup_log_file_path}")

		# Loglevel 
		numeric_level = getattr(logging, log_level.upper(), None)
		if not isinstance(numeric_level, int):
			raise ValueError(f"Ungültiges Log-Level: {log_level}")

		# Konfiguriere das Logging für ein neues Log-File
		logging.basicConfig(filename=log_file_path, filemode='w', level=numeric_level,
							format='%(asctime)s - %(levelname)s - %(message)s')
		
	except OSError as e:
		# Fange Fehler beim Umbenennen der Log-Datei oder bei der Logging-Konfiguration ab
		logging.critical(f"Fehler beim Sichern der alten Log-Datei oder beim Erstellen der neuen Log-Datei: {e}")
		# Beende das Programm mit einem Fehlercode
		exit(1)
	except Exception as e:
		# Fange unerwartete Fehler ab
		logging.critical(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
		exit(1)

	logging.info("Logging-System wurde mit Level %s initialisiert.", log_level.upper())


# -----------------------------------------------------------------------------------------------------
#
# clean_filename
#
# Bereinige den Dateinamen, der aus der Spalte Bezeichnung gebildet wird.
# ° wird durch ein G ersetzt
# - durch einen _
# sonstge unzulässige zeichen werden durch '' ersetzt
# -----------------------------------------------------------------------------------------------------

def clean_filename(filename):
	filename = re.sub(r'[°]', 'G', filename)
	filename = re.sub(r'[-]', '_', filename)
	filename = re.sub(r'[^0-9a-zA-Z_]', '', filename)
	return filename


# -----------------------------------------------------------------------------------------------------
#
# read_shape_files
#
# Lese die in FreeCAD möglichen Shape Files ein
# -----------------------------------------------------------------------------------------------------

def read_shape_files(config):
	shape_files = {}
	shape_path = config["freecad_tool_shapes_path"]
	for file in os.listdir(shape_path):
		if file.endswith(".fcstd"):
			shape_key = file.replace(".fcstd", "")
			shape_files[shape_key.lower()] = file
	return shape_files


# -----------------------------------------------------------------------------------------------------
#
# get_shape_for_type
#
# Wandle die Shapes des Excel Files in die FreeCAD Shapes um
# -----------------------------------------------------------------------------------------------------

def get_shape_for_type(tool_name, tool_type, type_shape_mapping, available_shapes):
	# Konvertiere tool_type sicher in einen String und wende .lower() an
	shape_key = type_shape_mapping.get(str(tool_type).lower(), None)

	if shape_key and shape_key in available_shapes:
		return available_shapes[shape_key]
	else:
		logging.warning(f"Kein Shape für das Werkzeug '{tool_name}' mit den Werkzeugtyp '{tool_type}' gefunden.")
		return None
		

# -----------------------------------------------------------------------------------------------------
#
# create_tool_definition
#
# Erzeuge die Werkzeug Definition und schreibe die Werkzeug json
#
# Excel Dateiaufbau - Spalten:
# 		Bezeichnung	
# 		Typ	
# 		Kopfform	
# 		Schaft Ø	
# 		Front Ø	
# 		Schneidende Ø	
# 		Schneidwinkel	
# 		Gesamtlänge	
# 		Schneidlänge	
# 		Freischlifflänge	
# 		Zahnanzahl	
# 		Beschichtung	
# 		für Material
#
# -----------------------------------------------------------------------------------------------------

def create_tool_definition(row, config, available_shapes):
	tool_shape = get_shape_for_type(row['Bezeichnung'], row['Kopfform'], config["type_shape_mapping"], available_shapes)
	if tool_shape:
		tool_name = config['prefix'] + clean_filename(row['Bezeichnung'])
		tool_data = {
			"version": 2,
			"name": tool_name,
			"shape": tool_shape,
			"parameter": {},
			"attribute": {}
		}
	
		# Holen der Werte aus Excel mit Standardwert falls nicht vorhanden
		# siehe https://forum.freecad.org/viewtopic.php?t=23917
		# siehe auch deutsch - https://www.sandvik.coromant.com/de-de/knowledge/machining-formulas-definitions/cutting-tool-parameters
		# und        english - https://www.sandvik.coromant.com/en-us/knowledge/machining-formulas-definitions/cutting-tool-parameters
		# siehe auch https://www.pokolm.de/media/pdf/hs_zub_477_de.pdf
	
		# Spannlast / Chipload / Vorschub pro Zahn = Vorschubgeschwindigkeit in mm/min / Spindeldrehzahl in U/min * effektive Zähnezahl
		chipload = f"{row.get('Chipload', '0,00')} mm"

		# Schneidenlänge
		cuttingEdgeHeight = f"{row.get('Schneidlänge', '1,00')} mm"

		# Durchmesser des Schneidbereichs
		diameter = f"{row.get('Schneidende Ø', '1,00')} mm"

		# Zahnanzahl
		flutes = f"{row.get('Zahnanzahl', '0')}"

		# Gesamtlänge
		lenght = f"{row.get('Gesamtlänge', '2,00')} mm"

		# Fräsermaterial
		material = f"{row.get('Beschichtung', '')}"

		# 
		shankDiameter = f"{row.get('Schaft Ø', '4,00')} mm"

		# Schneidenwinkel
		cuttingEdgeAngle = f"{row.get('Schneidwinkel', '90,00')}  \u00b0"

		# Radius = halber (!) Durchmesser an der Spitze
		flatRadius = f"{row.get('Front Ø', '4,00') / 2} mm"

		# Durchmesser an der Spitze
		tipDiameter = f"{row.get('Front Ø', '4,00')} mm"
	
		# Durchmesser an der Spitze
		tipAngle = f"{row.get('Schneidwinkel', '90,00')}  \u00b0"
	
		# Durchmesser an der Spitze
		flatRadius = f"{row.get('Front Ø', '4,00')} mm"
	
		# Spindle Drehrichtung
		spindleDirection = "Forward"
	
		# Spindle aktiv/aus
		spindlePower = "False"
	
		# Dicke des Sägeblattes
		bladeThickness = "3,00 mm"
	
		# Schneiden-Durchmesser beim Schlitzfräser slittingsaw
		capDiameter = "8,00 mm"
	
		# Schneiden-Höhe beim Schlitzfräser - slittingsaw
		capHeight = "3,00 mm"
	
		# Steigung ???
		crest = "0,10 mm"
	
		# Durchmesser des Halses, also des Teils, das eintauchen kann in das Loch in dem das Gewinde geschnitten wird
		neckDiameter = "3,00 mm"
	
		# Länge des Halses, also des Teils, das eintauchen kann in das Loch in dem das Gewinde geschnitten wird
		neckLenght = "3,00 mm"
	
		# Winkel
		cuttingAngle = f"{row.get('Schneidwinkel', '90,00')}  \u00b0"
	
		# Unterscheide zwischen den Typen und setze Parameter entsprechend

		# abgerundetes Fräserende
		if tool_shape == "ballend":
			tool_data["parameter"] = {
				"Chipload": chipload,
				"CuttingEdgeHeight": cuttingEdgeHeight,
				"Diameter": diameter,
				"Flutes": flutes,
				"Length": lenght,
				"Material": material,
				"ShankDiameter": shankDiameter,
			}

		# flaches Fräserende mit abgerundeter Kante
		elif tool_shape == "bullnose":
			tool_data["parameter"] = {
				"Chipload": chipload,
				"CuttingEdgeHeight": cuttingEdgeHeight,
				"Diameter": diameter,
				"FlatRadius": flatRadius,
				"Flutes": flutes,
				"Length": lenght,
				"Material": material,
				"ShankDiameter": shankDiameter,
			}

		# Fräser zum Anphasen
		elif tool_shape == "chamfer":
			tool_data["parameter"] = {
				"Chipload": chipload,
				"CuttingEdgeAngle": cuttingEdgeAngle,
				"CuttingEdgeHeight": cuttingEdgeHeight,
				"Diameter": diameter,
				"Flutes": flutes,
				"Length": lenght,
				"Material": material,
				"ShankDiameter": shankDiameter,
				"TipDiameter": tipDiameter,
			}

		# Bohrer
		elif tool_shape == "drill":
			tool_data["parameter"] = {
				"Chipload": chipload,
				"Diameter": diameter,
				"Flutes": flutes,
				"Length": lenght,
				"Material": material,
				"TipAngle": tipAngle,
			}

		# Schaftfräser
		elif tool_shape == "endmill":
			tool_data["parameter"] = {
				"Chipload": chipload,
				"CuttingEdgeHeight": cuttingEdgeHeight,
				"Diameter": diameter,
				"Flutes": flutes,
				"Length": lenght,
				"Material": material,
				"ShankDiameter": shankDiameter,
				"SpindleDirection": spindleDirection,
			}

		# Fräser mit flachem Ende (womöglich nicht gut zum Eintauchen)
		elif tool_shape == "flatend":
			tool_data["parameter"] = {
				"Chipload": chipload,
				"CuttingEdgeHeight": cuttingEdgeHeight,
				"Diameter": diameter,
				"Flutes": flutes,
				"Length": lenght,
				"Material": material,
				"ShankDiameter": shankDiameter,
			}

		# Messtaster
		elif tool_shape == "probe":
			tool_data["parameter"] = {
				"Diameter": diameter,
				"Flutes": flutes,
				"Length": lenght,
				"ShankDiameter": shankDiameter,
				"spindlePower": spindlePower,
			}

		# Schlitzfräser
		elif tool_shape == "slittingsaw":
			tool_data["parameter"] = {
				"BladeThickness": bladeThickness,
				"CapDiameter": capDiameter,
				"CapHeight": capHeight,
				"Chipload": chipload,
				"Diameter": diameter,
				"Flutes": flutes,
				"Length": lenght,
				"Material": material,
				"ShankDiameter": shankDiameter,
			}

		# Gewindeschneider
		elif tool_shape == "thread-mill":
			tool_data["parameter"] = {
				"Chipload": chipload,
				"Crest": crest,
				"Diameter": diameter,
				"Flutes": flutes,
				"Length": lenght,
				"Material": material,
				"NeckDiameter": neckDiameter,
				"NeckLength": neckLenght,
				"ShankDiameter": shankDiameter,
				"cuttingAngle": cuttingAngle,
			}

		# Gravierstichel
		elif tool_shape == "v-bit":
			tool_data["parameter"] = {
				"Chipload": chipload,
				"CuttingEdgeAngle": cuttingEdgeAngle,
				"CuttingEdgeHeight": cuttingEdgeHeight,
				"Diameter": diameter,
				"Flutes": flutes,
				"Length": lenght,
				"Material": material,
				"ShankDiameter": shankDiameter,
				"TipDiameter": tipDiameter,
			}

		fctb_filename = os.path.join(config["output_directory"], tool_name + '.fctb')

		try:
			with open(fctb_filename, 'w', encoding='utf-8') as fctb_file:
				json.dump(tool_data, fctb_file, indent=4)
		except IOError as e:
			logging.critical(f"Fehler beim Schreiben der Werkzeug-Datei {fctb_filename}: {e}")

		return fctb_filename
	
	return None


# -----------------------------------------------------------------------------------------------------
#
# create_library_file
#
# Erzeuge die Werkzeug Bibliothek
# -----------------------------------------------------------------------------------------------------

def create_library_file(tools_paths, config):
	library_data = {
		"tools": [],
		"version": config["library_version"]
	}
	for tool_nr, tool_path in enumerate(tools_paths, start=1):
		library_data["tools"].append({"nr": tool_nr, "path": os.path.basename(tool_path)})
	fctl_filename = os.path.join(config["output_directory"], config['prefix'] + 'library.fctl')

	try:
		with open(fctl_filename, 'w', encoding='utf-8') as fctl_file:
			json.dump(library_data, fctl_file, indent=4)
	except IOError as e:
		logging.critical(f"Fehler beim Schreiben der Bibliotheks-Datei {fctl_filename}: {e}")


# -----------------------------------------------------------------------------------------------------
#
# read_additional_libraries
#
# Lesen der zu erzeugenden zusätzlichen Bibliotheken neben der Gesamt Bibliothek
# -----------------------------------------------------------------------------------------------------

def read_additional_libraries(excelFile):
	# Initialisiere ein leeres Dictionary für Library-Namen und deren Spaltenindizes
	library_names_with_index = {}
	
	# Iteriere über die Spalten ab der sechsten Spalte (Index 5)
	for index, name in enumerate(excelFile.iloc[2, 5:], start=5):
		if pd.notna(name):
			# Speichere den Namen der Library und den entsprechenden Spaltenindex im Dictionary
			library_names_with_index[name] = index
	
	return library_names_with_index


# -----------------------------------------------------------------------------------------------------
#
# generate_library_tool_structure
#
# Welches Tool soll in welche Library
# -----------------------------------------------------------------------------------------------------

def generate_library_tool_structure(excelFile, library_names_with_index, tools_paths):
	# Extrahiere Werkzeugnamen aus den Pfaden
	tool_names_to_path = {
		path.split("\\")[-1].replace("sjj_", "").replace(".fctb", ""): path
		for path in tools_paths
	}
	
	# Initialisiere die  Datenstruktur
	libraries_with_tool_paths = {library: [] for library in library_names_with_index.keys()}
	
	# Durchsuche das Excel-Blatt
	for index, row in excelFile.iterrows():
		if pd.isna(row.iloc[0]):
			continue

		tool_name = clean_filename(row.iloc[0]) # Werkzeugname befindet sich in Spalte 1, Umwandlung notwendig
	
		if tool_name in tool_names_to_path:  # Überprüfe, ob der Werkzeugname gültig ist
			for library_name, col_index in library_names_with_index.items():
				if row.iloc[col_index] == "x":  # Wenn ein "x" in der Library-Spalte gefunden wird
					tool_path = tool_names_to_path[tool_name]  # Hole den Pfad für das Werkzeug
					libraries_with_tool_paths[library_name].append(tool_path)  # Füge den Pfad zur entsprechenden Library hinzu

	return libraries_with_tool_paths



def generate_library_files(libraries_with_tool_paths, config):
	for library_name, tool_paths in libraries_with_tool_paths.items():
		# Extrahiere nur den Dateinamen aus dem gesamten Pfad und entferne das Verzeichnis
		tools_for_library = [{"nr": i + 1, "path": os.path.basename(path)} for i, path in enumerate(tool_paths)]

		library_data = {
			"tools": tools_for_library,
			"version": config["library_version"]
		}

		# Erstelle den Dateinamen für die aktuelle Library
		fctl_filename = os.path.join(config["output_directory"], f"{config['prefix']}{library_name}.fctl")

		# Versuche, die .fctl Datei für die Library zu schreiben
		try:
			with open(fctl_filename, 'w', encoding='utf-8') as fctl_file:
				json.dump(library_data, fctl_file, indent=4)
			logging.info(f"Bibliotheks-Datei für '{library_name}' erstellt: {fctl_filename}")
		except IOError as e:
			logging.critical(f"Fehler beim Schreiben der Bibliotheks-Datei {fctl_filename}: {e}")


# -----------------------------------------------------------------------------------------------------
#
# create_additional_library_files
#
# schreibe die Files
# -----------------------------------------------------------------------------------------------------

def create_additional_library_files(tool_libraries, config):
	for library_name in set([lib for libs in tool_libraries.values() for lib in libs]):
		tools_in_library = [tool_name for tool_name, libraries in tool_libraries.items() if library_name in libraries]
		# An dieser Stelle wäre die Logik zum Schreiben der Library-Dateien,
		# basierend auf `tools_in_library` und `config`, implementiert.
		logging.info(f"Zusätzliche Library-Datei für '{library_name}' erstellt.")


# -----------------------------------------------------------------------------------------------------
#
# load_config
#
# Lese die Konfigurationsdatei ein
# -----------------------------------------------------------------------------------------------------

def load_config(config_path):
	try:
		tree = ET.parse(config_path)
		root = tree.getroot()
		
		config = {
			"prefix": root.find('prefix').text,
			"excel_file_path": root.find('excel_file_path').text,
			"output_directory": root.find('output_directory').text,
			"freecad_tool_shapes_path": root.find('freecad_tool_shapes_path').text,
			"type_shape_mapping": {mapping.get('type'): mapping.get('shape') for mapping in root.find('type_shape_mapping')},
			"library_version": int(root.find('library_version').text),
		}
	except ET.ParseError:
		logging.error(f"Fehler beim Parsen der Konfigurationsdatei: {config_path}")
		sys.exit(1)
	except FileNotFoundError:
		logging.critical(f"Konfigurationsdatei nicht gefunden: {config_path}")
		sys.exit(1)
	except Exception as e:  # Generische Fehlerbehandlung für andere unerwartete Fehler
		logging.critical(f"Fehler beim Laden der Konfiguration: {str(e)}")
		sys.exit(1)

	return config


# -----------------------------------------------------------------------------------------------------
#
# read_excel_sheet
#
# Lese die Werkzeug Excel Datei ein
# -----------------------------------------------------------------------------------------------------

def read_excel_sheet(excel_file_path, sheet_name=0, header=0):
	# Liest ein spezifisches Blatt aus einer Excel-Datei und gibt es als DataFrame zurück.

	# :param excel_file_path: Der Pfad zur Excel-Datei.
	# :param sheet_name: Der Name oder die Indexnummer des Blatts, das gelesen werden soll. Standard ist das erste Blatt.
	# :param header: Die Zeilennummer (0-indexiert) der Überschriftenzeile. Standard ist die erste Zeile.
	# :return: Ein pandas DataFrame mit den Daten des spezifischen Blatts.

	try:
		excelFile = pd.read_excel(excel_file_path, sheet_name=sheet_name, header=header)
		return excelFile
	except FileNotFoundError:
		logging.critical(f"Excel-Datei nicht gefunden: {excel_file_path}")
		exit(1)
	except Exception as e:  # Fängt andere mögliche Fehler beim Lesen der Excel-Datei ab
		logging.critical(f"Fehler beim Lesen der Excel-Datei '{excel_file_path}' (Sheet: {sheet_name}): {e}")
		exit(1)


# -----------------------------------------------------------------------------------------------------
#
# main
#
# -----------------------------------------------------------------------------------------------------

def main():
	
	# argparse-Setup
	parser = argparse.ArgumentParser(description='Erzeugt FreeCAD Toolbibliotheken aus einer Excel-Tabelle.')
	parser.add_argument(
						'-c', 
						'--config', 
						type=str, 
						default='D:/OneDrives/OneDrive - La Gondola Barocca/_PCBüroLustheim/Programme/FreeCAD-CNC-Tools-from-Excel/config.xml',
						help='Pfad zur XML-Konfigurationsdatei'
					)
	parser.add_argument(
						'-l', 
						'--loglevel', 
						type=str, 
						help="Setzt das Logging-Level (z.B. DEBUG, INFO, WARNING, ERROR, CRITICAL)", 
						default="INFO"
					)

	# Parse die Argumente
	args = parser.parse_args()

	# Logging starten
	setup_logging(log_file_path='cnc_tools.log', log_level=args.loglevel)

	# Konfigurationsdatei
	logging.info(f"Konfigurationsdatei: {args.config}")

	# Lade Konfiguration
	config = load_config(args.config)

	# Stelle sicher, dass das Ausgabeverzeichnis existiert
	if not os.path.exists(config["output_directory"]):
		try:
			os.makedirs(config["output_directory"])
		except OSError as e:
			logging.critical(f"Fehler beim Erzeugen des Ausgabeverzeichnisses {config['output_directory']}: {e}")
			sys.exit(1)


	# Lese die in FreeCAD verfügbaren Shapes
	available_shapes = read_shape_files(config)

	# Lese die Excel-Datei mit den Werkzeugen, Bibliothekszuordnungen, etc.
	excel_file_path = config["excel_file_path"]

	# sheet_name = 0: die Werkzeuge stehen auf dem Blatt 1
	# header=0: die Spaltenüberschriften stehen in Zeile 1
	werkzeuge = read_excel_sheet(excel_file_path, sheet_name=0, header=0)

	# sheet_name = 1: die Zuordnung der Werkzeuge zu den Libraries stehen auf dem Blatt 2
	# header=None: wir lesen das ganze File ohne eine zeile als Überschriftn zu spezifizieren
	werkzeuge_libs = read_excel_sheet(excel_file_path, sheet_name=1, header=None)

	# Liste für gesammelte Tool-Pfade
	tools_paths = []
	tool_names = []

	# weitere Bibliotheken
	library_names_with_index = read_additional_libraries(werkzeuge_libs)

	# Überprüfe den Inhalt der DataFrame-Zeilen
	for index, row in werkzeuge.iterrows():

		# Zeile leer?
		if pd.isna(row['Bezeichnung']):
			logging.warning(f"Zeile {index+1}: leer - übersprungen")
			continue

		# Überschrift (Bezeichnung nicht leer, Kopfform leer)
		if pd.notna(row['Bezeichnung']) and pd.isna(row['Kopfform']):
			logging.warning(f"Zeile {index+1}: Überschrift - übersprungen")
			continue

		logging.debug(f"Zeile {index+1}: Werkzeug mit Bezeichnung={row['Bezeichnung']}, Kopfform={row['Kopfform']}")

		# Überprüfe, ob die Werkzeugbezeichnung bereits in der Liste der gesammelten Werkzeugnamen enthalten ist
		if row['Bezeichnung'] in tool_names:
			logging.error(f"Warnung: Zeile {index+1}: Werkzeugbezeichnung '{row['Bezeichnung']}' nicht eindeutig - übersprungen!")
		else:
			tool_names.append(row['Bezeichnung'])
			
			# Erstelle Tool-Definitionen nur für Zeilen, in denen die Spalte 'Kopfform' nicht NaN (z.B. leer) ist
			if pd.notnull(row['Kopfform']):
				tool_path = create_tool_definition(row, config, available_shapes)
				if tool_path:
					logging.info(f"Tool-Definition erstellt für Werkzeug in Zeile {index+1}: {row['Bezeichnung']}")
					tools_paths.append(tool_path)
				else:
					logging.error(f"Sollte nicht auftauchen - Programmfehler - Keine Tool-Definition erstellt für Werkzeug in Zeile {index+1}")
				
	# Filtere None-Einträge heraus
	tools_paths = [path for path in tools_paths if path]

	# Erstelle die Biblitheken

	# dazu erst ermitteln, welches Werkzeug in welche Bibliothek soll:
	libraries_with_tool_paths = generate_library_tool_structure(werkzeuge_libs, library_names_with_index, tools_paths)

	# Dann schreibe die Bibliotheksdateien
	generate_library_files(libraries_with_tool_paths, config)


	# zunächst die Gesamt Bibliothek
	#create_library_file(tools_paths, config)

	# dann die zusätzlichen aus Blatt 2
	##tool_libraries = update_tool_libraries(werkzeuge_libs_filtered, tool_names)
	#create_additional_library_files(tool_libraries, config)

if __name__ == "__main__":
	main()


