# app.py
import streamlit as st
import re
import json
import os
import random
import calendar
from datetime import date, datetime
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup

from docx import Document
from docx.shared import Pt
from docx.enum.style import WD_STYLE_TYPE

# Intenta cargar instaloader (para extraer captions de Instagram)
try:
    import instaloader
    HAS_INSTALOADER = True
except Exception:
    HAS_INSTALOADER = False

# ========== Configuración de página ==========
st.set_page_config(page_title="Recetario + Plan mensual", page_icon="🍽️", layout="wide")
st.title("📚 Recetario desde Instagram/TikTok + 📅 Plan mensual")

# ---------- Inicialización de estado seguro (no perder datos del formulario) ----------
def init_form_state():
    defaults = {
        "link": "",
        "caption_manual": "",
        "titulo": "",
        "porciones": "No especificado",
        "tiempo": "",
        "ingredientes_text": "",
        "procedimiento_text": "",
        "categoria": "Seleccionar opción",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_form_state()

# ========== Utilidades de almacenamiento ==========
RECETAS_FILE = "recetas.json"

def cargar_recetas(nombre_archivo: str = RECETAS_FILE) -> List[Dict[str, Any]]:
    if not os.path.exists(nombre_archivo):
        return []
    with open(nombre_archivo, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []

def guardar_recetas(lista_recetas: List[Dict[str, Any]], nombre_archivo: str = RECETAS_FILE) -> None:
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(lista_recetas, f, ensure_ascii=False, indent=4)

# ========== Estilos DOCX ==========
def asegurar_estilos_docx(doc: Document):
    styles = doc.styles
    if 'Titulo1' not in styles:
        s1 = styles.add_style('Titulo1', WD_STYLE_TYPE.PARAGRAPH)
        s1.font.size = Pt(16); s1.font.bold = True
    if 'Titulo2' not in styles:
        s2 = styles.add_style('Titulo2', WD_STYLE_TYPE.PARAGRAPH)
        s2.font.size = Pt(14); s2.font.bold = True
    if 'Titulo3' not in styles:
        s3 = styles.add_style('Titulo3', WD_STYLE_TYPE.PARAGRAPH)
        s3.font.size = Pt(12); s3.font.bold = True

# ========== Helpers de texto ==========
def capitalizar_oracion(texto: str) -> str:
    if not texto:
        return texto
    return texto[0].upper() + texto[1:]

# ========== Extracción IG / TikTok ==========
def ig_shortcode_from_url(url: str) -> Optional[str]:
    """
    Extrae el shortcode del URL de Instagram (reels, posts).
    Ej: https://www.instagram.com/reel/DM7IUz9NUv8/ -> DM7IUz9NUv8
    """
    try:
        parts = [p for p in url.split("/") if p.strip()]
        for p in reversed(parts):
            if re.fullmatch(r"[A-Za-z0-9_-]{5,20}", p):
                return p
        return None
    except Exception:
        return None

def get_instagram_caption(url: str) -> str:
    """
    Intenta obtener el caption:
    1) instaloader (si disponible y el post es público)
    2) fallback: open graph meta description
    """
    # 1) instaloader
    if HAS_INSTALOADER:
        try:
            L = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False
            )
            shortcode = ig_shortcode_from_url(url)
            if shortcode:
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                if post and post.caption:
                    return post.caption
        except Exception:
            pass

    # 2) Fallback BeautifulSoup (no siempre funciona por protecciones de IG)
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name":"description"})
        if meta and meta.get("content"):
            return meta["content"]
    except Exception:
        pass

    return ""  # vacío -> permitirá pegar manualmente

# ========== Parseo de recetas desde caption (ES/EN) ==========
def clean_bullet(text: str) -> str:
    """Limpia caracteres de viñeta/guiones al inicio de la línea."""
    return re.sub(r"^[\-\•\●\·\*]+\s*", "", text).strip()

def extract_recipe_sections(text: str) -> Dict[str, str]:
    """Extrae secciones de una receta en inglés a partir de la estructura básica."""
    sections = {"title": "", "servings": "", "time": "", "ingredients": "", "method": ""}

    lines = text.split("\n")
    method_started = False
    ingredients_started = False
    method_lines = []
    ingredient_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if sections["title"] == "":
            sections["title"] = line
            continue

        if line.lower().startswith("serves"):
            sections["servings"] = line
            continue

        if line.lower().startswith("takes"):
            sections["time"] = line
            continue

        if line.lower().startswith("ingredients"):
            ingredients_started = True
            method_started = False
            continue

        if ingredients_started and not line.lower().startswith("method"):
            ingredient_lines.append(line)
            continue

        if line.lower().startswith("method"):
            method_started = True
            ingredients_started = False
            continue

        if method_started:
            method_lines.append(line)

    sections["ingredients"] = "\n".join(ingredient_lines)
    sections["method"] = "\n".join(method_lines)
    return sections

def parse_recipe_from_caption(caption: str) -> Dict[str, Any]:
    """
    Separa título, porciones, tiempo, ingredientes y método.
    Soporta EN/ES (Ingredients:, Method:, Ingredientes:, Preparación:/Procedimiento:).
    """
    rec = {"titulo": "", "porciones": "", "tiempo": "", "ingredientes": [], "procedimiento": []}
    if not caption:
        return rec

    # Título = primera línea no vacía
    lines = [l.strip() for l in caption.split("\n")]
    first_nonempty = next((l for l in lines if l), "")
    rec["titulo"] = first_nonempty

    # Porciones / Serves
    m_serves = re.search(r"(Serves|Porciones|Rinde)\s*[:\-]?\s*([0-9]+)", caption, flags=re.IGNORECASE)
    if m_serves:
        rec["porciones"] = m_serves.group(2).strip()

    # Tiempo / Takes
    m_time = re.search(r"(Takes|Tiempo)\s*[:\-]?\s*([0-9]+\s*\w+)", caption, flags=re.IGNORECASE)
    if m_time:
        rec["tiempo"] = m_time.group(2).strip()

    # EN primero
    ing_split = re.split(r"(Ingredients?:)", caption, flags=re.IGNORECASE)
    if len(ing_split) >= 3:
        after_ing = "".join(ing_split[2:])
        before_method = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)[0]
        rec["ingredientes"] = [clean_bullet(x) for x in before_method.split("\n") if x.strip()]

        method_part = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)
        if len(method_part) >= 4:
            method_text = "".join(method_part[3:])
            rec["procedimiento"] = [clean_bullet(x) for x in method_text.split("\n") if x.strip()]
    else:
        # ES
        ing_split_es = re.split(r"(Ingredientes?:)", caption, flags=re.IGNORECASE)
        if len(ing_split_es) >= 3:
            after_ing = "".join(ing_split_es[2:])
            before_method = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)[0]
            rec["ingredientes"] = [clean_bullet(x) for x in before_method.split("\n") if x.strip()]

            method_part = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)
            if len(method_part) >= 4:
                method_text = "".join(method_part[3:])
                rec["procedimiento"] = [clean_bullet(x) for x in method_text.split("\n") if x.strip()]

    # Refuerzo con el extractor de secciones EN (para casos rebeldes)
    sections = extract_recipe_sections(caption)
    if sections.get("ingredients") and not rec["ingredientes"]:
        rec["ingredientes"] = [clean_bullet(x) for x in sections["ingredients"].split("\n") if x.strip()]
    if sections.get("method") and not rec["procedimiento"]:
        rec["procedimiento"] = [clean_bullet(x) for x in sections["method"].split("\n") if x.strip()]

    return rec

# ========== Exportar recetas a Word ==========
def exportar_recetas_a_word(recetas: List[Dict[str, Any]], nombre_archivo: str = "recetas_exportadas.docx") -> str:
    doc = Document()
    asegurar_estilos_docx(doc)

    categorias = sorted(set([r.get('categoria', 'Sin categoría') for r in recetas]))
    for categoria in categorias:
        doc.add_paragraph(categoria, style='Titulo1')
        recetas_categoria = [r for r in recetas if r.get('categoria') == categoria]
        for r in recetas_categoria:
            doc.add_paragraph(r.get('titulo', 'Sin título'), style='Titulo2')
            por = r.get('porciones', 'No especificado')
            tie = r.get('tiempo', r.get('tiempo_preparacion', ''))
            if tie:
                doc.add_paragraph(f"Porciones: {por} | Tiempo: {tie}", style='Titulo3')
            else:
                doc.add_paragraph(f"Porciones: {por}", style='Titulo3')

            doc.add_paragraph("Ingredientes:", style='Titulo3')
            for ing in r.get('ingredientes', []):
                doc.add_paragraph(ing, style='Normal')

            doc.add_paragraph("Procedimiento:", style='Titulo3')
            pasos = r.get('procedimiento', [])
            for i, paso in enumerate(pasos, 1):
                if re.match(r"^\d+\.", paso.strip()):
                    doc.add_paragraph(paso, style='Normal')
                else:
                    doc.add_paragraph(f"{i}. {paso}", style='Normal')
            doc.add_paragraph("")  # espacio

    doc.save(nombre_archivo)
    return nombre_archivo

# ========== Detección de familia de proteína ==========
PROTEIN_FAMILIES = {
    "pollo/ave": [
        "pollo", "chicken", "pechuga", "muslo", "ala", "pavo", "turkey", "hen", "gallina"
    ],
    "res": [
        "res", "carne de res", "beef", "ternera", "lomo de res", "brisket", "ossobuco", "solomo"
    ],
    "cerdo": [
        "cerdo", "pork", "tocino", "bacon", "lomo de cerdo", "costilla", "jamón"
    ],
    "pescado": [
        "pescado", "fish", "salmón", "salmon", "tilapia", "bacalao", "merluza", "atún", "tuna",
        "trucha", "corvina", "dorado", "pargo", "sardina"
    ],
    "mariscos": [
        "camarón", "camaron", "shrimp", "langostino", "calamar", "pulpo", "mejillón", "mejillon",
        "almeja", "ostión", "ostion", "cangrejo", "jaiba", "scallop", "vieira"
    ],
    "frijoles/legumbres": [
        "frijol", "frijoles", "beans", "garbanzo", "chickpea", "lenteja", "lentil", "habas",
        "poroto", "porotos", "alubia", "judía", "judia"
    ],
    "huevo": [
        "huevo", "huevos", "egg", "eggs"
    ],
    "soya/tofu": [
        "soya", "soja", "tofu", "tempeh", "edamame"
    ],
}
FAMILY_PRIORITY = list(PROTEIN_FAMILIES.keys()) + ["mixta/otra"]

def detectar_familia_proteina(ingredientes: List[str]) -> str:
    text = " ".join(ingredientes).lower()
    hits = []
    for fam, kws in PROTEIN_FAMILIES.items():
        for kw in kws:
            if kw in text:
                hits.append(fam)
                break
    if not hits:
        return "mixta/otra"
    for fam in FAMILY_PRIORITY:
        if fam in hits:
            return fam
    return hits[0]

# ========== Plan mensual ==========
def generar_plan_mensual(
    recetas: List[Dict[str, Any]],
    year: int,
    month: int,
    pescado_viernes: bool = True,
    frijoles_jueves: bool = True,
) -> List[Dict[str, Any]]:
    """
    Genera un plan día a día con reglas:
    - No repetir SOPA ni PROTEÍNA (familia) día consecutivo.
    - Si es viernes -> familia 'pescado' (si está activado y hay recetas).
    - Si es jueves -> familia 'frijoles/legumbres' (si está activado y hay recetas).
    """
    por_cat: Dict[str, List[Dict[str, Any]]] = {}
    for r in recetas:
        por_cat.setdefault(r.get("categoria", ""), []).append(r)

    sopas = por_cat.get("Sopa", [])
    proteinas = por_cat.get("Proteína", [])
    guarniciones = por_cat.get("Guarnición", [])
    arroces = por_cat.get("Arroz", [])
    ensaladas = por_cat.get("Ensalada", [])
    postres = por_cat.get("Postre", [])

    prot_ext = []
    for p in proteinas:
        fam = detectar_familia_proteina(p.get("ingredientes", []))
        prot_ext.append({**p, "_familia": fam})

    last_soup_title = None
    last_prot_family = None

    ndays = calendar.monthrange(year, month)[1]
    plan: List[Dict[str, Any]] = []

    for d in range(1, ndays + 1):
        day_date = date(year, month, d)
        weekday_idx = day_date.weekday()  # 0=Lunes ... 6=Domingo

        required_family: Optional[str] = None
        if pescado_viernes and weekday_idx == 4:
            required_family = "pescado"
        if frijoles_jueves and weekday_idx == 3:
            required_family = "frijoles/legumbres"

        day_menu: Dict[str, Any] = {}

        if sopas:
            soup_options = [s for s in sopas if s.get("titulo") != last_soup_title] or sopas
            sopa_pick = random.choice(soup_options)
            day_menu["Sopa"] = sopa_pick.get("titulo", "Sopa")
            last_soup_title = sopa_pick.get("titulo")

        prot_pool = prot_ext[:]
        if required_family:
            pool_req = [p for p in prot_pool if p["_familia"] == required_family]
            if pool_req:
                prot_pool = pool_req

        pool_no_rep = [p for p in prot_pool if p["_familia"] != last_prot_family] or prot_pool
        if pool_no_rep:
            p_pick = random.choice(pool_no_rep)
            day_menu["Proteína"] = f"{p_pick.get('titulo', 'Proteína')} (familia: {p_pick['_familia']})"
            last_prot_family = p_pick["_familia"]

        if guarniciones:
            g_pick = random.choice(guarniciones)
            day_menu["Guarnición"] = g_pick.get("titulo", "Guarnición")
        if arroces:
            a_pick = random.choice(arroces)
            day_menu["Arroz"] = a_pick.get("titulo", "Arroz")
        if ensaladas:
            e_pick = random.choice(ensaladas)
            day_menu["Ensalada"] = e_pick.get("titulo", "Ensalada")
        if postres:
            postre_pick = random.choice(postres)
            day_menu["Postre"] = postre_pick.get("titulo", "Postre")

        plan.append({
            "fecha": day_date.isoformat(),
            "dia_es": ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"][weekday_idx],
            "menu": day_menu,
            "notas": ""
        })

    return plan

def exportar_plan_a_word(plan: List[Dict[str, Any]], year: int, month: int) -> str:
    nombre = f"plan_mensual_{year}_{str(month).zfill(2)}.docx"
    doc = Document()
    asegurar_estilos_docx(doc)

    nombre_mes = [
        "", "Enero","Febrero","Marzo","Abril","Mayo","Junio",
        "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
    ][month]

    doc.add_paragraph(f"Plan de alimentación - {nombre_mes} {year}", style="Titulo1")

    for dia in plan:
        f = dia["fecha"]
        fecha_dt = datetime.fromisoformat(f)
        titulo_dia = f"{fecha_dt.strftime('%Y-%m-%d')} - {dia['dia_es']}"
        doc.add_paragraph(titulo_dia, style="Titulo2")

        for seccion in ["Sopa","Proteína","Guarnición","Arroz","Ensalada","Postre"]:
            if seccion in dia["menu"]:
                doc.add_paragraph(seccion + ":", style="Titulo3")
                doc.add_paragraph(dia["menu"][seccion], style="Normal")

        doc.add_paragraph("Notas:", style="Titulo3")
        doc.add_paragraph(dia.get("notas",""), style="Normal")
        doc.add_paragraph("")

    doc.save(nombre)
    return nombre

# ========== UI: Sidebar navegación ==========
pestanas = st.sidebar.radio(
    "Navegación",
    ["Nueva receta", "Ver recetas", "Exportar recetas", "Plan mensual"]
)

# ========== UI: Nueva receta (con estado persistente) ==========
if pestanas == "Nueva receta":
    st.header("Agregar nueva receta desde enlace (Instagram/TikTok)")

    st.text_input("Ingresa el link del post (Instagram o TikTok):", key="link")

    cA, cB, cC = st.columns([1,1,1])
    with cA:
        if st.button("Leer descripción del enlace"):
            if "instagram.com" in st.session_state.link:
                caption = get_instagram_caption(st.session_state.link)
                if caption:
                    st.session_state.caption_manual = caption
                    parsed = parse_recipe_from_caption(caption)
                    # Solo sobreescribir si el parser trajo algo
                    if parsed.get("titulo"): st.session_state.titulo = parsed["titulo"]
                    if parsed.get("porciones"): st.session_state.porciones = parsed["porciones"]
                    if parsed.get("tiempo"): st.session_state.tiempo = parsed["tiempo"]
                    if parsed.get("ingredientes"): st.session_state.ingredientes_text = "\n".join(parsed["ingredientes"])
                    if parsed.get("procedimiento"): st.session_state.procedimiento_text = "\n".join(parsed["procedimiento"])
                    st.success("Descripción leída y campos rellenados.")
                else:
                    st.warning("No se pudo leer automáticamente la descripción. Pega el texto manualmente abajo.")
            else:
                st.info("Para TikTok u otros sitios, pega el texto manualmente abajo y usa el botón de la derecha.")
    with cB:
        if st.button("Rellenar desde el texto de abajo"):
            cap = st.session_state.caption_manual or ""
            if cap.strip():
                parsed = parse_recipe_from_caption(cap)
                if parsed.get("titulo"): st.session_state.titulo = parsed["titulo"]
                if parsed.get("porciones"): st.session_state.porciones = parsed["porciones"]
                if parsed.get("tiempo"): st.session_state.tiempo = parsed["tiempo"]
                if parsed.get("ingredientes"): st.session_state.ingredientes_text = "\n".join(parsed["ingredientes"])
                if parsed.get("procedimiento"): st.session_state.procedimiento_text = "\n".join(parsed["procedimiento"])
                st.success("Campos rellenados desde el texto.")
            else:
                st.warning("No hay texto para analizar.")
    with cC:
        if st.button("Limpiar formulario"):
            # Limpia el formulario sin tocar el archivo recetas.json
            st.session_state.caption_manual = ""
            st.session_state.titulo = ""
            st.session_state.porciones = "No especificado"
            st.session_state.tiempo = ""
            st.session_state.ingredientes_text = ""
            st.session_state.procedimiento_text = ""
            st.session_state.categoria = "Seleccionar opción"
            st.info("Formulario limpio. (No se borró nada de tus recetas guardadas)")

    st.text_area(
        "Descripción / receta (pega el texto completo si no se detectó automáticamente):",
        key="caption_manual",
        height=220
    )

    st.subheader("📌 Datos de la receta")
    st.text_input("Nombre de la receta:", key="titulo")
    st.text_input("Porciones:", key="porciones")
    st.text_input("Tiempo (opcional):", key="tiempo")

    categorias = ["Seleccionar opción", "Sopa", "Proteína", "Arroz", "Guarnición", "Ensalada", "Postre"]
    st.selectbox("Selecciona categoría", categorias, key="categoria")

    col1, col2 = st.columns(2)
    with col1:
        st.text_area("Ingredientes (uno por línea):", key="ingredientes_text", height=200)
    with col2:
        st.text_area("Procedimiento (uno por línea):", key="procedimiento_text", height=200)

    if st.button("Guardar receta"):
        if st.session_state.categoria == "Seleccionar opción":
            st.error("❌ Debes seleccionar una categoría válida. (Tus datos se mantienen en el formulario)")
        elif not st.session_state.titulo.strip():
            st.error("❌ Debes ingresar un nombre para la receta. (Tus datos se mantienen en el formulario)")
        else:
            recetas = cargar_recetas()
            nueva = {
                "fuente": st.session_state.link.strip(),
                "titulo": capitalizar_oracion(st.session_state.titulo.strip()),
                "categoria": st.session_state.categoria.strip(),
                "porciones": st.session_state.porciones.strip() or "No especificado",
                "tiempo": st.session_state.tiempo.strip(),
                "ingredientes": [i.strip() for i in st.session_state.ingredientes_text.split("\n") if i.strip()],
                "procedimiento": [p.strip() for p in st.session_state.procedimiento_text.split("\n") if p.strip()]
            }
            recetas.append(nueva)
            guardar_recetas(recetas)
            st.success("✅ Receta guardada exitosamente. El formulario conserva tus datos.")

# ========== UI: Ver recetas ==========
elif pestanas == "Ver recetas":
    st.header("Recetas guardadas")
    recetas = cargar_recetas()

    if not recetas:
        st.info("No hay recetas guardadas aún.")
    else:
        cats = ["Todas"] + sorted(set([r.get("categoria","Sin categoría") for r in recetas]))
        cat_sel = st.selectbox("Filtrar por categoría:", cats)
        if cat_sel == "Todas":
            rec_filtradas = recetas
        else:
            rec_filtradas = [r for r in recetas if r.get("categoria") == cat_sel]

        for idx, r in enumerate(rec_filtradas):
            key_base = f"rec_{idx}_{r.get('titulo','')}"
            with st.expander(f"{r.get('categoria','?')} · {r.get('titulo','(sin título)')}"):
                st.markdown(f"**Porciones:** {r.get('porciones','No especificado')}")
                if r.get("tiempo"): st.markdown(f"**Tiempo:** {r.get('tiempo')}")
                st.markdown("**Ingredientes:**")
                for ing in r.get("ingredientes", []):
                    st.write(f"- {ing}")
                st.markdown("**Procedimiento:**")
                for i, paso in enumerate(r.get("procedimiento", []), 1):
                    st.write(f"{i}. {paso}")

                c1, c2, _ = st.columns([1,1,1])
                with c1:
                    if st.button("Eliminar", key=key_base+"_del"):
                        recetas.remove(r)
                        guardar_recetas(recetas)
                        st.success("🗑️ Receta eliminada.")
                        st.rerun()
                with c2:
                    if st.button("Editar", key=key_base+"_edit"):
                        st.session_state[key_base+"_editing"] = True

                if st.session_state.get(key_base+"_editing", False):
                    st.info("Editando…")
                    ntitulo = st.text_input("Título", value=r.get("titulo",""), key=key_base+"_t")
                    ncat = st.selectbox("Categoría", ["Sopa","Proteína","Arroz","Guarnición","Ensalada","Postre"],
                                        index=["Sopa","Proteína","Arroz","Guarnición","Ensalada","Postre"].index(r.get("categoria","Proteína")),
                                        key=key_base+"_c")
                    npor = st.text_input("Porciones", value=r.get("porciones","No especificado"), key=key_base+"_p")
                    ntiempo = st.text_input("Tiempo", value=r.get("tiempo",""), key=key_base+"_ti")
                    ning = st.text_area("Ingredientes (uno por línea)", value="\n".join(r.get("ingredientes",[])), key=key_base+"_ing")
                    nproc = st.text_area("Procedimiento (uno por línea)", value="\n".join(r.get("procedimiento",[])), key=key_base+"_proc")
                    cc1, cc2 = st.columns([1,1])
                    with cc1:
                        if st.button("Guardar cambios", key=key_base+"_save"):
                            r["titulo"] = ntitulo.strip() or r["titulo"]
                            r["categoria"] = ncat
                            r["porciones"] = npor.strip() or "No especificado"
                            r["tiempo"] = ntiempo.strip()
                            r["ingredientes"] = [i.strip() for i in ning.split("\n") if i.strip()]
                            r["procedimiento"] = [p.strip() for p in nproc.split("\n") if p.strip()]
                            guardar_recetas(recetas)
                            st.session_state[key_base+"_editing"] = False
                            st.success("💾 Receta actualizada.")
                            st.rerun()
                    with cc2:
                        if st.button("Cancelar", key=key_base+"_cancel"):
                            st.session_state[key_base+"_editing"] = False
                            st.rerun()

# ========== UI: Exportar recetas ==========
elif pestanas == "Exportar recetas":
    st.header("Exportar recetas guardadas")
    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas guardadas para exportar.")
    else:
        opciones_categoria = ["Todas"] + sorted(list(set(r.get("categoria", "Sin categoría") for r in recetas)))
        categoria_exportar = st.selectbox("Selecciona categoría para exportar", opciones_categoria)

        if categoria_exportar == "Todas":
            recetas_filtradas = recetas
        else:
            recetas_filtradas = [r for r in recetas if r.get("categoria") == categoria_exportar]

        nombres_recetas = [r.get("titulo","(sin título)") for r in recetas_filtradas]
        seleccionadas = st.multiselect(
            "Selecciona las recetas a exportar (puedes seleccionar varias):",
            options=nombres_recetas,
            default=nombres_recetas if categoria_exportar == "Todas" else []
        )

        if st.button("Exportar a Word"):
            if not seleccionadas:
                st.error("❌ Por favor, selecciona al menos una receta para exportar.")
            else:
                a_exportar = [r for r in recetas_filtradas if r.get("titulo") in seleccionadas]
                archivo_generado = exportar_recetas_a_word(a_exportar)
                with open(archivo_generado, "rb") as file:
                    st.download_button(
                        label="⬇️ Descargar archivo Word",
                        data=file,
                        file_name=archivo_generado,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )

# ========== UI: Plan mensual ==========
elif pestanas == "Plan mensual":
    st.header("📅 Generar plan de alimentación mensual (sin repetir proteína/sopa)")

    recetas = cargar_recetas()
    if not recetas:
        st.info("❌ No hay recetas guardadas suficientes para armar el plan.")
    else:
        hoy = date.today()
        colA, colB, colC = st.columns([1,1,2])

        with colA:
            year = st.number_input("Año", min_value=2023, max_value=2100, value=hoy.year, step=1)
        with colB:
            month = st.number_input("Mes (1-12)", min_value=1, max_value=12, value=hoy.month, step=1)
        with colC:
            st.write("")

        c1, c2 = st.columns([1,1])
        with c1:
            pescado_viernes = st.checkbox("Pescado los viernes", value=True)
        with c2:
            frijoles_jueves = st.checkbox("Fríjoles/legumbres los jueves", value=True)

        if st.button("Generar plan"):
            plan = generar_plan_mensual(
                recetas, int(year), int(month),
                pescado_viernes=pescado_viernes,
                frijoles_jueves=frijoles_jueves
            )
            st.session_state["plan_mensual"] = plan
            st.success("✅ Plan generado.")

        plan = st.session_state.get("plan_mensual", [])
        if plan:
            st.subheader("Vista del plan")
            for d in plan:
                with st.expander(f"{d['fecha']} · {d['dia_es']}"):
                    for k, v in d["menu"].items():
                        st.markdown(f"**{k}:** {v}")
                    key_nota = f"nota_{d['fecha']}"
                    d["notas"] = st.text_area("Notas", value=d.get("notas",""), key=key_nota)

            if st.button("Exportar plan a Word"):
                for d in plan:
                    key_nota = f"nota_{d['fecha']}"
                    if key_nota in st.session_state:
                        d["notas"] = st.session_state[key_nota]
                archivo = exportar_plan_a_word(plan, int(year), int(month))
                with open(archivo, "rb") as f:
                    st.download_button(
                        label="⬇️ Descargar plan mensual (Word)",
                        data=f,
                        file_name=archivo,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
