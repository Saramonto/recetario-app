# app.py
import streamlit as st
import re
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from docx import Document
from docx.shared import Pt
from docx.enum.style import WD_STYLE_TYPE
import random

try:
    import instaloader
    HAS_INSTALOADER = True
except Exception:
    HAS_INSTALOADER = False

st.set_page_config(page_title="Recetario + Plan mensual", page_icon="🍽️", layout="wide")
st.title("📚 Recetario desde Instagram/TikTok + 📅 Plan mensual")

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

RECETAS_FILE = "recetas.json"
def cargar_recetas(nombre_archivo: str = RECETAS_FILE) -> List[Dict[str, Any]]:
    if not os.path.exists(nombre_archivo):
        return []
    with open(nombre_archivo, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
def guardar_recetas(lista_recetas: List[Dict[str, Any]], nombre_archivo: str = RECETAS_FILE) -> None:
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(lista_recetas, f, ensure_ascii=False, indent=4)

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

def capitalizar_oracion(texto: str) -> str:
    return texto[0].upper() + texto[1:] if texto else texto
def clean_bullet(text: str) -> str:
    return re.sub(r"^[\-\•\●\·\*✻❖❇️▪️✍🏼👨‍🍳]+\s*", "", text).strip()
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
                download_pictures=False, download_videos=False,
                download_video_thumbnails=False, download_comments=False,
                save_metadata=False, compress_json=False
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
    lines = [l.strip() for l in caption.split("\n") if l.strip()]
    rec["titulo"] = lines[0] if lines else ""
    m_serves = re.search(r"(Serves|Porciones|Rinde)\s*[:\-]?\s*([0-9]+)", caption, flags=re.IGNORECASE)
    if m_serves:
        rec["porciones"] = m_serves.group(2).strip()
    m_time = re.search(r"(Takes|Tiempo)\s*[:\-]?\s*([0-9]+\s*\w+)", caption, flags=re.IGNORECASE)
    if m_time:
        rec["tiempo"] = m_time.group(2).strip()
    ing_split = re.split(r"(Ingredientes?:|Ingredients?:|✍🏼Ingredientes|👨‍🍳INGREDIENTES|❶ 𝐈𝐧𝐠𝐫𝐞𝐝𝐢𝐞𝐧𝐭𝐞𝐬:)", caption, flags=re.IGNORECASE)
    if len(ing_split) >= 2:
        after_ing = "".join(ing_split[1:])
        before_method = re.split(r"(Preparaci[oó]n:|Procedimiento:|Método:|Method:|❷ 𝐏𝐫𝐞𝐩𝐚𝐫𝐚𝐜𝐢[oó]n:)", after_ing, flags=re.IGNORECASE)[0]
        rec["ingredientes"] = [clean_bullet(x) for x in before_method.split("\n") if x.strip()]
        method_part = re.split(r"(Preparaci[oó]n:|Procedimiento:|Método:|Method:|❷ 𝐏𝐫𝐞𝐩𝐚𝐫𝐚𝐜𝐢[oó]n:)", after_ing, flags=re.IGNORECASE)
        if len(method_part) >= 2:
            rec["procedimiento"] = [clean_bullet(x) for x in "".join(method_part[1:]).split("\n") if x.strip()]
    if not rec["ingredientes"]:
        posibles_ingredientes = []
        posibles_procedimiento = []
        for l in lines[1:]:
            if re.match(r"^(\d+\/?\d*\s?(g|kg|ml|l|cucharad[ao]s?|tazas?|cdas?|cdtas?|pizca)?\s+.+)", l, flags=re.IGNORECASE):
                posibles_ingredientes.append(clean_bullet(l))
            else:
                posibles_procedimiento.append(clean_bullet(l))
        rec["ingredientes"] = posibles_ingredientes
        rec["procedimiento"] = posibles_procedimiento
    return rec

pestanas = st.sidebar.radio(
    "Navegación",
    ["Nueva receta", "Ver recetas", "Exportar recetas", "Plan mensual balanceado"]
)

categorias_base = ["Sopa", "Proteína", "Arroz", "Guarnición", "Ensalada", "Postre"]

# ----- Aquí se mantendría la pestaña "Nueva receta" y "Ver recetas" como estaba -----
# (sin cambios excepto añadir "Ensalada" a categorías)  

# ========== Pestaña: Exportar recetas ==========
if pestanas == "Exportar recetas":
    st.header("📤 Exportar recetas a DOCX")
    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas para exportar.")
    else:
        # Botón descargar todas
        if st.button("💾 Descargar todas las recetas"):
            doc = Document()
            asegurar_estilos_docx(doc)
            for receta in recetas:
                doc.add_paragraph(receta["titulo"], style="Titulo1")
                doc.add_paragraph(f"Categoría: {receta['categoria']}")
                doc.add_paragraph(f"Porciones: {receta['porciones']} | Tiempo: {receta['tiempo']}")
                doc.add_paragraph("Ingredientes:", style="Titulo2")
                for ing in receta["ingredientes"]:
                    doc.add_paragraph(f"- {ing}")
                doc.add_paragraph("Procedimiento:", style="Titulo2")
                for step in receta["procedimiento"]:
                    doc.add_paragraph(f"- {step}")
                doc.add_paragraph("\n")
            fname = f"recetario_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
            doc.save(fname)
            with open(fname, "rb") as f:
                st.download_button("💾 Descargar DOCX", f, file_name=fname)

        # Descargar por categoría
        for cat in categorias_base:
            if st.button(f"📂 Descargar {cat}"):
                recetas_cat = [r for r in recetas if r["categoria"]==cat]
                if recetas_cat:
                    doc = Document()
                    asegurar_estilos_docx(doc)
                    for receta in recetas_cat:
                        doc.add_paragraph(receta["titulo"], style="Titulo1")
                        doc.add_paragraph(f"Categoría: {receta['categoria']}")
                        doc.add_paragraph(f"Porciones: {receta['porciones']} | Tiempo: {receta['tiempo']}")
                        doc.add_paragraph("Ingredientes:", style="Titulo2")
                        for ing in receta["ingredientes"]:
                            doc.add_paragraph(f"- {ing}")
                        doc.add_paragraph("Procedimiento:", style="Titulo2")
                        for step in receta["procedimiento"]:
                            doc.add_paragraph(f"- {step}")
                        doc.add_paragraph("\n")
                    fname = f"recetario_{cat}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
                    doc.save(fname)
                    with open(fname, "rb") as f:
                        st.download_button(f"💾 Descargar {cat} DOCX", f, file_name=fname)

        # Selector múltiple
        seleccionadas = st.multiselect("Selecciona recetas específicas:", [r["titulo"] for r in recetas])
        if st.button("💾 Exportar recetas seleccionadas"):
            if seleccionadas:
                doc = Document()
                asegurar_estilos_docx(doc)
                for t in seleccionadas:
                    receta = next((r for r in recetas if r["titulo"]==t), None)
                    if receta:
                        doc.add_paragraph(receta["titulo"], style="Titulo1")
                        doc.add_paragraph(f"Categoría: {receta['categoria']}")
                        doc.add_paragraph(f"Porciones: {receta['porciones']} | Tiempo: {receta['tiempo']}")
                        doc.add_paragraph("Ingredientes:", style="Titulo2")
                        for ing in receta["ingredientes"]:
                            doc.add_paragraph(f"- {ing}")
                        doc.add_paragraph("Procedimiento:", style="Titulo2")
                        for step in receta["procedimiento"]:
                            doc.add_paragraph(f"- {step}")
                        doc.add_paragraph("\n")
                fname = f"recetas_seleccionadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
                doc.save(fname)
                with open(fname, "rb") as f:
                    st.download_button(f"💾 Descargar DOCX recetas seleccionadas", f, file_name=fname)

# ========== Pestaña: Plan mensual balanceado ==========
if pestanas == "Plan mensual balanceado":
    st.header("🗓️ Generador de plan mensual balanceado")
    recetas = cargar_recetas()
    requisito = st.text_input("Requisito especial (ej: pescado todos los viernes)")
    dia_requisito = st.selectbox("Día del requisito:", [""] + ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"])
    if st.button("Generar plan mensual balanceado"):
        plan = {}
        dias_semana = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
        recetas_por_cat = {cat:[r for r in recetas if r["categoria"]==cat] for cat in categorias_base}
        last_proteina = None
        for dia in dias_semana:
            plan[dia] = {}
            for cat in categorias_base:
                lista = recetas_por_cat.get(cat, [])
                if not lista:
                    plan[dia][cat] = None
                else:
                    if cat=="Proteína":
                        opciones = [r for r in lista if r["titulo"] != last_proteina]
                        if dia == dia_requisito and requisito.strip().lower() in [r["titulo"].lower() for r in lista]:
                            match = next((r for r in lista if requisito.strip().lower() in r["titulo"].lower()), None)
                            plan[dia][cat] = match
                            last_proteina = match["titulo"]
                        else:
                            if opciones:
                                eleccion = random.choice(opciones)
                                plan[dia][cat] = eleccion
                                last_proteina = eleccion["titulo"]
                            else:
                                eleccion = random.choice(lista)
                                plan[dia][cat] = eleccion
                                last_proteina = eleccion["titulo"]
                    else:
                        plan[dia][cat] = random.choice(lista)
        st.write("✅ Plan mensual generado")
        for dia in dias_semana:
            st.subheader(dia)
            for cat in categorias_base:
                receta = plan[dia][cat]
                st.write(f"**{cat}:** {receta['titulo'] if receta else 'No disponible'}")
