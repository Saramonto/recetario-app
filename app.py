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
        # view/edit state (global index of recipe being viewed/edited)
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
    # 2) fallback
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
    # título = primera línea no vacía
    lines = [l.strip() for l in caption.split("\n")]
    first_nonempty = next((l for l in lines if l), "")
    rec["titulo"] = first_nonempty

    # porciones
    m_serves = re.search(r"(Serves|Porciones|Rinde)\s*[:\-]?\s*([0-9]+)", caption, flags=re.IGNORECASE)
    if m_serves:
        rec["porciones"] = m_serves.group(2).strip()
    # tiempo
    m_time = re.search(r"(Takes|Tiempo)\s*[:\-]?\s*([0-9]+\s*\w+)", caption, flags=re.IGNORECASE)
    if m_time:
        rec["tiempo"] = m_time.group(2).strip()

    # intenta EN / ES
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

    # refuerzo con extractor EN
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

    # Agrupa por categoría fija en orden
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
            doc.add_paragraph("")  # espacio

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# ========== Detección familia proteína / Plan mensual ==========
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

def generar_plan_mensual(recetas: List[Dict[str, Any]], year: int, month: int,
                         pescado_viernes: bool = True, frijoles_jueves: bool = True) -> List[Dict[str, Any]]:
    por_cat: Dict[str, List[Dict[str, Any]]] = {}
    for r in recetas:
        por_cat.setdefault(r.get("categoria", ""), []).append(r)

    sopas = por_cat.get("Sopa", [])
    proteinas = por_cat.get("Proteína", [])
    guarniciones = por_cat.get("Guarnición", [])
    arroces = por_cat.get("Arroz", [])
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
            day_menu["Guarnición"] = random.choice(guarniciones).get("titulo", "Guarnición")
        if arroces:
            day_menu["Arroz"] = random.choice(arroces).get("titulo", "Arroz")
        if postres:
            day_menu["Postre"] = random.choice(postres).get("titulo", "Postre")

        plan.append({
            "fecha": day_date.isoformat(),
            "dia_es": ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"][weekday_idx],
            "menu": day_menu,
            "notas": ""
        })

    return plan

def exportar_plan_a_word(plan: List[Dict[str, Any]], year: int, month: int) -> BytesIO:
    doc = Document()
    asegurar_estilos_docx(doc)
    nombre_mes = [
        "", "Enero","Febrero","Marzo","Abril","Mayo","Junio",
        "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
    ][month]
    doc.add_paragraph(f"Plan de alimentación - {nombre_mes} {year}", style='Titulo1')
    for dia in plan:
        f = dia["fecha"]
        fecha_dt = datetime.fromisoformat(f)
        titulo_dia = f"{fecha_dt.strftime('%Y-%m-%d')} - {dia['dia_es']}"
        doc.add_paragraph(titulo_dia, style='Titulo2')
        for seccion in ["Sopa","Proteína","Guarnición","Arroz","Postre"]:
            if seccion in dia["menu"]:
                doc.add_paragraph(seccion + ":", style='Titulo3')
                doc.add_paragraph(dia["menu"][seccion], style='Normal')
        doc.add_paragraph("Notas:", style='Titulo3')
        doc.add_paragraph(dia.get("notas",""), style='Normal')
        doc.add_paragraph("")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# ========== UI: Sidebar navegación ==========
pestanas = st.sidebar.radio(
    "Navegación",
    ["Nueva receta", "Ver recetas", "Exportar recetas", "Plan mensual"]
)

# ========== UI: Nueva receta ==========
if pestanas == "Nueva receta":
    st.header("Agregar nueva receta desde enlace (Instagram/TikTok)")

    # Input link (persistente)
    st.text_input("Ingresa el link del post (Instagram o TikTok):", key="link")

    col_a, col_b, col_c = st.columns([1,1,1])
    with col_a:
        if st.button("Leer descripción del enlace"):
            link_val = st.session_state.get("link", "").strip()
            if not link_val:
                st.warning("Ingresa primero un enlace.")
            else:
                caption = get_instagram_caption(link_val) if "instagram.com" in link_val else ""
                if caption:
                    st.session_state.caption_manual = caption
                    parsed = parse_recipe_from_caption(caption)
                    # solo rellenar los campos que el parser encuentre (no sobreescribir vacío)
                    if parsed.get("titulo"): st.session_state.titulo = parsed["titulo"]
                    if parsed.get("porciones"): st.session_state.porciones = parsed["porciones"]
                    if parsed.get("tiempo"): st.session_state.tiempo = parsed["tiempo"]
                    if parsed.get("ingredientes"): st.session_state.ingredientes_text = "\n".join(parsed["ingredientes"])
                    if parsed.get("procedimiento"): st.session_state.procedimiento_text = "\n".join(parsed["procedimiento"])
                    st.success("Descripción leída y campos rellenados.")
                else:
                    st.warning("No se pudo leer automáticamente la descripción (o no es Instagram público). Pega el texto manualmente abajo.")
    with col_b:
        if st.button("Rellenar desde el texto de abajo"):
            cap = st.session_state.get("caption_manual", "")
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
    with col_c:
        if st.button("Limpiar formulario"):
            st.session_state.caption_manual = ""
            st.session_state.titulo = ""
            st.session_state.porciones = "No especificado"
            st.session_state.tiempo = ""
            st.session_state.ingredientes_text = ""
            st.session_state.procedimiento_text = ""
            st.session_state.categoria = "Seleccionar opción"
            st.info("Formulario limpio. (No se borraron tus recetas guardadas)")

    st.text_area(
        "Descripción / receta (pega el texto si no se detectó automáticamente):",
        key="caption_manual", height=200
    )

    st.subheader("📌 Datos de la receta")
    st.text_input("Nombre de la receta:", key="titulo")
    st.text_input("Porciones:", key="porciones")
    st.text_input("Tiempo (opcional):", key="tiempo")

    categorias = ["Seleccionar opción", "Sopa", "Proteína", "Arroz", "Guarnición", "Postre"]
    st.selectbox("Selecciona categoría", categorias, key="categoria")

    col1, col2 = st.columns(2)
    with col1:
        st.text_area("Ingredientes (uno por línea):", key="ingredientes_text", height=200)
    with col2:
        st.text_area("Procedimiento (uno por línea):", key="procedimiento_text", height=200)

    if st.button("Guardar receta"):
        # Validaciones: no borrar campos en caso de error (se usan session_state)
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
                "procedimiento": [p.strip() for p in st.session_state.procedimiento_text.split("\n") if p.strip()],
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        # Mostrar siempre las categorías fijas y dentro las recetas
        categorias_fijas = ["Sopa", "Proteína", "Arroz", "Guarnición", "Postre"]
        # Mapear categoría -> lista de índices en recetas (para referencia global)
        cat_indices: Dict[str, List[int]] = {c: [] for c in categorias_fijas}
        for idx, r in enumerate(recetas):
            cat = r.get("categoria", "Sin categoría")
            if cat in cat_indices:
                cat_indices[cat].append(idx)

        # Mostrar expanders por categoría
        for cat in categorias_fijas:
            with st.expander(f"{cat} ({len(cat_indices[cat])})"):
                if not cat_indices[cat]:
                    st.write("No hay recetas en esta categoría.")
                else:
                    for idx in cat_indices[cat]:
                        r = recetas[idx]
                        # cada receta en su propio expander para ver detalles al instante
                        with st.expander(r.get("titulo", "(sin título)")):
                            # botones arriba (Eliminar / Editar)
                            cdel, cedit, csp = st.columns([1,1,6])
                            with cdel:
                                if st.button("🗑️ Eliminar", key=f"del_{idx}"):
                                    titulo_elim = r.get("titulo", "(sin título)")
                                    # recargar para evitar desincronía
                                    all_rec = cargar_recetas()
                                    # si el índice sigue válido, eliminar
                                    if idx < len(all_rec):
                                        all_rec.pop(idx)
                                        guardar_recetas(all_rec)
                                        st.success(f"Receta '{titulo_elim}' eliminada.")
                                    else:
                                        st.warning("La receta no se encontró para eliminar.")
                                    # limpiar posibles estados
                                    if st.session_state.get("view_idx") == idx:
                                        st.session_state.view_idx = None
                                    if st.session_state.get("editing_idx") == idx:
                                        st.session_state.editing_idx = None
                                    st.experimental_rerun()
                            with cedit:
                                if st.button("✏️ Editar", key=f"edit_{idx}"):
                                    st.session_state.editing_idx = idx
                                    st.experimental_rerun()

                            # Si se está editando esta receta, mostrar formulario de edición
                            if st.session_state.get("editing_idx") == idx:
                                st.info("Editando receta — modifica los campos y guarda o cancela.")
                                # prefill from current data (use keys per idx)
                                nt = st.text_input("Título", value=r.get("titulo",""), key=f"edit_titulo_{idx}")
                                ncat = st.selectbox(
                                    "Categoría",
                                    ["Sopa","Proteína","Arroz","Guarnición","Postre"],
                                    index=["Sopa","Proteína","Arroz","Guarnición","Postre"].index(r.get("categoria","Proteína")),
                                    key=f"edit_categoria_{idx}"
                                )
                                npor = st.text_input("Porciones", value=r.get("porciones","No especificado"), key=f"edit_por_{idx}")
                                ntiempo = st.text_input("Tiempo", value=r.get("tiempo",""), key=f"edit_time_{idx}")
                                ning = st.text_area("Ingredientes (uno por línea)", value="\n".join(r.get("ingredientes",[])), key=f"edit_ing_{idx}")
                                nproc = st.text_area("Procedimiento (uno por línea)", value="\n".join(r.get("procedimiento",[])), key=f"edit_proc_{idx}")

                                cc1, cc2 = st.columns([1,1])
                                with cc1:
                                    if st.button("💾 Guardar cambios", key=f"save_edit_{idx}"):
                                        if not nt.strip():
                                            st.error("El título no puede quedar vacío.")
                                        else:
                                            all_rec = cargar_recetas()
                                            if idx < len(all_rec):
                                                all_rec[idx]["titulo"] = nt.strip()
                                                all_rec[idx]["categoria"] = ncat
                                                all_rec[idx]["porciones"] = npor.strip() or "No especificado"
                                                all_rec[idx]["tiempo"] = ntiempo.strip()
                                                all_rec[idx]["ingredientes"] = [i.strip() for i in ning.split("\n") if i.strip()]
                                                all_rec[idx]["procedimiento"] = [p.strip() for p in nproc.split("\n") if p.strip()]
                                                guardar_recetas(all_rec)
                                                st.success("Receta actualizada.")
                                                st.session_state.editing_idx = None
                                                st.experimental_rerun()
                                            else:
                                                st.error("No se pudo localizar la receta para actualizar.")
                                with cc2:
                                    if st.button("Cancelar edición", key=f"cancel_edit_{idx}"):
                                        st.session_state.editing_idx = None
                                        st.experimental_rerun()
                            else:
                                # mostrar detalle completo (porciones, ingredientes, procedimiento)
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
                                # separación visual
                                st.markdown("---")

# ========== UI: Exportar recetas ==========
elif pestanas == "Exportar recetas":
    st.header("Exportar recetas guardadas")
    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas guardadas para exportar.")
    else:
        # Export JSON
        if st.button("⬇️ Descargar JSON (recetas.json)"):
            data_str = json.dumps(recetas, indent=4, ensure_ascii=False)
            st.download_button("Descargar JSON", data=data_str, file_name=RECETAS_FILE, mime="application/json")

        # Export Word
        if st.button("📄 Exportar a Word (recetario.docx)"):
            buffer = exportar_recetas_a_word(recetas)
            st.download_button("Descargar Word", data=buffer.getvalue(), file_name="recetario.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# ========== UI: Plan mensual ==========
elif pestanas == "Plan mensual":
    st.header("📅 Generar plan de alimentación mensual (sin repetir proteína/sopa)")

    recetas = cargar_recetas()
    if not recetas:
        st.info("❌ No hay recetas guardadas suficientes para armar el plan.")
    else:
        hoy = date.today()
        colA, colB = st.columns([1,1])
        with colA:
            year = st.number_input("Año", min_value=2023, max_value=2100, value=hoy.year, step=1)
        with colB:
            month = st.number_input("Mes (1-12)", min_value=1, max_value=12, value=hoy.month, step=1)
        c1, c2 = st.columns([1,1])
        with c1:
            pescado_viernes = st.checkbox("Pescado los viernes", value=True)
        with c2:
            frijoles_jueves = st.checkbox("Fríjoles/legumbres los jueves", value=True)

        if st.button("Generar plan"):
            plan = generar_plan_mensual(recetas, int(year), int(month),
                                       pescado_viernes=pescado_viernes,
                                       frijoles_jueves=frijoles_jueves)
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
                buffer = exportar_plan_a_word(plan, int(year), int(month))
                st.download_button("⬇️ Descargar plan (Word)", data=buffer.getvalue(), file_name=f"plan_{year}_{month:02d}.docx",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
