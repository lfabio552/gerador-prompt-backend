import youtube_transcript_api
from youtube_transcript_api import YouTubeTranscriptApi
import os

print("\n--- DIAGNÓSTICO DO SISTEMA ---")
print(f"1. Onde o Python está achando a biblioteca?")
print(f"Caminho: {youtube_transcript_api.__file__}")

print(f"\n2. O que tem dentro dessa biblioteca?")
try:
    print(f"Tem 'list_transcripts'? {'list_transcripts' in dir(YouTubeTranscriptApi)}")
    print(f"Tem 'get_transcript'? {'get_transcript' in dir(YouTubeTranscriptApi)}")
except:
    print("Não consegui ler o conteúdo.")

print("\n3. Lista completa de funções disponíveis:")
print(dir(YouTubeTranscriptApi))
print("------------------------------\n")