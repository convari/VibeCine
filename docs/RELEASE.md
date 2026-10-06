# RELEASE.md — Como publicar uma nova versão do VibeCine

> Para mantenedores. Nada aqui é executado pelo usuário final.
> NÃO commite senhas/chaves — este processo não usa nenhuma.

## Visão geral do pipeline

```
branding.py (versão) → CHANGELOG.md → build.py → make_latest_json.py → release/
                                                                    ├─ VibeCine-Setup-X.Y.Z.exe
                                                                    ├─ VibeCine-X.Y.Z-portable.zip
                                                                    ├─ SHA256SUMS.txt
                                                                    ├─ latest.json
                                                                    └─ CHANGELOG.md
```

## 1) Alterar a versão

Edite **somente** `app/core/branding.py`:

```python
APP_VERSION = "2.0.1"   # fonte única — app e instalador usam este valor
```

Atualize `CHANGELOG.md` com a nova seção.

## 2) Gerar build + instalador

```powershell
cd <raiz do projeto>
.\.venv\Scripts\python.exe build\build.py
```

Isso gera os ícones, roda o PyInstaller (`dist/VibeCine/`), executa o
selftest do `.exe`, cria o portable ZIP, o instalador (se o Inno Setup
estiver instalado) e o `SHA256SUMS.txt`.

## 3) Conferir hashes

```powershell
Get-Content release\SHA256SUMS.txt
```

## 4) Gerar latest.json

```powershell
.\.venv\Scripts\python.exe build\make_latest_json.py
```

Ajuste `BASE_URL` no script para o domínio real do servidor de updates.

## 5) Estrutura exigida no servidor de atualização

O app consulta `APP_UPDATE_URL` (ver `app/core/app_updater.py`):
**`https://updates.vibcine.app/latest.json`** (placeholder — troque pelo
URL real e reconstrua, ou defina `VIBECINE_UPDATE_URL` no ambiente).

Estrutura mínima de URLs que o servidor precisa servir:

```
https://<seu-dominio>/latest.json
https://<seu-dominio>/v2/VibeCine-2.0.0-portable.zip
https://<seu-dominio>/v2/VibeCine-Setup-2.0.0.exe
https://<seu-dominio>/v2/CHANGELOG.md
```

(O prefixo `/v2/` é o `BASE_URL` de `build/make_latest_json.py` —
adicione-o aos caminhos se o mantiver.)

Compatibilidade do app com o manifesto:
- Lê: `version`, `url`, `sha256` (e exibe o restante ao usuário).
- `url`/`sha256` DEVEM se referir ao **portable.zip** (é o pacote que o
  mecanismo interno baixa, verifica e aplica via swap).
- `installer_url` é o link que a UI oferece ao usuário para download manual.

## 6) Upload

Envie para o servidor (na pasta escolhida):
- `VibeCine-Setup-2.0.0.exe`
- `VibeCine-2.0.0-portable.zip`
- `latest.json`
- `CHANGELOG.md`
- `SHA256SUMS.txt` (referência para os usuários conferirem)

## 7) Testar a atualização LOCALMENTE (antes de publicar)

Sem expor nada na internet, valide o ciclo completo:

```powershell
# 1) Suba um servidor local servindo a pasta release/:
cd release
python -m http.server 8080

# 2) Em outro terminal, com o app de desenvolvimento (mesmo código):
$env:VIBECINE_UPDATE_URL = "http://127.0.0.1:8080/latest.json"
.\.venv\Scripts\python.exe -c @"
from app.core import app_updater
m = app_updater.check_for_update()
print('manifesto:', m['version'], m['url'])
p = app_updater.download_update(m)
print('baixado+validado:', p)
"@
```

O download será **validado pelo SHA-256 real** do manifesto. Para testar
o swap completo, instale a build em uma pasta de teste (ver Fase 6,
Teste C) e substitua o `url` por `file:///` no manifesto local.

Para testar a rejeição de pacote adulterado, altere 1 byte do ZIP e
regenere o manifesto — o app DEVE recusar.

## 8) Publicar

- Suba os arquivos do item 5.
- Anuncie. Usuários existentes verão "Nova versão disponível" em
  Configurações → Atualizações.

## Checklist antes de publicar qualquer versão
- [ ] Versão em `branding.py` == nome dos arquivos == `latest.json`
- [ ] `sha256` do portable confere (`Get-FileHash` vs `latest.json`)
- [ ] `sha256` do instalador confere
- [ ] CHANGELOG.md atualizado e copiado para `release/`
- [ ] Teste local do update (item 7) PASSOU
- [ ] Suíte completa OK: `python -m unittest discover -s tests`
- [ ] QA E2E OK: `python qa_e2e.py`
