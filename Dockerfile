# Usa o Python que FUNCIONA (3.11)
FROM python:3.11-slim

# Define o diretório de trabalho
WORKDIR /app

# Copia tudo pro container
COPY . /app

# Instala dependências
RUN pip install --no-cache-dir -r requirements.txt && playwright install --with-deps chromium

# Expõe a porta do Streamlit
EXPOSE 10000

# Roda o app
CMD ["streamlit", "run", "app.py", "--server.port=10000", "--server.address=0.0.0.0"]
