import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import json
import os

# Archivo para guardar las recetas
ARCHIVO_JSON = "recetas.json"

# Categorías disponibles
CATEGORIAS = ["sopa", "proteina", "arroz", "guarnicion", "ensalada", "postre"]

# --- FUNCIONES ---

def extraer_receta(texto):
    texto = texto.replace("\r", "").replace("\n", "\n")
    lineas = texto.split("\n")
    ingredientes = []
    procedimiento = []
    porciones = "No especificado"
    titulo = None

    recolectando_ingredientes = False

    # Intentar sacar título del principio, si está todo en mayúscula o tras 'INGREDIENTES:' salteamos
    if lineas:
        posible_titulo = lineas[0].strip()
        if 3 < len(posible_titulo) < 50 and "ingredientes" not in posible_titulo.lower():
            titulo = posible_titulo

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

def guardar_receta(receta):
    recetas = cargar_recetas()
    recetas.append(receta)
    with open(ARCHIVO_JSON, "w", encoding="utf-8") as f:
        json.dump(recetas, f, ensure_ascii=False, indent=4)

# --- INTERFAZ ---

st.title("📖 Recetario Online")

pestanas = st.sidebar.radio("Navegar por:", ["Agregar receta", "Ver recetas"])

if pestanas == "Agregar receta":
    st.header("Agregar nueva receta desde Instagram o TikTok")

    link = st.text_input("🔗 Ingresa el link de la receta (Instagram o TikTok)")
    if link:
        (titulo_extraido, ingredientes, procedimiento, porciones), fuente = extraer_texto_desde_link(link)

        if not titulo_extraido:
            titulo_extraido = st.text_input("Nombre de la receta", "")

        else:
            st.write(f"**Título extraído:** {titulo_extraido}")

        categoria = st.selectbox("Categoría", CATEGORIAS)

        st.write(f"**Porciones:** {porciones}")
        st.write("**Ingredientes:**")
        for i in ingredientes:
            st.write("-", i)
        st.write("**Procedimiento:**")
        for p in procedimiento:
            st.write(p)

        guardar = st.button("Guardar receta")
        if guardar:
            if not titulo_extraido:
                st.error("Por favor, ingresa un nombre para la receta.")
            else:
                receta_guardar = {
                    "titulo": titulo_extraido,
                    "categoria": categoria,
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
        categoria_seleccionada = st.selectbox("Filtrar por categoría", ["Todas"] + categorias_encontradas)

        if categoria_seleccionada == "Todas":
            recetas_filtradas = recetas
        else:
            recetas_filtradas = [r for r in recetas if r["categoria"] == categoria_seleccionada]

        for receta in recetas_filtradas:
            with st.expander(f'{receta["titulo"]}'):
                st.markdown(f"**Categoría:** {receta['categoria'].capitalize()}")
                st.markdown(f"**Porciones:** {receta['porciones']}")
                st.markdown("**Ingredientes:**")
                for ing in receta["ingredientes"]:
                    st.write("-", ing)
                st.markdown("**Procedimiento:**")
                for paso in receta["procedimiento"]:
                    st.write(paso)
                st.markdown(f"[Fuente]({receta['fuente']})")


