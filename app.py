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
from io import BytesIO

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
        # view/edit state
        "view_idx": None,
        "editing_idx": None,
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

# ========== Helpers de texto y parseo ==========
def capitalizar_oracion(texto: str) -> str:
    if not texto:
        return texto
    return texto[0].upper() + texto[1:]

def clean_bullet(text: str) -> str:
    return re.sub(r"^[\-\•\●\·\*]+\s*", "", text).strip()

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

def extract_recipe_sections(text: str) -> Dict[str, str]:
    sections = {"title": "", "servings": "", "time": "", "ingredients": "", "method": ""}
    lines = text.split("\n")
    method_started = False
    ingredients_started = False
    method_lines, ingredient_lines = [], []
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
    rec = {"titulo": "", "porciones": "", "tiempo": "", "ingredientes": [], "procedimiento": []}
    if not caption:
        return rec
    lines = [l.strip() for l in caption.split("\n")]
    first_nonempty = next((l for l in lines if l), "")
    rec["titulo"] = first_nonempty
    m_serves = re.search(r"(Serves|Porciones|Rinde)\s*[:\-]?\s*([0-9]+)", caption, flags=re.IGNORECASE)
    if m_serves:
        rec["porciones"] = m_serves.group(2).strip()
    m_time = re.search(r"(Takes|Tiempo)\s*[:\-]?\s*([0-9]+\s*\w+)", caption, flags=re.IGNORECASE)
    if m_time:
        rec["tiempo"] = m_time.group(2).strip()
    ing_split = re.split(r"(Ingredients?:)", caption, flags=re.IGNORECASE)
    if len(ing_split) >= 3:
        after_ing = "".join(ing_split[2:])
        before_method = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)[0]
        rec["ingredientes"] = [clean_bullet(x) for x in before_method.split("\n") if x.strip()]
        method_part = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)
        if len(method_part) >= 4:
            rec["procedimiento"] = [clean_bullet(x) for x in "".join(method_part[3:]).split("\n") if x.strip()]
    else:
        ing_split_es = re.split(r"(Ingredientes?:)", caption, flags=re.IGNORECASE)
        if len(ing_split_es) >= 3:
            after_ing = "".join(ing_split_es[2:])
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

# ========== Exportar recetas a Word ==========
def exportar_recetas_a_word(recetas: List[Dict[str, Any]], nombre_archivo: str = "recetas_exportadas.docx") -> BytesIO:
    doc = Document()
    asegurar_estilos_docx(doc)
    doc.add_heading("Recetario", 0)
    categorias_orden = ["Sopa", "Proteína", "Arroz", "Guarnición", "Postre"]
    for categoria in categorias_orden:
        filtered = [r for r in recetas if r.get("categoria") == categoria]
        if not filtered:
            continue
        doc.add_paragraph(categoria, style='Titulo1')
        for r in filtered:
            doc.add_paragraph(r.get('titulo', 'Sin título'), style='Titulo2')
            por = r.get('porciones', 'No especificado')
            tie = r.get('tiempo', '')
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
                doc.add_paragraph(f"{i}. {paso}", style='Normal')
            doc.add_paragraph("")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# ========== Detección familia proteína / Plan mensual ==========
# (esta parte queda igual que la tuya original)

PROTEIN_FAMILIES = {
    "pollo/ave": ["pollo","chicken","pechuga","muslo","ala","pavo"],
    "res": ["res","carne de res","beef","ternera"],
    "cerdo": ["cerdo","pork","tocino","bacon"],
    "pescado": ["pescado","fish","salmón","salmon","atún","tuna"],
    "mariscos": ["camarón","camaron","shrimp","langostino","calamar"],
    "frijoles/legumbres": ["frijol","frijoles","lenteja","garbanzo"],
    "huevo": ["huevo","huevos","egg"],
    "soya/tofu": ["soya","tofu","soja"]
}
FAMILY_PRIORITY = list(PROTEIN_FAMILIES.keys()) + ["mixta/otra"]

# ... resto del código de detección, plan mensual y exportación (sin cambios)

# ========== UI: Sidebar navegación ==========
pestanas = st.sidebar.radio(
    "Navegación",
    ["Nueva receta", "Ver recetas", "Exportar recetas", "Plan mensual"]
)

# ========== UI: Nueva receta ==========
# (igual que tu código actual, no lo repito aquí por espacio, pero se mantiene)

# ========== UI: Ver recetas ==========
elif pestanas == "Ver recetas":
    st.header("Recetas guardadas")
    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas guardadas aún.")
    else:
        categorias_fijas = ["Sopa", "Proteína", "Arroz", "Guarnición", "Postre"]
        cat_indices: Dict[str, List[int]] = {c: [] for c in categorias_fijas}
        for idx, r in enumerate(recetas):
            if r.get("categoria") in cat_indices:
                cat_indices[r["categoria"]].append(idx)
        for cat in categorias_fijas:
            with st.expander(f"{cat} ({len(cat_indices[cat])})"):
                if not cat_indices[cat]:
                    st.write("No hay recetas en esta categoría.")
                else:
                    for idx in cat_indices[cat]:
                        r = recetas[idx]
                        with st.expander(r.get("titulo", "(sin título)")):
                            st.write(f"**Porciones:** {r.get('porciones','No especificado')}")
                            if r.get("tiempo"):
                                st.write(f"**Tiempo:** {r.get('tiempo')}")
                            st.write("**Ingredientes:**")
                            for ing in r.get("ingredientes", []):
                                st.write(f"- {ing}")
                            st.write("**Procedimiento:**")
                            for i, paso in enumerate(r.get("procedimiento", []), 1):
                                st.write(f"{i}. {paso}")
                            st.write(f"*Agregada: {r.get('fecha','')}*")

# ========== UI: Exportar recetas ==========
# (igual que tu código actual)

# ========== UI: Plan mensual ==========
# (igual que tu código actual)
