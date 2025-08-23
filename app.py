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
    return re.sub(r"^[\-\•\●\·\*✻❖❇️]+\s*", "", text).strip()

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

    # Detectar ingredientes y preparación en ES/EN
    ing_split = re.split(r"(Ingredients?:|Ingredientes?:)", caption, flags=re.IGNORECASE)
    if len(ing_split) >= 3:
        after_ing = "".join(ing_split[2:])
        before_method = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)[0]
        rec["ingredientes"] = [clean_bullet(x) for x in before_method.split("\n") if x.strip()]
        method_part = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:|❷)", after_ing, flags=re.IGNORECASE)
        if len(method_part) >= 4:
            rec["procedimiento"] = [clean_bullet(x) for x in "".join(method_part[3:]).split("\n") if x.strip()]

    # Si todavía no detecta procedimiento, buscar marcadores como "❷"
    if not rec["procedimiento"]:
        proc_match = re.split(r"(Preparaci[oó]n:|Procedimiento:|❷)", caption, flags=re.IGNORECASE)
        if len(proc_match) >= 3:
            rec["procedimiento"] = [clean_bullet(x) for x in "".join(proc_match[2:]).split("\n") if x.strip()]

    return rec

# ========== UI: Sidebar ==========
pestanas = st.sidebar.radio(
    "Navegación",
    ["Nueva receta", "Ver recetas", "Exportar recetas", "Plan mensual"]
)

# ========== UI: Nueva receta ==========
if pestanas == "Nueva receta":
    st.header("Agregar nueva receta desde enlace (Instagram/TikTok)")
    st.text_input("Ingresa el link del post:", key="link")

    col_a, col_b, col_c = st.columns([1,1,1])
    with col_a:
        if st.button("Leer descripción del enlace"):
            link_val = st.session_state.get("link", "").strip()
            if link_val:
                caption = get_instagram_caption(link_val) if "instagram.com" in link_val else ""
                if caption:
                    st.session_state.caption_manual = caption
                    parsed = parse_recipe_from_caption(caption)
                    if parsed.get("titulo"): st.session_state.titulo = parsed["titulo"]
                    if parsed.get("porciones"): st.session_state.porciones = parsed["porciones"]
                    if parsed.get("tiempo"): st.session_state.tiempo = parsed["tiempo"]
                    if parsed.get("ingredientes"): st.session_state.ingredientes_text = "\n".join(parsed["ingredientes"])
                    if parsed.get("procedimiento"): st.session_state.procedimiento_text = "\n".join(parsed["procedimiento"])
                    st.success("Descripción leída y campos rellenados.")
                else:
                    st.warning("No se pudo leer la descripción.")
    with col_b:
        if st.button("Rellenar desde el texto"):
            cap = st.session_state.get("caption_manual", "")
            if cap.strip():
                parsed = parse_recipe_from_caption(cap)
                if parsed.get("titulo"): st.session_state.titulo = parsed["titulo"]
                if parsed.get("porciones"): st.session_state.porciones = parsed["porciones"]
                if parsed.get("tiempo"): st.session_state.tiempo = parsed["tiempo"]
                if parsed.get("ingredientes"): st.session_state.ingredientes_text = "\n".join(parsed["ingredientes"])
                if parsed.get("procedimiento"): st.session_state.procedimiento_text = "\n".join(parsed["procedimiento"])
                st.success("Campos rellenados desde el texto.")
    with col_c:
        if st.button("Limpiar formulario"):
            st.session_state.caption_manual = ""
            st.session_state.titulo = ""
            st.session_state.porciones = "No especificado"
            st.session_state.tiempo = ""
            st.session_state.ingredientes_text = ""
            st.session_state.procedimiento_text = ""
            st.session_state.categoria = "Seleccionar opción"
            st.info("Formulario limpio.")

    st.text_area("Descripción / receta:", key="caption_manual", height=200)
    st.subheader("📌 Datos de la receta")
    st.text_input("Nombre de la receta:", key="titulo")
    st.text_input("Porciones:", key="porciones")
    st.text_input("Tiempo:", key="tiempo")
    categorias = ["Seleccionar opción", "Sopa", "Proteína", "Arroz", "Guarnición", "Postre"]
    st.selectbox("Categoría:", categorias, key="categoria")

    col1, col2 = st.columns(2)
    with col1:
        st.text_area("Ingredientes:", key="ingredientes_text", height=200)
    with col2:
        st.text_area("Procedimiento:", key="procedimiento_text", height=200)

    if st.button("Guardar receta"):
        if st.session_state.categoria == "Seleccionar opción":
            st.error("❌ Selecciona una categoría válida.")
        elif not st.session_state.titulo.strip():
            st.error("❌ Ingresa un nombre para la receta.")
        else:
            recetas = cargar_recetas()
            nueva = {
                "fuente": st.session_state.link.strip(),
                "titulo": capitalizar_oracion(st.session_state.titulo.strip()),
                "categoria": st.session_state.categoria.strip(),
                "porciones": st.session_state.porciones.strip() or "No especificado",
                "tiempo": st.session_state.tiempo.strip(),
                "ingredientes": [i.strip() for i in st.session_state.ingredientes_text.split("\n") if i.strip()],
                "procedimiento": [p.strip() for p in st.session_state.procedimiento_text.split("\n") if p.strip()],
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            recetas.append(nueva)
            guardar_recetas(recetas)
            st.success("✅ Receta guardada. (El formulario conserva tus datos)")
