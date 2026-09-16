# 🚀 Guia Rápido — Primeiros passos com o VetClinic

## 1️⃣ Abrir e entrar

1. Abra o app no navegador (a prévia está rodando; no seu computador seria `http://localhost:8501`);
2. Na tela de login, entre com:
   - **Usuário:** `admin`
   - **Senha:** `admin123`
3. **Troque a senha na hora**: barra lateral → **🔑 Trocar minha senha**.

## 2️⃣ Escolha: testar com exemplos OU começar do zero

**Opção A — Explorar rápido (recomendado para conhecer):**
- Barra lateral → **⚙️ Utilidades** → **Carregar dados de exemplo**.
- Serão criados 3 tutores, 4 pets, atendimentos, agendamentos, vacinas e lançamentos.
- Navegue por todas as telas para conhecer. Quando terminar, volte em ⚙️ Utilidades → **🗑️ Apagar todos os dados** e comece de verdade.

**Opção B — Direto ao trabalho:** pule para o passo 3.

## 3️⃣ Cadastre seu primeiro tutor (dono do pet)

1. Menu **👤 Tutores** → abra **➕ Cadastrar novo tutor**;
2. Preencha pelo menos o **nome**; telefone/WhatsApp é muito útil (serve para os lembretes 📲);
3. **💾 Salvar tutor**.

## 4️⃣ Cadastre o primeiro pet

1. Menu **🐾 Pets** → **➕ Cadastrar novo pet**;
2. Escolha o **tutor**, dê o **nome**, espécie, raça, nascimento etc.;
3. **💾 Salvar pet** — a idade é calculada automaticamente.

## 5️⃣ Fluxo do dia a dia (o ciclo básico)

```
📅 Agendar → 🐾 Atender → 📋 Histórico → 💰 Cobrar → 💉 Vacina quando houver
```

1. **📅 Agenda → ➕ Novo agendamento**: marque a consulta (o app avisa se houver choque de horário);
2. Quando o cliente chegar: abra o dia na agenda e mude o status para **Confirmado**;
3. Ao terminar o atendimento: status **Concluído** + marque _"registrar também no histórico"_ — o sistema já cria o registro no prontuário;
4. **💰 Financeiro → ➕ Novo lançamento**: registre a receita da consulta (pode vincular ao pet);
5. Se aplicou vacina: **💉 Vacinas → ➕ Registrar vacina** com a data do próximo reforço — **o sistema te avisa automaticamente** quando estiver perto de vencer;
6. Recebeu um exame? **📎 Exames** → anexe o PDF/imagem ao pet.

## 6️⃣ Recursos que você vai amar

- **🏠 Início**: tudo que importa hoje — agenda, vacinas vencendo, saldo do mês;
- **📲 Lembretes**: na página Vacinas e na Agenda, um clique abre o WhatsApp do tutor com a mensagem pronta;
- **📄 Relatórios**: imprima em PDF a carteirinha de vacinação, o histórico do pet, o financeiro do mês ou a agenda do dia;
- **⬇️ CSV**: quase todas as listas exportam para Excel.

## 7️⃣ Equipe

- **🔐 Usuários** (só admin): crie um login para cada pessoa — Recepção, Veterinário(a) ou Administrador;
- Cada um entra com seu login; suas ações ficam registradas com o próprio usuário ativo.

## 8️⃣ Seus dados estão seguros?

- Os dados ficam no arquivo `vetclinic.db` (modo 💾 Local) — faça cópia dele de tempos em tempos como backup;
- Para acessar de vários computadores/celulares: configure a **☁️ Nuvem** (Turso, grátis) — veja o README.md;
- Para deixar o app na internet 24h: veja o **DEPLOY.md**.

---
💡 **Dica de ouro:** cadastre sempre o **WhatsApp do tutor com DDD** no cadastro do tutor —
é o que alimenta os botões de lembrete 📲 e os alertas de vacinação!
