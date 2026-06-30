"""Extrae estructura de un renglón de pliego: tipo, código, cantidad, specs,
y arma la query de búsqueda para proveedores de Paraguay/Argentina.

Port limpio del structured_extractor de la V2, integrado con el clasificador.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from radar.parsing.classifier import clasificar_renglon, normalizar


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").replace("\n", " ")).strip()


def _quitar_prefijo_basura(texto: str) -> str:
    """Quita dígitos/puntuación sueltos al inicio (ej. cantidad que se filtró
    de la línea anterior: '1 12 COMPUTADORA' -> 'COMPUTADORA')."""
    return re.sub(r"^[\d\.\-\s]+(?=[A-Za-zÁÉÍÓÚÑ])", "", texto or "").strip()


def _normalizar_clave(campo: str) -> str:
    return normalizar(campo).replace(" ", "_")


def extraer_codigo(texto: str) -> str:
    t = (texto or "").upper()
    m = re.search(r"C[ÓO]DIGO\s+([A-Z]{1,4}\d{2,5}[A-Z]?)", t)
    if m:
        return m.group(1)
    codigos = re.findall(
        r"\b(CE\d{3,4}A|CF\d{3,4}A|MP\d{3,4}|TN\d{3,5}|DR\d{3,5}|CRG\d{3,5})\b", t
    )
    return codigos[0] if codigos else ""


def extraer_marca_sugerida(texto: str) -> str:
    m = re.search(r"Marca Sugerida:\s*(.*?)(?:\s+-\s+|$)", texto or "", flags=re.I)
    return _limpiar(m.group(1)).replace("//", "/") if m else ""


def extraer_cantidad(texto: str) -> int | None:
    for p in (
        r"Cantidad\s*[:\-]?\s*(\d+)",
        r"Cant\s+Sol\s+(\d+)",
        r"cant:\s*(\d+)",
        r"\bItem\s+\d+\s+(\d+)\b",
    ):
        m = re.search(p, texto or "", flags=re.I)
        if m:
            return int(m.group(1))
    return None


def extraer_precio_oficial(texto: str) -> str:
    """Busca precio testigo / presupuesto oficial / precio estimado si el pliego lo trae."""
    patrones = [
        r"(?:precio\s+testigo|presupuesto\s+oficial|precio\s+estimad[oa]|"
        r"precio\s+unitario\s+estimad[oa]|valor\s+estimad[oa])\s*[:\-]?\s*"
        r"((?:Gs\.?|U\$S|US\$|USD|AR\$|\$)\s?[\d\.\,]+)",
    ]
    for p in patrones:
        m = re.search(p, texto or "", flags=re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def extraer_tipo_producto(texto: str) -> str:
    texto = _quitar_prefijo_basura(_limpiar(texto))
    if ";" in texto:
        return _quitar_prefijo_basura(texto.split(";")[0]).strip().upper()
    conocidos = [
        "CARTUCHO DE TONER", "COMPUTADORA", "NOTEBOOK", "MONITOR",
        "DISCO RIGIDO", "DISCO EXTERNO", "ESTABILIZADOR DE TENSION",
        "CABLE CONECTOR", "ESCRITORIO", "IMPRESORA", "AIRE ACONDICIONADO",
        "ROUTER", "SWITCH", "RESMA", "TUBO LED",
    ]
    t = texto.upper()
    for k in conocidos:
        if k in t:
            return k
    return texto[:60].upper()


def _extraer_valor(campo: str, texto: str) -> str:
    patron = rf"{re.escape(campo)}\s+(.+?)(?:\s+-\s+|$)"
    m = re.search(patron, texto or "", flags=re.I)
    return _limpiar(m.group(1)) if m else ""


def extraer_especificaciones(texto: str) -> dict[str, str]:
    campos = [
        "Tipo", "Color", "Uso", "Memoria", "Disco", "Microprocesador",
        "Tamaño", "Tecnología", "Resolución", "Interfaz", "Potencia",
        "Tensión De Entrada", "Tensión De Salida", "Material", "Capacidad",
    ]
    specs: dict[str, str] = {}
    for campo in campos:
        valor = _extraer_valor(campo, texto)
        if valor:
            specs[_normalizar_clave(campo)] = valor
    # Normalizaciones conocidas
    if "memoria" in specs:
        specs["ram"] = specs.pop("memoria").replace("DDR4320", "DDR4 3200")
    if "microprocesador" in specs:
        specs["cpu"] = specs.pop("microprocesador")
    return specs


def construir_busqueda(tipo: str, texto: str, specs: dict, pais: str = "PY") -> str:
    codigo = extraer_codigo(texto)
    marca = extraer_marca_sugerida(texto)
    tipo_up = tipo.upper()

    if codigo:
        base = f"{marca} {codigo}".strip() if marca else codigo
    elif "COMPUTADORA" in tipo_up or "NOTEBOOK" in tipo_up:
        base = " ".join(
            p for p in ["pc", specs.get("cpu", ""), specs.get("ram", ""),
                        specs.get("almacenamiento", "")] if p
        ) or "pc escritorio"
    elif "DISCO" in tipo_up:
        base = "disco externo"
    elif "MONITOR" in tipo_up:
        base = " ".join(
            p for p in ["monitor", specs.get("tamano", ""),
                        specs.get("resolucion", "")] if p
        )
    elif "ESTABILIZADOR" in tipo_up:
        base = f"estabilizador automatico {specs.get('potencia', '')}".strip()
    else:
        base = tipo

    base = _limpiar(base)
    sufijo = " Argentina" if pais == "AR" else " Paraguay Ciudad del Este"
    return _limpiar(base + sufijo)


@dataclass
class Renglon:
    texto_original: str
    producto: str
    codigo: str
    cantidad: int | None
    marca_sugerida: str
    rubro: str
    decision: str
    puntaje: int
    especificaciones: dict = field(default_factory=dict)
    buscar_py: str = ""
    buscar_ar: str = ""
    compatible_mm: bool = True
    requiere_servicio: bool = False
    renglon_mixto: bool = False
    precio_oficial: str = ""
    archivo: str | None = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def estructurar_renglon(texto: str, archivo: str | None = None) -> Renglon:
    texto = _quitar_prefijo_basura(_limpiar(texto))
    tipo = extraer_tipo_producto(texto)
    specs = extraer_especificaciones(texto)
    clasif = clasificar_renglon(texto)

    r = Renglon(
        texto_original=texto,
        producto=tipo,
        codigo=extraer_codigo(texto),
        cantidad=extraer_cantidad(texto),
        marca_sugerida=extraer_marca_sugerida(texto),
        rubro=clasif.rubro,
        decision=clasif.decision,
        puntaje=clasif.puntaje,
        especificaciones=specs,
        archivo=archivo,
    )
    r.buscar_py = construir_busqueda(tipo, texto, specs, "PY")
    r.buscar_ar = construir_busqueda(tipo, texto, specs, "AR")
    r.compatible_mm = clasif.decision != "DESCARTAR"

    # Renglón mixto: el bien viene con servicio/instalación/garantía (Prompt Maestro).
    from radar.keywords import SERVICIOS
    from radar.parsing.classifier import normalizar as _norm
    t_norm = _norm(texto)
    r.requiere_servicio = any(s in t_norm for s in SERVICIOS)
    r.renglon_mixto = r.requiere_servicio and r.decision != "DESCARTAR"
    r.precio_oficial = extraer_precio_oficial(texto)
    return r


def estructurar_renglones(textos: list[str], archivo: str | None = None) -> list[Renglon]:
    salida: list[Renglon] = []
    vistos: set[str] = set()
    for t in textos or []:
        r = estructurar_renglon(t, archivo=archivo)
        clave = f"{r.producto}|{r.codigo}|{r.buscar_py}".lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        salida.append(r)
    return salida
