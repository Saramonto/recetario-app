import streamlit as st
import instaloader
import re

# --- Función para obtener la descripción de un post de Instagram ---
def get_instagram_caption(url):
    try:
        L = instaloader.Instaloader(download_pictures=False, download_videos=False, download_video_thumbnails=False,
                                    download_comments=False, save_metadata=False, compress_json=False)
        shortcode = url.split("/")[-2]  # extrae el ID del post (ej: DM7IUz9NUv8)
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        return post.caption
    except Exception as e:
        return f"Error obteniendo datos: {e}"

# --- Procesar receta desde el caption ---
def parse_recipe(caption):
    recipe = {"title": "", "serves": "", "time": "", "ingredients": [], "method": []}

    # 1. Extraer título (primera línea)
    lines = caption.split("\n")
    recipe["title"] = lines[0].strip()

    # 2. Buscar porciones y tiempo
    match_serves = re.search(r"Serves\s+(\d+)", caption, re.IGNORECASE)
    if match_serves:
        recipe["serves"] = match_serves.group(1)

    match_time = re.search(r"Takes\s+([\w\s]+)", caption, re.IGNORECASE)
    if match_time:
        recipe["time"] = match_time.group(1)

    # 3. Ingredientes
    if "Ingredients:" in caption:
        ingredients_text = caption.split("Ingredients:")[1].split("Method:")[0]
        recipe["ingredients"] = [i.strip("•- ") for i in ingredients_text.split("\n") if i.strip()]

    # 4. Método
    if "Method:" in caption:
        method_text = caption.split("Method:")[1]
        recipe["method"] = [m.strip("•- ") for m in method_text.split("\n") if m.strip()]

    return recipe

# --- Interfaz Streamlit ---
st.set_page_config(page_title="Extractor de Recetas IG", page_icon="🍝", layout="centered")
st.title("🍴 Extractor de Recetas desde Instagram")

url = st.text_input("Pega el enlace del post de Instagram (ejemplo: reel o publicación):")

if url:
    caption = get_instagram_caption(url)
    
    if "Error" in caption:
        st.error(caption)
    else:
        recipe = parse_recipe(caption)

        st.subheader(f"📌 {recipe['title']}")
        st.write(f"👥 Porciones: {recipe['serves']} | ⏱ Tiempo: {recipe['time']}")

        st.subheader("🥗 Ingredientes")
        for ing in recipe["ingredients"]:
            st.markdown(f"- {ing}")

        st.subheader("👨‍🍳 Método")
        for i, step in enumerate(recipe["method"], 1):
            st.markdown(f"{i}. {step}")
