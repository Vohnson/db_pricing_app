import os
import time
from io import BytesIO
from datetime import datetime

import pandas as pd
import streamlit as st

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

# ---------------------------
# UI (Streamlit) – aparência e layout
# ---------------------------
st.set_page_config(
    page_title="DB-Pricing",
    page_icon="🧪",
    layout="wide"
)

with st.sidebar:
    st.markdown("### 🧪 DB-Pricing")
    st.caption("Coleta de preços – Diagnósticos do Brasil")
    st.markdown("---")
    st.markdown("**Dica:** use o código do convênio (ServSol) que aparece no final da URL, ex.: `c14296`.")

st.title("DB-Pricing")
st.subheader("Coletor de preços do Diagnósticos do Brasil")

# ---------------------------
# Formulário de entrada
# ---------------------------
with st.form("form_inputs", clear_on_submit=False):
    col1, col2 = st.columns([1,1])
    with col1:
        servsol = st.text_input("Código do Convênio (ServSol)", placeholder="ex.: c14296").strip()
        usuario = st.text_input("Usuário (CPF)", placeholder="00000000000").strip()
    with col2:
        senha = st.text_input("Senha", type="password")
        total_paginas = st.number_input("Limite de páginas para coletar", 1, 500, value=50, step=1)

    submitted = st.form_submit_button("🔎 Coletar e gerar Excel", use_container_width=True)

# ---------------------------
# Funções auxiliares Selenium
# ---------------------------
def build_driver():
    """
    Cria um Chrome headless usando o Chromium do ambiente do Streamlit Cloud.
    Não depende do SO do usuário final.
    """
    chrome_options = webdriver.ChromeOptions()
    # Binário e driver do apt (Streamlit Cloud)
    chrome_bin = "/usr/bin/chromium"
    driver_bin = "/usr/bin/chromedriver"
    if os.path.exists(chrome_bin):
        chrome_options.binary_location = chrome_bin

    # flags necessárias no ambiente cloud
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=pt-BR")

    service = Service(driver_bin) if os.path.exists(driver_bin) else Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(60)
    return driver

def wait_gone(driver, locator, timeout=15):
    try:
        WebDriverWait(driver, timeout).until(EC.invisibility_of_element_located(locator))
    except Exception:
        pass

def try_click_next(driver, timeout=10):
    """
    Clica no botão 'next' da paginação.
    Retorna True se conseguiu clicar, False caso contrário.
    """
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, '//button[@aria-label="go to next page"]'))
        )
        btn.click()
        # pequena espera para render
        time.sleep(1.5)
        return True
    except Exception:
        return False

def coletar_pagina(driver):
    """
    Lê todos os cards da página atual e retorna lista de dicts.
    Usa os mesmos seletores do seu robô original.
    """
    dados = []

    # Cada linha de resultado
    cards = driver.find_elements(By.XPATH, '//div[contains(@class,"container-wb-lista-historico-preco")]')
    if not cards:
        return dados

    # Em cada card existem 3 spans alvo:
    # - Código (20% | exps-txts-headers)
    # - Descrição (45% | span texto)
    # - Valor (20% | exps-txts-headers)
    codigos = driver.find_elements(By.XPATH, '//div[@class="container-wb-lista-historico-preco"]//div[contains(@style,"width: 20%;")]/span[@class="exps-txts-headers"]')
    nomes   = driver.find_elements(By.XPATH, '//div[@class="container-wb-lista-historico-preco"]//div[contains(@style,"width: 45%;")]/span')
    valores = driver.find_elements(By.XPATH, '//div[@class="container-wb-lista-historico-preco"]//div[contains(@style,"width: 20%;") and contains(@style,"text-align: center")]/span[@class="exps-txts-headers"]')

    n = min(len(codigos), len(nomes), len(valores))
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    for i in range(n):
        codigo = codigos[i].text.strip()
        nome   = nomes[i].text.strip()
        valor  = valores[i].text.strip()
        dados.append({
            "Código": codigo,
            "Exame": nome,
            "Valor": valor,
            "Data/Hora Coleta": agora
        })

    return dados

def fazer_login(driver, servsol, usuario, senha, status_cb):
    """
    Executa o login e navega até a Tabela de Preços (lista com botão 'Filtrar').
    """
    base_login = f"https://out-prd.diagnosticosdobrasil.com.br/Portal/Login?ServSol={servsol}"
    status_cb.write("🌐 Acessando login…")
    try:
        driver.get(base_login)
    except TimeoutException:
        driver.refresh()

    status_cb.write("⌛ Esperando campos de login…")
    user_input = WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.ID, "Input_UsernameVal")))
    pass_input = driver.find_element(By.ID, "Input_PasswordVal")

    user_input.clear(); user_input.send_keys(usuario)
    pass_input.clear(); pass_input.send_keys(senha)
    driver.find_element(By.CSS_SELECTOR, "button.btn-login").click()

    status_cb.write("🔐 Autenticando…")
    # Quando o campo some é porque entrou
    WebDriverWait(driver, 25).until_not(EC.presence_of_element_located((By.ID, "Input_UsernameVal")))
    status_cb.write("✅ Login ok!")

    # Ir para o módulo Financeiro
    status_cb.write("📂 Abrindo Financeiro…")
    driver.get("https://out-prd.diagnosticosdobrasil.com.br/Portal/Financeiro?chave=")
    time.sleep(2)

    # Clicar no item "Tabela de Preços" do menu lateral (é o primeiro .fin-sidemenu-item)
    menu = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CLASS_NAME, "fin-sidemenu-item")))
    menu.click()
    time.sleep(1.5)

    # Clicar no botão "Filtrar"
    status_cb.write("🔎 Aplicando filtro…")
    filtro = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, '//button[contains(@class,"btn-wb-hp-filtrar")]'))
    )
    filtro.click()
    time.sleep(2.5)

def rodar_coleta(servsol, usuario, senha, limite_paginas, progress, status_cb):
    """
    Orquestra tudo: login, leitura por páginas e saída DataFrame.
    """
    driver = None
    try:
        driver = build_driver()
        fazer_login(driver, servsol, usuario, senha, status_cb)

        todas = []
        pagina = 1
        progress.progress(0.0, text="Coletando página 1…")

        while pagina <= limite_paginas:
            dados = coletar_pagina(driver)
            if dados:
                todas.extend(dados)
                status_cb.write(f"✅ Página {pagina} coletada ({len(dados)} registros).")
            else:
                status_cb.write(f"⚠️ Página {pagina} sem dados.")
            # próxima
            if not try_click_next(driver):
                status_cb.write("⛔ Não há próxima página. Encerrando.")
                break

            pagina += 1
            progress.progress(min(pagina/limite_paginas, 1.0), text=f"Coletando página {pagina}…")

        df = pd.DataFrame(todas, columns=["Código", "Exame", "Valor", "Data/Hora Coleta"])
        return df

    except (TimeoutException, NoSuchElementException, WebDriverException) as e:
        status_cb.error(f"Erro durante a coleta: {e}")
        return pd.DataFrame(columns=["Código", "Exame", "Valor", "Data/Hora Coleta"])
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

# ---------------------------
# Execução quando enviar o formulário
# ---------------------------
if submitted:
    if not servsol or not usuario or not senha:
        st.error("Por favor, preencha **ServSol**, **Usuário** e **Senha**.")
        st.stop()

    # Normaliza ServSol (aceita “c14296” ou “14296”)
    if servsol.lower().startswith("c"):
        servsol = servsol.lower()
    else:
        servsol = f"c{servsol}"

    st.info(f"Convênio: **{servsol}**")
    progress = st.progress(0.0, text="Iniciando…")
    status_cb = st.empty()

    df = rodar_coleta(servsol, usuario, senha, int(total_paginas), progress, status_cb)

    st.markdown("---")
    if df.empty:
        st.warning("Nenhum dado retornado. Verifique as credenciais/convênio ou tente novamente.")
    else:
        st.success(f"Coleta finalizada! {len(df)} linhas.")
        st.dataframe(df, use_container_width=True, height=420)

        # Gera Excel em memória
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="DB_Pricing")
        output.seek(0)

        st.download_button(
            label="📥 Baixar Excel (.xlsx)",
            data=output,
            file_name=f"DB_Pricing_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    progress.progress(1.0, text="Concluído!")
