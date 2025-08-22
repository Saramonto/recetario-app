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

# ========== Parseo de recetas ==========
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

    ing_split = re.split(r"(Ingredients?:|Ingredientes?:)", caption, flags=re.IGNORECASE)
    if len(ing_split) >= 3:
        after_ing = "".join(ing_split[2:])
        before_method = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)[0]
        rec["ingredientes"] = [clean_bullet(x) for x in before_method.split("\n") if x.strip()]
        method_part = re.split(r"(Method:|Preparaci[oó]n:|Procedimiento:|Método:)", after_ing, flags=re.IGNORECASE)
        if len(method_part) >= 4:
            method_text = "".join(method_part[3:])
            rec["procedimiento"] = [clean_bullet(x) for x in method_text.split("\n") if x.strip()]
    return rec

def clean_bullet(s: str) -> str:
    return s.strip().lstrip("•-*–— ").strip()

# ========== Exportar recetas a Word ==========
# (igual que tu versión previa, sin cambios...)

# ========== Detección de proteína / Plan mensual ==========
# (igual que tu versión previa, sin cambios...)

# ========== UI ==========
pestanas = st.sidebar.radio("Navegación", ["Nueva receta", "Ver recetas", "Exportar recetas", "Plan mensual"])

# --- Nueva receta (igual que antes) ---
# ... (todo tu código de "Nueva receta" se mantiene igual)

# --- Ver recetas actualizado ---
elif pestanas == "Ver recetas":
    st.header("📖 Recetas guardadas")
    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas guardadas aún.")
    else:
        categorias = sorted(set([r.get("categoria", "Sin categoría") for r in recetas]))
        for cat in categorias:
            with st.expander(f"📂 {cat}"):
                recetas_cat = [r for r in recetas if r.get("categoria", "Sin categoría") == cat]
                for idx, r in enumerate(recetas_cat):
                    key_base = f"rec_{cat}_{idx}_{r.get('titulo','')}"
                    with st.expander(f"🍴 {r.get('titulo','(sin título)')}"):
                        st.markdown(f"**Porciones:** {r.get('porciones','No especificado')}")
                        if r.get("tiempo"):
                            st.markdown(f"**Tiempo:** {r.get('tiempo')}")
                        st.markdown("**Ingredientes:**")
                        for ing in r.get("ingredientes", []):
                            st.write(f"- {ing}")
                        st.markdown("**Procedimiento:**")
                        for i, paso in enumerate(r.get("procedimiento", []), 1):
                            st.write(f"{i}. {paso}")

                        c1, c2, c3 = st.columns([1,1,1])
                        with c1:
                            if st.button("🗑️ Eliminar", key=key_base+"_del"):
                                recetas.remove(r)
                                guardar_recetas(recetas)
                                st.success("Receta eliminada.")
                                st.rerun()
                        with c2:
                            if st.button("✏️ Editar", key=key_base+"_edit"):
                                st.session_state[key_base+"_editing"] = True
                        with c3:
                            st.write("")

                        if st.session_state.get(key_base+"_editing", False):
                            st.info("Editando…")
                            ntitulo = st.text_input("Título", value=r.get("titulo",""), key=key_base+"_t")
                            ncat = st.selectbox("Categoría", ["Sopa","Proteína","Arroz","Guarnición","Ensalada","Postre"], index=["Sopa","Proteína","Arroz","Guarnición","Ensalada","Postre"].index(r.get("categoria","Proteína")), key=key_base+"_c")
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

# --- Exportar recetas  ---========
elif opcion == "Exportar recetas":
    st.subheader("📤 Exportar recetas")

    try:
        with open("recetas.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        st.download_button(
            "⬇️ Descargar recetas en JSON",
            data=json.dumps(data, indent=4, ensure_ascii=False),
            file_name="recetas.json",
            mime="application/json"
        )
        st.info("Puedes descargar todas tus recetas guardadas en un archivo JSON.")

    except FileNotFoundError:
        st.warning("⚠️ No se encontró el archivo de recetas. Guarda una receta primero.")

# ---  Plan mensual ---========
elif opcion == "Plan mensual":
    st.subheader("🗓️ Plan mensual de comidas")

    try:
        with open("recetas.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data:
            st.warning("⚠️ No hay recetas disponibles. Guarda recetas primero en la sección *Guardar receta*.")
        else:
            dias = [
                "Lunes", "Martes", "Miércoles", "Jueves",
                "Viernes", "Sábado", "Domingo"
            ]
            plan = {}

            for dia in dias:
                recetas = [r["nombre"] for r in data]
                seleccion = st.selectbox(
                    f"🍽️ Receta para {dia}",
                    ["Ninguna"] + recetas,
                    key=f"plan_{dia}"
                )
                plan[dia] = seleccion

            if st.button("💾 Guardar plan mensual"):
                with open("plan_mensual.json", "w", encoding="utf-8") as f:
                    json.dump(plan, f, indent=4, ensure_ascii=False)
                st.success("✅ Plan mensual guardado exitosamente")

            # Mostrar el plan actual
            if plan:
                st.subheader("📋 Tu plan semanal actual")
                for dia, receta in plan.items():
                    st.write(f"**{dia}:** {receta if receta != 'Ninguna' else '---'}")

    except FileNotFoundError:
        st.warning("⚠️ No se encontró el archivo de recetas. Guarda una receta primero.")

