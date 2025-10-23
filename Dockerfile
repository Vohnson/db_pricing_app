# Usa imagem base leve com Python 3.11
FROM python:3.11-slim

# Evita prompts interativos
ENV DEBIAN_FRONTEND=noninteractive

# Define diretório de trabalho
WORKDIR /app

# Copia os arquivos da aplicação
COPY . /app

# Instala dependências do sistema necessárias pro Chromium e fontes
RUN apt-get update && apt-get install -y \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libgtk-3-0 \
    fonts-liberation \
    fonts-unifont \
    fonts-ubuntu \
    fonts-dejavu \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Instala o navegador Chromium via Playwright (sem travar se der warning)
RUN playwright install --with-deps chromium || true

# Expõe a porta padrão do Streamlit
EXPOSE 10000

# Comando para iniciar o app
CMD ["streamlit", "run", "app.py", "--server.port=10000", "--server.address=0.0.0.0"]
