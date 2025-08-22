import streamlit as st
from bs4 import BeautifulSoup
import requests
import re
from docx import Document
from docx.shared import Pt
from docx.enum.style import WD_STYLE_TYPE
import json
import os
import calendar
import random
from datetime import date

# --- Funciones para manejo de recetas ---

def capitalizar_oracion(texto):
    if not texto:
        return texto
    return texto[0].upper() + texto[1:].lower()

def extraer_receta(texto):
    texto = texto.replace("\r", "").replace("\n", "\n")  # Normaliza saltos
    lineas = texto.split("\n")
    ingredientes = []
    procedimiento = []
    porciones = "No especificado"

    recolectando_ingredientes = False

    for linea in lineas:
        linea = linea.strip()

        if "ingredientes" in linea.lower():
            recolectando_ingredientes = True
            continue

        if re.match(r"^\d+\.", linea):
            recolectando_ingredientes = False
            procedimiento.append(linea)
            continue

        if recolectando_ingredientes and linea:
            ingredientes.append(linea)

        if "porciones" in linea.lower():
            partes = linea.split(":")
            if len(partes) > 1:
                porciones = partes[-1].strip()

    return ingredientes, procedimiento, porciones

def extraer_texto_desde_link(link):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(link, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        if "instagram.com" in link:
            meta = soup.find("meta", attrs={"property": "og:description"})
            texto = meta["content"] if meta else "No se encontró descripción."
            ingredientes, procedimiento, porciones = extraer_receta(texto)
            titulo = texto.split("INGREDIENTES")[0].strip() if "INGREDIENTES" in texto else ""
            return {
                "fuente": link,
                "titulo": titulo,
                "ingredientes": ingredientes,
                "procedimiento": procedimiento,
                "porciones": porciones
            }
        elif "tiktok.com" in link:
            meta = soup.find("meta", attrs={"name": "description"})
            texto = meta["content"] if meta else "No se encontró descripción."
            return {
                "fuente": link,
                "titulo": "",
                "ingredientes": [],
                "procedimiento": [],
                "porciones": "No especificado"
            }
        else:
            return {
                "fuente": link,
                "titulo": "",
                "ingredientes": [],
                "procedimiento": [],
                "porciones": "No especificado"
            }
    except Exception:
        return {
            "fuente": link,
            "titulo": "",
            "ingredientes": [],
            "procedimiento": [],
            "porciones": "No especificado"
        }

def cargar_recetas(nombre_archivo="recetas.json"):
    if not os.path.exists(nombre_archivo):
        return []
    with open(nombre_archivo, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def guardar_recetas(lista_recetas, nombre_archivo="recetas.json"):
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(lista_recetas, f, ensure_ascii=False, indent=4)

def exportar_a_word(recetas, nombre_archivo="recetas_exportadas.docx"):
    doc = Document()
    
    styles = doc.styles
    if 'Titulo1' not in styles:
        style1 = styles.add_style('Titulo1', WD_STYLE_TYPE.PARAGRAPH)
        style1.font.size = Pt(16)
        style1.font.bold = True
    if 'Titulo2' not in styles:
        style2 = styles.add_style('Titulo2', WD_STYLE_TYPE.PARAGRAPH)
        style2.font.size = Pt(14)
        style2.font.bold = True
    if 'Titulo3' not in styles:
        style3 = styles.add_style('Titulo3', WD_STYLE_TYPE.PARAGRAPH)
        style3.font.size = Pt(12)
        style3.font.bold = True

    categorias = sorted(set([r['categoria'] for r in recetas]))
    for categoria in categorias:
        doc.add_paragraph(categoria, style='Titulo1')
        recetas_categoria = [r for r in recetas if r['categoria'] == categoria]
        for r in recetas_categoria:
            doc.add_paragraph(r['titulo'], style='Titulo2')
            doc.add_paragraph(f"Porciones: {r['porciones']}", style='Titulo3')
            doc.add_paragraph("Ingredientes:", style='Titulo3')
            for ing in r['ingredientes']:
                doc.add_paragraph(ing, style='Normal')
            doc.add_paragraph("Procedimiento:", style='Titulo3')
            for paso in r['procedimiento']:
                doc.add_paragraph(paso, style='Normal')
            doc.add_paragraph("")  
    
    doc.save(nombre_archivo)
    return nombre_archivo

# --- Función para plan mensual ---

def generar_plan_mensual(recetas, restricciones=None):
    if restricciones is None:
        restricciones = {}
    recetas_por_cat = {}
    for r in recetas:
        recetas_por_cat.setdefault(r["categoria"], []).append(r)

    dias_mes = calendar.monthrange(date.today().year, date.today().month)[1]
    plan = []

    ultima_proteina = ""
    ultima_sopa = ""

    for dia in range(1, dias_mes + 1):
        fecha = date(date.today().year, date.today().month, dia)
        dia_semana = fecha.strftime("%A")

        comida_dia = {"fecha": str(fecha), "menu": {}, "notas": ""}

        # Sopa
        sopas = recetas_por_cat.get("Sopa", [])
        sopa = random.choice([s for s in sopas if s["titulo"] != ultima_sopa]) if sopas else None
        if sopa:
            comida_dia["menu"]["Sopa"] = sopa["titulo"]
            ultima_sopa = sopa["titulo"]

        # Proteína
        proteinas = recetas_por_cat.get("Proteína", [])
        proteina = None
        if dia_semana in restricciones:
            proteina = next((p for p in proteinas if restricciones[dia_semana].lower() in " ".join(p["ingredientes"]).lower()), None)

        if not proteina and proteinas:
            proteina = random.choice([p for p in proteinas if p["titulo"] != ultima_proteina])

        if proteina:
            comida_dia["menu"]["Proteína"] = proteina["titulo"]
            ultima_proteina = proteina["titulo"]

        # Otras categorías
        for cat in ["Guarnición", "Ensalada", "Postre"]:
            opciones = recetas_por_cat.get(cat, [])
            if opciones:
                comida_dia["menu"][cat] = random.choice(opciones)["titulo"]

        plan.append(comida_dia)

    return plan

# --- Streamlit UI ---

st.title("📚 Recetario desde Instagram/TikTok")

pestanas = st.sidebar.radio("Navegación", ["Nueva receta", "Ver recetas", "Exportar recetas", "Plan mensual"])

if pestanas == "Nueva receta":
    st.header("Agregar nueva receta desde enlace")
    link = st.text_input("Ingresa el link del post (Instagram o TikTok):")
    if link:
        datos_receta = extraer_texto_desde_link(link)
        titulo_detectado = datos_receta.get("titulo", "").strip()
        if titulo_detectado:
            titulo_receta = st.text_input("Nombre de la receta:", value=titulo_detectado)
        else:
            titulo_receta = st.text_input("Nombre de la receta:")

        categorias = ["Seleccionar opción", "Sopa", "Proteína", "Arroz", "Guarnición", "Ensalada", "Postre"]
        categoria = st.selectbox("Selecciona categoría", categorias)

        porciones = st.text_input("Porciones:", value=datos_receta.get("porciones", "No especificado"))
        ingredientes = st.text_area("Ingredientes:", value="\n".join(datos_receta.get("ingredientes", [])))
        procedimiento = st.text_area("Procedimiento:", value="\n".join(datos_receta.get("procedimiento", [])))

        if st.button("Guardar receta"):
            if categoria == "Seleccionar opción":
                st.error("❌ Debes seleccionar una categoría válida.")
            elif not titulo_receta.strip():
                st.error("❌ Debes ingresar un nombre para la receta.")
            else:
                recetas = cargar_recetas()
                nueva_receta = {
                    "fuente": link,
                    "titulo": capitalizar_oracion(titulo_receta.strip()),
                    "categoria": capitalizar_oracion(categoria.strip()),
                    "porciones": porciones.strip(),
                    "ingredientes": [i.strip() for i in ingredientes.split("\n") if i.strip()],
                    "procedimiento": [p.strip() for p in procedimiento.split("\n") if p.strip()]
                }
                recetas.append(nueva_receta)
                guardar_recetas(recetas)
                st.success("✅ Receta guardada exitosamente.")

elif pestanas == "Ver recetas":
    st.header("Recetas guardadas")
    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas guardadas aún.")
    else:
        categorias = sorted(set([r["categoria"] for r in recetas]))
        for categoria in categorias:
            with st.expander(categoria):
                recetas_cat = [r for r in recetas if r["categoria"] == categoria]
                for idx, r in enumerate(recetas_cat):
                    with st.expander(r["titulo"]):
                        st.markdown(f"**Porciones:** {r['porciones']}")
                        st.markdown("**Ingredientes:**")
                        for ing in r["ingredientes"]:
                            st.write(f"- {ing}")
                        st.markdown("**Procedimiento:**")
                        for paso in r["procedimiento"]:
                            st.write(f"- {paso}")

                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"Eliminar: {r['titulo']}", key=f"del_{categoria}_{idx}"):
                                recetas.remove(r)
                                guardar_recetas(recetas)
                                st.experimental_rerun()
                        with col2:
                            if st.button(f"Editar: {r['titulo']}", key=f"edit_{categoria}_{idx}"):
                                st.info("Funcionalidad de edición no implementada aún.")

elif pestanas == "Exportar recetas":
    st.header("Exportar recetas guardadas")
    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas guardadas para exportar.")
    else:
        opciones_categoria = ["Todas"] + sorted(list(set(r["categoria"] for r in recetas)))
        categoria_exportar = st.selectbox("Selecciona categoría para exportar", opciones_categoria)
        if categoria_exportar == "Todas":
            recetas_filtradas = recetas
        else:
            recetas_filtradas = [r for r in recetas if r["categoria"] == categoria_exportar]

        nombres_recetas = [r["titulo"] for r in recetas_filtradas]
        seleccionadas = st.multiselect("Selecciona las recetas a exportar:", options=nombres_recetas, default=nombres_recetas)

        if st.button("Exportar a Word"):
            if not seleccionadas:
                st.error("❌ Selecciona al menos una receta.")
            else:
                a_exportar = [r for r in recetas_filtradas if r["titulo"] in seleccionadas]
                archivo_generado = exportar_a_word(a_exportar)
                with open(archivo_generado, "rb") as file:
                    st.download_button(
                        label="⬇️ Descargar archivo Word",
                        data=file,
                        file_name=archivo_generado,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )

elif pestanas == "Plan mensual":
    st.header("📅 Plan de alimentación mensual")
    recetas = cargar_recetas()
    if not recetas:
        st.info("❌ No hay recetas guardadas suficientes para armar el plan.")
    else:
        if st.button("Generar plan"):
            restricciones = {"Friday": "pescado", "Thursday": "frijol"}  # ejemplo
            plan = generar_plan_mensual(recetas, restricciones)

            for dia in plan:
                st.subheader(dia["fecha"])
                for categoria, plato in dia["menu"].items():
                    st.write(f"**{categoria}:** {plato}")
                st.text_area("Notas:", value=dia["notas"], key=dia["fecha"])
