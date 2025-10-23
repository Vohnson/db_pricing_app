import asyncio
import pandas as pd
from io import BytesIO
from datetime import datetime
from playwright.async_api import async_playwright
import streamlit as st

# ============================================================
# 🧪 CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(page_title="DB-Pricing", page_icon="🧪", layout="wide")

st.title("🧪 DB-Pricing")
st.subheader("Coletor automático de preços do Diagnósticos do Brasil 💼")

with st.sidebar:
    st.markdown("### ⚙️ Configurações")
    st.markdown("Insira abaixo os dados do convênio e login.")
    st.divider()
    st.caption("💡 *Use o código ServSol igual ao final da URL (ex.: c14296).*")

# ============================================================
# FORMULÁRIO DE LOGIN
# ============================================================
with st.form("dados_db"):
    servsol = st.text_input("🔑 Código do Convênio (ServSol)", "c14296")
    usuario = st.text_input("👤 Usuário (CPF)", "")
    senha = st.text_input("🔒 Senha", type="password")
    paginas = st.number_input("📄 Páginas a coletar", 1, 300, 50)
    enviar = st.form_submit_button("🚀 Iniciar Coleta", use_container_width=True)

# ============================================================
# FUNÇÃO PRINCIPAL (ASYNC)
# ============================================================

async def coletar_dados(servsol, usuario, senha, paginas, status_cb, progress):
    url_login = f"https://out-prd.diagnosticosdobrasil.com.br/Portal/Login?ServSol={servsol}"
    dados_total = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        status_cb.write("🌎 Acessando portal...")
        await page.goto(url_login, timeout=60000)

        # Login
        status_cb.write("🔐 Fazendo login...")
        await page.fill("#Input_UsernameVal", usuario)
        await page.fill("#Input_PasswordVal", senha)
        await page.click("button.btn-login")
        await page.wait_for_timeout(3000)

        # Acessar menu financeiro
        status_cb.write("📂 Acessando menu financeiro...")
        await page.goto("https://out-prd.diagnosticosdobrasil.com.br/Portal/Financeiro?chave=")
        await page.wait_for_timeout(4000)
        await page.click(".fin-sidemenu-item")
        await page.wait_for_timeout(2000)
        await page.click("button.btn-wb-hp-filtrar")
        await page.wait_for_timeout(5000)

        for i in range(1, paginas + 1):
            progress.progress(i / paginas, text=f"Coletando página {i}...")
            status_cb.write(f"📄 Coletando dados da página {i}...")

            # Extrair dados da página
            codigos = await page.query_selector_all(
                '//div[@class="container-wb-lista-historico-preco"]//div[contains(@style, "width: 20%;")]/span[@class="exps-txts-headers"]'
            )
            nomes = await page.query_selector_all(
                '//div[@class="container-wb-lista-historico-preco"]//div[contains(@style, "width: 45%;")]/span'
            )
            valores = await page.query_selector_all(
                '//div[@class="container-wb-lista-historico-preco"]//div[contains(@style, "width: 20%; text-align: center;")]/span[@class="exps-txts-headers"]'
            )

            lista = []
            data_execucao = datetime.now().strftime("%d/%m/%Y %H:%M")

            for idx in range(min(len(codigos), len(nomes), len(valores))):
                codigo = (await codigos[idx].inner_text()).strip()
                nome = (await nomes[idx].inner_text()).strip()
                valor = (await valores[idx].inner_text()).strip()
                lista.append([codigo, nome, valor, data_execucao])

            if lista:
                dados_total.extend(lista)
                status_cb.write(f"✅ Página {i} coletada com {len(lista)} registros.")
            else:
                status_cb.write(f"⚠️ Página {i} sem dados.")

            # Próxima página
            try:
                botao_next = await page.query_selector('//button[@aria-label="go to next page"]')
                if botao_next:
                    await botao_next.click()
                    await page.wait_for_timeout(3000)
                else:
                    status_cb.write("🚫 Última página encontrada.")
                    break
            except:
                status_cb.write("🚫 Erro ao mudar de página.")
                break

        await browser.close()
    return dados_total

# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

if enviar:
    if not (servsol and usuario and senha):
        st.error("⚠️ Preencha todos os campos antes de continuar.")
        st.stop()

    progress = st.progress(0.0, text="Iniciando...")
    status_cb = st.empty()
    st.info("⏳ Iniciando coleta... Aguarde, pode levar alguns minutos.")

    data = asyncio.run(coletar_dados(servsol, usuario, senha, paginas, status_cb, progress))

    if not data:
        st.error("Nenhum dado encontrado ou erro de login.")
    else:
        df = pd.DataFrame(data, columns=["Código", "Exame", "Valor", "Data/Hora Coleta"])
        st.success(f"✅ Coleta finalizada! {len(df)} registros.")
        st.dataframe(df, use_container_width=True, height=420)

        # Gera Excel para download
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="DB_Pricing")
        buffer.seek(0)

        st.download_button(
            label="📥 Baixar Excel (.xlsx)",
            data=buffer,
            file_name=f"DB_Pricing_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
