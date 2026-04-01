import os
import time
import tempfile
import shutil
import zipfile
from io import BytesIO
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
from PIL import Image

import streamlit as st

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# ================= DRIVER SETUP =================

def setup_driver():

    chrome_options = Options()

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.implicitly_wait(5)

    return driver


# ================= UTILITIES =================

def remove_sticky_elements(driver):

    driver.execute_script("""
    var elements = document.querySelectorAll('*');
    for (var i = 0; i < elements.length; i++) {
        var style = window.getComputedStyle(elements[i]);
        if (style.position === 'fixed' || style.position === 'sticky') {
            elements[i].style.position = 'absolute';
        }
    }
    """)


def capture_fullpage_screenshot(driver, url, folder):

    driver.get(url)

    time.sleep(3)

    remove_sticky_elements(driver)

    time.sleep(1)

    total_height = driver.execute_script(
        "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
    )

    viewport_height = driver.execute_script("return window.innerHeight")

    images = []

    scroll_position = 0

    while scroll_position < total_height:

        driver.execute_script(f"window.scrollTo(0,{scroll_position})")

        time.sleep(0.6)

        png = driver.get_screenshot_as_png()

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")

        with open(temp_file.name, "wb") as f:
            f.write(png)

        img = Image.open(temp_file.name)

        images.append(img)

        scroll_position += viewport_height

    total_width = max(img.width for img in images)
    combined_height = sum(img.height for img in images)

    stitched_image = Image.new("RGB", (total_width, combined_height))

    y_offset = 0

    for img in images:
        stitched_image.paste(img, (0, y_offset))
        y_offset += img.height

    parsed = urlparse(url)

    safe_name = parsed.netloc.replace("www.", "").replace(".", "_")

    path_part = parsed.path.strip("/").replace("/", "_") or "homepage"

    filename = "".join(
        c if c.isalnum() or c in "_-." else "_" for c in f"{safe_name}_{path_part}.png"
    )

    file_path = os.path.join(folder, filename)

    stitched_image.save(file_path)

    for img in images:
        try:
            os.remove(img.filename)
        except:
            pass

    return file_path


def zip_folder(folder_path):

    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:

        for root, _, files in os.walk(folder_path):

            for file in files:

                full_path = os.path.join(root, file)

                arcname = os.path.relpath(full_path, folder_path)

                zipf.write(full_path, arcname)

    zip_buffer.seek(0)

    return zip_buffer


# ================= STREAMLIT APP =================

def main():

    st.set_page_config(page_title="Policies Screenshot Maker", layout="wide")

    st.title("Policies Screenshot Maker")

    st.write("Capture full-page screenshots and download them as ZIP.")

    st.subheader("Provide URLs")

    input_mode = st.radio(
        "Choose Input Method",
        [
            "Manual Input (16 URLs)",
            "Paste Multiple URLs",
            "Upload Excel / CSV File",
        ],
    )

    urls = []

    if input_mode == "Manual Input (16 URLs)":

        cols = st.columns(2)

        for i in range(16):

            col = cols[i % 2]

            url = col.text_input(f"URL {i+1}", key=f"url_{i}")

            if url.strip():

                if not url.startswith(("http://", "https://")):
                    url = "https://" + url.strip()

                urls.append(url.strip())

    elif input_mode == "Paste Multiple URLs":

        bulk_urls = st.text_area("Paste URLs (one per line)", height=250)

        if bulk_urls:

            for line in bulk_urls.splitlines():

                url = line.strip()

                if url:

                    if not url.startswith(("http://", "https://")):
                        url = "https://" + url

                    urls.append(url)

    elif input_mode == "Upload Excel / CSV File":

        uploaded_file = st.file_uploader(
            "Upload file containing URLs",
            type=["xlsx", "xls", "csv"]
        )

        if uploaded_file is not None:

            try:

                if uploaded_file.name.endswith(".csv"):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)

                st.dataframe(df.head())

                url_column = df.columns[0]

                for u in df[url_column].dropna():

                    url = str(u).strip()

                    if not url.startswith(("http://", "https://")):
                        url = "https://" + url

                    urls.append(url)

                st.success(f"{len(urls)} URLs loaded")

            except Exception as e:

                st.error(f"Error reading file: {e}")

    if st.button("Start Capture"):

        if not urls:

            st.warning("Please provide at least one URL")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        output_folder = f"Policies_Screenshots_{timestamp}"

        os.makedirs(output_folder, exist_ok=True)

        try:

            driver = setup_driver()

            st.success("Chrome launched")

            progress = st.progress(0.0)

            for i, url in enumerate(urls, 1):

                st.write(f"Capturing {url}")

                try:

                    file_path = capture_fullpage_screenshot(
                        driver,
                        url,
                        output_folder
                    )

                    st.image(file_path, caption=url)

                except Exception as e:

                    st.error(f"Failed: {url} — {e}")

                progress.progress(i / len(urls))

            driver.quit()

            st.success("All screenshots captured")

        except Exception as e:

            st.error(f"Fatal error: {e}")

        zip_buffer = zip_folder(output_folder)

        st.download_button(
            label="Download All Screenshots (ZIP)",
            data=zip_buffer,
            file_name=f"{output_folder}.zip",
            mime="application/zip",
        )


if __name__ == "__main__":
    main()
