# Recebimento de links externos (`vibcine://`) — plano para Fase 5/6

> Status: **não implementado** (decisão registrada na Fase 4). Este documento
> descreve como será feito quando autorizado.

## Objetivo

Permitir que links abram diretamente no VibeCine:

1. **Protocolo próprio**: um link `vibcine://load?url=<URL codificada>`
   clicado no navegador/WhatsApp abre o app e já carrega a playlist/vídeo
   na página Biblioteca.
2. **Detecção de clipboard**: ao focar a janela, se o clipboard contém uma
   URL de playlist/YouTube, mostrar um toast "Link detectado — carregar?"
   com ação em um clique.

## Como será implementado (Windows)

### Protocolo `vibcine://`

Registro no sistema (feito pelo instalador Inno Setup na Fase 6, ou por
uma ação "Registrar protocolo" nas Configurações com permissão de usuário):

```
HKCU\Software\Classes\vibcine
    (padrão)            = "URL:VibeCine Protocol"
    URL Protocol        = ""
HKCU\Software\Classes\vibcine\shell\open\command
    (padrão)            = "C:\...\VibeCine.exe" "%1"
```

- Registrar em `HKCU` (sem privilégio de administrador).
- O executável/launcher (`vibcine.py`) passa a aceitar argumento:
  `vibcine.py "vibcine://load?url=https%3A%2F%2F..."`.
- Se o app já estiver aberto, a segunda instância retransmite o link à
  primeira via **named pipe / QLocalServer** (`QLocalSocket`), evitando
  duas janelas.

### Fluxo dentro do app

```
vibcine://load?url=ENCODED
        │
        ▼
app/ui/main_window.py  → decodifica (urllib.parse)
        │
        ▼  passa pelo MESMO pipeline de segurança já existente:
app/core/url_router.validate_url()  →  extractor.extract_entries()
        │
        ▼
Biblioteca carrega o conteúdo automaticamente (página "library")
```

Nenhuma lógica nova de extração é necessária: a rota apenas injeta a URL
no campo da Biblioteca e dispara `load_url()`.

### Segurança

- Aceitar somente esquema `http/https` após decodificação (reuso de
  `url_router.validate_url`; `file://` de links externos será recusado).
- Nunca executar nada da URL além do carregamento normal.
- Registrar no log somente a URL mascarada (`redact_url`).
