# Instalação — VibeCine Downloader Pro 2.0.0

## Requisitos
- Windows 10/11 64-bit
- Conexão com a internet na primeira execução (o app baixa yt-dlp, FFmpeg
  e Deno — ferramentas de terceiros — para sua pasta de dados)
- **Não precisa** de Python, pip ou qualquer configuração manual

## Instalação (recomendado)
1. Baixe `VibeCine-Setup-2.0.0.exe`.
2. Opcional: confira o hash SHA-256 no arquivo `SHA256SUMS.txt`
   (`certutil -hashfile VibeCine-Setup-2.0.0.exe SHA256`).
3. Execute o instalador (não pede administrador — instala por usuário).
4. Marque o atalho na Área de Trabalho se desejar.
5. Ao abrir, siga o assistente (Termos de Uso → pasta de downloads →
   verificação das ferramentas).

## Versão portable
1. Baixe `VibeCine-2.0.0-portable.zip`.
2. Extraia e execute `VibeCine\VibeCine.exe`.
- As configurações e o histórico ficam em `%APPDATA%\VibeCine` (não na
  pasta portable), então a configuração é compartilhada com a versão
  instalada e sobrevive a atualizações.

## Desinstalação
- Menu Iniciar → VibeCine → Desinstalar.
- O desinstalador remove o programa e o protocolo `vibcine://`.
- Seus dados (`%APPDATA%\VibeCine`) e seus downloads **não são apagados**.

## Problemas comuns
- **"yt-dlp/deno não encontrado"**: Configurações → Atualizações →
  "Verificar e atualizar ferramentas".
- **Link expirado (403)**: links de IPTV expiram; solicite um novo ao
  provedor.
- **YouTube pede verificação**: atualize as ferramentas (ver acima) e
  tente novamente.
