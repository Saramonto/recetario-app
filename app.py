import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import os
from docx import Document

# ========== FUNCIONES BASE ==========

def limpiar_texto(texto):
    texto = re.sub(r"@[A-Za-z0-9_]+", "", texto)
    texto = re.sub(r"#\w+", "", texto)
    texto = re.sub(r"[^\x00-\x7F]+", " ", texto)
    return texto.strip()

def extraer_texto_desde_link(link):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.get(link, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        if "instagram.com" in link:
            meta = soup.find("meta", attrs={"property": "og:description"}) or \
                   soup.find("meta", attrs={"name": "description"})
        elif "tiktok.com" in link:
            meta = soup.find("meta", attrs={"name": "description"}) or \
                   soup.find("meta", attrs={"property": "og:description"})
        else:
            return None

        if meta and "content" in meta.attrs:
            return limpiar_texto(meta["content"])
        return None

    except Exception:
        return None

def extraer_titulo_de_texto(texto):
    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
    if lineas:
        posible_titulo = lineas[0]
        if 3 <= len(posible_titulo) <= 50:
            return posible_titulo
    return None

def extraer_ingredientes_y_procedimiento(texto):
    lineas = texto.split("\n")
    ingredientes = {}
    procedimiento = []
    porciones = "No especificado"
    seccion_actual = None
    modo_ingredientes = False
    modo_procedimiento = False

    for linea in lineas:
        linea = linea.strip()
        if "porciones" in linea.lower() or "rinde" in linea.lower():
            partes = re.split(r":|-", linea)
            if len(partes) > 1:
                porciones = partes[-1].strip()
        if re.match(r"^(ingredientes|ganache|para decorar|relleno|masa|salsa|cobertura)", linea.lower()):
            seccion_actual = linea
            modo_ingredientes = True
            modo_procedimiento = False
            if seccion_actual not in ingredientes:
                ingredientes[seccion_actual] = []
            continue
        if re.match(r"^\d+\.", linea):
            modo_ingredientes = False
            modo_procedimiento = True
        if modo_ingredientes:
            if linea:
                ingredientes.setdefault(seccion_actual or "Ingredientes generales", []).append(linea)
            continue
        if modo_procedimiento:
            if linea:
                procedimiento.append(linea)
    return ingredientes, procedimiento, porciones

def guardar_en_word(data, archivo="recetas.docx"):
    if os.path.exists(archivo):
        doc = Document(archivo)
    else:
        doc = Document()

    doc.add_heading(data.get("categoria", "Categoría").capitalize(), level=1)
    doc.add_heading(data.get("titulo", "Receta sin título"), level=2)
    
    doc.add_heading("Porciones", level=3)
    doc.add_paragraph(data.get("porciones", "No especificado"))

    doc.add_heading("Ingredientes", level=3)
    for seccion, lista in data.get("ingredientes", {}).items():
        doc.add_heading(seccion.capitalize(), level=4)
        for ing in lista:
            doc.add_paragraph(ing, style='List Bullet')

    doc.add_heading("Procedimiento", level=3)
    for paso in data.get("procedimiento", []):
        doc.add_paragraph(paso, style='List Number')

    doc.add_paragraph("\n")
    doc.save(archivo)
    return True

# ========== APP STREAMLIT ==========

st.set_page_config(page_title="Recetario Web", layout="centered")
st.title("📱 Recetario desde Instagram o TikTok")

link = st.text_input("🔗 Pegá el link de la receta:")
if st.button("Extraer receta"):
    if not link:
        st.warning("Por favor, ingresá un link.")
    else:
        texto = extraer_texto_desde_link(link)
        if not texto:
            st.error("No se pudo extraer texto del link.")
        else:
            titulo_sugerido = extraer_titulo_de_texto(texto) or ""
            ingredientes, procedimiento, porciones = extraer_ingredientes_y_procedimiento(texto)

            st.success("✅ Receta detectada correctamente.")
            with st.form("guardar_receta_form"):
                titulo = st.text_input("📌 Título de la receta:", value=titulo_sugerido)
                categorias = ["sopa", "proteina", "arroz", "guarnicion", "ensalada", "postre"]
                categoria = st.selectbox("📂 Categoría:", categorias)
                mostrar_texto = st.text_area("📄 Texto completo extraído:", value=texto, height=200)

                guardar = st.form_submit_button("Guardar receta")
                if guardar:
                    data = {
                        "fuente": link,
                        "titulo": titulo,
                        "categoria": categoria,
                        "ingredientes": ingredientes,
                        "procedimiento": procedimiento,
                        "porciones": porciones
                    }
                    guardar_en_word(data)
                    st.success("💾 Receta guardada en 'recetas.docx'")

