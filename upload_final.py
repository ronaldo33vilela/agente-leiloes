#!/usr/bin/env python3
"""
Upload final para GitHub de todos os arquivos corrigidos.
"""
import subprocess
import sys
import os

os.chdir('/home/ubuntu/agente-leiloes')

# Configurar git
subprocess.run(['git', 'config', 'user.email', 'bot@agente-leiloes.com'], check=False)
subprocess.run(['git', 'config', 'user.name', 'Agente Bot'], check=False)

# Adicionar todos os arquivos
print("📝 Adicionando arquivos...")
subprocess.run(['git', 'add', '-A'], check=True)

# Verificar status
result = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True)
print(f"Status:\n{result.stdout}")

# Commit
print("\n💾 Fazendo commit...")
subprocess.run([
    'git', 'commit', 
    '-m', 'Rebuild: scrapers reescritos com URLs corretas e filtro de relevância'
], check=True)

# Push
print("\n🚀 Enviando para GitHub...")
subprocess.run(['git', 'push', 'origin', 'main'], check=True)

print("\n✅ Upload concluído com sucesso!")
