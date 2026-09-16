# 🐾 VetClinic — Gestão de Clínica Veterinária

Aplicativo web (Python + Streamlit) para gerenciamento de clínica veterinária, com dados salvos localmente em SQLite (`vetclinic.db`).

## Acesso

O sistema possui **login obrigatório**. No primeiro uso, entre com:

```
Usuário: admin
Senha:   admin123
```

Troque a senha em **🔑 Trocar minha senha** (barra lateral). O administrador pode criar usuários com os papéis **Recepção**, **Veterinário(a)** e **Administrador** na página **🔐 Usuários** (visível apenas para admins).

## Módulos

- **🏠 Início** — painel com indicadores do dia: tutores, pets, compromissos de hoje, saldo do mês, vacinas vencidas e a vencer, agenda do dia, alertas de vacinas, aniversariantes e últimos atendimentos.
- **📅 Agenda** — marcação de consultas/vacinas/exames/cirurgias com horário; aviso de conflito de horário; controle de status (Agendado → Confirmado → Concluído / Faltou / Cancelado); ao concluir, pode registrar automaticamente no histórico do pet.
- **💉 Vacinas** — carteirinha de vacinação por pet com controle de reforços; alertas de vacinas vencidas e a vencer nos próximos 15 dias (com telefone do tutor); sugestões de vacinas por espécie; registro opcional no histórico.
- **👤 Tutores** — cadastro completo (nome, telefone, e-mail, CPF, endereço, observações), busca, edição, exclusão com aviso de dados vinculados e exportação CSV.
- **🐾 Pets** — cadastro vinculado ao tutor (espécie, raça, sexo, nascimento, peso, cor, microchip, castração), cálculo automático de idade, filtros por espécie/tutor e busca.
- **📋 Histórico** — prontuário de atendimentos por pet (data, tipo, veterinário, peso no dia, descrição), com edição e exportação CSV.
- **📎 Exames** — anexo de exames e documentos por pet (PDF/PNG/JPG até 10 MB), com pré-visualização de imagens, download e exclusão. Os arquivos ficam salvos dentro do banco SQLite.
- **💬 Lembretes** — nos alertas de vacinas e na agenda do dia, botões que abrem o **WhatsApp** ou o **e-mail** já com a mensagem pronta para o tutor.
- **🔐 Usuários** — gestão de logins com senhas criptografadas (PBKDF2-SHA256) e papéis (recepção / veterinário / administrador).
- **💰 Financeiro** — receitas e despesas por mês com categorias, formas de pagamento, vínculo opcional a um pet, métricas de receitas/despesas/saldo, gráficos por dia e por categoria, exportação CSV.
- **📄 Relatórios** — geração de PDFs: carteirinha de vacinação do pet, histórico de atendimentos do pet, relatório financeiro do mês e agenda do dia.

## Como executar

```bash
cd vetclinic
pip install streamlit pandas fpdf2
streamlit run app.py
```

Acesse em `http://localhost:8501`.

## Estrutura

```
vetclinic/
├── app.py          # aplicação completa
├── dbcloud.py      # cliente da API do Turso (banco em nuvem)
├── db_config.json  # credenciais da nuvem (criado ao conectar — NÃO compartilhar)
└── vetclinic.db    # banco SQLite local (criado automaticamente no primeiro uso)
```

## ☁️ Banco em nuvem (acesso de vários computadores)

O app funciona por padrão com SQLite **local**. Para compartilhar os dados entre vários
computadores/acessos, conecte-o a um banco na nuvem usando o **Turso** (SQLite em nuvem,
plano gratuito) — a página **☁️ Nuvem** (visível para administradores) guia o processo:

1. Crie uma conta grátis em [turso.tech](https://turso.tech);
2. No painel do Turso, crie um banco (ex.: `vetclinic`) e gere um **token de acesso**;
3. No app: menu **☁️ Nuvem** → cole a URL (`libsql://...`) e o token → **Testar conexão** → **Salvar e conectar**;
4. Opcional: use **📦 Migrar dados locais para a nuvem** para levar os cadastros existentes
   (nada é sobrescrito — tabelas com dados na nuvem são puladas).

Após conectar, **todos os módulos passam a ler e gravar na nuvem automaticamente**.
A barra lateral mostra o modo atual: `☁️ Nuvem` ou `💾 Local`.

A configuração também pode vir de variáveis de ambiente (`TURSO_DATABASE_URL` e
`TURSO_AUTH_TOKEN`) ou `.streamlit/secrets.toml`, que têm prioridade sobre o arquivo
`db_config.json`. Para voltar ao modo local: página **☁️ Nuvem → Desconectar da nuvem**
(ou apague `db_config.json`).

> 🗄️ Deploy multi-usuário: como a sessão de login fica por navegador, o mesmo app pode ser
> acessado por toda a equipe, cada um com seu usuário — basta hospedar o Streamlit em um
> servidor acessível e configurar a nuvem.

## 🌐 Deploy público (acesso pela internet)

Tudo pronto para colocar o app no ar **de graça** (Streamlit Community Cloud + Turso):

```
app.py · dbcloud.py · requirements.txt · .streamlit/config.toml · .gitignore · DEPLOY.md
```

➡️ Siga o **[DEPLOY.md](DEPLOY.md)** — guia passo a passo em português
(~15 minutos: GitHub → Streamlit Cloud → Secrets → pronto).

**Antes de publicar, confira:**
- [ ] `vetclinic.db`, `db_config.json` e `.streamlit/secrets.toml` **NÃO** foram enviados ao GitHub
- [ ] Secrets do Turso configuradas no Streamlit Cloud (`TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN`)
- [ ] Senha do admin trocada no primeiro acesso

## Utilidades (barra lateral)

- **Carregar dados de exemplo** — popula a base vazia com 3 tutores, 4 pets, atendimentos, agendamentos, vacinas (incluindo uma vencida para demonstrar os alertas) e lançamentos financeiros.
- **Apagar todos os dados** — limpa completamente o banco (com confirmação).
