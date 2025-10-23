#!/usr/bin/env python3
# ============================================================
# DB-Pricing • Streamlit Web App
# Coleta Tabela de Preços (Portal DB) -> Gera Excel (.xlsx)
# Tema: Azul/Branco (dashboard profissional)
# ============================================================

import os
import time
from io import BytesIO
from datetime import datetime

import pandas as pd
import streamlit as st

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ============================================================
# Aparência / Layout
# ============================================================
st.set_page_config(
    page_title="DB-Pricing",
    page_icon="🧪",
    layout="wide",
)

st.markdown(
    """
    <style>
    .css-18ni7ap {padding-top: 1rem;}
    .css-1d391kg {padding-top: 1rem;}
    .stProgress > div > div > div > div { background-color: #007BFF; }
    .big-label { font-size: 1.05rem; font-weight: 600; color: #0b4da2; }
    .hint { color:#6b7280; font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🧪 DB-Pricing")
st.caption("Coleta a **Tabela de Preços** do portal Diagnósticos do Brasil e gera um **Excel (.xlsx)** — sem instalar nada.")


# ============================================================
# Helpers
# ============================================================
def _normalize_servsol(raw: str) -> str:
    """Garante o formato do parâmetro ServSol (ex.: 'c14296')."""
    raw = (raw or "").strip()
    if not raw:
        return "c14296"
    # aceita "14296" e coloca 'c' na frente
    if raw.lower().startswith("c"):
        return raw.lower()
    return "c" + raw


def _headless_chrome() -> webdriver.Chrome:
    """
    Inicializa um Chrome headless que funcione:
      • localmente (Linux/Windows/Mac) com webdriver_manager
      • no Streamlit Cloud (via packages.txt com chromium + chromium-driver)
    """
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,768")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")

    # 1) Tenta chromedriver do sistema (ex: Streamlit Cloud: chromium + chromium-driver)
    for path in ("/usr/bin/chromedriver", "/usr/lib/chromium/chromedriver"):
        if os.path.exists(path):
            try:
                return webdriver.Chrome(service=Service(path), options=options)
            except WebDriverException:
                pass

    # 2) Fallback pro webdriver_manager (máquinas locais com Google Chrome)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        raise RuntimeError(
            f"Falha ao inicializar o Chrome. Erro: {e}\n"
            "Se estiver no Streamlit Cloud, confirme que instalou os pacotes do SO (packages.txt): 'chromium' e 'chromium-driver'."
        )


def _wait_disappear(driver, by, value, timeout=15):
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located((by, value))
        )
    except Exception:
        pass


def _click_next_page(driver, status, tentativas=3):
    for tent in range(tentativas):
        try:
            btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//button[@aria-label="go to next page"]'))
            )
            btn.click()
            _wait_disappear(driver, By.ID, "b1-b1-DIV_SplashLoading", 15)
            time.sleep(1.0)
            return True
        except Exception:
            status.write(f"🔁 Re-tentando avançar a página... ({tent+1}/{tentativas})")
            time.sleep(1.0)
    return False


def _login(driver, servsol, user, pwd, status):
    url_login = f"https://out-prd.diagnosticosdobrasil.com.br/Portal/Login?ServSol={servsol}"
    status.write("🌎 Acessando portal de login…")
    try:
        driver.set_page_load_timeout(60)
        driver.get(url_login)
    except TimeoutException:
        status.write("⚠️ Timeout no carregamento — atualizando…")
        driver.refresh()
        time.sleep(2)

    status.write("⌛ Aguardando campos de login…")
    user_input = WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((By.ID, "Input_UsernameVal"))
    )
    pass_input = driver.find_element(By.ID, "Input_PasswordVal")

    status.write("🧾 Preenchendo usuário e senha…")
    user_input.clear(); user_input.send_keys(user.strip())
    pass_input.clear(); pass_input.send_keys(pwd)

    driver.find_element(By.CSS_SELECTOR, "button.btn-login").click()
    status.write("🔐 Fazendo login…")
    WebDriverWait(driver, 30).until_not(
        EC.presence_of_element_located((By.ID, "Input_UsernameVal"))
    )
    status.write("✅ Login realizado!")


def _abrir_tabela_preco(driver, status):
    status.write("📂 Abrindo menu financeiro…")
    driver.get("https://out-prd.diagnosticosdobrasil.com.br/Portal/Financeiro?chave=")
    time.sleep(2.0)

    # Clica no item "Tabela de Preços" (primeiro da lista no side-menu)
    WebDriverWait(driver, 25).until(
        EC.element_to_be_clickable((By.CLASS_NAME, "fin-sidemenu-item"))
    ).click()
    time.sleep(1.0)

    status.write("🔍 Aplicando filtro…")
    WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, '//button[contains(@class, "btn-wb-hp-filtrar")]'))
    ).click()
    time.sleep(2.0)


def _coletar_pagina(driver):
    codigos = driver.find_elements(
        By.XPATH,
        '//div[@class="container-wb-lista-historico-preco"]'
        '//div[contains(@style, "width: 20%;")]/span[@class="exps-txts-headers"]'
    )
    nomes = driver.find_elements(
        By.XPATH,
        '//div[@class="container-wb-lista-historico-preco"]'
        '//div[contains(@style, "width: 45%;")]/span'
    )
    valores = driver.find_elements(
        By.XPATH,
        '//div[@class="container-wb-lista-historico-preco"]'
        '//div[contains(@style, "width: 20%; text-align: center;")]/span[@class="exps-txts-headers"]'
    )
    rows = []
    if len(codigos) == len(nomes) == len(valores) and len(codigos) > 0:
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        for i in range(len(codigos)):
            rows.append([
                codigos[i].text.strip(),
                nomes[i].text.strip(),
                valores[i].text.strip(),
                now
            ])
    return rows


def coletar_dados(servsol, user, pwd, start_page, max_pages, progress, status):
    """
    Fluxo principal de coleta. Retorna DataFrame.
    """
    driver = _headless_chrome()
    data_all = []
    try:
        _login(driver, servsol, user, pwd, status)
        _abrir_tabela_preco(driver, status)

        total_to_run = max_pages
        for idx in range(total_to_run):
            current_page = start_page + idx
            status.write(f"📄 Coletando página {current_page}…")
            rows = _coletar_pagina(driver)

            if rows:
                data_all.extend(rows)
                status.write(f"✅ Página {current_page} coletada ({len(rows)} registros).")
            else:
                status.write("⚠️ Página sem dados.")

            progress.progress(min((idx + 1) / total_to_run, 1.0))

            # tenta ir pra próxima; se não conseguir, encerra
            if not _click_next_page(driver, status):
                status.write("⛔ Não foi possível avançar. Finalizando.")
                break

        if not data_all:
            return pd.DataFrame(columns=["Código", "Exame", "Valor", "Data/Hora Coleta"])

        df = pd.DataFrame(data_all, columns=["Código", "Exame", "Valor", "Data/Hora Coleta"])
        return df

    except Exception as e:
        status.error(f"💥 Erro durante a coleta: {e}")
        return pd.DataFrame(columns=["Código", "Exame", "Valor", "Data/Hora Coleta"])
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def df_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="DB_Pricing")
    buf.seek(0)
    return buf.read()


# ============================================================
# UI — Formulário
# ============================================================
with st.form("form-db-pricing"):
    st.markdown("#### 🔐 Acesso ao Portal DB")
    c1, c2, c3 = st.columns([1, 1, 1.2])

    with c1:
        servsol_raw = st.text_input(
            "Código do Convênio (ServSol)",
            value="c14296",
            help="Aceita 'c14296' ou apenas '14296' (o 'c' eu coloco automaticamente).",
        )
    with c2:
        user = st.text_input("Usuário (CPF)", value="", max_chars=14, placeholder="000.000.000-00")
    with c3:
        pwd = st.text_input("Senha", value="", type="password")

    st.markdown("---")
    st.markdown("#### ⚙️ Parâmetros de Coleta")
    c4, c5 = st.columns(2)
    with c4:
        start_page = st.number_input("Página inicial", min_value=1, value=1, step=1)
    with c5:
        max_pages = st.number_input("Total de páginas a processar", min_value=1, value=5, step=1)

    submitted = st.form_submit_button("🚀 Iniciar Coleta", use_container_width=True)

# ============================================================
# Execução
# ============================================================
if submitted:
    if not user or not pwd:
        st.warning("Informe **Usuário** e **Senha**.")
        st.stop()

    servsol = _normalize_servsol(servsol_raw)
    st.info(f"Convênio: **{servsol}** — Iniciando…")

    progress = st.progress(0.0)
    status = st.empty()

    df = coletar_dados(servsol, user, pwd, start_page, max_pages, progress, status)

    st.markdown("---")
    if df.empty:
        st.error("Nenhum registro coletado. Verifique as credenciais/convênio e tente novamente.")
    else:
        st.success(f"Coleta concluída! Total de linhas: **{len(df)}**")
        st.dataframe(df.head(50), use_container_width=True)

        xlsx_bytes = df_to_xlsx_bytes(df)
        st.download_button(
            "💾 Baixar Excel (.xlsx)",
            data=xlsx_bytes,
            file_name=f"DB_Pricing_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )