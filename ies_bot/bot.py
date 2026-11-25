# -*- coding: utf-8 -*-
"""Lógica del bot (árbol numérico, búsqueda con sinónimos y atajos). PURA: sin Streamlit.

Punto de entrada: `procesar_mensaje()`, que recibe el texto del alumno y devuelve una `Respuesta`
que la interfaz se encarga de dibujar. Nada de este módulo lee la planilla ni llama a la red:
recibe el `Arbol` ya armado. Tests: `tests/test_bot.py`."""
from __future__ import annotations

import difflib
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    CAMPOS_CONTACTO, COMANDOS_AYUDA, COMANDOS_MENU, COMANDOS_VOLVER, CONTACTO_GENERICO,
    ETIQUETAS_CONTACTO, FACTOR_GANADOR, FALLOS_PARA_DERIVAR, ICONOS_POR_PALABRA,
    ICONO_DEFECTO, ID_RAIZ, INTENCIONES_CONTACTO, LLM_CANDIDATOS, LLM_MIN_PALABRAS,
    MAX_SUGERENCIAS, PALABRAS_DESPEDIDA, PALABRAS_SALUDO, PALABRAS_VACIAS, PUNTAJE_DIRECTO,
    PUNTAJE_TITULO, SINONIMOS,
)
from .privacidad import anonimizar_consulta


@dataclass
class Arbol:
    """Índices en memoria del árbol de decisiones."""
    por_id: Dict[str, Dict[str, Any]]          # id → nodo
    hijos: Dict[str, List[Dict[str, Any]]]     # padre_id → hijos ordenados por 'opcion'


def _clave_orden(nodo: Dict[str, Any]) -> Tuple[int, Any]:
    """Orden numérico de las opciones (1, 2, ..., 10). Las no numéricas van al final."""
    op = nodo["opcion"]
    return (0, int(op)) if op.isdigit() else (1, op)


def construir_arbol(nodos: List[Dict[str, Any]]) -> Arbol:
    """
    Indexa la lista plana de filas del Sheets como un árbol.
    Si un `id` está repetido se conserva la PRIMERA fila y se ignoran las demás.
    """
    por_id: Dict[str, Dict[str, Any]] = {}
    for nodo in nodos:
        por_id.setdefault(nodo["id"], nodo)
    hijos: Dict[str, List[Dict[str, Any]]] = {}
    for nodo in por_id.values():
        hijos.setdefault(nodo["padre_id"], []).append(nodo)
    for lista in hijos.values():
        lista.sort(key=_clave_orden)
    return Arbol(por_id=por_id, hijos=hijos)


def auditar_nodos(nodos: List[Dict[str, Any]]) -> List[str]:
    """Problemas de carga en el Sheets (ids repetidos, opciones repetidas, padres inexistentes)."""
    problemas: List[str] = []
    ids = [n["id"] for n in nodos]
    for i in sorted({i for i in ids if ids.count(i) > 1}):
        problemas.append(f"id repetido: «{i}» (se usa solo la primera fila).")
    arbol = construir_arbol(nodos)
    for padre, hermanos in arbol.hijos.items():
        ops = [h["opcion"] for h in hermanos]
        for op in sorted({o for o in ops if ops.count(o) > 1}):
            problemas.append(f"opción repetida: «{op}» dentro de «{padre}».")
        if padre != ID_RAIZ and padre not in arbol.por_id:
            problemas.append(f"padre_id inexistente: «{padre}» (sus filas quedan inalcanzables).")

    # Filas a las que no se llega desde el menú principal por un ciclo (ej. padre_id = id).
    alcanzables, pila = set(), [ID_RAIZ]
    while pila:
        for hijo in arbol.hijos.get(pila.pop(), []):
            if hijo["id"] not in alcanzables:
                alcanzables.add(hijo["id"])
                pila.append(hijo["id"])
    en_ciclo = [i for i, n in arbol.por_id.items() if i not in alcanzables and n["padre_id"] in arbol.por_id]
    if en_ciclo:
        problemas.append("filas inalcanzables por un ciclo en padre_id (ej. una fila que es su propio "
                         f"padre): {', '.join(en_ciclo)}.")

    # ids con puntos ("5.10.1") cuyo padre_id no coincide con el prefijo del id. Suele pasar cuando
    # Google Sheets convierte un texto como "5.10" en el número 5,1.
    for nodo in arbol.por_id.values():
        if "." in nodo["id"]:
            esperado = nodo["id"].rsplit(".", 1)[0]
            if esperado in arbol.por_id and nodo["padre_id"] != esperado:
                problemas.append(
                    f"posible padre_id incorrecto en «{nodo['id']}»: dice «{nodo['padre_id']}» pero por "
                    f"su id debería colgar de «{esperado}» (¿Sheets lo convirtió en número?)."
                )
    return problemas


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sin tildes ni puntuación en los bordes: '¡Menú!' → 'menu'."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip(" .,;:!¡?¿")


def _tokens(texto: str) -> List[str]:
    """Palabras útiles de un texto: normalizadas y sin conectores ni palabras de 1-2 letras."""
    return [
        p for p in re.findall(r"[a-z0-9]+", normalizar_texto(texto))
        if len(p) > 2 and p not in PALABRAS_VACIAS
    ]


def _coincide(a: str, b: str) -> bool:
    """Dos palabras equivalentes: iguales, de la misma raíz (≥ 4 letras) o casi iguales."""
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    if a.startswith(b) or b.startswith(a):
        return True
    comun = len(os.path.commonprefix([a, b]))
    if comun >= 4 and comun >= 0.75 * min(len(a), len(b)) and abs(len(a) - len(b)) <= 2:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def _conceptos(texto: str) -> List[List[str]]:
    """Cada palabra útil de la consulta junto con sus sinónimos (un 'concepto' = un grupo)."""
    return [[p, *SINONIMOS.get(p, ())] for p in _tokens(texto)]


def puntuar_opciones(texto: str, arbol: Arbol) -> List[Tuple[int, Dict[str, Any]]]:
    """Búsqueda por palabras clave para texto libre. Devuelve [(puntaje, nodo)] de mejor a peor."""
    conceptos = _conceptos(texto)
    if not conceptos:
        return []
    resultados: List[Tuple[int, Dict[str, Any]]] = []
    for nodo in arbol.por_id.values():
        campos = (
            (4, set(_tokens(nodo.get("palabras_clave", "")))),
            (3, set(_tokens(nodo["titulo"]))),
            (2, set(_tokens(" ".join(t for t, _ in nodo["links"])))),
            (1, set(_tokens(nodo["respuesta"]))),
        )
        mejores: List[int] = []
        for grupo in conceptos:
            mejor = 0
            for peso, palabras in campos:
                if any(_coincide(c, p) for c in grupo for p in palabras):
                    mejor = peso
                    break
            mejores.append(mejor)
        puntaje = sum(mejores)
        if not puntaje:
            continue
        if len(conceptos) > 1 and all(mejores):
            puntaje += 2
        ancestros = set(_tokens(" ".join(ruta_nodo(nodo["padre_id"], arbol)[1:])))
        puntaje += sum(
            1 for grupo, m in zip(conceptos, mejores)
            if not m and any(_coincide(c, p) for c in grupo for p in ancestros)
        )
        resultados.append((puntaje, nodo))
    resultados.sort(key=lambda r: (-r[0], _clave_orden(r[1])))
    return resultados


def _profundidad(nodo: Dict[str, Any], arbol: Arbol) -> int:
    """Nivel del nodo en el menú (1 = menú principal)."""
    return len(ruta_nodo(nodo["id"], arbol))


def tema_ganador(puntuados: List[Tuple[int, Dict[str, Any]]], arbol: Arbol) -> Optional[Dict[str, Any]]:
    """
    Desempata cuando un TEMA entero coincide con la consulta.

    Ejemplo: "pasantías" coincide con «Pasantías y Empleo» y con sus tres hijas (9.1, 9.2, 9.3). Las
    cuatro empatan en puntaje, pero no compiten entre sí: son un mismo tema del menú. Entre los
    nodos que empatan en el primer puesto se busca uno que sea ANCESTRO de otros (el tema); si al
    menos dos tercios de los empatados cuelgan de él (o son él), se devuelve para abrirlo: el alumno
    ve la descripción del tema y sus hijas como opciones. Si no hay un tema claro devuelve None y el
    bot sigue con sus sugerencias de siempre. Ante la duda NO decide: es una regla conservadora.
    """
    if len(puntuados) < 2 or puntuados[0][0] < PUNTAJE_DIRECTO:
        return None
    empatados = [n for p, n in puntuados if p == puntuados[0][0]]
    ids = {n["id"] for n in empatados}
    cobertura: Dict[str, int] = {}                 # tema candidato → cuántos empatados cuelgan de él
    for nodo in empatados:
        actual, visto = nodo["padre_id"], set()
        while actual in arbol.por_id and actual not in visto:
            visto.add(actual)
            if actual in ids:
                cobertura[actual] = cobertura.get(actual, 0) + 1
            actual = arbol.por_id[actual]["padre_id"]
    if not cobertura:
        return None
    tema = max(cobertura, key=lambda i: (cobertura[i], -_profundidad(arbol.por_id[i], arbol)))
    dentro = 1 + cobertura[tema]
    fuera = len(empatados) - dentro
    return arbol.por_id[tema] if dentro >= 2 * fuera else None


def buscar_opciones(texto: str, arbol: Arbol, limite: int = MAX_SUGERENCIAS) -> List[Dict[str, Any]]:
    return [nodo for _, nodo in puntuar_opciones(texto, arbol)[:limite]]


def icono_nodo(nodo: Dict[str, Any]) -> str:
    if nodo.get("icono"):
        return nodo["icono"]
    palabras = _tokens(nodo["titulo"])
    for claves, icono in ICONOS_POR_PALABRA:
        if any(p.startswith(c) for p in palabras for c in claves):
            return icono
    return ICONO_DEFECTO


def ruta_nodo(nodo_id: str, arbol: Arbol) -> List[str]:
    """Migas de pan: ['Inicio', 'Trámites administrativos', ...] hasta el nodo indicado."""
    ruta: List[str] = []
    visto = set()
    while nodo_id != ID_RAIZ and nodo_id in arbol.por_id and nodo_id not in visto:
        visto.add(nodo_id)
        ruta.append(arbol.por_id[nodo_id]["titulo"])
        nodo_id = arbol.por_id[nodo_id]["padre_id"]
    return ["Inicio"] + ruta[::-1]


@dataclass
class Respuesta:
    """Resultado de procesar un mensaje; la UI decide cómo dibujarlo."""
    texto: str                                   
    nodo: str                                    
    links: List[Tuple[str, str]] = field(default_factory=list)         
    sugerencias: List[Tuple[str, str]] = field(default_factory=list)   
    fallo: bool = False                          
    usar_llm: bool = False                       
    consulta_llm: str = ""                       
    candidatos: List[str] = field(default_factory=list)   


def _texto_nodo(nodo: Dict[str, Any], hoja: bool) -> str:
    partes = [f"**{nodo['titulo']}**"]
    if nodo["respuesta"]:
        partes.append(nodo["respuesta"].replace("\n", "  \n"))
    elif hoja and not nodo["links"]:
        partes.append("Por el momento no hay información cargada para esta opción.")
    return "\n\n".join(partes)


def _respuesta_nivel(nodo_id: str, arbol: Arbol, config: Dict[str, str]) -> Respuesta:
    if nodo_id == ID_RAIZ:
        return Respuesta(config["mensaje_bienvenida"], ID_RAIZ)
    nodo = arbol.por_id[nodo_id]
    return Respuesta(_texto_nodo(nodo, hoja=False), nodo_id, list(nodo["links"]))


def _abrir_opcion(
    nodo: Dict[str, Any], nodo_actual: str, arbol: Arbol, config: Dict[str, str], salto: bool = False
) -> Respuesta:
    if arbol.hijos.get(nodo["id"]):
        return _respuesta_nivel(nodo["id"], arbol, config)
    destino = nodo_actual
    if salto:
        destino = nodo["padre_id"]
        if destino != ID_RAIZ and destino not in arbol.por_id:
            destino = ID_RAIZ
    return Respuesta(_texto_nodo(nodo, hoja=True), destino, list(nodo["links"]))


# --- Comandos y atajos --------------------------------------------------------

def _es_saludo(palabras: List[str]) -> bool:
    return bool(palabras) and all(p in PALABRAS_SALUDO for p in palabras)

def _es_despedida(palabras: List[str]) -> bool:
    return len(palabras) <= 5 and any(p in PALABRAS_DESPEDIDA for p in palabras)

def _extraer_numero(t: str) -> Optional[str]:
    m = re.fullmatch(r"(?:(?:la |el )?(?:opcion|numero|nro|num)\.? ?|la |el )?(\d{1,3})", t)
    return m.group(1) if m else None

def _datos_contacto(config: Dict[str, str], claves: Any) -> List[str]:
    return [
        f"{CAMPOS_CONTACTO[c]} **{ETIQUETAS_CONTACTO[c]}:** {config[c]}"
        for c in claves if config.get(c)
    ]

def _respuesta_ayuda(nodo_actual: str, config: Dict[str, str]) -> Respuesta:
    texto = config["mensaje_ayuda"]
    if _datos_contacto(config, CAMPOS_CONTACTO):
        texto += "\n- Escribí **contacto**, **horarios** o **dirección** y te paso los datos del Instituto."
    return Respuesta(texto, nodo_actual)

def _respuesta_contacto(t: str, nodo_actual: str, config: Dict[str, str]) -> Optional[Respuesta]:
    palabras = set(re.findall(r"[a-z0-9]+", t))
    pedidos = [c for c, claves in INTENCIONES_CONTACTO.items() if palabras & set(claves)]
    if not pedidos and not (palabras & set(CONTACTO_GENERICO)):
        return None
    todos = _datos_contacto(config, CAMPOS_CONTACTO)
    if not todos:
        return None
    puntuales = _datos_contacto(config, pedidos)
    if puntuales:
        lineas, intro = puntuales, "Acá lo tenés 👇"
    elif pedidos:
        lineas, intro = todos, "No tengo ese dato puntual, pero estos son los canales del Instituto 👇"
    else:
        lineas, intro = todos, "Estos son los datos de contacto del Instituto 👇"
    return Respuesta(f"{intro}\n\n" + "  \n".join(lineas), nodo_actual)

def _respuesta_fallo(texto: str, nodo_actual: str, config: Dict[str, str], fallos_previos: int) -> Respuesta:
    if fallos_previos + 1 >= FALLOS_PARA_DERIVAR:
        datos = _datos_contacto(config, CAMPOS_CONTACTO)
        if datos:
            texto += "\n\nSi preferís, comunicate directamente con el Instituto:\n\n" + "  \n".join(datos)
        else:
            texto += "\n\nSi no encontrás lo que buscás, consultá directamente en secretaría."
    return Respuesta(texto, nodo_actual, fallo=True)

# Con un EMPATE real entre temas distintos (sin tema ganador) se le pasa la consulta a la IA aunque
# tenga 1 o 2 palabras, con los empatados como candidatos. Si la IA no está disponible, se agotó la
# cuota o falla, la interfaz muestra las sugerencias de siempre.
MIN_PALABRAS_IA_EMPATE = 1
MAX_CANDIDATOS_EMPATE = 8


def _con_ia(
    resp: Respuesta, texto: str, palabras: List[str],
    puntuados: List[Tuple[int, Dict[str, Any]]], llm_disponible: bool,
    min_palabras: int = LLM_MIN_PALABRAS, max_candidatos: int = LLM_CANDIDATOS,
) -> Respuesta:
    if llm_disponible and len(palabras) >= min_palabras:
        resp.usar_llm = True
        resp.consulta_llm = anonimizar_consulta(texto)
        resp.candidatos = [n["id"] for _, n in puntuados[:max_candidatos]]
    return resp


def procesar_mensaje(
    texto: str, nodo_actual: str, arbol: Arbol, config: Dict[str, str],
    ir_a: Optional[str] = None, fallos_previos: int = 0, llm_disponible: bool = False,
) -> Respuesta:
    """Núcleo del bot. Evalúa comandos, menú y texto libre."""
    if nodo_actual != ID_RAIZ and nodo_actual not in arbol.por_id:
        nodo_actual = ID_RAIZ

    if ir_a and ir_a in arbol.por_id:
        return _abrir_opcion(arbol.por_id[ir_a], nodo_actual, arbol, config, salto=True)

    t = normalizar_texto(texto)
    palabras = re.findall(r"[a-z0-9]+", t)

    if not t:
        return _respuesta_ayuda(nodo_actual, config)

    if t in COMANDOS_MENU or _es_saludo(palabras):
        return _respuesta_nivel(ID_RAIZ, arbol, config)

    if t in COMANDOS_VOLVER:
        padre = ID_RAIZ if nodo_actual == ID_RAIZ else arbol.por_id[nodo_actual]["padre_id"]
        if padre != ID_RAIZ and padre not in arbol.por_id:
            padre = ID_RAIZ
        return _respuesta_nivel(padre, arbol, config)

    if t in COMANDOS_AYUDA:
        return _respuesta_ayuda(nodo_actual, config)

    if _es_despedida(palabras):
        return Respuesta(config["mensaje_despedida"], nodo_actual)

    # --- Selección numérica -------------------------------------------------
    numero = _extraer_numero(t)
    clave = numero if numero is not None else t
    hijos = arbol.hijos.get(nodo_actual, [])
    elegido = next((h for h in hijos if normalizar_texto(h["opcion"]) == clave), None)
    if elegido is not None:
        return _abrir_opcion(elegido, nodo_actual, arbol, config)

    if not t.isdigit():
        por_id = next((n for n in arbol.por_id.values() if normalizar_texto(n["id"]) == t), None)
        if por_id is not None:
            return _abrir_opcion(por_id, nodo_actual, arbol, config, salto=True)

    # Título escrito tal cual (ej. "Beca Progresar"): se abre ese nodo sin pasar por la búsqueda.
    # Si el mismo título se repite (ej. "Materias y Plan de Estudios" en cada carrera), se elige el
    # que cuelga del menú donde está el alumno; si sigue habiendo duda, decide la búsqueda.
    if not t.isdigit():
        iguales = [n for n in arbol.por_id.values() if normalizar_texto(n["titulo"]) == t]
        if len(iguales) > 1:
            iguales = [n for n in iguales if n["padre_id"] == nodo_actual]
        if len(iguales) == 1:
            return _abrir_opcion(iguales[0], nodo_actual, arbol, config, salto=True)

    if numero is not None:
        validas = ", ".join(h["opcion"] for h in hijos)
        aviso = (
            f"La opción **{numero}** no existe en este menú. Elegí una de estas: **{validas}** "
            "(o **0** para volver al inicio)."
            if validas else "Este menú no tiene opciones numeradas. Escribí **0** para volver al inicio."
        )
        return _respuesta_fallo(aviso, nodo_actual, config, fallos_previos)

    # --- Texto libre --------------------------------------------------------
    puntuados = puntuar_opciones(texto, arbol)

    if not any(p >= PUNTAJE_TITULO for p, _ in puntuados):
        contacto = _respuesta_contacto(t, nodo_actual, config)
        if contacto is not None:
            return contacto

    if puntuados:
        mejor, segundo = puntuados[0], (puntuados[1][0] if len(puntuados) > 1 else 0)
        unico = len(puntuados) == 1

        # 📌 CORRECCIÓN CLAVE PARA LA IA:
        # Si la consulta tiene 3 o más palabras y Gemini está encendido,
        # FORZAMOS que pase por la IA en lugar de mostrar la tarjeta directa del Excel.
        # Esto permite que Gemini parafrasee y conteste como un humano.
        if llm_disponible and len(palabras) >= LLM_MIN_PALABRAS:
            sugerencias = [(n["id"], n["titulo"]) for _, n in puntuados[:MAX_SUGERENCIAS]]
            resp = Respuesta(config["mensaje_sugerencias"], nodo_actual, sugerencias=sugerencias)
            return _con_ia(resp, texto, palabras, puntuados, llm_disponible)

        # Si son 1 o 2 palabras (ej. "becas", "software"), mantenemos la velocidad del botón directo:
        if unico or (mejor[0] >= PUNTAJE_DIRECTO and mejor[0] >= FACTOR_GANADOR * segundo):
            resp = _abrir_opcion(mejor[1], nodo_actual, arbol, config, salto=True)
            resp.texto = "Esto es lo que encontré 👇\n\n" + resp.texto
            return resp

        # Empate entre un tema y sus propias hijas (ej. "pasantías"): se abre el tema.
        tema = tema_ganador(puntuados, arbol)
        if tema is not None:
            resp = _abrir_opcion(tema, nodo_actual, arbol, config, salto=True)
            resp.texto = "Esto es lo que encontré 👇\n\n" + resp.texto
            return resp

        sugerencias = [(n["id"], n["titulo"]) for _, n in puntuados[:MAX_SUGERENCIAS]]
        resp = Respuesta(config["mensaje_sugerencias"], nodo_actual, sugerencias=sugerencias)
        empatados = sum(1 for p, _ in puntuados if p == puntuados[0][0])
        return _con_ia(resp, texto, palabras, puntuados, llm_disponible,
                       min_palabras=MIN_PALABRAS_IA_EMPATE,
                       max_candidatos=min(max(LLM_CANDIDATOS, empatados), MAX_CANDIDATOS_EMPATE))

    resp = _respuesta_fallo(config["mensaje_error"], nodo_actual, config, fallos_previos)
    return _con_ia(resp, texto, palabras, puntuados, llm_disponible)