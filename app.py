"""
app.py — Agente Comparador de Materiais Educacionais
Interface Streamlit: roda local (python -m streamlit run app.py)
ou deploy gratuito no Streamlit Cloud.

Fluxo:
  1. Usuário define o nome da aula
  2. Upload de 3 PDFs antigos (2025): Resumo, Apostila, Mapa Mental
  3. Upload de N áudios novos (2026): Aula Resumo, Aula 1, Aula 2, etc.
  4. Sistema compara CADA áudio com CADA PDF
  5. Gera relatório PDF estruturado com todas as comparações
"""

import io
import os
import json
import tempfile
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, PageBreak
)
from reportlab.platypus.flowables import Flowable

# ── Paleta ────────────────────────────────────────────────────────────────────
DARK   = colors.HexColor("#0F1623")
BLUE   = colors.HexColor("#1A6EFF")
GREEN  = colors.HexColor("#00C48C")
WARN   = colors.HexColor("#FF6B35")
LIGHT  = colors.HexColor("#F0F4FF")
GMID   = colors.HexColor("#6B7280")
GLIGHT = colors.HexColor("#E5E9F0")
WHITE  = colors.white

OPENAI_BASE = "https://api.openai.com/v1"

# ── PDFs fixos (antigos - 2025) ──────────────────────────────────────────────
PDFS_ANTIGOS = [
    {"id": "resumo",   "label": "Resumo"},
    {"id": "apostila", "label": "Apostila"},
    {"id": "mapa",     "label": "Mapa Mental"},
    {"id": "material_acompanhamento", "label": "Material de Acompanhamento"},
    {"id": "material_aula_resumo", "label": "Material de Acompanhamento - Aula Resumo"},
]

# Configuração do Streamlit para aceitar arquivos grandes
MAX_UPLOAD_SIZE = 500  # MB


# ══════════════════════════════════════════════════════════════════════════════
#  OPENAI  (urllib — sem dependência extra)
# ══════════════════════════════════════════════════════════════════════════════

def _post_json(api_key, endpoint, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OPENAI_BASE}{endpoint}", data=data,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


def _converter_para_mp3_puro(audio_bytes, filename):
    """
    Converte áudio para MP3 usando apenas Python puro (sem FFmpeg).
    Usa wave para ler WAV e converte para formato simples.
    """
    MAX_SIZE = 24 * 1024 * 1024  # 24MB

    if len(audio_bytes) <= MAX_SIZE:
        return audio_bytes, filename

    # Áudio muito grande - tenta converter
    tamanho_mb = len(audio_bytes) / (1024 * 1024)
    st.warning(f"⚠️ Áudio grande detectado ({tamanho_mb:.1f}MB). Convertendo para reduzir tamanho...")

    try:
        # Detecta se é WAV
        ext = Path(filename).suffix.lower()

        if ext == '.wav':
            # Para WAV, vamos fazer downsampling simples usando wave
            import wave
            import struct

            # Salva temporariamente
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            # Lê WAV
            with wave.open(tmp_path, 'rb') as wav:
                params = wav.getparams()
                nchannels, sampwidth, framerate, nframes = params[:4]
                frames = wav.readframes(nframes)

            # Converte para mono se for estéreo
            if nchannels == 2:
                st.info("🔄 Convertendo de estéreo para mono...")
                frames_array = struct.unpack(f'{nframes * nchannels}h', frames)
                # Média dos canais para mono
                mono_frames = []
                for i in range(0, len(frames_array), 2):
                    mono_frames.append((frames_array[i] + frames_array[i+1]) // 2)
                frames = struct.pack(f'{len(mono_frames)}h', *mono_frames)
                nchannels = 1

            # Reduz sample rate se necessário (de 44100 para 16000)
            if framerate > 16000:
                st.info("🔄 Reduzindo qualidade de áudio para 16kHz...")
                # Downsampling simples
                ratio = framerate / 16000
                frames_array = struct.unpack(f'{len(frames)//sampwidth}h', frames)
                downsampled = [frames_array[int(i * ratio)] for i in range(int(len(frames_array) / ratio))]
                frames = struct.pack(f'{len(downsampled)}h', *downsampled)
                framerate = 16000

            # Salva WAV otimizado
            output_path = tempfile.mktemp(suffix='.wav')
            with wave.open(output_path, 'wb') as wav_out:
                wav_out.setnchannels(nchannels)
                wav_out.setsampwidth(sampwidth)
                wav_out.setframerate(framerate)
                wav_out.writeframes(frames)

            # Lê arquivo otimizado
            with open(output_path, 'rb') as f:
                audio_otimizado = f.read()

            # Limpa temporários
            os.unlink(tmp_path)
            os.unlink(output_path)

            tamanho_novo_mb = len(audio_otimizado) / (1024 * 1024)
            reducao = ((tamanho_mb - tamanho_novo_mb) / tamanho_mb) * 100

            st.success(f"✅ Áudio otimizado: {tamanho_mb:.1f}MB → {tamanho_novo_mb:.1f}MB (redução de {reducao:.0f}%)")

            # Se ainda está grande, precisa dividir
            if len(audio_otimizado) > MAX_SIZE:
                st.warning(f"⚠️ Áudio ainda grande ({tamanho_novo_mb:.1f}MB). Dividindo em partes...")
                return audio_otimizado, filename  # Vai dividir depois

            return audio_otimizado, filename

        else:
            # Não é WAV, não podemos otimizar facilmente
            st.error(f"❌ Arquivo {ext} muito grande ({tamanho_mb:.1f}MB). Comprima manualmente antes de enviar.")
            raise ValueError(f"Arquivo {filename} muito grande. Comprima manualmente.")

    except Exception as e:
        st.error(f"❌ Erro ao otimizar áudio: {str(e)}")
        raise ValueError(f"Não foi possível processar o áudio. Comprima manualmente antes de enviar.")


def _dividir_audio_wav_em_partes(audio_bytes, filename):
    """
    Divide um arquivo WAV grande em partes temporais válidas.
    Cada parte é um arquivo WAV válido que pode ser transcrito.
    """
    import wave
    import struct

    MAX_SIZE = 24 * 1024 * 1024  # 24MB por parte

    if len(audio_bytes) <= MAX_SIZE:
        return [(audio_bytes, filename)]

    tamanho_mb = len(audio_bytes) / (1024 * 1024)
    st.info(f"📦 Áudio muito grande ({tamanho_mb:.1f}MB). Dividindo em partes de até 24MB...")

    try:
        # Salva temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # Lê informações do WAV
        with wave.open(tmp_path, 'rb') as wav:
            params = wav.getparams()
            nchannels, sampwidth, framerate, nframes = params[:4]

            # Calcula quantos frames cabem em 24MB
            # Tamanho de um frame = nchannels * sampwidth
            frame_size = nchannels * sampwidth

            # Quantos frames cabem em 24MB? (deixa margem de segurança)
            max_frames_por_parte = int((MAX_SIZE * 0.9) / frame_size)

            # Quantas partes precisamos?
            num_partes = (nframes + max_frames_por_parte - 1) // max_frames_por_parte

            st.info(f"🔢 Dividindo em {num_partes} partes de ~{max_frames_por_parte/framerate/60:.1f} minutos cada")

            partes = []

            for i in range(num_partes):
                # Calcula início e fim desta parte
                frame_inicio = i * max_frames_por_parte
                frame_fim = min((i + 1) * max_frames_por_parte, nframes)
                frames_nesta_parte = frame_fim - frame_inicio

                # Posiciona no início desta parte
                wav.setpos(frame_inicio)

                # Lê os frames desta parte
                frames_data = wav.readframes(frames_nesta_parte)

                # Cria um novo arquivo WAV com esses frames
                parte_path = tempfile.mktemp(suffix=f'_parte{i+1}.wav')

                with wave.open(parte_path, 'wb') as wav_parte:
                    wav_parte.setnchannels(nchannels)
                    wav_parte.setsampwidth(sampwidth)
                    wav_parte.setframerate(framerate)
                    wav_parte.writeframes(frames_data)

                # Lê o arquivo da parte
                with open(parte_path, 'rb') as f:
                    parte_bytes = f.read()

                # Nome da parte
                nome_base = Path(filename).stem
                extensao = Path(filename).suffix
                nome_parte = f"{nome_base}_parte{i+1}{extensao}"

                partes.append((parte_bytes, nome_parte))

                # Limpa arquivo temporário
                os.unlink(parte_path)

                tamanho_parte_mb = len(parte_bytes) / (1024 * 1024)
                st.success(f"✅ Parte {i+1}/{num_partes}: {tamanho_parte_mb:.1f}MB")

        # Limpa arquivo temporário original
        os.unlink(tmp_path)

        return partes

    except Exception as e:
        st.error(f"❌ Erro ao dividir áudio: {str(e)}")
        raise ValueError(f"Não foi possível dividir o áudio: {str(e)}")


def _corrigir_termos_medicos(transcricao):
    """Corrige termos médicos comuns que o Whisper transcreve errado."""
    correcoes = {
        # Medicamentos
        "caverdilol": "carvedilol",
        "cavernilol": "carvedilol",
        "carnedilol": "carvedilol",
        "octreotida": "octreotida",
        "terlipressina": "terlipressina",

        # Termos médicos
        "valizes": "varizes",
        "valiz": "variz",
        "valicosa": "varicosa",
        "esofagogástrica": "esofagogástrica",
        "esofagogástricas": "esofagogástricas",
        "hepatocarcinoma": "hepatocarcinoma",
        "encefalopatia": "encefalopatia",
        "esplenorrenal": "esplenorrenal",
        "portossistêmico": "portossistêmico",

        # Siglas
        "mel d": "MELD",
        "meld": "MELD",
        "tips": "TIPS",
        "hiv": "HIV",

        # Anatomia
        "couinaud": "Couinaud",
        "cantilli": "Cantlie",
        "cantili": "Cantlie",
        "rex cantlie": "Rex-Cantlie",
    }

    texto_corrigido = transcricao
    for errado, correto in correcoes.items():
        # Correção case-insensitive
        import re
        texto_corrigido = re.sub(
            r'\b' + re.escape(errado) + r'\b',
            correto,
            texto_corrigido,
            flags=re.IGNORECASE
        )

    return texto_corrigido


def _transcrever_parte(api_key, audio_bytes, filename):
    """Transcreve uma parte de áudio via Whisper-1."""
    import uuid

    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    def w(s): body.write(s.encode())
    for k, v in [("model", "whisper-1"), ("language", "pt"),
                 ("response_format", "text")]:
        w(f"--{boundary}\r\nContent-Disposition: form-data; "
          f'name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{boundary}\r\nContent-Disposition: form-data; "
      f'name="file"; filename="{filename}"\r\n'
      "Content-Type: application/octet-stream\r\n\r\n")
    body.write(audio_bytes)
    w(f"\r\n--{boundary}--\r\n")
    req = urllib.request.Request(
        f"{OPENAI_BASE}/audio/transcriptions",
        data=body.getvalue(),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        result = r.read().decode()
    try:
        return json.loads(result).get("text", result)
    except Exception:
        return result


def _dividir_audio_generico(audio_bytes, filename):
    """
    Divide qualquer arquivo de áudio (MP3, M4A, etc) em partes de até 24MB.
    Para formatos comprimidos, divide por bytes mas mantém estrutura do arquivo.
    """
    MAX_SIZE = 24 * 1024 * 1024  # 24MB

    if len(audio_bytes) <= MAX_SIZE:
        return [(audio_bytes, filename)]

    tamanho_mb = len(audio_bytes) / (1024 * 1024)

    # Para MP3/M4A muito grandes, não conseguimos dividir corretamente
    # pois não são formatos simples como WAV
    st.error(
        f"❌ Arquivo {filename} muito grande ({tamanho_mb:.1f}MB).\n\n"
        f"Arquivos MP3/M4A grandes não podem ser divididos automaticamente.\n\n"
        f"**Solução:** Divida o áudio manualmente em partes menores (use Audacity ou similar) "
        f"e envie cada parte separadamente, OU converta para WAV primeiro."
    )
    raise ValueError(f"Arquivo {filename} muito grande para processar.")


def _dividir_mp3_em_chunks(audio_bytes, filename):
    """
    Divide MP3 em chunks menores que 24MB.
    Usa a API Whisper diretamente com prompt para continuar a transcrição.
    """
    MAX_SIZE = 24 * 1024 * 1024  # 24MB

    if len(audio_bytes) <= MAX_SIZE:
        return [(audio_bytes, filename)]

    tamanho_mb = len(audio_bytes) / (1024 * 1024)
    st.info(f"📦 MP3 grande ({tamanho_mb:.1f}MB). Dividindo em partes de ~{MAX_SIZE/(1024*1024):.0f}MB...")

    # Calcula quantas partes precisamos
    num_partes = (len(audio_bytes) + MAX_SIZE - 1) // MAX_SIZE
    tamanho_por_parte = len(audio_bytes) // num_partes

    partes = []

    for i in range(num_partes):
        inicio = i * tamanho_por_parte
        fim = min((i + 1) * tamanho_por_parte, len(audio_bytes))

        # Para MP3, precisamos encontrar um sync byte válido
        # MP3 frames começam com 0xFF seguido de 0xE0-0xFF
        if i > 0:
            # Procura o próximo frame sync perto do ponto de corte
            for offset in range(max(0, inicio - 1000), min(len(audio_bytes), inicio + 1000)):
                if offset < len(audio_bytes) - 1:
                    if audio_bytes[offset] == 0xFF and (audio_bytes[offset + 1] & 0xE0) == 0xE0:
                        inicio = offset
                        break

        # Corta o chunk
        chunk = audio_bytes[inicio:fim]

        nome_base = Path(filename).stem
        extensao = Path(filename).suffix
        nome_parte = f"{nome_base}_parte{i+1}{extensao}"

        partes.append((chunk, nome_parte))

        tamanho_parte_mb = len(chunk) / (1024 * 1024)
        st.success(f"✅ Parte {i+1}/{num_partes}: {tamanho_parte_mb:.1f}MB")

    return partes


def _whisper(api_key, audio_bytes, filename):
    """Transcreve áudio via Whisper-1. Otimiza e divide automaticamente se necessário."""

    ext = Path(filename).suffix.lower()
    MAX_SIZE = 24 * 1024 * 1024

    # ESTRATÉGIA:
    # 1. Se for pequeno: transcreve direto
    # 2. Se for WAV grande: otimiza e divide
    # 3. Se for MP3 grande: divide em chunks válidos

    if len(audio_bytes) <= MAX_SIZE:
        # Arquivo pequeno, transcreve direto
        transcricao = _transcrever_parte(api_key, audio_bytes, filename)
    else:
        # Arquivo grande precisa processar
        tamanho_mb = len(audio_bytes) / (1024 * 1024)
        st.warning(f"⚠️ Arquivo grande detectado ({tamanho_mb:.1f}MB). Processando...")

        if ext == '.wav':
            # WAV: otimiza primeiro
            audio_bytes, filename = _converter_para_mp3_puro(audio_bytes, filename)

            # Se ainda estiver grande, divide
            if len(audio_bytes) > MAX_SIZE:
                partes = _dividir_audio_wav_em_partes(audio_bytes, filename)
            else:
                partes = [(audio_bytes, filename)]

        elif ext in ['.mp3', '.m4a', '.mp4']:
            # MP3/M4A: divide diretamente em chunks
            partes = _dividir_mp3_em_chunks(audio_bytes, filename)

        else:
            # Outros formatos não suportados
            st.error(f"❌ Formato {ext} não suportado para arquivos grandes.")
            raise ValueError(f"Formato não suportado: {ext}")

        # Transcreve cada parte
        if len(partes) == 1:
            transcricao = _transcrever_parte(api_key, partes[0][0], partes[0][1])
        else:
            transcricoes = []
            for i, (parte_bytes, parte_nome) in enumerate(partes, 1):
                st.info(f"🎤 Transcrevendo parte {i}/{len(partes)}...")
                transcricao_parte = _transcrever_parte(api_key, parte_bytes, parte_nome)
                transcricoes.append(transcricao_parte)

            # Junta todas as transcrições
            transcricao = " ".join(transcricoes)
            st.success(f"✅ {len(partes)} partes transcritas e combinadas!")

    # Corrige termos médicos
    transcricao = _corrigir_termos_medicos(transcricao)
    return transcricao


def _analisar(api_key, transcricao, material_texto, nome_material, nome_aula):
    """Compara transcricao do audio novo com material escrito antigo via GPT-4o.

    Abordagem topic-first:
      1. Extrai topicos do audio
      2. Para cada topico presente em AMBOS, compara o conteudo
      3. Retorna apenas divergencias (conteudo diferente entre audio e PDF)
    """
    system = (
        "Voce e um especialista em controle de qualidade de materiais educacionais medicos. "
        "Sua tarefa e identificar topicos que aparecem TANTO no audio QUANTO no PDF, mas com conteudo DIFERENTE. "
        "IGNORE topicos que estao so no audio ou so no PDF. "
        "Retorne APENAS JSON valido, sem texto fora do JSON."
    )
    user = f"""
Compare o material educacional medico abaixo.

## CONTEXTO:
- AUDIO (2026): Aula do professor com protocolos/diretrizes atualizados
- {nome_material.upper()} (2025): Material escrito que pode estar desatualizado

---

## AUDIO DAS AULAS (2026):
{transcricao[:12000]}

---

## {nome_material.upper()} (2025):
{material_texto[:12000]}

---

## PASSO 1 - TOPICOS DO AUDIO:
Identifique os topicos/conceitos principais abordados no audio.

## PASSO 2 - INTERSECAO:
Para cada topico do audio, verifique se ele tambem aparece no PDF.
- Se o topico NAO estiver no PDF: IGNORE completamente.
- Se o topico estiver no PDF: compare o conteudo.

## PASSO 3 - CLASSIFICACAO (apenas para topicos presentes em AMBOS):
- ATUALIZAR PDF: o conteudo difere entre audio e PDF (valor, droga, protocolo, classificacao mudou).
- OK: o conteudo e equivalente em ambos.

---

## REGRAS:
- Compare apenas topicos presentes nos DOIS materiais.
- Foque em diferencas de CONTEUDO clinico: valores numericos, doses, farmacos, condutas, diretrizes.
- IGNORE diferencas de estilo/redacao.
- Seja especifico: cite o valor/conduta exato do audio e do PDF.

## EXEMPLO:
Audio: "A nova diretriz recomenda MELD > 18 para transplante"
PDF: "MELD > 15 indica transplante"
-> atualizacoes_necessarias, acao "ATUALIZAR PDF"

---

Retorne EXATAMENTE este JSON (sem nenhum texto fora do JSON):
{{
  "atualizacoes_necessarias": [
    {{
      "item": "Nome do topico/conceito",
      "pdf_2025": "O que esta no PDF (conteudo atual)",
      "aula_2026": "O que o professor disse (conteudo atualizado)",
      "acao": "ATUALIZAR PDF"
    }}
  ],
  "sem_mudancas": [
    {{
      "item": "Topico presente em ambos com conteudo equivalente",
      "conteudo": "Resumo do conteudo (igual nos dois)"
    }}
  ]
}}"""
    resp = _post_json(api_key, "/chat/completions", {
        "model": "gpt-4o",
        "max_tokens": 4000,
        "temperature": 0.1,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    })
    raw = resp["choices"][0]["message"]["content"].strip()
    if "```" in raw:
        raw = raw.split("```json")[-1].split("```")[0].strip()
    try:
        return json.loads(raw)
    except Exception:
        return {
            "atualizacoes_necessarias": [],
            "sem_mudancas": [],
        }


def limpar_texto_pdf(texto):
    """Remove lixo comum de PDFs: cabeçalhos, rodapés, elementos visuais."""
    import re

    # Remove linhas muito curtas (geralmente lixo)
    linhas = texto.split('\n')
    linhas_limpas = [l for l in linhas if len(l.strip()) > 5]

    # Remove padrões comuns de lixo
    padroes_lixo = [
        r'Tópico \d+',
        r'Info \d+',
        r'Item \d+',
        r'Assunto\s*$',
        r'TEMA MÉDICO\s*$',
        r'Dados\s*$',
        r'Critérios Notificações',
        r'^\d+\s*$',  # Números de página isolados
        r'^Page \d+',
        r'^\s*\d+\s*/\s*\d+\s*$',  # Paginação tipo "1/10"
    ]

    texto_limpo = '\n'.join(linhas_limpas)
    for padrao in padroes_lixo:
        texto_limpo = re.sub(padrao, '', texto_limpo, flags=re.MULTILINE | re.IGNORECASE)

    # Remove linhas vazias excessivas
    texto_limpo = re.sub(r'\n\s*\n\s*\n+', '\n\n', texto_limpo)

    return texto_limpo.strip()


def extrair_texto_pdf(arquivo_bytes):
    try:
        reader = PdfReader(io.BytesIO(arquivo_bytes))
        texto = "\n".join(p.extract_text() or "" for p in reader.pages)
        return limpar_texto_pdf(texto)
    except Exception:
        return arquivo_bytes.decode("utf-8", errors="replace")


def extrair_texto_docx(arquivo_bytes):
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(io.BytesIO(arquivo_bytes)) as z:
            xml_c = z.read("word/document.xml")
        root = ET.fromstring(xml_c)
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        return " ".join(t.text or "" for t in root.iter(f"{{{ns}}}t"))
    except Exception:
        return arquivo_bytes.decode("utf-8", errors="replace")


# ══════════════════════════════════════════════════════════════════════════════
#  PDF REPORT
# ══════════════════════════════════════════════════════════════════════════════

class Barra(Flowable):
    def __init__(self, w, h=4, cor=BLUE):
        super().__init__()
        self.bw, self.bh, self.cor = w, h, cor
    def draw(self):
        self.canv.setFillColor(self.cor)
        self.canv.roundRect(0, 0, self.bw, self.bh, 2, fill=1, stroke=0)
    def wrap(self, *a): return (self.bw, self.bh + 4)


class Gauge(Flowable):
    def __init__(self, score, w=360):
        super().__init__()
        self.score = max(0, min(100, score))
        self.gw, self.gh = w, 22
    def draw(self):
        c = self.canv
        c.setFillColor(GLIGHT)
        c.roundRect(0, 0, self.gw, self.gh, self.gh/2, fill=1, stroke=0)
        fw = (self.score/100)*self.gw
        if fw > 0:
            col = GREEN if self.score >= 75 else (BLUE if self.score >= 50 else WARN)
            c.setFillColor(col)
            c.roundRect(0, 0, max(fw, self.gh), self.gh, self.gh/2, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(fw/2 if fw > 32 else self.gw/2, 6, f"{self.score}%")
    def wrap(self, *a): return (self.gw, self.gh + 6)


def gerar_pdf(nome_aula, resultados):
    """Gera PDF em formato de tabela comparativa (Antes vs Depois)."""
    buf = io.BytesIO()
    MARGIN = 1.5*cm
    pw, ph = A4
    cw = pw - 2*MARGIN

    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN)

    # Estilos
    s = {
        "titulo": ParagraphStyle("t", fontName="Helvetica-Bold",
            fontSize=16, textColor=DARK, spaceAfter=6, leading=20),
        "material": ParagraphStyle("mat", fontName="Helvetica-Bold",
            fontSize=13, textColor=BLUE, spaceBefore=12, spaceAfter=8),
        "header": ParagraphStyle("h", fontName="Helvetica-Bold",
            fontSize=9, textColor=WHITE, alignment=TA_CENTER),
        "cell": ParagraphStyle("c", fontName="Helvetica",
            fontSize=8, textColor=DARK, leading=11),
        "cell_item": ParagraphStyle("ci", fontName="Helvetica-Bold",
            fontSize=9, textColor=DARK, leading=11),
        "secao": ParagraphStyle("sec", fontName="Helvetica-Bold",
            fontSize=10, textColor=WARN, spaceBefore=8, spaceAfter=4),
    }

    def sp(h=10): return Spacer(1, h)

    story = []

    # CAPA
    story.append(Paragraph(f"DEPARA: {nome_aula}", s["titulo"]))
    story.append(Paragraph(f"Comparação de Materiais Educacionais", s["cell"]))
    story.append(Paragraph(f"Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}", s["cell"]))
    story.append(sp(15))

    # Agrupa resultados por material (Apostila, Resumo, Mapa Mental)
    resultados_por_material = {}
    for r in resultados:
        material = r['pdf_label']
        if material not in resultados_por_material:
            resultados_por_material[material] = []
        resultados_por_material[material].append(r)

    # Para cada material
    for material, comparacoes in resultados_por_material.items():
        story.append(Paragraph(f"{material}", s["material"]))
        story.append(sp(5))

        # Combina todas as análises deste material
        todas_atualizacoes = []
        todos_sem_mudancas = []

        for comp in comparacoes:
            an = comp['analise']
            todas_atualizacoes.extend(an.get("atualizacoes_necessarias", []))
            todos_sem_mudancas.extend(an.get("sem_mudancas", []))

        # TABELA DE ATUALIZAÇÕES NECESSÁRIAS
        if todas_atualizacoes:
            # Cabeçalho da tabela
            tabela_data = [
                [
                    Paragraph("<b>Item</b>", s["header"]),
                    Paragraph("<b>Antes (Materiais 2025)</b>", s["header"]),
                    Paragraph("<b>Depois (Atualização da aula)</b>", s["header"]),
                ]
            ]

            # Linhas de dados
            for atualizacao in todas_atualizacoes:
                # Ordem: Item | Antes (Materiais 2025) | Depois (Atualização da aula)
                tabela_data.append([
                    Paragraph(atualizacao.get('item', ''), s["cell_item"]),
                    Paragraph(atualizacao.get('pdf_2025', 'Não mencionado'), s["cell"]),
                    Paragraph(atualizacao.get('aula_2026', 'Não mencionado'), s["cell"]),
                ])

            # Cria tabela com 3 colunas
            larguras = [cw * 0.20, cw * 0.40, cw * 0.40]
            tabela = Table(tabela_data, colWidths=larguras, repeatRows=1)
            tabela.setStyle(TableStyle([
                # Cabeçalho
                ('BACKGROUND', (0, 0), (-1, 0), DARK),
                ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),

                # Dados
                ('BACKGROUND', (0, 1), (-1, -1), LIGHT),
                ('TEXTCOLOR', (0, 1), (-1, -1), DARK),
                ('ALIGN', (0, 1), (0, -1), 'LEFT'),
                ('ALIGN', (1, 1), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('LEFTPADDING', (0, 1), (-1, -1), 6),
                ('RIGHTPADDING', (0, 1), (-1, -1), 6),

                # Bordas
                ('GRID', (0, 0), (-1, -1), 0.5, GMID),
                ('LINEBELOW', (0, 0), (-1, 0), 1.5, DARK),

                # Alternância de cores
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT, WHITE]),

                # Valign
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))

            story.append(tabela)
            story.append(sp(10))

        # CONTEUDO SEM MUDANCAS (opcional - apenas se quiser mostrar)
        if todos_sem_mudancas and len(todos_sem_mudancas) <= 5:  # Mostra apenas se forem poucos
            story.append(Paragraph("✅ Conteúdo sem alterações:", s["secao"]))
            for item in todos_sem_mudancas:
                story.append(Paragraph(
                    f"• <b>{item.get('item', '')}</b>: {item.get('conteudo', '')}", s["cell"]))
            story.append(sp(8))

        # Se nao houver nenhuma atualizacao
        if not todas_atualizacoes:
            story.append(Paragraph("Nenhuma divergencia encontrada entre o audio e este material.", s["cell"]))

        story.append(sp(15))
        story.append(HRFlowable(width=cw, thickness=1, color=GLIGHT, spaceBefore=5, spaceAfter=5))

    doc.build(story)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
#  STREAMLIT UI
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Comparador de Materiais",
    page_icon="📋",
    layout="wide",
)

# ── CSS customizado ────────────────────────────────────────────────────────────
st.markdown("""
<style>
.hero-title { font-size: 2rem; font-weight: 800; color: #0F1623; margin-bottom: 0; }
.hero-sub   { font-size: 1rem; color: #6B7280; margin-top: 2px; margin-bottom: 1.5rem; }

.badge-ok   { background: #D1FAE5; color: #065F46; border-radius: 99px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; }
.badge-pend { background: #FEF3C7; color: #92400E; border-radius: 99px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; }
.badge-info { background: #DBEAFE; color: #1E40AF; border-radius: 99px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; }

.preflight {
    background: #F0F9FF;
    border-left: 4px solid #1A6EFF;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 12px 0;
    font-size: 0.9rem;
    line-height: 1.8;
}

.metric-card {
    background: #F8FAFF;
    border: 1.5px solid #E5E9F0;
    border-radius: 12px;
    padding: 20px 16px;
    text-align: center;
}
.metric-num   { font-size: 2.2rem; font-weight: 800; }
.metric-label { font-size: 0.78rem; color: #6B7280; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 4px; }
.num-red    { color: #DC2626; }
.num-orange { color: #F97316; }
.num-green  { color: #16A34A; }

.tag-atualizar { background: #FEE2E2; color: #991B1B; border-radius: 6px; padding: 2px 8px; font-size: 0.72rem; font-weight: 700; margin-right: 6px; }
.tag-incluir   { background: #FEF3C7; color: #92400E; border-radius: 6px; padding: 2px 8px; font-size: 0.72rem; font-weight: 700; margin-right: 6px; }
.tag-ok        { background: #D1FAE5; color: #065F46; border-radius: 6px; padding: 2px 8px; font-size: 0.72rem; font-weight: 700; margin-right: 6px; }
</style>
""", unsafe_allow_html=True)

# ── Hero header ────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 11])
with col_logo:
    st.markdown("## 📋")
with col_title:
    st.markdown('<p class="hero-title">Comparador de Materiais</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">Transcreve áudios 2026, localiza os tópicos nos PDFs 2025 e gera relatório de depara.</p>', unsafe_allow_html=True)

st.divider()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuração")

    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        st.markdown('<span class="badge-ok">✓ API Key configurada</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-pend">⚠ API Key ausente (.env)</span>', unsafe_allow_html=True)

    st.markdown("")
    nome_aula = st.text_input(
        "Nome da aula",
        placeholder="Ex: Hipertensão Arterial",
        help="Aparecerá na capa do relatório.")

    st.divider()
    modo_debug = st.toggle(
        "Modo Debug",
        value=False,
        help="Mostra prévias das transcrições e textos extraídos dos PDFs"
    )
    if modo_debug:
        st.caption("Você verá prévia de transcrições, PDFs e amostras enviadas ao GPT.")

    st.divider()
    with st.expander("ℹ️ Como funciona"):
        st.markdown("""
1. Faça upload dos **PDFs 2025** (materiais escritos)
2. Faça upload dos **Áudios 2026** (aulas gravadas)
3. O sistema transcreve e localiza os tópicos nos PDFs
4. Gera relatório PDF com as divergências encontradas
        """)
    with st.expander("📁 Formatos aceitos"):
        st.markdown("""
**Áudio:** MP3, MP4, WAV, M4A *(qualquer tamanho)*
**Material:** PDF, DOCX, TXT

**Processamento automático:**
- Arquivo pequeno → transcreve direto
- MP3 grande → divide em chunks
- WAV grande → otimiza → divide
        """)

# ── Tabs de upload ─────────────────────────────────────────────────────────────
tab_pdfs, tab_audios = st.tabs(["📄  Materiais 2025 (PDFs)", "🎤  Áudios 2026"])

pdfs_antigos = {}

with tab_pdfs:
    st.markdown("##### Materiais obrigatórios")
    cols_pdf_1 = st.columns(3)
    for i in range(3):
        pdf_info = PDFS_ANTIGOS[i]
        with cols_pdf_1[i]:
            with st.container(border=True):
                pdf_up = st.file_uploader(
                    f"**{pdf_info['label']}**",
                    type=["pdf", "docx", "txt"],
                    key=f"pdf_{pdf_info['id']}",
                )
                if pdf_up:
                    st.markdown(f'<span class="badge-ok">✓ {pdf_up.name}</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span class="badge-pend">Aguardando arquivo</span>', unsafe_allow_html=True)
            pdfs_antigos[pdf_info['id']] = {"upload": pdf_up, "label": pdf_info['label']}

    st.markdown("##### Materiais opcionais")
    cols_pdf_2 = st.columns(2)

    with cols_pdf_2[0]:
        pdf_info = PDFS_ANTIGOS[3]
        with st.container(border=True):
            pdf_up = st.file_uploader(
                f"**{pdf_info['label']}**",
                type=["pdf", "docx", "txt"],
                key=f"pdf_{pdf_info['id']}",
                help="Comparado com o conteúdo completo das aulas."
            )
            if pdf_up:
                st.markdown(f'<span class="badge-ok">✓ {pdf_up.name}</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge-info">Opcional</span>', unsafe_allow_html=True)
        pdfs_antigos[pdf_info['id']] = {"upload": pdf_up, "label": pdf_info['label']}

    with cols_pdf_2[1]:
        pdf_info = PDFS_ANTIGOS[4]
        with st.container(border=True):
            pdf_up = st.file_uploader(
                f"**{pdf_info['label']}**",
                type=["pdf", "docx", "txt"],
                key=f"pdf_{pdf_info['id']}",
                help="Se enviado, comparado 1:1 com o áudio da Aula Resumo."
            )
            if pdf_up:
                st.markdown(f'<span class="badge-ok">✓ {pdf_up.name}</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge-info">Opcional</span>', unsafe_allow_html=True)
        pdfs_antigos[pdf_info['id']] = {"upload": pdf_up, "label": pdf_info['label']}

audios_novos = []

with tab_audios:
    st.markdown("##### Áudios fixos")

    with st.container(border=True):
        c1, c2 = st.columns([2, 8])
        with c1:
            st.markdown("**Aula Resumo**")
        with c2:
            audio_resumo = st.file_uploader(
                "Aula Resumo", type=["mp3", "mp4", "wav", "m4a"],
                key="audio_aula_resumo", label_visibility="collapsed"
            )
            if audio_resumo:
                st.markdown(f'<span class="badge-ok">✓ {audio_resumo.name}</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge-pend">Aguardando áudio</span>', unsafe_allow_html=True)
    if audio_resumo:
        audios_novos.append({"nome": "Aula Resumo", "upload": audio_resumo})

    with st.container(border=True):
        c1, c2 = st.columns([2, 8])
        with c1:
            st.markdown("**EMR+**")
        with c2:
            audio_emr = st.file_uploader(
                "EMR+", type=["mp3", "mp4", "wav", "m4a"],
                key="audio_emr", label_visibility="collapsed"
            )
            if audio_emr:
                st.markdown(f'<span class="badge-ok">✓ {audio_emr.name}</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge-info">Opcional</span>', unsafe_allow_html=True)
    if audio_emr:
        audios_novos.append({"nome": "EMR+", "upload": audio_emr})

    st.markdown("##### Aulas (blocos)")

    if "num_aulas" not in st.session_state:
        st.session_state.num_aulas = 1

    for i in range(st.session_state.num_aulas):
        with st.container(border=True):
            c_nome, c_audio, c_del = st.columns([2, 7, 1])
            with c_nome:
                nome_audio = st.text_input(
                    f"Nome {i+1}",
                    value=f"Aula {i+1}",
                    key=f"nome_aula_{i}",
                    label_visibility="collapsed",
                    placeholder="Ex: Aula 1"
                )
            with c_audio:
                audio_up = st.file_uploader(
                    f"Audio {i+1}",
                    type=["mp3", "mp4", "wav", "m4a"],
                    key=f"audio_aula_{i}",
                    label_visibility="collapsed"
                )
                if audio_up:
                    st.markdown(f'<span class="badge-ok">✓ {audio_up.name}</span>', unsafe_allow_html=True)
            with c_del:
                if i >= 1:
                    if st.button("🗑️", key=f"remove_aula_{i}", help="Remover"):
                        st.session_state.num_aulas -= 1
                        st.rerun()

        if audio_up and nome_audio:
            audios_novos.append({"nome": nome_audio, "upload": audio_up})

    if st.button("➕ Adicionar aula", type="secondary"):
        st.session_state.num_aulas += 1
        st.rerun()

# ── Preflight status + botão ───────────────────────────────────────────────────
st.markdown("")
pdfs_prontos   = sum(1 for v in pdfs_antigos.values() if v["upload"] is not None)
audios_prontos = len(audios_novos)

def _check(ok, label):
    return f"{'✅' if ok else '⬜'} {label}"

col_status, col_btn = st.columns([3, 2])
with col_status:
    st.markdown(
        f'<div class="preflight">'
        f'{_check(bool(nome_aula), "Nome da aula: <b>" + (nome_aula or "não definido") + "</b>")}<br>'
        f'{_check(pdfs_prontos > 0, f"<b>{pdfs_prontos}</b> PDF(s) carregado(s)")}<br>'
        f'{_check(audios_prontos > 0, f"<b>{audios_prontos}</b> áudio(s) carregado(s)")}<br>'
        f'{_check(bool(api_key), "API Key OpenAI configurada")}'
        f'</div>',
        unsafe_allow_html=True,
    )
with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    gerar = st.button(
        "🚀 Gerar Relatório",
        type="primary",
        use_container_width=True,
        disabled=not (nome_aula and pdfs_prontos > 0 and audios_prontos > 0 and api_key),
    )

if gerar:
    # ── Validações ─────────────────────────────────────────────────────────────
    erros = []

    if not api_key:
        erros.append("❌ Chave API da OpenAI não configurada. Verifique o arquivo .env")

    if not nome_aula:
        erros.append("❌ Insira o nome da aula na barra lateral.")

    pdfs_enviados = {k: v for k, v in pdfs_antigos.items() if v["upload"] is not None}
    if len(pdfs_enviados) == 0:
        erros.append("❌ Envie pelo menos 1 PDF antigo (Resumo, Apostila ou Mapa Mental).")

    if len(audios_novos) == 0:
        erros.append("❌ Envie pelo menos 1 áudio novo.")

    if erros:
        for e in erros:
            st.error(e)
        st.stop()

    # ── Preparação dos PDFs ────────────────────────────────────────────────────
    st.info(f"📄 {len(pdfs_enviados)} PDFs | 🎤 {len(audios_novos)} áudios — iniciando processamento...")

    pdfs_processados = {}

    with st.spinner("Extraindo texto dos PDFs antigos..."):
        for pdf_id, pdf_data in pdfs_enviados.items():
            pdf_bytes = pdf_data["upload"].read()
            pdf_nome = pdf_data["upload"].name

            ext = Path(pdf_nome).suffix.lower()
            if ext == ".pdf":
                texto = extrair_texto_pdf(pdf_bytes)
            elif ext == ".docx":
                texto = extrair_texto_docx(pdf_bytes)
            else:
                texto = pdf_bytes.decode("utf-8", errors="replace")

            if not texto.strip():
                st.warning(f"⚠️ {pdf_data['label']}: não foi possível extrair texto.")
                continue

            pdfs_processados[pdf_id] = {"label": pdf_data['label'], "texto": texto}

            if modo_debug:
                with st.expander(f"📄 Prévia: {pdf_data['label']} ({len(texto)} caracteres)"):
                    st.text_area(
                        f"Primeiros 2000 caracteres do {pdf_data['label']}:",
                        texto[:2000], height=200, key=f"preview_pdf_{pdf_id}"
                    )

    if not pdfs_processados:
        st.error("❌ Nenhum PDF foi processado com sucesso.")
        st.stop()

    # ── Separar áudios por tipo ────────────────────────────────────────────────
    audios_com_pdf = []
    audios_aulas = []

    pdf_material_aula_resumo_disponivel = pdfs_processados.get("material_aula_resumo") is not None

    for audio_data in audios_novos:
        nome = audio_data["nome"].lower()
        if "aula resumo" in nome and pdf_material_aula_resumo_disponivel:
            audios_com_pdf.append(("Aula Resumo", audio_data, "Material de Acompanhamento"))
        elif "emr" in nome or "emr+" in nome:
            audios_com_pdf.append(("EMR+", audio_data, "EMR+"))
        elif "dica" in nome and "prova" in nome:
            audios_com_pdf.append(("Dica de Prova", audio_data, "Dica de Prova"))
        else:
            audios_aulas.append(audio_data)

    pdfs_para_aulas_combinadas = 0
    for pdf_id, pdf_data in pdfs_processados.items():
        label_lower = pdf_data['label'].lower()
        if not ('material' in label_lower and 'acompanhamento' in label_lower and 'aula resumo' in label_lower) and \
           not ('emr' in label_lower or label_lower == 'emr+') and \
           not ('dica' in label_lower and 'prova' in label_lower):
            pdfs_para_aulas_combinadas += 1

    total_comparacoes = len(audios_com_pdf) + pdfs_para_aulas_combinadas
    progress = st.progress(0, text="Iniciando transcrições...")
    contador = 0

    resultados = []
    transcricoes_aulas = []

    st.info(f"📊 Estrutura: {len(audios_com_pdf)} comparações 1:1 + {len(pdfs_processados)} comparações com aulas combinadas")

    # ── Passo 1: Transcrições ──────────────────────────────────────────────────
    audios_com_pdf_transcritos = []
    for nome_limpo, audio_data, pdf_correspondente in audios_com_pdf:
        progress.progress(contador / (total_comparacoes + len(audios_aulas)),
                         text=f"🎤 Transcrevendo: **{nome_limpo}**...")
        try:
            audio_bytes = audio_data["upload"].read()
            audio_filename = audio_data["upload"].name
            transcricao = _whisper(api_key, audio_bytes, audio_filename)
            palavras = len(transcricao.split())
            st.toast(f"✅ {nome_limpo}: {palavras} palavras transcritas")
            audios_com_pdf_transcritos.append((nome_limpo, transcricao, pdf_correspondente))
            if modo_debug:
                with st.expander(f"🎤 {nome_limpo} ({palavras} palavras)"):
                    st.text_area("Transcrição:", transcricao, height=200, key=f"prev_{nome_limpo}")
        except Exception as e:
            st.error(f"❌ {nome_limpo}: {e}")
        contador += 1

    for audio_data in audios_aulas:
        audio_nome = audio_data["nome"]
        progress.progress(contador / (total_comparacoes + len(audios_aulas)),
                         text=f"🎤 Transcrevendo: **{audio_nome}**...")
        try:
            audio_bytes = audio_data["upload"].read()
            audio_filename = audio_data["upload"].name
            transcricao = _whisper(api_key, audio_bytes, audio_filename)
            palavras = len(transcricao.split())
            st.toast(f"✅ {audio_nome}: {palavras} palavras transcritas")
            transcricoes_aulas.append({"nome": audio_nome, "transcricao": transcricao})
            if modo_debug:
                with st.expander(f"🎤 {audio_nome} ({palavras} palavras)"):
                    st.text_area("Transcrição:", transcricao, height=200, key=f"prev_{audio_nome.replace(' ', '_')}")
        except Exception as e:
            st.error(f"❌ {audio_nome}: {e}")
        contador += 1

    # ── Passo 2: Combina transcrições ─────────────────────────────────────────
    if transcricoes_aulas:
        conteudo_completo_aulas = "\n\n--- NOVA AULA ---\n\n".join([
            f"=== {t['nome']} ===\n{t['transcricao']}"
            for t in transcricoes_aulas
        ])
        total_palavras = sum(len(t['transcricao'].split()) for t in transcricoes_aulas)
        st.success(f"✅ Aulas combinadas: {len(transcricoes_aulas)} aulas, {total_palavras} palavras")
        if modo_debug:
            with st.expander(f"📚 Conteúdo Completo das Aulas ({total_palavras} palavras)"):
                st.text_area("Todas as aulas combinadas:", conteudo_completo_aulas[:2000] + "\n\n[...]", height=300, key="prev_combinado")

    # ── Passo 3: Comparações ──────────────────────────────────────────────────
    for nome_audio, transcricao, pdf_nome in audios_com_pdf_transcritos:
        pdf_data = None
        for pdf_id, pdf in pdfs_processados.items():
            label_lower = pdf['label'].lower()
            pdf_nome_lower = pdf_nome.lower()
            if label_lower == pdf_nome_lower or pdf_nome_lower in label_lower or label_lower in pdf_nome_lower:
                pdf_data = pdf
                break

        if not pdf_data:
            st.warning(f"⚠️ PDF '{pdf_nome}' não encontrado para {nome_audio}.")
            continue

        comparacao_label = f"{nome_audio} vs {pdf_data['label']}"
        progress.progress(min(1.0, contador / total_comparacoes), text=f"⚙️ Analisando: {comparacao_label}...")

        try:
            if modo_debug:
                with st.expander(f"🔍 {comparacao_label}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.caption(f"**{nome_audio}**:")
                        st.code(transcricao[:500] + "\n[...]", language="text")
                    with col2:
                        st.caption(f"**{pdf_data['label']}**:")
                        st.code(pdf_data['texto'][:500] + "\n[...]", language="text")

            analise = _analisar(api_key, transcricao, pdf_data['texto'], pdf_data['label'], nome_aula)
            resultados.append({
                "audio_nome": nome_audio,
                "pdf_label": pdf_data['label'],
                "comparacao": comparacao_label,
                "analise": analise,
            })
        except Exception as e:
            st.error(f"❌ {comparacao_label}: {e}")

        contador += 1

    if transcricoes_aulas:
        for pdf_id, pdf_data in pdfs_processados.items():
            label_lower = pdf_data['label'].lower()

            if 'material' in label_lower and 'acompanhamento' in label_lower and 'aula resumo' in label_lower:
                continue
            if 'emr' in label_lower or label_lower == 'emr+':
                continue
            if 'dica' in label_lower and 'prova' in label_lower:
                continue

            comparacao_label = f"Aulas Completas vs {pdf_data['label']}"
            progress.progress(min(1.0, contador / total_comparacoes), text=f"⚙️ Analisando: {comparacao_label}...")

            try:
                if modo_debug:
                    with st.expander(f"🔍 {comparacao_label}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.caption("**Todas as Aulas**:")
                            st.code(conteudo_completo_aulas[:500] + "\n[...]", language="text")
                        with col2:
                            st.caption(f"**{pdf_data['label']}**:")
                            st.code(pdf_data['texto'][:500] + "\n[...]", language="text")

                analise = _analisar(api_key, conteudo_completo_aulas, pdf_data['texto'], pdf_data['label'], nome_aula)
                resultados.append({
                    "audio_nome": "Aulas Completas",
                    "pdf_label": pdf_data['label'],
                    "comparacao": comparacao_label,
                    "analise": analise,
                })
            except Exception as e:
                st.error(f"❌ {comparacao_label}: {e}")

            contador += 1

    progress.progress(1.0, text="✅ Todas as comparações concluídas!")

    if not resultados:
        st.error("❌ Nenhuma comparação foi processada com sucesso.")
        st.stop()

    # ── Métricas de resumo ─────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 Resumo")

    total_atualizar = sum(len(r["analise"].get("atualizacoes_necessarias", [])) for r in resultados)
    total_ok        = sum(len(r["analise"].get("sem_mudancas", []))              for r in resultados)

    m1, m2 = st.columns(2)
    with m1:
        st.markdown(
            f'<div class="metric-card">'
            f'<div class="metric-num num-red">{total_atualizar}</div>'
            f'<div class="metric-label">Divergencias encontradas</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with m2:
        st.markdown(
            f'<div class="metric-card">'
            f'<div class="metric-num num-green">{total_ok}</div>'
            f'<div class="metric-label">Conteudo Alinhado</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    # ── Resultados inline por material ────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔍 Resultados por Material")

    for r in resultados:
        an = r["analise"]
        atualizacoes = an.get("atualizacoes_necessarias", [])
        sem_mudancas = an.get("sem_mudancas", [])
        total_issues = len(atualizacoes)
        label_badge  = f"🔴 {total_issues} divergencia(s)" if total_issues > 0 else "🟢 Alinhado"

        with st.expander(f"**{r['comparacao']}** — {label_badge}", expanded=(total_issues > 0)):
            if atualizacoes:
                st.markdown("**Divergencias encontradas (audio vs PDF):**")
                for item in atualizacoes:
                    c1, c2, c3 = st.columns([3, 4, 4])
                    with c1:
                        st.markdown(
                            f'<span class="tag-atualizar">ATUALIZAR</span> **{item.get("item", "")}**',
                            unsafe_allow_html=True
                        )
                    with c2:
                        st.caption("Antes (Materiais 2025)")
                        st.markdown(f'_{item.get("pdf_2025", "—")}_')
                    with c3:
                        st.caption("Depois (Atualização da aula)")
                        st.markdown(f'**{item.get("aula_2026", "—")}**')
                st.markdown("")

            if sem_mudancas:
                with st.expander(f"✅ {len(sem_mudancas)} topico(s) alinhado(s)", expanded=False):
                    for item in sem_mudancas:
                        st.markdown(
                            f'<span class="tag-ok">OK</span> **{item.get("item", "")}** — {item.get("conteudo", "")}',
                            unsafe_allow_html=True
                        )

            if not atualizacoes:
                st.success("Nenhuma divergencia encontrada entre o audio e este material.")

    # ── Download PDF ───────────────────────────────────────────────────────────
    st.markdown("---")
    with st.spinner("Gerando relatório PDF..."):
        pdf_bytes = gerar_pdf(nome_aula, resultados)

    nome_arquivo = (nome_aula.lower()
                    .replace(" ", "_")
                    .replace("/", "-")[:40])
    nome_arquivo = f"comparacao_{nome_arquivo}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"

    st.success(f"✅ Relatório gerado! {len(resultados)} comparações incluídas.")
    st.download_button(
        label="⬇️ Baixar Relatório Completo (PDF)",
        data=pdf_bytes,
        file_name=nome_arquivo,
        mime="application/pdf",
        use_container_width=True,
        type="primary",
    )
