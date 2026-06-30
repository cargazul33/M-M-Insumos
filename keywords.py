"""Listas de palabras clave para clasificación.

Se externalizan acá para que puedas ajustarlas sin tocar la lógica.
Todo se compara en minúsculas y sin tildes (ver parsing.classifier.normalizar).
"""

from __future__ import annotations

# Rubros que NUNCA le sirven a M&M -> descarte duro.
EXCLUIR_DURO = [
    "ministerio de salud", "hospital", "medicamento", "farmacia", "insumo medico",
    "consejo provincial de educacion", "c.p.e", "cpe",
    "alimento", "comida", "viveres", "racion", "catering",
    "obra publica", "construccion", "demolicion", "pavimento",
    "combustible", "nafta", "gasoil", "neumatico",
    "seguro", "poliza", "alquiler de inmueble", "locacion de inmueble",
]

# Rubros núcleo de M&M -> cotizar fuerte.
COTIZAR_FUERTE = [
    "resma", "papel a4", "toner", "cartucho", "tinta",
    "impresora", "multifuncion", "scanner", "escaner",
    "notebook", "computadora", "pc de escritorio", "pc escritorio",
    "monitor", "teclado", "mouse", "webcam", "auricular",
    "pendrive", "memoria usb", "disco externo", "disco rigido", "ssd", "hdd",
    "router", "switch", "rack", "cable utp", "patch cord", "access point",
    "starlink", "ups", "estabilizador",
    "insumos informaticos", "equipamiento informatico", "hardware",
    "libreria", "papeleria", "utiles de oficina",
    "videovigilancia", "videoseguridad", "camara de seguridad",
]

# Rubros que pueden servir según proveedor / lote -> revisar.
REVISAR = [
    "aire acondicionado", "split", "climatizacion",
    "mobiliario", "silla", "escritorio", "armario", "estanteria",
    "proyector", "pantalla", "televisor", "smart tv",
    "materiales electricos", "ferreteria", "iluminacion", "tubo led", "lampara",
    "herramienta", "taladro", "amoladora",
    "limpieza", "articulos de limpieza", "bazar", "menaje",
]

# Pistas de que un renglón es un SERVICIO (mano de obra), no un bien -> baja prioridad.
SERVICIOS = [
    "servicio de", "mano de obra", "instalacion", "puesta en marcha",
    "mantenimiento", "reparacion", "capacitacion", "consultoria",
    "abono mensual", "tracto sucesivo",
]

# Claves para detectar líneas que parecen renglones dentro de un texto largo.
CLAVES_RENGLON = [
    "rengl", "item", "cantidad", "descripcion", "unidad",
    "marca sugerida", "especificacion",
    "resma", "toner", "cartucho", "impresora", "notebook", "computadora",
    "monitor", "mouse", "teclado", "router", "switch", "starlink",
    "escritorio", "silla", "disco", "estabilizador", "ups",
]
