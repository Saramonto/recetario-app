import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import json
import os
from docx import Document
from docx.shared import Pt

ARCHIVO_JSON = "recetas.json"
CATEGORIAS = ["Sopa", "Proteina", "Arroz", "Guarnicion", "Ensalada", "Postre"]

def capitalizar_oracion(texto):
    # Capitaliza la primera letra, deja el resto igual
    if not texto:
        return texto
    return texto[0].upper() + texto[1:]

def extraer_receta(texto):
    texto = texto.replace("\r", "").replace("\n", "\n")
    lineas = texto.split("\n")
    ingredientes = []
    procedimiento = []
    porciones = "No especificado"
    titulo = None

    recolectando_ingredientes = False

    if lineas:
        posible_titulo = lineas[0].strip()
        if 3 < len(posible_titulo) < 50 and "ingredientes" not in posible_titulo.lower():
            titulo = capitalizar_oracion(posible_titulo)

    for linea in lineas:
        linea = linea.strip()

        if "ingredientes" in linea.lower():
            recolectando_ingredientes = True
            continue

        if re.match(r"^\d+\.", linea):
            recolectando_ingredientes = False
            procedimiento.append(capitalizar_oracion(linea))
            continue

        if recolectando_ingredientes and linea:
            ingredientes.append(capitalizar_oracion(linea))

        if "porciones" in linea.lower():
            partes = linea.split(":")
            if len(partes) > 1:
                porciones = capitalizar_oracion(partes[-1].strip())

    return titulo, ingredientes, procedimiento, porciones

def extraer_texto_desde_link(link):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(link, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        if "instagram.com" in link:
            meta = soup.find("meta", attrs={"property": "og:description"})
            texto = meta["content"] if meta else "No se encontró descripción."
            return extraer_receta(texto), link

        elif "tiktok.com" in link:
            meta = soup.find("meta", attrs={"name": "description"})
            texto = meta["content"] if meta else "No se encontró descripción."
            return (None, [], [], "No especificado"), link

        else:
            return (None, [], [], "No especificado"), link

    except Exception as e:
        st.error(f"Error al procesar el link: {e}")
        return (None, [], [], "No especificado"), link

def cargar_recetas():
    if os.path.exists(ARCHIVO_JSON):
        with open(ARCHIVO_JSON, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def guardar_recetas(recetas):
    with open(ARCHIVO_JSON, "w", encoding="utf-8") as f:
        json.dump(recetas, f, ensure_ascii=False, indent=4)

def guardar_receta(receta):
    recetas = cargar_recetas()
    recetas.append(receta)
    guardar_recetas(recetas)

def exportar_a_word(recetas, nombre_archivo="recetas_exportadas.docx"):
    doc = Document()

    # Estilos para títulos (si quieres ajustar tamaño o fuente, se puede)
    estilo_cat = doc.styles['Heading 1']
    estilo_cat.font.name = 'Arial'
    estilo_cat.font.size = Pt(16)
    estilo_cat.font.bold = True

    estilo_rec = doc.styles['Heading 2']
    estilo_rec.font.name = 'Arial'
    estilo_rec.font.size = Pt(14)
    estilo_rec.font.bold = True

    estilo_sec = doc.styles['Heading 3']
    estilo_sec.font.name = 'Arial'
    estilo_sec.font.size = Pt(12)
    estilo_sec.font.bold = True

    categorias = sorted(list(set(r["categoria"] for r in recetas)))

    for categoria in categorias:
        doc.add_heading(categoria.capitalize(), level=1)
        recetas_cat = [r for r in recetas if r["categoria"] == categoria]
        for r in recetas_cat:
            doc.add_heading(r["titulo"], level=2)
            doc.add_heading("Porciones", level=3)
            doc.add_paragraph(r["porciones"])

            doc.add_heading("Ingredientes", level=3)
            for ing in r["ingredientes"]:
                doc.add_paragraph(ing, style='List Bullet')

            doc.add_heading("Procedimiento", level=3)
            for paso in r["procedimiento"]:
                doc.add_paragraph(paso, style='List Number')

            doc.add_paragraph(f"Fuente: {r['fuente']}")

    doc.save(nombre_archivo)
    return nombre_archivo

st.title("📖 Recetario Online 2.0")

pestanas = st.sidebar.radio("Navegar por:", ["Agregar receta", "Ver recetas", "Exportar recetas"])

if pestanas == "Agregar receta":
    st.header("Agregar nueva receta desde Instagram o TikTok")

    link = st.text_input("🔗 Ingresa el link de la receta (Instagram o TikTok)")
    if link:
        (titulo_extraido, ingredientes, procedimiento, porciones), fuente = extraer_texto_desde_link(link)

        if not titulo_extraido:
            titulo_extraido = st.text_input("Nombre de la receta")
        else:
            st.write(f"**Título extraído:** {titulo_extraido}")

        categoria = st.selectbox("Categoría", ["Seleccionar opción"] + CATEGORIAS)

        st.write(f"**Porciones:** {porciones}")
        st.write("**Ingredientes:**")
        for i in ingredientes:
            st.write("-", i)
        st.write("**Procedimiento:**")
        for p in procedimiento:
            st.write(p)

        guardar = st.button("Guardar receta")
        if guardar:
            if not titulo_extraido or titulo_extraido.strip() == "":
                st.error("❌ Por favor, ingresa un nombre para la receta.")
            elif categoria == "Seleccionar opción":
                st.error("❌ Por favor, selecciona una categoría.")
            else:
                receta_guardar = {
                    "titulo": capitalizar_oracion(titulo_extraido.strip()),
                    "categoria": categoria.capitalize(),
                    "porciones": porciones,
                    "ingredientes": ingredientes,
                    "procedimiento": procedimiento,
                    "fuente": fuente
                }
                guardar_receta(receta_guardar)
                st.success("✅ Receta guardada correctamente!")

elif pestanas == "Ver recetas":
    st.header("Recetas guardadas por categoría")

    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas guardadas aún.")
    else:
        categorias_encontradas = sorted(list(set(r["categoria"] for r in recetas)))

        for categoria in categorias_encontradas:
            with st.expander(f"Categoría: {categoria}"):
                recetas_filtradas = [r for r in recetas if r["categoria"] == categoria]
                if not recetas_filtradas:
                    st.write("No hay recetas en esta categoría.")
                else:
                    for idx, receta in enumerate(recetas_filtradas):
                        with st.expander(receta["titulo"]):
                            # Editable fields para editar receta
                            nuevo_titulo = st.text_input(f"Editar nombre receta #{idx}", value=receta["titulo"], key=f"titulo_{categoria}_{idx}")
                            nueva_categoria = st.selectbox(f"Editar categoría #{idx}", ["Seleccionar opción"] + CATEGORIAS, index=CATEGORIAS.index(receta["categoria"]) + 1 if receta["categoria"] in CATEGORIAS else 0, key=f"categoria_{categoria}_{idx}")
                            nuevas_porciones = st.text_input(f"Editar porciones #{idx}", value=receta["porciones"], key=f"porciones_{categoria}_{idx}")
                            nuevos_ingredientes = st.text_area(f"Editar ingredientes (uno por línea) #{idx}", value="\n".join(receta["ingredientes"]), key=f"ingredientes_{categoria}_{idx}")
                            nuevos_procedimientos = st.text_area(f"Editar procedimiento (uno por línea) #{idx}", value="\n".join(receta["procedimiento"]), key=f"procedimiento_{categoria}_{idx}")

                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button(f"Guardar cambios #{idx}", key=f"guardar_{categoria}_{idx}"):
                                    if not nuevo_titulo.strip():
                                        st.error("❌ El nombre de la receta no puede estar vacío.")
                                    elif nueva_categoria == "Seleccionar opción":
                                        st.error("❌ Debe seleccionar una categoría válida.")
                                    else:
                                        # Actualizar receta
                                        receta["titulo"] = capitalizar_oracion(nuevo_titulo.strip())
                                        receta["categoria"] = nueva_categoria.capitalize()
                                        receta["porciones"] = capitalizar_oracion(nuevas_porciones.strip())
                                        receta["ingredientes"] = [capitalizar_oracion(i.strip()) for i in nuevos_ingredientes.strip().split("\n") if i.strip()]
                                        receta["procedimiento"] = [capitalizar_oracion(p.strip()) for p in nuevos_procedimientos.strip().split("\n") if p.strip()]

                                        # Guardar cambios en archivo
                                        todas_recetas = cargar_recetas()
                                        # Encontrar y reemplazar en lista
                                        for i, r in enumerate(todas_recetas):
                                            if r["fuente"] == receta["fuente"] and r["titulo"] == receta["titulo"]:
                                                todas_recetas[i] = receta
                                                break
                                        else:
                                            # Si no lo encuentra por fuente+titulo, buscar por id índice (en este caso sin id, se busca por posición)
                                            todas_recetas = recetas
                                        guardar_recetas(todas_recetas)
                                        st.success("✅ Cambios guardados!")

                            with col2:
                                if st.button(f"Eliminar receta #{idx}", key=f"eliminar_{categoria}_{idx}"):
                                    # Eliminar receta
                                    todas_recetas = cargar_recetas()
                                    # Buscar receta para eliminar (por título y fuente, porque puede haber recetas con mismo nombre)
                                    todas_recetas = [r for r in todas_recetas if not (r["titulo"] == receta["titulo"] and r["fuente"] == receta["fuente"])]
                                    guardar_recetas(todas_recetas)
                                    st.success("🗑️ Receta eliminada!")
                                    st.experimental_rerun()

elif pestanas == "Exportar recetas":
    st.header("Exportar recetas guardadas")

    recetas = cargar_recetas()
    if not recetas:
        st.info("No hay recetas guardadas para exportar.")
    else:
        opciones = ["Todas"] + sorted(list(set(r["categoria"] for r in recetas)))
        categoria_exportar = st.selectbox("Selecciona categoría para exportar", opciones)

        if st.button("Exportar a Word"):
            if categoria_exportar == "Todas":
                a_exportar = recetas
            else:
                a_exportar = [r for r in recetas if r["categoria"] == categoria_exportar]

            archivo_generado = exportar_a_word(a_exportar)
            with open(archivo_generado, "rb") as file:
                btn = st.download_button(
                    label="⬇️ Descargar archivo Word",
                    data=file,
                    file_name=archivo_generado,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
