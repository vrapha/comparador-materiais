# Agente Comparador de Materiais Educacionais

Compara áudios novos com materiais escritos antigos e gera um relatório PDF
de depara por material (Mapa Mental, Resumo, MR+, Dica de Prova,
Material de Acompanhamento, Apostila).

---

## Como rodar localmente (no seu computador)

### 1. Pré-requisitos
- Python 3.10 ou superior instalado
- Conta OpenAI com chave de API

### 2. Instalar dependências

Abra o terminal na pasta do projeto e execute:

```bash
pip install -r requirements.txt
```

### 3. Rodar o app

```bash
streamlit run app.py
```

O navegador abrirá automaticamente em `http://localhost:8501`

---

## Como publicar online (Streamlit Cloud — gratuito)

Para que qualquer pessoa da equipe acesse por link, sem instalar nada:

### 1. Criar repositório no GitHub
- Acesse github.com e crie um repositório (pode ser privado)
- Faça upload dos arquivos: `app.py` e `requirements.txt`

### 2. Deploy no Streamlit Cloud
- Acesse share.streamlit.io
- Conecte sua conta GitHub
- Selecione o repositório e o arquivo `app.py`
- Clique em "Deploy"

Em ~2 minutos o app estará no ar com um link para compartilhar com a equipe.

### 3. Chave da API (IMPORTANTE - LEIA COM ATENÇÃO!)

**OPÇÃO 1: Uso local com arquivo .env (RECOMENDADO para equipes)**
- A chave fica no arquivo `.env` (já criado pelo administrador)
- **Apenas o administrador configura a chave uma vez**
- Todos os usuários usam o app **sem precisar saber a chave**
- O arquivo `.env` **NUNCA** deve ser compartilhado ou commitado no Git
- O `.gitignore` já está configurado para proteger este arquivo

**OPÇÃO 2: Streamlit Cloud (para acesso online)**
- Vá em "Settings > Secrets" no Streamlit Cloud e adicione:
  ```
  OPENAI_API_KEY = "sk-..."
  ```
- Usuários acessam sem precisar digitar a chave

---

## Como usar

1. Digite o **nome da aula** (ex: "Hipertensão Arterial")
2. **PDFs Antigos (2025):** Faça upload dos 3 materiais:
   - Resumo.pdf
   - Apostila.pdf
   - Mapa Mental.pdf
3. **Áudios Novos (2026):** Faça upload dos áudios atualizados:
   - Aula Resumo
   - Aula 1, Aula 2, Aula 3... (quantas tiver)
   - Use o botão "➕ Adicionar mais uma aula" conforme necessário
4. Clique em **"🚀 Gerar Relatório de Depara"**
5. Aguarde o processamento (transcrição + análise de cada combinação)
6. Baixe o **relatório PDF estruturado**

---

## Como funciona

O sistema compara **CADA áudio novo (2026)** com **CADA PDF antigo (2025)**:

- **Aula Resumo** vs Resumo → Relatório 1
- **Aula Resumo** vs Apostila → Relatório 2
- **Aula Resumo** vs Mapa Mental → Relatório 3
- **Aula 1** vs Resumo → Relatório 4
- **Aula 1** vs Apostila → Relatório 5
- **Aula 1** vs Mapa Mental → Relatório 6
- ... e assim por diante

**Exemplo:** 3 PDFs + 5 áudios = **15 comparações** no relatório final

---

## Formatos aceitos

- **Áudios:** MP3, MP4, WAV, M4A (até 500MB)
- **PDFs:** PDF, DOCX, TXT

---

## Custo estimado

Usando GPT-4o e Whisper da OpenAI:
- Transcrição Whisper: ~$0.006 por minuto de áudio
- Análise GPT-4o: ~$0.03 por comparação
- **Exemplo:** 3 PDFs + 5 áudios (15 comparações) ≈ $0.50 - $1.00

---

## Dúvidas

Fale com o time responsável pelo projeto.