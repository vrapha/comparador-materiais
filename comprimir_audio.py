"""
Script simples para comprimir áudios WAV grandes para MP3.
Uso: python comprimir_audio.py arquivo.wav

Gera arquivo_comprimido.mp3 na mesma pasta.
"""

import sys
import os

def comprimir_audio(arquivo_entrada):
    """Comprime áudio usando FFmpeg."""
    if not os.path.exists(arquivo_entrada):
        print(f"❌ Arquivo não encontrado: {arquivo_entrada}")
        return False

    # Nome do arquivo de saída
    nome_base = os.path.splitext(arquivo_entrada)[0]
    arquivo_saida = f"{nome_base}_comprimido.mp3"

    # Comando FFmpeg para compressão máxima
    # 64kbps, mono, qualidade suficiente para transcrição
    comando = f'ffmpeg -i "{arquivo_entrada}" -b:a 64k -ac 1 -ar 16000 "{arquivo_saida}" -y'

    print(f"🔄 Comprimindo: {arquivo_entrada}")
    print(f"📦 Saída: {arquivo_saida}")
    print(f"⚙️ Comando: {comando}")
    print()

    resultado = os.system(comando)

    if resultado == 0:
        # Verifica tamanhos
        tamanho_original = os.path.getsize(arquivo_entrada) / (1024 * 1024)
        tamanho_comprimido = os.path.getsize(arquivo_saida) / (1024 * 1024)
        reducao = ((tamanho_original - tamanho_comprimido) / tamanho_original) * 100

        print()
        print(f"✅ Compressão concluída!")
        print(f"   Original: {tamanho_original:.1f}MB")
        print(f"   Comprimido: {tamanho_comprimido:.1f}MB")
        print(f"   Redução: {reducao:.1f}%")

        if tamanho_comprimido > 25:
            print()
            print(f"⚠️ ATENÇÃO: Arquivo ainda está grande ({tamanho_comprimido:.1f}MB).")
            print(f"   O limite da API é 25MB. Considere dividir o áudio.")

        return True
    else:
        print()
        print("❌ Erro na compressão.")
        print("Certifique-se de que o FFmpeg está instalado:")
        print("   winget install Gyan.FFmpeg")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python comprimir_audio.py arquivo.wav")
        print()
        print("Exemplo:")
        print('  python comprimir_audio.py "Aula Resumo.wav"')
        sys.exit(1)

    arquivo = sys.argv[1]
    comprimir_audio(arquivo)
