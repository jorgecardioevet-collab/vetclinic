# 🌐 Guia de Deploy — VetClinic no ar 24h (grátis)

Este guia leva o VetClinic para a internet em **~15 minutos**, sem pagar nada:

| Peça | Onde | Custo |
|---|---|---|
| Aplicativo (site) | Streamlit Community Cloud | Grátis |
| Banco de dados | Turso (SQLite na nuvem) | Grátis |
| Código-fonte | GitHub | Grátis |

> ⚠️ **Por que o banco em nuvem é obrigatório no deploy?**
> No Streamlit Cloud, os arquivos locais do app (inclusive o `vetclinic.db`) são
> **apagados a cada reinício**. Com o Turso, os dados ficam seguros e acessíveis
> para toda a equipe.

---

## Passo 1 — Criar o banco na nuvem (Turso)

1. Acesse **[turso.tech](https://turso.tech)** e crie a conta (grátis, pode entrar com GitHub/Google);
2. No painel, clique em **Create Database** → nome: `vetclinic` → local: o mais próximo do Brasil disponível;
3. Com o banco criado, copie a **Database URL** — formato `libsql://vetclinic-xxxx.turso.io`;
4. Clique em **Generate Token** (ou "Create Token") e copie o **token**.

Guarde os dois — vamos usá-los no Passo 3.

## Passo 2 — Publicar o código no GitHub

### Opção A — pelo navegador (mais fácil, sem instalar nada)

1. Acesse **[github.com](https://github.com)** e crie a conta, se ainda não tiver;
2. Clique em **New repository** (ou o botão **+** → *New repository*):
   - Nome: `vetclinic`
   - Deixe **Private** (recomendado) ou Public
   - Marque **"Add a README file"** apenas se quiser (não é necessário);
3. Dentro do repositório, clique em **Add file → Upload files**;
4. Arraste estes arquivos da pasta `vetclinic/`:

   ```
   app.py
   dbcloud.py
   requirements.txt
   README.md
   DEPLOY.md
   .gitignore
   .streamlit/config.toml
   .streamlit/secrets.toml.example
   ```

   > 🚫 **NUNCA envie:** `vetclinic.db` (dados), `db_config.json` (token) nem
   > `.streamlit/secrets.toml` preenchido.

5. Clique em **Commit changes**.

### Opção B — pela linha de comando (se você usa git)

```bash
cd vetclinic
git init
git add app.py dbcloud.py requirements.txt README.md DEPLOY.md .gitignore .streamlit/
git commit -m "VetClinic - primeira versão"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/vetclinic.git
git push -u origin main
```

## Passo 3 — Publicar o app no Streamlit Cloud

1. Acesse **[share.streamlit.io](https://share.streamlit.io)** e entre com a conta do **GitHub**;
2. Clique em **Create app** (ou **New app**);
3. Preencha:
   - **Repository**: `seu-usuario/vetclinic`
   - **Branch**: `main`
   - **Main file path**: `app.py`
4. **Antes de clicar em Deploy**, abra **Advanced settings → Secrets** e cole (substituindo pelos valores do Passo 1):

   ```toml
   TURSO_DATABASE_URL = "libsql://vetclinic-xxxx.turso.io"
   TURSO_AUTH_TOKEN = "seu-token-aqui"
   ```

5. Clique em **Deploy** e aguarde ~2 minutos. 🎉
   Seu app estará no ar em um endereço como `https://seu-app.streamlit.app`.

> Se esquecer das Secrets: tudo bem! O app abre em modo local (💾). Depois vá em
> **⋮ → Settings → Secrets**, cole as variáveis e salve — o app reinicia sozinho e
> conecta na nuvem.

## Passo 4 — Primeiro acesso no ar (obrigatório!)

1. Abra a URL do app e entre com **admin / admin123**;
2. **Troque a senha imediatamente** (barra lateral → 🔑 Trocar minha senha);
3. Em **🔐 Usuários**, crie os logins da recepção e dos veterinários;
4. Na primeira execução, o app cria as tabelas no Turso automaticamente. ✅

## Passo 5 — Levar seus dados atuais para a nuvem (opcional)

Se você já usava o app localmente e quer levar os cadastros:

1. Rode o app **no seu computador** (ou nesta prévia) com a **mesma URL e token do Turso**
   configurados na página **☁️ Nuvem**;
2. Clique em **📦 Migrar dados locais para a nuvem agora**;
3. Pronto — como o app no ar usa o mesmo banco Turso, os dados aparecem lá automaticamente.

## Compartilhando com a equipe

- Envie a URL do app + o login/senha de cada pessoa (as contas criadas no Passo 4);
- Para mais privacidade, no painel do Streamlit Cloud: **Settings → Sharing** —
  defina quem pode ver o app (por e-mail). O login do VetClinic continua protegendo os dados.

## Atualizando o sistema

Sempre que uma nova versão dos arquivos for gerada:
- **Opção A (navegador)**: no GitHub, abra cada arquivo → lápis (*Edit*) → cole o novo conteúdo → Commit;
- **Opção B (git)**: `git add -A && git commit -m "atualização" && git push`.

O Streamlit Cloud **republica automaticamente** a cada commit. Os dados no Turso não são afetados.

## Custos e limites (planos gratuitos)

- **Streamlit Community Cloud**: ideal para 1 app; adormece após alguns dias sem acesso e
  "acorda" sozinho quando alguém abre (primeiro acesso pode levar ~30 segundos) — normal!
- **Turso (plano Starter)**: mais que suficiente para uma clínica pequena/média
  (diversos GB e milhões de leituras/mês).

## Alternativa sem internet

O app também funciona 100% **offline** em modo local (💾): deixe-o rodando em um computador
da clínica e acesse pelos outros PCs via `http://IP-DO-COMPUTADOR:8501` na mesma rede — sem Turso.
