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

# ---------- Inicialización de estado seguro ----------
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

# ========== Helpers ==========
def capitalizar_oracion(texto: str) -> str:
    if not texto:
        return texto
    return texto[0].upper() + texto[1:]

def clean_bullet(text: str) -> str:
    return re.sub(r"^[\-\•\●\·\*]+\s*", "", text).strip()

# ========== Extracción IG ==========
def ig_shortcode_from_url(url: str) -> Optional[str]:
    try:
        parts = [p for p in url.split("/") if p.strip()]
        for p in reversed(parts):
            if re.fullmatch(r"[A-Za-z0-9_-]{5,20}", p):
                return p
        return None
    except Exception:
        return None

def get_instagram_caption(url: str) -> str:
    if HAS_INSTALOADER:
        try:
            L = instaloader.Instaloader(download_pictures=False, download_videos=False)
            shortcode = ig_shortcode_from_url(url)
            if shortcode:
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                if post and post.caption:
                    return post.caption
        except Exception:
            pass
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name":"description"})
        if meta and meta.get("content"):
            return meta["content"]
    except Exception:
        pass
    return ""

# ========== Parseo ==========
def extract_recipe_sections(text: str) -> Dict[str, str]:
    sections = {"title": "", "servings": "", "time": "", "ingredients": "", "method": ""}
    lines = text.split("\n")
    method_started = False
    ingredients_started = False
    method_lines, ingredient_lines = [], []
    for line in lines:
        line = line.strip()
        if not line: continue
        if sections["title"] == "":
            sections["title"] = line
            continue
        if line.lower().startswith("serves"):
            sections["servings"] = line; continue
        if line.lower().startswith("takes"):
            sections["time"] = line; continue
        if line.lower().startswith("ingredients"):
            ingredients_started = True; method_started = False; continue
        if ingredients_started and not line.lower().startswith("method"):
            ingredient_lines.append(line); continue
        if line.lower().startswith("method"):
            method_started = True; ingredients_started = False; continue
        if method_started: method_lines.append(line)
    sections["ingredients"] = "\n".join(ingredient_lines)
    sections["method"] = "\n".join(method_lines)
    return sections

def parse_recipe_from_caption(caption: str) -> Dict[str, Any]:
    rec = {"titulo": "", "porciones": "", "tiempo": "", "ingredientes": [], "procedimiento": []}
    if not caption: return rec
    lines = [l.strip() for l in caption.split("\n")]
    first_nonempty = next((l for l in lines if l), "")
    rec["titulo"] = first_nonempty
    m_serves = re.search(r"(Serves|Porciones|Rinde)\s*[:\-]?\s*([0-9]+)", caption, flags=re.IGNORECASE)
    if m_serves: rec["porciones"] = m_serves.group(2).strip()
    m_time = re.search(r"(Takes|Tiempo)\s*[:\-]?\s*([0-9]+\s*\w+)", caption, flags=re.IGNORECASE)
    if m_time: rec["tiempo"] = m_time.group(2).strip()
    ing_split = re.split(r"(Ingredients?:|Ingredientes?:)", caption, flags=re.IGNORECASE)
    if len(ing_split) >= 3:
        after_ing = "".join(ing_split[2:])
        before_method = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)[0]
        rec["ingredientes"] = [clean_bullet(x) for x in before_method.split("\n") if x.strip()]
        method_part = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)
        if len(method_part) >= 4:
            rec["procedimiento"] = [clean_bullet(x) for x in "".join(method_part[3:]).split("\n") if x.strip()]
    sections = extract_recipe_sections(caption)
    if sections.get("ingredients") and not rec["ingredientes"]:
        rec["ingredientes"] = [clean_bullet(x) for x in sections["ingredients"].split("\n") if x.strip()]
    if sections.get("method") and not rec["procedimiento"]:
        rec["procedimiento"] = [clean_bullet(x) for x in sections["method"].split("\n") if x.strip()]
    return rec

# ========== Exportar recetas ==========
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
            doc.add_paragraph(f"Porciones: {por} | Tiempo: {tie}", style='Titulo3')
            doc.add_paragraph("Ingredientes:", style='Titulo3')
            for ing in r.get('ingredientes', []): doc.add_paragraph(ing, style='Normal')
            doc.add_paragraph("Procedimiento:", style='Titulo3')
            for i, paso in enumerate(r.get('procedimiento', []), 1):
                doc.add_paragraph(f"{i}. {paso}", style='Normal')
            doc.add_paragraph("")
    doc.save(nombre_archivo)
    return nombre_archivo

# ========== UI ==========
pestanas = st.sidebar.radio("Navegación", ["Nueva receta", "Ver recetas", "Exportar recetas", "Plan mensual"])

# ========== UI: Nueva receta ==========
if pestanas == "Nueva receta":
    st.header("➕ Nueva receta")
    with st.form("form_nueva_receta", clear_on_submit=False):
        link = st.text_input("Enlace de Instagram/TikTok", value=st.session_state.link)
        if st.form_submit_button("📥 Leer descripción del enlace"):
            caption = get_instagram_caption(link)
            if caption:
                parsed = parse_recipe_from_caption(caption)
                st.session_state.titulo = parsed.get("titulo", "")
                st.session_state.porciones = parsed.get("porciones", "")
                st.session_state.tiempo = parsed.get("tiempo", "")
                st.session_state.ingredientes_text = "\n".join(parsed.get("ingredientes", []))
                st.session_state.procedimiento_text = "\n".join(parsed.get("procedimiento", []))
                st.success("Descripción extraída correctamente.")
            else:
                st.warning("No se pudo extraer información del enlace.")

        titulo = st.text_input("Título de la receta", value=st.session_state.titulo)
        porciones = st.text_input("Porciones", value=st.session_state.porciones)
        tiempo = st.text_input("Tiempo de preparación", value=st.session_state.tiempo)
        ingredientes_text = st.text_area("Ingredientes (uno por línea)", value=st.session_state.ingredientes_text)
        procedimiento_text = st.text_area("Procedimiento (uno por línea)", value=st.session_state.procedimiento_text)

        categoria = st.selectbox("Categoría", ["Seleccionar opción", "Desayuno", "Almuerzo", "Cena", "Postres", "Snacks", "Bebidas"], index=0)

        submitted = st.form_submit_button("💾 Guardar receta")
        if submitted:
            if not titulo.strip():
                st.error("El título es obligatorio.")
            elif categoria == "Seleccionar opción":
                st.error("Debes seleccionar una categoría válida.")
            else:
                nueva = {
                    "titulo": titulo.strip(),
                    "porciones": porciones.strip(),
                    "tiempo": tiempo.strip(),
                    "ingredientes": [x.strip() for x in ingredientes_text.split("\n") if x.strip()],
                    "procedimiento": [x.strip() for x in procedimiento_text.split("\n") if x.strip()],
                    "categoria": categoria
                }
                recetas = cargar_recetas()
                recetas.append(nueva)
                guardar_recetas(recetas)
                st.success("Receta guardada exitosamente.")

# ========== UI: Ver recetas ==========
elif pestanas == "Ver recetas":
    st.header("📖 Recetas guardadas")
    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas guardadas aún.")
    else:
        categorias = sorted(set([r.get("categoria","Sin categoría") for r in recetas]))
        for cat in categorias:
            with st.expander(cat):
                recetas_cat = [r for r in recetas if r.get("categoria")==cat]
                for idx, r in enumerate(recetas_cat):
                    key_base = f"{cat}_{idx}"
                    with st.expander(r.get("titulo","(sin título)")):
                        st.markdown(f"**Porciones:** {r.get('porciones','No especificado')}")
                        if r.get("tiempo"): st.markdown(f"**Tiempo:** {r.get('tiempo')}")
                        st.markdown("**Ingredientes:**")
                        for ing in r.get("ingredientes", []): st.write(f"- {ing}")
                        st.markdown("**Procedimiento:**")
                        for i, paso in enumerate(r.get("procedimiento", []), 1): st.write(f"{i}. {paso}")
                        if st.button("Eliminar", key=key_base+"_del"):
                            recetas.remove(r); guardar_recetas(recetas); st.rerun()

# ========== UI: Exportar recetas ==========
elif pestanas == "Exportar recetas":
    st.header("📤 Exportar recetas")
    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas para exportar.")
    else:
        if st.button("📄 Exportar a Word"):
            nombre_archivo = exportar_recetas_a_word(recetas)
            with open(nombre_archivo, "rb") as f:
                st.download_button("⬇️ Descargar archivo", f, file_name=nombre_archivo)

# ========== UI: Plan mensual ==========
elif pestanas == "Plan mensual":
    st.header("📅 Plan mensual de recetas")
    recetas = cargar_recetas()
    if not recetas:
        st.info("Debes tener recetas guardadas para generar un plan mensual.")
    else:
        hoy = date.today()
        mes_actual = hoy.month
        anio_actual = hoy.year
        dias_en_mes = calendar.monthrange(anio_actual, mes_actual)[1]
        plan = {d: random.choice(recetas) for d in range(1, dias_en_mes+1)}

        for d in range(1, dias_en_mes+1):
            r = plan[d]
            st.write(f"**{d}/{mes_actual}/{anio_actual}** → {r.get('titulo')} ({r.get('categoria')})")
