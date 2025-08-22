import streamlit as st
from bs4 import BeautifulSoup
import requests
import re
from docx import Document
from docx.shared import Pt
from docx.enum.style import WD_STYLE_TYPE
import json
import os

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
            # Intentar extraer título de la descripción
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
            # Aquí podrías adaptar según formato TikTok
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
    except Exception as e:
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
    
    # Estilos personalizados
    styles = doc.styles
    
    # Titulo 1: Categoría
    if 'Titulo1' not in styles:
        style1 = styles.add_style('Titulo1', WD_STYLE_TYPE.PARAGRAPH)
        style1.font.size = Pt(16)
        style1.font.bold = True
    else:
        style1 = styles['Titulo1']
    # Titulo 2: Nombre receta
    if 'Titulo2' not in styles:
        style2 = styles.add_style('Titulo2', WD_STYLE_TYPE.PARAGRAPH)
        style2.font.size = Pt(14)
        style2.font.bold = True
    else:
        style2 = styles['Titulo2']
    # Titulo 3: Porciones, ingredientes, procedimiento
    if 'Titulo3' not in styles:
        style3 = styles.add_style('Titulo3', WD_STYLE_TYPE.PARAGRAPH)
        style3.font.size = Pt(12)
        style3.font.bold = True
    else:
        style3 = styles['Titulo3']

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
            doc.add_paragraph("")  # espacio
    
    doc.save(nombre_archivo)
    return nombre_archivo

# --- Streamlit UI ---

st.title("📚 Recetario desde Instagram/TikTok")

pestanas = st.sidebar.radio("Navegación", ["Nueva receta", "Ver recetas", "Exportar recetas"])

if pestanas == "Nueva receta":
    st.header("Agregar nueva receta desde enlace")

    link = st.text_input("Ingresa el link del post (Instagram o TikTok):")
    if link:
        datos_receta = extraer_texto_desde_link(link)

        # Tomar título de la descripción, si está vacío pedir nombre
        titulo_detectado = datos_receta.get("titulo", "").strip()
        if titulo_detectado:
            titulo_receta = st.text_input("Nombre de la receta (detectado o ingresa otro):", value=titulo_detectado)
        else:
            titulo_receta = st.text_input("Nombre de la receta:")

        categorias = ["Seleccionar opción", "Sopa", "Proteína", "Arroz", "Guarnición", "Ensalada", "Postre"]
        categoria = st.selectbox("Selecciona categoría", categorias)

        porciones = st.text_input("Porciones:", value=datos_receta.get("porciones", "No especificado"))
        ingredientes = st.text_area("Ingredientes (separados por línea):", value="\n".join(datos_receta.get("ingredientes", [])))
        procedimiento = st.text_area("Procedimiento (pasos numerados, separados por línea):", value="\n".join(datos_receta.get("procedimiento", [])))

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

                        # Botones eliminar y editar (sin funcionalidad por ahora)
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"Eliminar receta: {r['titulo']}", key=f"eliminar_{categoria}_{idx}"):
                                recetas.remove(r)
                                guardar_recetas(recetas)
                                st.experimental_rerun()
                        with col2:
                            if st.button(f"Editar receta: {r['titulo']}", key=f"editar_{categoria}_{idx}"):
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
        seleccionadas = st.multiselect(
            "Selecciona las recetas a exportar (puedes seleccionar varias):",
            options=nombres_recetas,
            default=nombres_recetas if categoria_exportar == "Todas" else []
        )

        if st.button("Exportar a Word"):
            if not seleccionadas:
                st.error("❌ Por favor, selecciona al menos una receta para exportar.")
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
