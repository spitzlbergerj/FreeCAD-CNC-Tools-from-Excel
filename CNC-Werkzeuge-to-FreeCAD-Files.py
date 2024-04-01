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
import json
import re
import os
import argparse

def clean_filename(filename):
	# Bereinige den Dateinamen, der aus der Spalte Bezeichnung gebildet wird.
	# ° wird durch ein G ersetzt
	# - durch einen _
	# sonstge unzulässige zeichen werden durch '' ersetzt
	#
	filename = re.sub(r'[°]', 'G', filename)
	filename = re.sub(r'[-]', '_', filename)
	filename = re.sub(r'[^0-9a-zA-Z_]', '', filename)
	return filename

def read_shape_files(config):
	shape_files = {}
	shape_path = config["freecad_tool_shapes_path"]
	for file in os.listdir(shape_path):
		if file.endswith(".fcstd"):
			shape_key = file.replace(".fcstd", "")
			shape_files[shape_key.lower()] = file
	return shape_files

def get_shape_for_type(tool_name, tool_type, type_shape_mapping, available_shapes):
	# Konvertiere tool_type sicher in einen String und wende .lower() an
	shape_key = type_shape_mapping.get(str(tool_type).lower(), None)

	if shape_key and shape_key in available_shapes:
		return available_shapes[shape_key]
	else:
		print(f"Kein Shape für das Werkzeug '{tool_name}' mit den Werkzeugtyp '{tool_type}' gefunden.")
		return None
		
def create_tool_definition(row, config, available_shapes):
	tool_shape = get_shape_for_type(row['Bezeichnung'], row['Kopfform'], config["type_shape_mapping"], available_shapes)
	if tool_shape:
		tool_name = config['prefix'] + clean_filename(row['Bezeichnung'])
		tool_data = {
			"version": 2,
			"name": tool_name,
			"shape": tool_shape,
			"parameter": {
				# Füge hier die Parameter ein, die aus den Excel-Daten gelesen werden sollen
			},
			"attribute": {}
		}
		fctb_filename = os.path.join(config["output_directory"], tool_name + '.fctb')
		with open(fctb_filename, 'w', encoding='utf-8') as fctb_file:
			json.dump(tool_data, fctb_file, indent=4)
		return fctb_filename
	return None

def create_library_file(tools_paths, config):
	library_data = {
		"tools": [],
		"version": config["library_version"]
	}
	for tool_nr, tool_path in enumerate(tools_paths, start=1):
		library_data["tools"].append({"nr": tool_nr, "path": os.path.basename(tool_path)})
	fctl_filename = os.path.join(config["output_directory"], config['prefix'] + 'library.fctl')
	with open(fctl_filename, 'w', encoding='utf-8') as fctl_file:
		json.dump(library_data, fctl_file, indent=4)


def load_config(config_path):
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
	
	return config


def main():
	# argparse-Setup
	parser = argparse.ArgumentParser(description='Erzeugt FreeCAD Toolbibliotheken aus einer Excel-Tabelle.')
	parser.add_argument(
						'-c', 
						'--config', 
						type=str, 
						default='D:/OneDrives/OneDrive - La Gondola Barocca/_PCBüroLustheim/Programme/Python/config.xml',
						help='Pfad zur XML-Konfigurationsdatei'
					)

	# Parse die Argumente
	args = parser.parse_args()

	# Lade Konfiguration
	config = load_config(args.config)

	# Stelle sicher, dass das Ausgabeverzeichnis existiert
	if not os.path.exists(config["output_directory"]):
		os.makedirs(config["output_directory"])

	# Lese die verfügbaren Shapes
	available_shapes = read_shape_files(config)

	# Lese die Excel-Datei
	# sheet_name= 0
	#    die Werkzeuge stehen auf dem Blatt 0
	# header=4
	#    die Spaltenüberschriften stehen in Zeile 1
	excel_file_path = config["excel_file_path"]
	df = pd.read_excel(excel_file_path, sheet_name=0, header=0)

	# Liste für gesammelte Tool-Pfade
	tools_paths = []
	tool_names = []

	# Überprüfe den Inhalt der DataFrame-Zeilen
	for index, row in df.iterrows():
		if pd.isna(row['Bezeichnung']) or not any(pd.notnull(row[col]) for col in ['Bezeichnung', 'Kopfform']):
			print(f"Zeile {index+1}: kein Werkzeug - Bezeichnung={row['Bezeichnung']}, Kopfform={row['Kopfform']} - übersprungen")
		else:
			# print(f"Zeile mit Werkzeug {index+1}: Bezeichnung={row['Bezeichnung']}, Kopfform={row['Kopfform']}")

			# Überprüfe, ob die Werkzeugbezeichnung bereits in der Liste der gesammelten Werkzeugnamen enthalten ist
			if row['Bezeichnung'] in tool_names:
				print(f"Warnung: Zeile {index+1}: Werkzeugbezeichnung '{row['Bezeichnung']}' nicht eindeutig - übersprungen!")
			else:
				tool_names.append(row['Bezeichnung'])
				
				# Erstelle Tool-Definitionen nur für Zeilen, in denen die Spalte 'Kopfform' nicht NaN (z.B. leer) ist
				if pd.notnull(row['Kopfform']):
					tool_path = create_tool_definition(row, config, available_shapes)
					if tool_path:
						print(f"Tool-Definition erstellt für Werkzeug in Zeile {index+1}: {row['Bezeichnung']}")
						tools_paths.append(tool_path)
					else:
						print(f"Sollte nicht auftauchen - Programmfehler - Keine Tool-Definition erstellt für Werkzeug in Zeile {index+1}")
				
	# Filtere None-Einträge heraus
	tools_paths = [path for path in tools_paths if path]

	# Erstelle die Library-Datei
	create_library_file(tools_paths, config)

if __name__ == "__main__":
	main()


