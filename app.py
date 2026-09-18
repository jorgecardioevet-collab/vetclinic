# -*- coding: utf-8 -*-
"""
CARDIOEVET — Sistema de gestão para clínica veterinária
Módulos: Início, Agenda, Vacinas, Tutores, Pets, Histórico, Exames, Financeiro e Relatórios
Banco de dados: SQLite local (padrão) ou ☁️ Turso — configure na página "Nuvem".
Execute com:  streamlit run app.py
"""

import base64
import hashlib
import io
import json
import os
import secrets
import sqlite3
import urllib.parse
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st
from fpdf import FPDF

import dbcloud

DB_PATH = "vetclinic.db"

ESPECIES = ["Cachorro", "Gato", "Ave", "Coelho", "Roedor", "Réptil", "Peixe", "Outro"]
SEXOS = ["Macho", "Fêmea"]
TIPOS_ATENDIMENTO = ["Consulta", "Vacina", "Exame", "Cirurgia", "Retorno", "Emergência", "Outro"]
TIPOS_AGENDAMENTO = ["Consulta", "Vacina", "Retorno", "Exame", "Cirurgia", "Banho/Tosa", "Outro"]
STATUS_AGENDAMENTO = ["Agendado", "Confirmado", "Concluído", "Faltou", "Cancelado"]
STATUS_EMOJI = {
    "Agendado": "🗓️ Agendado",
    "Confirmado": "✅ Confirmado",
    "Concluído": "🟢 Concluído",
    "Faltou": "⚠️ Faltou",
    "Cancelado": "❌ Cancelado",
}
CATEGORIAS = {
    "Receita": ["Consulta", "Vacina", "Exame", "Cirurgia", "Banho/Tosa", "Produtos", "Outros"],
    "Despesa": ["Medicamentos", "Produtos", "Equipamentos", "Salários", "Aluguel", "Impostos", "Outros"],
}
FORMAS_PAGAMENTO = ["PIX", "Dinheiro", "Cartão de crédito", "Cartão de débito", "Boleto", "Outro"]
SUGESTOES_VACINAS = {
    "Cachorro": "V10/V8 (múltipla), Antirrábica, Giárdia, Leishmaniose, Tosse dos canis",
    "Gato": "V4/V5 (múltipla), Antirrábica, FeLV",
}

# Serviços iniciais sugeridos (criados na 1ª vez que abrir o Financeiro — preços editáveis)
SERVICOS_SEED = [
    ("Consulta clínica", "Consulta", 180.0),
    ("Retorno (reavaliação)", "Consulta", 90.0),
    ("Ecocardiograma (ECO)", "Exame", 450.0),
    ("Eletrocardiograma (ECG)", "Exame", 150.0),
    ("Holter 24h", "Exame", 550.0),
    ("MAPA (pressão ambulatorial)", "Exame", 500.0),
    ("Raio-X de tórax", "Exame", 250.0),
    ("Ultrassom abdominal", "Exame", 350.0),
    ("Hemograma completo", "Exame", 90.0),
    ("Bioquímica sérica", "Exame", 120.0),
    ("Vacina múltipla", "Vacina", 130.0),
    ("Vacina antirrábica", "Vacina", 90.0),
    ("Microchip", "Outros", 180.0),
    ("Atestado sanitário", "Outros", 80.0),
    ("Castração", "Cirurgia", 900.0),
]


def _seed_servicos():
    """Insere os serviços sugeridos na primeira vez (tabela vazia)."""
    try:
        if int(qdf("SELECT COUNT(*) c FROM servicos").iloc[0]["c"]) == 0:
            for nome, cat, preco in SERVICOS_SEED:
                run("INSERT INTO servicos (nome, categoria, preco) VALUES (?,?,?)", (nome, cat, preco))
    except Exception:
        pass

# --------------------------------------------------------------------------- #
#  Banco de dados
# --------------------------------------------------------------------------- #

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tutores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    telefone    TEXT,
    email       TEXT,
    cpf         TEXT,
    endereco    TEXT,
    observacoes TEXT,
    criado_em   TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS pets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tutor_id    INTEGER NOT NULL REFERENCES tutores(id) ON DELETE CASCADE,
    nome        TEXT NOT NULL,
    especie     TEXT,
    raca        TEXT,
    sexo        TEXT,
    nascimento  TEXT,          -- AAAA-MM-DD
    peso        REAL,
    cor         TEXT,
    microchip   TEXT,
    castrado    INTEGER DEFAULT 0,
    observacoes TEXT,
    criado_em   TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS historico (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id      INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    data        TEXT NOT NULL, -- AAAA-MM-DD
    tipo        TEXT,
    veterinario TEXT,
    peso_kg     REAL,
    descricao   TEXT,
    criado_em   TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS agendamentos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id      INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    data        TEXT NOT NULL, -- AAAA-MM-DD
    hora        TEXT NOT NULL, -- HH:MM
    tipo        TEXT,
    veterinario TEXT,
    motivo      TEXT,
    status      TEXT DEFAULT 'Agendado',
    criado_em   TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS vacinas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id         INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    vacina         TEXT NOT NULL,
    data_aplicacao TEXT NOT NULL, -- AAAA-MM-DD
    proxima_dose   TEXT,          -- AAAA-MM-DD ou NULL (dose única)
    veterinario    TEXT,
    lote           TEXT,
    observacao     TEXT,
    criado_em      TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS lancamentos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    data            TEXT NOT NULL, -- AAAA-MM-DD
    tipo            TEXT NOT NULL, -- Receita | Despesa
    categoria       TEXT,
    descricao       TEXT,
    valor           REAL NOT NULL,
    forma_pagamento TEXT,
    pet_id          INTEGER REFERENCES pets(id) ON DELETE SET NULL,
    criado_em       TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS usuarios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario    TEXT UNIQUE NOT NULL,
    nome       TEXT,
    senha_hash TEXT NOT NULL,
    papel      TEXT DEFAULT 'recepcao',
    criado_em  TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS anexos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id     INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    nome       TEXT,
    descricao  TEXT,
    mime       TEXT,
    tamanho    INTEGER,
    dados      BLOB,
    criado_em  TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor BLOB
);

CREATE TABLE IF NOT EXISTS servicos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL,
    categoria  TEXT,
    preco      REAL DEFAULT 0,
    ativo      INTEGER DEFAULT 1,
    criado_em  TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS laudos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id       INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    numero       INTEGER DEFAULT 0,
    data         TEXT NOT NULL,
    tipo         TEXT NOT NULL,              -- 'abdominal' ou 'eco'
    dados        TEXT NOT NULL DEFAULT '{}', -- JSON: descrições por órgão / medidas
    conclusao    TEXT DEFAULT '',
    recomendacoes TEXT DEFAULT '',
    veterinario  TEXT DEFAULT '',
    criado_em    TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS laudo_imagens (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    laudo_id  INTEGER NOT NULL REFERENCES laudos(id) ON DELETE CASCADE,
    ordem     INTEGER DEFAULT 0,
    legenda   TEXT DEFAULT '',
    dados     BLOB,
    criado_em TEXT DEFAULT (datetime('now', 'localtime'))
);
"""


def _init_db_local():
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def _init_db_nuvem():
    url, token = config_nuvem()
    for stmt in (s.strip() for s in SCHEMA_SQL.split(";") if s.strip()):
        dbcloud.executar(url, token, stmt)


def init_db():
    if nuvem_ativa():
        try:
            _init_db_nuvem()
        except Exception as e:
            st.error(f"☁️ Não foi possível conectar ao banco em nuvem: {e}")
            st.info(
                "Verifique a URL e o token na página **☁️ Nuvem**. "
                "Para voltar ao modo local, apague o arquivo `db_config.json` e recarregue o app."
            )
            st.stop()
    else:
        _init_db_local()
    garantir_admin()


# --------------------------------------------------------------------------- #
#  Backend de dados: 💾 SQLite local  ou  ☁️ Turso (SQLite na nuvem)
# --------------------------------------------------------------------------- #

CONFIG_PATH = "db_config.json"


def normalizar_url_nuvem(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    return url.rstrip("/")


def config_nuvem() -> tuple:
    """Lê as credenciais da nuvem: variáveis de ambiente → st.secrets → db_config.json."""
    url = os.environ.get("TURSO_DATABASE_URL", "")
    token = os.environ.get("TURSO_AUTH_TOKEN", "")
    if not url:
        try:
            url = str(st.secrets.get("TURSO_DATABASE_URL", "") or "")
            token = str(st.secrets.get("TURSO_AUTH_TOKEN", "") or "")
        except Exception:
            url, token = "", ""
    if not url and os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            url = str(cfg.get("url", "") or "")
            token = str(cfg.get("token", "") or "")
        except Exception:
            url, token = "", ""
    return normalizar_url_nuvem(url), (token or "").strip()


def nuvem_ativa() -> bool:
    url, token = config_nuvem()
    return bool(url and token)


def salvar_config_nuvem(url: str, token: str):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"url": normalizar_url_nuvem(url), "token": token.strip()}, f)


def _cloud_exec(sql: str, params: tuple = ()):
    url, token = config_nuvem()
    try:
        return dbcloud.executar(url, token, sql, params)
    except Exception as e:
        st.error(f"☁️ Erro ao acessar o banco em nuvem: {e}")
        st.stop()


def qdf(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Executa SELECT e devolve um DataFrame (nuvem ou local, conforme configuração)."""
    if nuvem_ativa():
        cols, rows, _ = _cloud_exec(sql, params)
        return pd.DataFrame(rows, columns=cols)
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def run(sql: str, params: tuple = ()):
    """Executa INSERT/UPDATE/DELETE (nuvem ou local, conforme configuração)."""
    if nuvem_ativa():
        return _cloud_exec(sql, params)[2]
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur


def qdf_local(sql: str, params: tuple = ()) -> pd.DataFrame:
    """SELECT forçado no banco LOCAL (usado na migração para a nuvem)."""
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def get_config(chave: str, padrao=None):
    """Lê um valor da tabela config (funciona no modo local e no modo nuvem)."""
    try:
        df = qdf("SELECT valor FROM config WHERE chave = ?", (chave,))
        if df.empty:
            return padrao
        val = df.iloc[0]["valor"]
        return padrao if val is None else val
    except Exception:
        return padrao


def set_config(chave: str, valor):
    """Grava (cria/atualiza) um valor na tabela config."""
    run(
        "INSERT INTO config (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, valor),
    )


# --------------------------------------------------------------------------- #
#  Utilidades
# --------------------------------------------------------------------------- #

def idade_str(nasc: str | None) -> str:
    if not nasc:
        return "—"
    try:
        d = datetime.strptime(nasc, "%Y-%m-%d").date()
    except ValueError:
        return "—"
    hoje = date.today()
    if d > hoje:
        return "—"
    meses_total = (hoje.year - d.year) * 12 + hoje.month - d.month - (1 if hoje.day < d.day else 0)
    if meses_total >= 12:
        anos, meses = divmod(meses_total, 12)
        txt = f"{anos} ano{'s' if anos > 1 else ''}"
        if meses:
            txt += f" e {meses} {'meses' if meses > 1 else 'mês'}"
        return txt
    if meses_total >= 1:
        return f"{meses_total} {'meses' if meses_total > 1 else 'mês'}"
    dias = (hoje - d).days
    return f"{dias} dia{'s' if dias != 1 else ''}"


def fmt_data(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def botao_csv(df: pd.DataFrame, nome_arquivo: str, label: str = "⬇️ Baixar CSV"):
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(label, csv, nome_arquivo, "text/csv", use_container_width=False)


def like(termo: str) -> str:
    return f"%{termo.strip()}%"


def parse_date(s) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def fmt_moeda(v) -> str:
    try:
        s = f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "R$ 0,00"
    return "R$ " + s.replace(",", " ").replace(".", ",").replace(" ", ".")


def situacao_vacina(prox_dose) -> tuple:
    """Devolve (texto, emoji) da situação do reforço da vacina."""
    alvo = parse_date(prox_dose)
    if alvo is None:
        return ("Dose única", "⚪")
    dias = (alvo - date.today()).days
    if dias < 0:
        return (f"Vencida há {-dias} dia(s)", "🔴")
    if dias == 0:
        return ("Vence hoje", "🟠")
    if dias <= 15:
        return (f"Vence em {dias} dia(s)", "🟡")
    return ("Em dia", "🟢")


_CHARS_PDF = {
    "—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "•": "-", "→": "->",
}


def pdf_san(s) -> str:
    """Sanitiza texto para as fontes padrão do PDF (latin-1)."""
    out = str(s if s is not None else "")
    for a, b in _CHARS_PDF.items():
        out = out.replace(a, b)
    return out.encode("latin-1", "replace").decode("latin-1")


# --------------------------------------------------------------------------- #
#  Autenticação e lembretes
# --------------------------------------------------------------------------- #

def hash_senha(senha: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 60000)
    return f"{salt}:{dk.hex()}"


def verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        salt, gravado = armazenado.split(":")
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 60000)
    return secrets.compare_digest(dk.hex(), gravado)


def garantir_admin():
    """Cria o usuário admin padrão na primeira execução."""
    if qdf("SELECT COUNT(*) c FROM usuarios").iloc[0]["c"] == 0:
        run(
            "INSERT INTO usuarios (usuario, nome, senha_hash, papel) VALUES (?,?,?,?)",
            ("admin", "Administrador", hash_senha("admin123"), "admin"),
        )


def link_whatsapp(telefone: str, mensagem: str) -> str:
    """Monta link wa.me com mensagem pronta (retorna '' se não houver telefone)."""
    num = "".join(c for c in (telefone or "") if c.isdigit())
    if not num:
        return ""
    if not num.startswith("55"):
        num = "55" + num
    return f"https://wa.me/{num}?text={urllib.parse.quote(mensagem)}"


def link_email(email: str, assunto: str, corpo: str) -> str:
    """Monta link mailto: com assunto e corpo prontos."""
    if not email or "@" not in email:
        return ""
    q = urllib.parse.urlencode({"subject": assunto, "body": corpo})
    return f"mailto:{email.strip()}?{q}"


# --------------------------------------------------------------------------- #
#  Página: Início
# --------------------------------------------------------------------------- #

def pagina_inicio():
    st.header("🏠 Visão geral")

    hoje = date.today()
    mes_atual = hoje.strftime("%Y-%m")

    n_tutores = qdf("SELECT COUNT(*) c FROM tutores").iloc[0]["c"]
    n_pets = qdf("SELECT COUNT(*) c FROM pets").iloc[0]["c"]
    n_hist = qdf("SELECT COUNT(*) c FROM historico").iloc[0]["c"]
    n_mes = qdf(
        "SELECT COUNT(*) c FROM historico WHERE strftime('%Y-%m', data) = ?",
        (mes_atual,),
    ).iloc[0]["c"]
    n_agenda_hoje = qdf(
        "SELECT COUNT(*) c FROM agendamentos WHERE data = ? AND status != 'Cancelado'",
        (hoje.isoformat(),),
    ).iloc[0]["c"]
    n_vencidas = qdf(
        """SELECT COUNT(*) c FROM vacinas
           WHERE proxima_dose IS NOT NULL AND proxima_dose != '' AND proxima_dose < ?""",
        (hoje.isoformat(),),
    ).iloc[0]["c"]
    n_a_vencer = qdf(
        """SELECT COUNT(*) c FROM vacinas
           WHERE proxima_dose >= ? AND proxima_dose <= date('now', 'localtime', '+15 days')""",
        (hoje.isoformat(),),
    ).iloc[0]["c"]
    receitas = float(qdf(
        "SELECT COALESCE(SUM(valor),0) s FROM lancamentos WHERE tipo='Receita' AND substr(data,1,7)=?",
        (mes_atual,),
    ).iloc[0]["s"])
    despesas = float(qdf(
        "SELECT COALESCE(SUM(valor),0) s FROM lancamentos WHERE tipo='Despesa' AND substr(data,1,7)=?",
        (mes_atual,),
    ).iloc[0]["s"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👤 Tutores", n_tutores)
    c2.metric("🐾 Pets", n_pets)
    c3.metric("📅 Compromissos hoje", n_agenda_hoje)
    c4.metric("💰 Saldo do mês", fmt_moeda(receitas - despesas))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("📋 Atendimentos", n_hist)
    c6.metric("🗓️ Atendimentos no mês", n_mes)
    c7.metric("🔴 Vacinas vencidas", n_vencidas)
    c8.metric("🟡 Reforços em 15 dias", n_a_vencer)

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Pets por espécie")
        df = qdf(
            """
            SELECT COALESCE(NULLIF(especie,''), 'Não informada') AS especie, COUNT(*) AS quantidade
            FROM pets GROUP BY especie ORDER BY quantidade DESC
            """
        )
        if df.empty:
            st.info("Nenhum pet cadastrado ainda.")
        else:
            st.bar_chart(df.set_index("especie"))

    with col_b:
        st.subheader("🎂 Aniversariantes do mês")
        df = qdf(
            """
            SELECT p.nome AS pet, p.especie, t.nome AS tutor, p.nascimento
            FROM pets p JOIN tutores t ON t.id = p.tutor_id
            WHERE p.nascimento IS NOT NULL AND p.nascimento != ''
              AND strftime('%m', p.nascimento) = ?
            ORDER BY strftime('%d', p.nascimento)
            """,
            (date.today().strftime("%m"),),
        )
        if df.empty:
            st.info("Nenhum pet faz aniversário este mês.")
        else:
            df["Dia"] = df["nascimento"].str[8:10].astype(int)
            st.dataframe(
                df[["Dia", "pet", "especie", "tutor"]],
                hide_index=True,
                use_container_width=True,
                column_config={"pet": "Pet", "especie": "Espécie", "tutor": "Tutor"},
            )

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("📅 Agenda de hoje")
        df = qdf(
            """SELECT a.hora, p.nome AS pet, t.nome AS tutor, a.tipo, a.status
               FROM agendamentos a
               JOIN pets p ON p.id = a.pet_id
               JOIN tutores t ON t.id = p.tutor_id
               WHERE a.data = ? AND a.status != 'Cancelado'
               ORDER BY a.hora""",
            (hoje.isoformat(),),
        )
        if df.empty:
            st.info("Nenhum compromisso hoje.")
        else:
            df["status"] = df["status"].map(lambda s: STATUS_EMOJI.get(s, s))
            st.dataframe(
                df, hide_index=True, use_container_width=True,
                column_config={"hora": "Hora", "pet": "Pet", "tutor": "Tutor",
                               "tipo": "Tipo", "status": "Status"},
            )

    with col_b:
        st.subheader("💉 Alertas de vacinas")
        df = qdf(
            """SELECT v.vacina, v.proxima_dose, p.nome AS pet, t.nome AS tutor
               FROM vacinas v
               JOIN pets p ON p.id = v.pet_id
               JOIN tutores t ON t.id = p.tutor_id
               WHERE v.proxima_dose IS NOT NULL AND v.proxima_dose != ''
                 AND v.proxima_dose <= date('now', 'localtime', '+15 days')
               ORDER BY v.proxima_dose
               LIMIT 8"""
        )
        if df.empty:
            st.success("Nenhuma vacina vencida ou a vencer em 15 dias. ✅")
        else:
            df["Situação"] = df["proxima_dose"].map(
                lambda d: f"{situacao_vacina(d)[1]} {situacao_vacina(d)[0]}"
            )
            df["Próx. dose"] = df["proxima_dose"].map(fmt_data)
            st.dataframe(
                df[["Próx. dose", "pet", "tutor", "vacina", "Situação"]],
                hide_index=True, use_container_width=True,
                column_config={"pet": "Pet", "tutor": "Tutor", "vacina": "Vacina"},
            )

    st.divider()
    st.subheader("🕒 Últimos atendimentos")
    df = qdf(
        """
        SELECT h.data, p.nome AS pet, t.nome AS tutor, h.tipo, h.veterinario, h.descricao
        FROM historico h
        JOIN pets p    ON p.id = h.pet_id
        JOIN tutores t ON t.id = p.tutor_id
        ORDER BY h.data DESC, h.id DESC
        LIMIT 8
        """
    )
    if df.empty:
        st.info("Nenhum atendimento registrado ainda. Comece cadastrando um tutor e um pet!")
    else:
        df["data"] = df["data"].map(fmt_data)
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "data": "Data",
                "pet": "Pet",
                "tutor": "Tutor",
                "tipo": "Tipo",
                "veterinario": "Veterinário(a)",
                "descricao": "Descrição",
            },
        )


# --------------------------------------------------------------------------- #
#  Página: Tutores
# --------------------------------------------------------------------------- #

def pagina_tutores():
    st.header("👤 Tutores")

    busca = st.text_input("🔎 Buscar", placeholder="Nome, telefone, e-mail ou CPF…", key="busca_tutor")

    df = qdf(
        """
        SELECT t.id, t.nome, t.telefone, t.email, t.cpf, t.endereco,
               (SELECT COUNT(*) FROM pets p WHERE p.tutor_id = t.id) AS pets
        FROM tutores t
        WHERE t.nome LIKE ? OR t.telefone LIKE ? OR t.email LIKE ? OR t.cpf LIKE ?
        ORDER BY t.nome
        """,
        (like(busca),) * 4,
    )

    st.caption(f"{len(df)} tutor(es) encontrado(s)")
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "id": st.column_config.NumberColumn("#", width="small"),
            "nome": "Nome",
            "telefone": "Telefone",
            "email": "E-mail",
            "cpf": "CPF",
            "endereco": "Endereço",
            "pets": st.column_config.NumberColumn("Pets", width="small"),
        },
    )
    if not df.empty:
        botao_csv(df, "tutores.csv", "⬇️ Baixar lista em CSV")

    # ---- Cadastrar ---------------------------------------------------------- #
    with st.expander("➕ Cadastrar novo tutor", expanded=df.empty and not busca):
        with st.form("form_novo_tutor", clear_on_submit=True):
            nome = st.text_input("Nome completo *")
            c1, c2 = st.columns(2)
            telefone = c1.text_input("Telefone / WhatsApp")
            email = c2.text_input("E-mail")
            c3, c4 = st.columns(2)
            cpf = c3.text_input("CPF")
            endereco = c4.text_input("Endereço")
            obs = st.text_area("Observações")
            if st.form_submit_button("💾 Salvar tutor", type="primary"):
                if not nome.strip():
                    st.error("O nome do tutor é obrigatório.")
                else:
                    run(
                        "INSERT INTO tutores (nome, telefone, email, cpf, endereco, observacoes) VALUES (?,?,?,?,?,?)",
                        (nome.strip(), telefone.strip(), email.strip(), cpf.strip(), endereco.strip(), obs.strip()),
                    )
                    st.success(f"Tutor **{nome.strip()}** cadastrado com sucesso!")
                    st.rerun()

    # ---- Editar / excluir ---------------------------------------------------- #
    todos = qdf("SELECT * FROM tutores ORDER BY nome")
    if todos.empty:
        return

    with st.expander("✏️ Editar ou excluir tutor"):
        opcoes = {f"{r['nome']} (#{r['id']})": r["id"] for _, r in todos.iterrows()}
        escolha = st.selectbox("Selecione o tutor", list(opcoes.keys()), key="sel_edit_tutor")
        tid = opcoes[escolha]
        row = qdf("SELECT * FROM tutores WHERE id = ?", (tid,)).iloc[0]

        with st.form("form_edit_tutor"):
            nome = st.text_input("Nome completo *", value=row["nome"])
            c1, c2 = st.columns(2)
            telefone = c1.text_input("Telefone / WhatsApp", value=row["telefone"] or "")
            email = c2.text_input("E-mail", value=row["email"] or "")
            c3, c4 = st.columns(2)
            cpf = c3.text_input("CPF", value=row["cpf"] or "")
            endereco = c4.text_input("Endereço", value=row["endereco"] or "")
            obs = st.text_area("Observações", value=row["observacoes"] or "")
            if st.form_submit_button("💾 Salvar alterações", type="primary"):
                if not nome.strip():
                    st.error("O nome do tutor é obrigatório.")
                else:
                    run(
                        "UPDATE tutores SET nome=?, telefone=?, email=?, cpf=?, endereco=?, observacoes=? WHERE id=?",
                        (nome.strip(), telefone.strip(), email.strip(), cpf.strip(), endereco.strip(), obs.strip(), tid),
                    )
                    st.success("Cadastro atualizado!")
                    st.rerun()

        n_pets = qdf("SELECT COUNT(*) c FROM pets WHERE tutor_id = ?", (tid,)).iloc[0]["c"]
        st.divider()
        st.markdown("**🗑️ Excluir tutor**")
        if n_pets:
            st.warning(
                f"⚠️ Este tutor possui **{n_pets} pet(s)** cadastrado(s). "
                "Ao excluir o tutor, os pets e todo o histórico deles também serão removidos."
            )
        confirma = st.checkbox("Confirmo que desejo excluir este tutor", key=f"conf_tutor_{tid}")
        if st.button("Excluir tutor", disabled=not confirma, key=f"del_tutor_{tid}"):
            run("DELETE FROM tutores WHERE id = ?", (tid,))
            st.success(f"Tutor **{row['nome']}** excluído.")
            st.rerun()


# --------------------------------------------------------------------------- #
#  Página: Pets
# --------------------------------------------------------------------------- #

def pagina_pets():
    st.header("🐾 Pets")

    tutores = qdf("SELECT id, nome FROM tutores ORDER BY nome")

    c1, c2, c3 = st.columns([2, 1, 1])
    busca = c1.text_input("🔎 Buscar", placeholder="Nome do pet, raça ou microchip…", key="busca_pet")
    f_esp = c2.multiselect("Espécie", ESPECIES, key="filtro_especie")
    f_tutor = c3.selectbox(
        "Tutor",
        ["Todos"] + [f"{r['nome']} (#{r['id']})" for _, r in tutores.iterrows()],
        key="filtro_tutor",
    )

    sql = """
        SELECT p.id, p.nome, p.especie, p.raca, p.sexo, p.nascimento, p.peso,
               p.cor, p.microchip, p.castrado, t.nome AS tutor, p.tutor_id
        FROM pets p JOIN tutores t ON t.id = p.tutor_id
        WHERE (p.nome LIKE ? OR p.raca LIKE ? OR p.microchip LIKE ?)
    """
    params = [like(busca)] * 3
    if f_esp:
        sql += f" AND p.especie IN ({','.join('?' * len(f_esp))})"
        params += f_esp
    if f_tutor != "Todos":
        sql += " AND p.tutor_id = ?"
        params.append(int(f_tutor.split("#")[-1].rstrip(")")))
    sql += " ORDER BY p.nome"

    df = qdf(sql, tuple(params))
    if not df.empty:
        df["idade"] = df["nascimento"].map(idade_str)
        df["castrado"] = df["castrado"].map({0: "Não", 1: "Sim"})

    st.caption(f"{len(df)} pet(s) encontrado(s)")
    st.dataframe(
        df[["id", "nome", "especie", "raca", "sexo", "idade", "peso", "castrado", "tutor"]]
        if not df.empty else df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "id": st.column_config.NumberColumn("#", width="small"),
            "nome": "Nome",
            "especie": "Espécie",
            "raca": "Raça",
            "sexo": "Sexo",
            "idade": "Idade",
            "peso": st.column_config.NumberColumn("Peso (kg)", format="%.2f"),
            "castrado": "Castrado",
            "tutor": "Tutor",
        },
    )
    if not df.empty:
        botao_csv(df.drop(columns=["tutor_id"]), "pets.csv", "⬇️ Baixar lista em CSV")

    # ---- Cadastrar ---------------------------------------------------------- #
    with st.expander("➕ Cadastrar novo pet", expanded=tutores.empty is False and df.empty and not busca and not f_esp):
        if tutores.empty:
            st.info("Cadastre primeiro um **tutor** na aba 👤 Tutores para poder adicionar pets.")
        else:
            with st.form("form_novo_pet", clear_on_submit=True):
                opcoes_tutor = {f"{r['nome']} (#{r['id']})": r["id"] for _, r in tutores.iterrows()}
                tutor_lbl = st.selectbox("Tutor *", list(opcoes_tutor.keys()))
                nome = st.text_input("Nome do pet *")
                c1, c2, c3 = st.columns(3)
                especie = c1.selectbox("Espécie", ESPECIES)
                raca = c2.text_input("Raça")
                sexo = c3.selectbox("Sexo", SEXOS)
                c4, c5, c6 = st.columns(3)
                nasc = c4.date_input(
                    "Data de nascimento",
                    value=None,
                    min_value=date(1990, 1, 1),
                    max_value=date.today(),
                    format="DD/MM/YYYY",
                )
                peso = c5.number_input("Peso (kg)", min_value=0.0, value=None, step=0.1, format="%.2f")
                cor = c6.text_input("Cor / pelagem")
                c7, c8 = st.columns(2)
                microchip = c7.text_input("Nº do microchip")
                castrado = c8.checkbox("Castrado(a)")
                obs = st.text_area("Observações (alergias, comportamento, etc.)")
                if st.form_submit_button("💾 Salvar pet", type="primary"):
                    if not nome.strip():
                        st.error("O nome do pet é obrigatório.")
                    else:
                        run(
                            """INSERT INTO pets
                               (tutor_id, nome, especie, raca, sexo, nascimento, peso, cor, microchip, castrado, observacoes)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                opcoes_tutor[tutor_lbl], nome.strip(), especie, raca.strip(), sexo,
                                nasc.isoformat() if nasc else None, peso, cor.strip(),
                                microchip.strip(), 1 if castrado else 0, obs.strip(),
                            ),
                        )
                        st.success(f"Pet **{nome.strip()}** cadastrado com sucesso!")
                        st.rerun()

    # ---- Editar / excluir ---------------------------------------------------- #
    todos = qdf(
        """SELECT p.*, t.nome AS tutor_nome FROM pets p
           JOIN tutores t ON t.id = p.tutor_id ORDER BY p.nome"""
    )
    if todos.empty:
        return

    with st.expander("✏️ Editar ou excluir pet"):
        opcoes = {f"{r['nome']} — {r['tutor_nome']} (#{r['id']})": r["id"] for _, r in todos.iterrows()}
        escolha = st.selectbox("Selecione o pet", list(opcoes.keys()), key="sel_edit_pet")
        pid = opcoes[escolha]
        row = todos[todos["id"] == pid].iloc[0]

        with st.form("form_edit_pet"):
            opcoes_tutor = {f"{r['nome']} (#{r['id']})": r["id"] for _, r in tutores.iterrows()}
            tutor_ids = list(opcoes_tutor.values())
            tutor_lbl = st.selectbox(
                "Tutor *", list(opcoes_tutor.keys()), index=tutor_ids.index(int(row["tutor_id"]))
            )
            nome = st.text_input("Nome do pet *", value=row["nome"])
            c1, c2, c3 = st.columns(3)
            especie = c1.selectbox(
                "Espécie", ESPECIES, index=ESPECIES.index(row["especie"]) if row["especie"] in ESPECIES else 0
            )
            raca = c2.text_input("Raça", value=row["raca"] or "")
            sexo = c3.selectbox(
                "Sexo", SEXOS, index=SEXOS.index(row["sexo"]) if row["sexo"] in SEXOS else 0
            )
            c4, c5, c6 = st.columns(3)
            try:
                nasc_val = datetime.strptime(row["nascimento"], "%Y-%m-%d").date() if row["nascimento"] else None
            except ValueError:
                nasc_val = None
            nasc = c4.date_input(
                "Data de nascimento",
                value=nasc_val,
                min_value=date(1990, 1, 1),
                max_value=date.today(),
                format="DD/MM/YYYY",
            )
            peso = c5.number_input(
                "Peso (kg)", min_value=0.0, value=float(row["peso"]) if pd.notna(row["peso"]) else None,
                step=0.1, format="%.2f",
            )
            cor = c6.text_input("Cor / pelagem", value=row["cor"] or "")
            c7, c8 = st.columns(2)
            microchip = c7.text_input("Nº do microchip", value=row["microchip"] or "")
            castrado = c8.checkbox("Castrado(a)", value=bool(row["castrado"]))
            obs = st.text_area("Observações", value=row["observacoes"] or "")
            if st.form_submit_button("💾 Salvar alterações", type="primary"):
                if not nome.strip():
                    st.error("O nome do pet é obrigatório.")
                else:
                    run(
                        """UPDATE pets SET tutor_id=?, nome=?, especie=?, raca=?, sexo=?, nascimento=?,
                           peso=?, cor=?, microchip=?, castrado=?, observacoes=? WHERE id=?""",
                        (
                            opcoes_tutor[tutor_lbl], nome.strip(), especie, raca.strip(), sexo,
                            nasc.isoformat() if nasc else None, peso, cor.strip(),
                            microchip.strip(), 1 if castrado else 0, obs.strip(), pid,
                        ),
                    )
                    st.success("Cadastro atualizado!")
                    st.rerun()

        n_hist = qdf("SELECT COUNT(*) c FROM historico WHERE pet_id = ?", (pid,)).iloc[0]["c"]
        st.divider()
        st.markdown("**🗑️ Excluir pet**")
        if n_hist:
            st.warning(f"⚠️ Este pet possui **{n_hist} registro(s)** de atendimento que também serão excluídos.")
        confirma = st.checkbox("Confirmo que desejo excluir este pet", key=f"conf_pet_{pid}")
        if st.button("Excluir pet", disabled=not confirma, key=f"del_pet_{pid}"):
            run("DELETE FROM pets WHERE id = ?", (pid,))
            st.success(f"Pet **{row['nome']}** excluído.")
            st.rerun()

    # ----------------------------------------------------------------- #
    #  📜 Emitir receita (simples ou controlada)
    # ----------------------------------------------------------------- #
    pid = pagina_receita_pet(df, tutores)


# --------------------------------------------------------------------------- #
#  Receitas (simples e controlada)
# --------------------------------------------------------------------------- #

def gerar_pdf_receita(num: int, controlada: bool, pet, meds, obs: str,
                      data_iso: str, cidade: str) -> bytes:
    """Gera receituário (simples ou de controle especial) em PDF."""
    import re
    ano = datetime.strptime(data_iso, "%Y-%m-%d").year
    if controlada:
        pdf = novo_pdf("RECEITA DE CONTROLE ESPECIAL",
                       subtitulo=f"Nº {num:04d}/{ano}  ·  Portaria SVS/MS nº 344/98")
    else:
        pdf = novo_pdf("Receituário Veterinário", subtitulo=f"Nº {num:04d}/{ano}")
    dados_pet(pdf, pet)

    if controlada:
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(22, 101, 96)
        pdf.cell(0, 6, "IDENTIFICAÇÃO DO COMPRADOR (TUTOR)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30)
        pdf_campo(pdf, "Nome:", pet["tutor"] or "—")
        if pet.get("cpf"):
            pdf_campo(pdf, "CPF:", pet["cpf"])
        if pet.get("endereco"):
            pdf_campo(pdf, "Endereço:", pet["endereco"])
        pdf.ln(2)
        if pet["nascimento"]:
            pass

    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(22, 101, 96)
    pdf.cell(0, 7, "MEDICAMENTO(S) PRESCRITO(S)" if controlada else "PRESCRIÇÃO",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30)
    for i, (nome, apres, qtd, poso) in enumerate(meds, 1):
        pdf.set_font("helvetica", "B", 10.5)
        linha1 = f"{i}. {nome}" + (f"  —  {apres}" if apres else "")
        pdf.multi_cell(0, 6, pdf_san(linha1), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "I", 9.5)
        pdf.set_text_color(70)
        if qtd:
            qtd_txt = str(qtd)
            if controlada:
                m = re.match(r"\s*(\d+)", qtd_txt)
                if m:
                    qtd_txt = f"{qtd_txt}  ({_ext_ate_999(int(m.group(1)))})"
            pdf.multi_cell(0, 5, pdf_san(f"     Quantidade: {qtd_txt}"), new_x="LMARGIN", new_y="NEXT")
        if poso:
            pdf.multi_cell(0, 5, pdf_san(f"     Uso: {poso}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30)
        pdf.ln(2)
    pdf.ln(2)

    if obs.strip():
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 6, "Orientações / Observações:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 9.5)
        pdf.multi_cell(0, 5, pdf_san(obs.strip()), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    if controlada:
        pdf.set_font("helvetica", "I", 8)
        pdf.set_text_color(150, 40, 40)
        pdf.multi_cell(0, 5, pdf_san(
            "Emitida em 2 vias — a farmácia DEVERÁ RETER a 1ª via, conforme a Portaria SVS/MS nº 344/98. "
            "É vedada a dispensação de medicamentos sujeitos a controle especial sem a apresentação desta receita."
        ), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30)
        pdf.ln(2)

    d = datetime.strptime(data_iso, "%Y-%m-%d")
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, pdf_san(f"{(cidade or 'Penha/SC')}, {d.day} de {meses[d.month - 1]} de {d.year}."),
             new_x="LMARGIN", new_y="NEXT")
    assinatura(pdf)
    return bytes(pdf.output())


def pagina_receita_pet(df, tutores):
    """Seção 📜 Emitir receita, exibida ao final da página de Pets."""
    if df.empty:
        return None
    st.divider()
    with st.expander("📜 Emitir receita (simples ou controlada)"):
        op = {f"{r['nome']} — {r['tutor']} (#{r['id']})": int(r["id"]) for _, r in df.iterrows()}
        sel = st.selectbox("Pet que receberá a receita", list(op.keys()), key="rec_pet_sel")
        pid = op[sel]
        tipo = st.radio("Tipo de receita", ["📄 Simples", "🔒 Controlada (Portaria 344/98)"],
                        horizontal=True, key="rec_tipo")
        ctrl = tipo.startswith("🔒")

        pet = qdf(
            """SELECT p.*, t.nome AS tutor, t.telefone, t.cpf, t.endereco
               FROM pets p JOIN tutores t ON t.id = p.tutor_id WHERE p.id = ?""",
            (pid,),
        ).iloc[0]

        if ctrl and (not pet["cpf"] or not pet["endereco"]):
            st.warning("⚠️ Receita controlada precisa de **CPF e endereço do tutor**. "
                       "Confira/complete abaixo (vale atualizar também no cadastro do tutor).")

        with st.form(f"form_receita_{pid}_{'c' if ctrl else 's'}"):
            meds = []
            st.caption("Itens da prescrição (preencha somente os necessários)")
            for i in range(4):
                c1, c2, c3 = st.columns([4, 3, 2])
                nm = c1.text_input(f"Medicamento {i + 1}", key=f"rec_nm{i}",
                                   placeholder="Ex.: Amoxicilina" if i == 0 else "")
                ap = c2.text_input(f"Apresentação {i + 1}", key=f"rec_ap{i}",
                                   placeholder="250 mg — comprimido" if i == 0 else "",
                                   label_visibility="visible")
                qd = c3.text_input(f"Qtd. {i + 1}", key=f"rec_qd{i}",
                                   placeholder="14 comp." if i == 0 else "")
                ps = st.text_area(f"Posologia {i + 1}", key=f"rec_ps{i}", height=48,
                                  placeholder="1 comp. via oral a cada 12h por 7 dias" if i == 0 else "")
                if nm.strip():
                    meds.append((nm.strip(), ap.strip(), qd.strip(), ps.strip()))
                st.markdown("")  # respiro visual

            if ctrl:
                c4, c5 = st.columns(2)
                t_cpf = c4.text_input("CPF do tutor *", value=pet["cpf"] or "")
                t_end = c5.text_input("Endereço do tutor *", value=pet["endereco"] or "")
            else:
                t_cpf = t_end = ""

            obs = st.text_area("Orientações / observações (opcional)", height=60)
            c6, c7 = st.columns(2)
            data_rec = c6.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            cid_rec = c7.text_input("Local (cidade/UF)",
                                    value=get_config("rec_cidade", "Penha/SC") or "Penha/SC")
            reg_hist = st.checkbox("Registrar também no histórico do pet", value=True)
            gerar = st.form_submit_button("📄 Gerar receita", type="primary")

        if gerar:
            if not meds:
                st.error("Informe pelo menos o **Medicamento 1** com seu uso.")
            elif ctrl and (not t_cpf.strip() or not t_end.strip()):
                st.error("Receita controlada exige **CPF e endereço do tutor**.")
            else:
                if ctrl:
                    pet = dict(pet)
                    pet["cpf"] = t_cpf.strip()
                    pet["endereco"] = t_end.strip()
                num = proximo_numero("receita_seq")
                set_config("rec_cidade", cid_rec.strip() or "Penha/SC")
                pdf_bytes = finalizar_pdf(gerar_pdf_receita(
                    num, ctrl, pet, meds, obs, data_rec.isoformat(), cid_rec.strip()))
                st.session_state["rec_pdf"] = pdf_bytes
                st.session_state["rec_num"] = num
                st.session_state["rec_pet"] = pet["nome"]
                if reg_hist:
                    resumo = "Receita" + (" de CONTROLE ESPECIAL" if ctrl else " simples") + \
                             f" nº {num:04d}/{data_rec.year} — " + \
                             "; ".join(f"{n} {a}".strip() for n, a, _, _ in meds)
                    vet = (get_config("carimbo_nome", "") or
                           st.session_state.usuario.get("nome", "")).strip()
                    run(
                        "INSERT INTO historico (pet_id, data, tipo, veterinario, descricao) VALUES (?,?,?,?,?)",
                        (pid, data_rec.isoformat(),
                         "Receita" + (" (controlada)" if ctrl else ""), vet, resumo[:480]),
                    )
                if ctrl and (not qdf("SELECT cpf FROM tutores WHERE id = ?", (pet["tutor_id"],)).iloc[0]["cpf"]):
                    run("UPDATE tutores SET cpf = COALESCE(cpf, ?), endereco = COALESCE(endereco, ?) WHERE id = ?",
                        (t_cpf.strip(), t_end.strip(), pet["tutor_id"]))
                st.success(f"✅ Receita nº {num:04d} gerada" +
                           (" e registrada no histórico!" if reg_hist else "!"))

        if st.session_state.get("rec_pdf"):
            st.download_button(
                f"⬇️ Baixar receita nº {st.session_state['rec_num']:04d} (PDF)",
                st.session_state["rec_pdf"],
                f"receita_{st.session_state['rec_num']:04d}_{st.session_state['rec_pet'].lower().replace(' ', '_')}.pdf",
                "application/pdf", type="primary")
            botao_imprimir_pdf(st.session_state["rec_pdf"],
                               f"receita_{st.session_state['rec_num']:04d}")
    return pid


# --------------------------------------------------------------------------- #
#  Página: Histórico de atendimentos
# --------------------------------------------------------------------------- #

def pagina_historico():
    st.header("📋 Histórico de atendimentos")

    pets = qdf(
        """SELECT p.id, p.nome, p.especie, p.raca, p.nascimento, t.nome AS tutor
           FROM pets p JOIN tutores t ON t.id = p.tutor_id ORDER BY p.nome"""
    )
    if pets.empty:
        st.info("Cadastre primeiro um **tutor** e um **pet** para registrar atendimentos.")
        return

    opcoes = {f"{r['nome']} — {r['tutor']} (#{r['id']})": r["id"] for _, r in pets.iterrows()}
    escolha = st.selectbox("Selecione o pet", list(opcoes.keys()))
    pid = opcoes[escolha]
    row = pets[pets["id"] == pid].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**🐾 {row['nome']}** ({row['especie'] or 'espécie não informada'})")
    c2.markdown(f"**Raça:** {row['raca'] or '—'}  |  **Idade:** {idade_str(row['nascimento'])}")
    c3.markdown(f"**Tutor:** {row['tutor']}")

    st.divider()
    st.subheader("➕ Registrar atendimento")
    with st.form("form_novo_atendimento", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data = c1.date_input(
            "Data *", value=date.today(), min_value=date(1990, 1, 1),
            max_value=date.today(), format="DD/MM/YYYY",
        )
        tipo = c2.selectbox("Tipo de atendimento", TIPOS_ATENDIMENTO)
        vet = c3.text_input("Veterinário(a) responsável")
        peso = c1.number_input("Peso no dia (kg) — opcional", min_value=0.0, value=None, step=0.1, format="%.2f")
        desc = st.text_area("Descrição / anotações *", placeholder="Ex.: Vacina antirrábica aplicada; retorno em 30 dias…")
        if st.form_submit_button("💾 Registrar", type="primary"):
            if not desc.strip():
                st.error("A descrição é obrigatória.")
            else:
                run(
                    "INSERT INTO historico (pet_id, data, tipo, veterinario, peso_kg, descricao) VALUES (?,?,?,?,?,?)",
                    (pid, data.isoformat(), tipo, vet.strip(), peso, desc.strip()),
                )
                st.success("Atendimento registrado!")
                st.rerun()

    st.divider()
    st.subheader("🗂️ Registros")
    df = qdf(
        "SELECT * FROM historico WHERE pet_id = ? ORDER BY data DESC, id DESC",
        (pid,),
    )
    if df.empty:
        st.info("Nenhum atendimento registrado para este pet ainda.")
        return

    df_show = df.copy()
    df_show["data"] = df_show["data"].map(fmt_data)
    st.dataframe(
        df_show[["data", "tipo", "veterinario", "peso_kg", "descricao"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "data": "Data",
            "tipo": "Tipo",
            "veterinario": "Veterinário(a)",
            "peso_kg": st.column_config.NumberColumn("Peso (kg)", format="%.2f"),
            "descricao": "Descrição",
        },
    )
    botao_csv(df_show[["data", "tipo", "veterinario", "peso_kg", "descricao"]],
              f"historico_{row['nome'].replace(' ', '_')}.csv", "⬇️ Baixar histórico em CSV")

    # ---- Histórico em PDF (para imprimir/baixar) ---------------------------- #
    if st.button("📄 Gerar histórico em PDF", key=f"gen_hist_{pid}"):
        with st.spinner("Gerando PDF do histórico…"):
            st.session_state[f"_histpdf_{pid}"] = finalizar_pdf(gerar_pdf_historico(pid))
    if st.session_state.get(f"_histpdf_{pid}"):
        st.download_button("⬇️ Baixar histórico em PDF", st.session_state[f"_histpdf_{pid}"],
                           f"historico_{row['nome'].lower().replace(' ', '_')}.pdf",
                           "application/pdf", type="primary", key=f"dl_hist_{pid}")
        botao_imprimir_pdf(st.session_state[f"_histpdf_{pid}"], f"histpet_{pid}")

    # ---- Editar / excluir registro ------------------------------------------ #
    with st.expander("✏️ Editar ou excluir um registro"):
        op_reg = {
            f"{fmt_data(r['data'])} — {r['tipo']} — {r['veterinario'] or 'sem vet.'} (#{r['id']})": r["id"]
            for _, r in df.iterrows()
        }
        sel = st.selectbox("Selecione o registro", list(op_reg.keys()), key="sel_edit_hist")
        hid = op_reg[sel]
        reg = df[df["id"] == hid].iloc[0]

        with st.form("form_edit_atendimento"):
            c1, c2, c3 = st.columns(3)
            try:
                data_val = datetime.strptime(reg["data"], "%Y-%m-%d").date()
            except ValueError:
                data_val = date.today()
            data = c1.date_input(
                "Data *", value=data_val, min_value=date(1990, 1, 1),
                max_value=date.today(), format="DD/MM/YYYY",
            )
            tipo = c2.selectbox(
                "Tipo de atendimento", TIPOS_ATENDIMENTO,
                index=TIPOS_ATENDIMENTO.index(reg["tipo"]) if reg["tipo"] in TIPOS_ATENDIMENTO else 0,
            )
            vet = c3.text_input("Veterinário(a) responsável", value=reg["veterinario"] or "")
            peso = c1.number_input(
                "Peso no dia (kg)", min_value=0.0,
                value=float(reg["peso_kg"]) if pd.notna(reg["peso_kg"]) else None,
                step=0.1, format="%.2f",
            )
            desc = st.text_area("Descrição / anotações *", value=reg["descricao"] or "")
            if st.form_submit_button("💾 Salvar alterações", type="primary"):
                if not desc.strip():
                    st.error("A descrição é obrigatória.")
                else:
                    run(
                        "UPDATE historico SET data=?, tipo=?, veterinario=?, peso_kg=?, descricao=? WHERE id=?",
                        (data.isoformat(), tipo, vet.strip(), peso, desc.strip(), hid),
                    )
                    st.success("Registro atualizado!")
                    st.rerun()

        st.markdown("**🗑️ Excluir registro**")
        confirma = st.checkbox("Confirmo que desejo excluir este registro", key=f"conf_hist_{hid}")
        if st.button("Excluir registro", disabled=not confirma, key=f"del_hist_{hid}"):
            run("DELETE FROM historico WHERE id = ?", (hid,))
            st.success("Registro excluído.")
            st.rerun()


# --------------------------------------------------------------------------- #
#  Página: Agenda
# --------------------------------------------------------------------------- #

def pagina_agenda():
    st.header("📅 Agenda de consultas")
    hoje = date.today()

    pets = qdf(
        """SELECT p.id, p.nome, t.nome AS tutor FROM pets p
           JOIN tutores t ON t.id = p.tutor_id ORDER BY p.nome"""
    )

    n_hoje = qdf(
        "SELECT COUNT(*) c FROM agendamentos WHERE data = ? AND status != 'Cancelado'",
        (hoje.isoformat(),),
    ).iloc[0]["c"]
    n_conf = qdf(
        "SELECT COUNT(*) c FROM agendamentos WHERE data = ? AND status = 'Confirmado'",
        (hoje.isoformat(),),
    ).iloc[0]["c"]
    n_futuros = qdf(
        "SELECT COUNT(*) c FROM agendamentos WHERE data >= ? AND status IN ('Agendado','Confirmado')",
        (hoje.isoformat(),),
    ).iloc[0]["c"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Compromissos hoje", n_hoje)
    c2.metric("Confirmados hoje", n_conf)
    c3.metric("Agendamentos futuros", n_futuros)

    # ---- Novo agendamento --------------------------------------------------- #
    with st.expander("➕ Novo agendamento", expanded=not pets.empty and n_hoje == 0):
        if pets.empty:
            st.info("Cadastre primeiro um **tutor** e um **pet** para agendar.")
        else:
            with st.form("form_novo_agendamento", clear_on_submit=True):
                op = {f"{r['nome']} — {r['tutor']} (#{r['id']})": r["id"] for _, r in pets.iterrows()}
                pet_lbl = st.selectbox("Pet *", list(op.keys()))
                c1, c2, c3 = st.columns(3)
                data = c1.date_input("Data *", value=hoje, min_value=date(2020, 1, 1), format="DD/MM/YYYY")
                hora = c2.time_input("Horário *", value=time(9, 0), step=900, format="HH:mm")
                tipo = c3.selectbox("Tipo", TIPOS_AGENDAMENTO)
                veterinario = st.text_input("Veterinário(a) responsável")
                motivo = st.text_input("Motivo / observações")
                if st.form_submit_button("💾 Agendar", type="primary"):
                    hora_txt = hora.strftime("%H:%M")
                    conflito = qdf(
                        "SELECT COUNT(*) c FROM agendamentos WHERE data=? AND hora=? AND status != 'Cancelado'",
                        (data.isoformat(), hora_txt),
                    ).iloc[0]["c"]
                    run(
                        """INSERT INTO agendamentos (pet_id, data, hora, tipo, veterinario, motivo, status)
                           VALUES (?,?,?,?,?,?,'Agendado')""",
                        (op[pet_lbl], data.isoformat(), hora_txt, tipo, veterinario.strip(), motivo.strip()),
                    )
                    if conflito:
                        st.warning(
                            f"Agendamento criado — atenção: já existe outro compromisso às **{hora_txt}** neste dia!"
                        )
                    else:
                        st.success("Agendamento criado!")
                    st.rerun()

    # ---- Agenda do dia ------------------------------------------------------ #
    st.divider()
    dia = st.date_input("Ver agenda do dia", value=hoje, format="DD/MM/YYYY", key="agenda_dia")
    df = qdf(
        """SELECT a.*, p.nome AS pet, t.nome AS tutor, t.telefone FROM agendamentos a
           JOIN pets p ON p.id = a.pet_id
           JOIN tutores t ON t.id = p.tutor_id
           WHERE a.data = ? ORDER BY a.hora""",
        (dia.isoformat(),),
    )
    if df.empty:
        st.info("Nenhum compromisso agendado para este dia.")
    else:
        view = df.copy()
        view["Situação"] = view["status"].map(lambda s: STATUS_EMOJI.get(s, s))

        def _msg_conf(r):
            return (
                f"Olá {r['tutor']}! 🐾 Aqui é da CARDIOEVET. Passando para confirmar: {r['tipo']} "
                f"do(a) {r['pet']} no dia {fmt_data(r['data'])} às {r['hora']}. "
                "Qualquer imprevisto, é só avisar por aqui!"
            )

        view["Lembrete"] = view.apply(
            lambda r: link_whatsapp(r["telefone"], _msg_conf(r)) if r["status"] != "Cancelado" else "",
            axis=1,
        )
        st.dataframe(
            view[["hora", "pet", "tutor", "tipo", "veterinario", "Situação", "motivo", "Lembrete"]],
            hide_index=True, use_container_width=True,
            column_config={
                "hora": "Hora", "pet": "Pet", "tutor": "Tutor", "tipo": "Tipo",
                "veterinario": "Veterinário(a)", "motivo": "Motivo",
                "Lembrete": st.column_config.LinkColumn("Lembrete", display_text="📲 WhatsApp", width="small"),
            },
        )
        botao_csv(view[["hora", "pet", "tutor", "tipo", "veterinario", "status", "motivo"]],
                  f"agenda_{dia.isoformat()}.csv", "⬇️ Baixar agenda do dia em CSV")

        # ---- Gerenciar agendamento ------------------------------------------ #
        with st.expander("✏️ Alterar status, editar ou excluir"):
            op = {f"{r['hora']} — {r['pet']} ({r['tutor']}) [{r['status']}] (#{r['id']})": r["id"]
                  for _, r in df.iterrows()}
            sel = st.selectbox("Selecione o agendamento", list(op.keys()), key="sel_edit_agenda")
            aid = op[sel]
            ap = df[df["id"] == aid].iloc[0]

            with st.form("form_edit_agendamento"):
                c1, c2, c3 = st.columns(3)
                nova_data = c1.date_input("Data *", value=parse_date(ap["data"]) or hoje,
                                          min_value=date(2020, 1, 1), format="DD/MM/YYYY")
                try:
                    hora_val = datetime.strptime(str(ap["hora"])[:5], "%H:%M").time()
                except ValueError:
                    hora_val = time(9, 0)
                nova_hora = c2.time_input("Horário *", value=hora_val, step=900, format="HH:mm")
                novo_status = c3.selectbox(
                    "Status", STATUS_AGENDAMENTO,
                    index=STATUS_AGENDAMENTO.index(ap["status"]) if ap["status"] in STATUS_AGENDAMENTO else 0,
                )
                novo_tipo = c1.selectbox(
                    "Tipo", TIPOS_AGENDAMENTO,
                    index=TIPOS_AGENDAMENTO.index(ap["tipo"]) if ap["tipo"] in TIPOS_AGENDAMENTO else 0,
                )
                novo_vet = c2.text_input("Veterinário(a)", value=ap["veterinario"] or "")
                novo_motivo = st.text_input("Motivo / observações", value=ap["motivo"] or "")
                registrar_hist = st.checkbox("Ao concluir, registrar também no histórico do pet")
                if st.form_submit_button("💾 Salvar alterações", type="primary"):
                    run(
                        """UPDATE agendamentos SET data=?, hora=?, tipo=?, veterinario=?, motivo=?, status=?
                           WHERE id=?""",
                        (nova_data.isoformat(), nova_hora.strftime("%H:%M"), novo_tipo,
                         novo_vet.strip(), novo_motivo.strip(), novo_status, aid),
                    )
                    if novo_status == "Concluído" and registrar_hist:
                        run(
                            """INSERT INTO historico (pet_id, data, tipo, veterinario, peso_kg, descricao)
                               VALUES (?,?,?,?,?,?)""",
                            (ap["pet_id"], nova_data.isoformat(), novo_tipo, novo_vet.strip(), None,
                             (novo_motivo.strip() or f"{novo_tipo} agendado(a)") + f" (agendamento #{aid})"),
                        )
                        st.success("Status atualizado e atendimento registrado no histórico!")
                    else:
                        st.success("Agendamento atualizado!")
                    st.rerun()

            st.markdown("**🗑️ Excluir agendamento**")
            confirma = st.checkbox("Confirmo que desejo excluir", key=f"conf_agenda_{aid}")
            if st.button("Excluir agendamento", disabled=not confirma, key=f"del_agenda_{aid}"):
                run("DELETE FROM agendamentos WHERE id = ?", (aid,))
                st.success("Agendamento excluído.")
                st.rerun()

    # ---- Próximos compromissos ---------------------------------------------- #
    st.divider()
    st.subheader("🗓️ Próximos compromissos")
    fut = qdf(
        """SELECT a.data, a.hora, p.nome AS pet, t.nome AS tutor, a.tipo, a.status
           FROM agendamentos a
           JOIN pets p ON p.id = a.pet_id
           JOIN tutores t ON t.id = p.tutor_id
           WHERE a.data >= ? AND a.status IN ('Agendado','Confirmado')
           ORDER BY a.data, a.hora LIMIT 15""",
        (hoje.isoformat(),),
    )
    if fut.empty:
        st.info("Nenhum compromisso futuro.")
    else:
        fut["data"] = fut["data"].map(fmt_data)
        fut["status"] = fut["status"].map(lambda s: STATUS_EMOJI.get(s, s))
        st.dataframe(
            fut, hide_index=True, use_container_width=True,
            column_config={"data": "Data", "hora": "Hora", "pet": "Pet",
                           "tutor": "Tutor", "tipo": "Tipo", "status": "Status"},
        )


# --------------------------------------------------------------------------- #
#  Página: Vacinas
# --------------------------------------------------------------------------- #

def pagina_vacinas():
    st.header("💉 Carteirinha de vacinação")
    hoje_iso = date.today().isoformat()

    # ---- Alertas gerais ----------------------------------------------------- #
    alertas = qdf(
        """SELECT v.vacina, v.proxima_dose, p.nome AS pet, t.nome AS tutor, t.telefone, t.email
           FROM vacinas v
           JOIN pets p ON p.id = v.pet_id
           JOIN tutores t ON t.id = p.tutor_id
           WHERE v.proxima_dose IS NOT NULL AND v.proxima_dose != ''
             AND v.proxima_dose <= date('now', 'localtime', '+15 days')
           ORDER BY v.proxima_dose"""
    )
    if alertas.empty:
        st.success("✅ Nenhuma vacina vencida ou a vencer nos próximos 15 dias.")
    else:
        n_venc = int((alertas["proxima_dose"] < hoje_iso).sum())
        if n_venc:
            st.error(f"🔴 **{n_venc} vacina(s) com reforço vencido!** Entre em contato com os tutores.")
        else:
            st.warning("🟡 Há vacinas com reforço a vencer nos próximos 15 dias.")
        al = alertas.copy()
        al["Situação"] = al["proxima_dose"].map(lambda d: f"{situacao_vacina(d)[1]} {situacao_vacina(d)[0]}")
        al["Próx. dose"] = al["proxima_dose"].map(fmt_data)

        def _msg_vac(r):
            sit = situacao_vacina(r["proxima_dose"])[0]
            return (
                f"Olá {r['tutor']}! 🐾 Aqui é da CARDIOEVET. Passando para lembrar da vacina "
                f"{r['vacina']} do(a) {r['pet']} — situação: {sit.lower()} (data de referência: "
                f"{fmt_data(r['proxima_dose'])}). Podemos agendar a aplicação?"
            )

        al["WhatsApp"] = al.apply(lambda r: link_whatsapp(r["telefone"], _msg_vac(r)), axis=1)
        al["E-mail"] = al.apply(
            lambda r: link_email(r["email"], f"Lembrete de vacina - {r['pet']} | CARDIOEVET", _msg_vac(r)),
            axis=1,
        )
        st.dataframe(
            al[["Próx. dose", "pet", "tutor", "telefone", "vacina", "Situação", "WhatsApp", "E-mail"]],
            hide_index=True, use_container_width=True,
            column_config={
                "pet": "Pet", "tutor": "Tutor", "telefone": "Telefone", "vacina": "Vacina",
                "WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="📲 Enviar", width="small"),
                "E-mail": st.column_config.LinkColumn("E-mail", display_text="✉️ Enviar", width="small"),
            },
        )
        st.caption("💡 Os botões abrem o WhatsApp ou o seu aplicativo de e-mail com a mensagem pronta — "
                   "é só revisar e enviar.")
    st.divider()

    pets = qdf(
        """SELECT p.id, p.nome, p.especie, t.nome AS tutor FROM pets p
           JOIN tutores t ON t.id = p.tutor_id ORDER BY p.nome"""
    )
    if pets.empty:
        st.info("Cadastre primeiro um **tutor** e um **pet** para registrar vacinas.")
        return

    op = {f"{r['nome']} — {r['tutor']} (#{r['id']})": r["id"] for _, r in pets.iterrows()}
    sel = st.selectbox("Selecione o pet", list(op.keys()))
    pid = op[sel]
    especie_pet = pets[pets["id"] == pid].iloc[0]["especie"]

    # ---- Registrar vacina --------------------------------------------------- #
    with st.expander("➕ Registrar vacina"):
        with st.form("form_nova_vacina", clear_on_submit=True):
            vacina = st.text_input("Vacina *", placeholder="Ex.: Antirrábica, V10…")
            if especie_pet in SUGESTOES_VACINAS:
                st.caption(f"Sugestões para **{especie_pet}**: {SUGESTOES_VACINAS[especie_pet]}")
            c1, c2 = st.columns(2)
            aplicacao = c1.date_input("Data de aplicação *", value=date.today(),
                                      min_value=date(1990, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
            reforco = c2.date_input("Próxima dose / reforço (deixe vazio se for dose única)",
                                    value=None, min_value=date(1990, 1, 1), format="DD/MM/YYYY")
            c3, c4 = st.columns(2)
            vet = c3.text_input("Veterinário(a)")
            lote = c4.text_input("Lote / fabricante")
            obs = st.text_input("Observações")
            registrar_hist = st.checkbox("Registrar também no histórico do pet", value=True)
            if st.form_submit_button("💾 Registrar vacina", type="primary"):
                if not vacina.strip():
                    st.error("Informe o nome da vacina.")
                elif reforco and reforco < aplicacao:
                    st.error("A data da próxima dose não pode ser anterior à aplicação.")
                else:
                    run(
                        """INSERT INTO vacinas (pet_id, vacina, data_aplicacao, proxima_dose,
                                                veterinario, lote, observacao)
                           VALUES (?,?,?,?,?,?,?)""",
                        (pid, vacina.strip(), aplicacao.isoformat(),
                         reforco.isoformat() if reforco else None, vet.strip(), lote.strip(), obs.strip()),
                    )
                    if registrar_hist:
                        desc = f"Vacina {vacina.strip()} aplicada"
                        if lote.strip():
                            desc += f" (lote {lote.strip()})"
                        if reforco:
                            desc += f". Reforço previsto: {reforco.strftime('%d/%m/%Y')}"
                        run(
                            "INSERT INTO historico (pet_id, data, tipo, veterinario, peso_kg, descricao)"
                            " VALUES (?,?,?,?,?,?)",
                            (pid, aplicacao.isoformat(), "Vacina", vet.strip(), None, desc),
                        )
                    st.success("Vacina registrada!")
                    st.rerun()

    # ---- Carteirinha --------------------------------------------------------- #
    st.subheader("🗂️ Vacinas registradas")
    df = qdf("SELECT * FROM vacinas WHERE pet_id = ? ORDER BY data_aplicacao DESC", (pid,))
    if df.empty:
        st.info("Nenhuma vacina registrada para este pet.")
        return

    view = df.copy()
    view["Aplicação"] = view["data_aplicacao"].map(fmt_data)
    view["Próx. dose"] = view["proxima_dose"].map(lambda d: fmt_data(d) if d else "—")
    view["Situação"] = view["proxima_dose"].map(lambda d: f"{situacao_vacina(d)[1]} {situacao_vacina(d)[0]}")
    st.dataframe(
        view[["vacina", "Aplicação", "Próx. dose", "Situação", "veterinario", "lote", "observacao"]],
        hide_index=True, use_container_width=True,
        column_config={"vacina": "Vacina", "veterinario": "Veterinário(a)",
                       "lote": "Lote", "observacao": "Observações"},
    )
    botao_csv(view[["vacina", "Aplicação", "Próx. dose", "veterinario", "lote", "observacao"]],
              f"vacinas_pet_{pid}.csv", "⬇️ Baixar carteirinha em CSV")

    # ---- Editar / excluir ----------------------------------------------------- #
    with st.expander("✏️ Editar ou excluir um registro"):
        op_reg = {f"{fmt_data(r['data_aplicacao'])} — {r['vacina']} (#{r['id']})": r["id"]
                  for _, r in df.iterrows()}
        sel2 = st.selectbox("Selecione o registro", list(op_reg.keys()), key="sel_edit_vac")
        vid = op_reg[sel2]
        reg = df[df["id"] == vid].iloc[0]

        with st.form("form_edit_vacina"):
            vacina = st.text_input("Vacina *", value=reg["vacina"])
            c1, c2 = st.columns(2)
            aplicacao = c1.date_input("Data de aplicação *",
                                      value=parse_date(reg["data_aplicacao"]) or date.today(),
                                      min_value=date(1990, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
            reforco = c2.date_input("Próxima dose / reforço", value=parse_date(reg["proxima_dose"]),
                                    min_value=date(1990, 1, 1), format="DD/MM/YYYY")
            c3, c4 = st.columns(2)
            vet = c3.text_input("Veterinário(a)", value=reg["veterinario"] or "")
            lote = c4.text_input("Lote / fabricante", value=reg["lote"] or "")
            obs = st.text_input("Observações", value=reg["observacao"] or "")
            if st.form_submit_button("💾 Salvar alterações", type="primary"):
                if not vacina.strip():
                    st.error("Informe o nome da vacina.")
                elif reforco and reforco < aplicacao:
                    st.error("A data da próxima dose não pode ser anterior à aplicação.")
                else:
                    run(
                        """UPDATE vacinas SET vacina=?, data_aplicacao=?, proxima_dose=?,
                           veterinario=?, lote=?, observacao=? WHERE id=?""",
                        (vacina.strip(), aplicacao.isoformat(), reforco.isoformat() if reforco else None,
                         vet.strip(), lote.strip(), obs.strip(), vid),
                    )
                    st.success("Registro atualizado!")
                    st.rerun()

        st.markdown("**🗑️ Excluir registro**")
        confirma = st.checkbox("Confirmo que desejo excluir", key=f"conf_vac_{vid}")
        if st.button("Excluir vacina", disabled=not confirma, key=f"del_vac_{vid}"):
            run("DELETE FROM vacinas WHERE id = ?", (vid,))
            st.success("Registro excluído.")
            st.rerun()


# --------------------------------------------------------------------------- #
#  Página: Financeiro
# --------------------------------------------------------------------------- #

def pagina_financeiro():
    st.header("💰 Financeiro")
    hoje = date.today()

    meses_db = qdf("SELECT DISTINCT substr(data, 1, 7) AS m FROM lancamentos")["m"].tolist()
    opcoes = sorted({hoje.strftime("%Y-%m"), *meses_db}, reverse=True)
    mes = st.selectbox(
        "Mês de referência", opcoes,
        format_func=lambda m: datetime.strptime(m, "%Y-%m").strftime("%m/%Y"),
    )

    receitas = float(qdf(
        "SELECT COALESCE(SUM(valor),0) s FROM lancamentos WHERE tipo='Receita' AND substr(data,1,7)=?",
        (mes,),
    ).iloc[0]["s"])
    despesas = float(qdf(
        "SELECT COALESCE(SUM(valor),0) s FROM lancamentos WHERE tipo='Despesa' AND substr(data,1,7)=?",
        (mes,),
    ).iloc[0]["s"])

    c1, c2, c3 = st.columns(3)
    c1.metric("📈 Receitas", fmt_moeda(receitas))
    c2.metric("📉 Despesas", fmt_moeda(despesas))
    c3.metric("💵 Saldo do mês", fmt_moeda(receitas - despesas))

    # ---- Tabela de serviços e valores --------------------------------------- #
    with st.expander("🩺 Tabela de serviços e valores"):
        _seed_servicos()
        sv = qdf("SELECT id, nome, categoria, preco, ativo FROM servicos ORDER BY ativo DESC, nome")
        n_ativos = int((sv["ativo"] == 1).sum()) if not sv.empty else 0
        st.caption(f"{n_ativos} serviço(s) ativo(s). Os preços iniciais são **sugestões editáveis** — ajuste para os valores da sua clínica.")
        if not sv.empty:
            view = sv.copy()
            view["Situação"] = view["ativo"].map({0: "⏸ Inativo", 1: "✅ Ativo"})
            st.dataframe(
                view[["nome", "categoria", "preco", "Situação"]],
                hide_index=True, use_container_width=True,
                column_config={
                    "nome": "Serviço", "categoria": "Categoria",
                    "preco": st.column_config.NumberColumn("Preço", format="R$ %.2f"),
                },
            )

        with st.container(border=True):
            st.markdown("**➕ Novo serviço**")
            c1, c2, c3 = st.columns([4, 2, 2])
            n_nome = c1.text_input("Nome do serviço *", placeholder="Ex.: Doppler renal", key="sv_nome_novo")
            n_cat = c2.selectbox("Categoria", CATEGORIAS["Receita"], key="sv_cat_novo")
            n_preco = c3.number_input("Preço (R$)", min_value=0.0, step=10.0, format="%.2f", key="sv_preco_novo")
            if st.button("💾 Adicionar serviço", type="primary", key="btn_sv_novo"):
                if not n_nome.strip():
                    st.error("Informe o nome do serviço.")
                else:
                    run("INSERT INTO servicos (nome, categoria, preco) VALUES (?,?,?)",
                        (n_nome.strip(), n_cat, float(n_preco)))
                    st.success(f"Serviço **{n_nome.strip()}** adicionado!")
                    st.rerun()

        if not sv.empty:
            with st.container(border=True):
                st.markdown("**✏️ Editar, pausar ou excluir serviço**")
                op_sv = {f"{r['nome']} — {fmt_moeda(r['preco'])} (#{r['id']})": int(r["id"])
                         for _, r in sv.iterrows()}
                sel_sv = st.selectbox("Selecione o serviço", list(op_sv.keys()), key="sv_sel_edit")
                sid = op_sv[sel_sv]
                row = sv[sv["id"] == sid].iloc[0]
                e1, e2, e3 = st.columns([4, 2, 2])
                e_nome = e1.text_input("Nome", value=row["nome"], key=f"sv_enome_{sid}")
                e_cat = e2.selectbox("Categoria", CATEGORIAS["Receita"],
                                     index=CATEGORIAS["Receita"].index(row["categoria"])
                                     if row["categoria"] in CATEGORIAS["Receita"] else 0,
                                     key=f"sv_ecat_{sid}")
                e_preco = e3.number_input("Preço (R$)", min_value=0.0, value=float(row["preco"] or 0),
                                          step=10.0, format="%.2f", key=f"sv_epreco_{sid}")
                e_ativo = st.checkbox("Serviço ativo (aparece no preenchimento rápido)",
                                      value=bool(row["ativo"]), key=f"sv_eativo_{sid}")
                b1, b2, b3 = st.columns([2, 2, 3])
                if b1.button("💾 Salvar alterações", key=f"sv_save_{sid}", type="primary"):
                    if not e_nome.strip():
                        st.error("O nome não pode ficar vazio.")
                    else:
                        run("UPDATE servicos SET nome=?, categoria=?, preco=?, ativo=? WHERE id=?",
                            (e_nome.strip(), e_cat, float(e_preco), 1 if e_ativo else 0, sid))
                        st.success("Serviço atualizado!")
                        st.rerun()
                conf_sv = st.checkbox("Confirmo a exclusão deste serviço", key=f"sv_conf_{sid}")
                if b2.button("🗑️ Excluir", key=f"sv_del_{sid}", disabled=not conf_sv):
                    run("DELETE FROM servicos WHERE id = ?", (sid,))
                    st.success("Serviço excluído.")
                    st.rerun()

    pets = qdf(
        """SELECT p.id, p.nome, t.nome AS tutor FROM pets p
           JOIN tutores t ON t.id = p.tutor_id ORDER BY p.nome"""
    )

    # ---- Novo lançamento ------------------------------------------------------ #
    with st.expander("➕ Novo lançamento", expanded=True):
        tipo = st.radio("Tipo", ["Receita", "Despesa"], horizontal=True, key="tipo_novo_lanc")
        sv_ativos = qdf("SELECT id, nome, preco, categoria FROM servicos WHERE ativo = 1 ORDER BY nome")
        if tipo == "Receita" and not sv_ativos.empty:
            sv_lbl = ["— Escolher manualmente —"] + [
                f"{r['nome']} — {fmt_moeda(r['preco'])}" for _, r in sv_ativos.iterrows()
            ]
            sel_aplica = st.selectbox("🩺 Aplicar serviço da tabela (preenche descrição e valor)",
                                      sv_lbl, key="nl_sel_servico")
            if sel_aplica != "— Escolher manualmente —":
                row_sv = sv_ativos.iloc[sv_lbl.index(sel_aplica) - 1]
                st.session_state["nl_default_desc"] = row_sv["nome"]
                st.session_state["nl_default_valor"] = float(row_sv["preco"] or 0)
                st.session_state["nl_default_cat"] = (
                    row_sv["categoria"] if row_sv["categoria"] in CATEGORIAS["Receita"] else "Consulta"
                )
        with st.form("form_novo_lancamento", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            data = c1.date_input("Data *", value=hoje, min_value=date(2020, 1, 1), format="DD/MM/YYYY")
            cat_opts = CATEGORIAS[tipo]
            cat_def = st.session_state.get("nl_default_cat")
            categoria = c2.selectbox("Categoria", cat_opts,
                                     index=cat_opts.index(cat_def) if cat_def in cat_opts else 0)
            pagamento = c3.selectbox("Forma de pagamento", FORMAS_PAGAMENTO)
            descricao = st.text_input(
                "Descrição *", value=st.session_state.get("nl_default_desc", ""),
                placeholder="Ex.: Consulta de rotina, compra de ração…")
            c4, c5 = st.columns(2)
            valor = c4.number_input("Valor (R$) *", min_value=0.0,
                                    value=st.session_state.get("nl_default_valor", 0.0) or None,
                                    step=10.0, format="%.2f")
            op = {"— Não vincular —": None}
            op.update({f"{r['nome']} — {r['tutor']}": r["id"] for _, r in pets.iterrows()})
            pet_lbl = c5.selectbox("Vincular a um pet (opcional)", list(op.keys()))
            if st.form_submit_button("💾 Salvar lançamento", type="primary"):
                if valor is None or valor <= 0:
                    st.error("Informe um valor maior que zero.")
                elif not descricao.strip():
                    st.error("A descrição é obrigatória.")
                else:
                    run(
                        """INSERT INTO lancamentos (data, tipo, categoria, descricao, valor,
                                                    forma_pagamento, pet_id)
                           VALUES (?,?,?,?,?,?,?)""",
                        (data.isoformat(), tipo, categoria, descricao.strip(),
                         float(valor), pagamento, op[pet_lbl]),
                    )
                    for k in ("nl_default_desc", "nl_default_valor", "nl_default_cat"):
                        st.session_state.pop(k, None)
                    st.success(f"Lançamento salvo: **{descricao.strip()}** — {fmt_moeda(float(valor))}")
                    st.rerun()

    # ---- Lançamentos do mês ---------------------------------------------------- #
    st.divider()
    st.subheader(f"Lançamentos de {datetime.strptime(mes, '%Y-%m').strftime('%m/%Y')}")
    df = qdf(
        """SELECT l.*, p.nome AS pet FROM lancamentos l
           LEFT JOIN pets p ON p.id = l.pet_id
           WHERE substr(l.data, 1, 7) = ?
           ORDER BY l.data DESC, l.id DESC""",
        (mes,),
    )
    if df.empty:
        st.info("Nenhum lançamento neste mês.")
        return

    view = df.copy()
    view["data"] = view["data"].map(fmt_data)
    view["tipo"] = view["tipo"].map({"Receita": "🟢 Receita", "Despesa": "🔴 Despesa"})
    st.dataframe(
        view[["data", "tipo", "categoria", "descricao", "pet", "forma_pagamento", "valor"]],
        hide_index=True, use_container_width=True,
        column_config={
            "data": "Data", "tipo": "Tipo", "categoria": "Categoria", "descricao": "Descrição",
            "pet": "Pet", "forma_pagamento": "Pagamento",
            "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
        },
    )
    botao_csv(
        df[["data", "tipo", "categoria", "descricao", "pet", "forma_pagamento", "valor"]],
        f"financeiro_{mes}.csv", "⬇️ Baixar mês em CSV",
    )

    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Receitas × despesas por dia")
        pv = qdf(
            """SELECT substr(data, 9, 2) AS dia,
                      SUM(CASE WHEN tipo='Receita' THEN valor END) AS Receitas,
                      SUM(CASE WHEN tipo='Despesa' THEN valor END) AS Despesas
               FROM lancamentos WHERE substr(data,1,7)=?
               GROUP BY dia ORDER BY dia""",
            (mes,),
        )
        st.bar_chart(pv.set_index("dia"))
    with g2:
        st.subheader("Por categoria")
        cat = qdf(
            """SELECT categoria, tipo, SUM(valor) AS total FROM lancamentos
               WHERE substr(data,1,7)=? GROUP BY tipo, categoria""",
            (mes,),
        )
        st.bar_chart(cat, x="categoria", y="total", color="tipo")

    # ---- Editar / excluir ------------------------------------------------------- #
    with st.expander("✏️ Editar ou excluir lançamento"):
        op_l = {f"{fmt_data(r['data'])} — {r['descricao']} ({fmt_moeda(r['valor'])}) (#{r['id']})": r["id"]
                for _, r in df.iterrows()}
        sel = st.selectbox("Selecione o lançamento", list(op_l.keys()), key="sel_edit_lanc")
        lid = op_l[sel]
        reg = df[df["id"] == lid].iloc[0]

        tipo_e = st.radio(
            "Tipo", ["Receita", "Despesa"], horizontal=True,
            index=0 if reg["tipo"] == "Receita" else 1, key="tipo_edit_lanc",
        )
        with st.form("form_edit_lancamento"):
            c1, c2, c3 = st.columns(3)
            data = c1.date_input("Data *", value=parse_date(reg["data"]) or hoje,
                                 min_value=date(2020, 1, 1), format="DD/MM/YYYY")
            cats = CATEGORIAS[tipo_e]
            categoria = c2.selectbox(
                "Categoria", cats,
                index=cats.index(reg["categoria"]) if reg["categoria"] in cats else 0,
            )
            pagamento = c3.selectbox(
                "Forma de pagamento", FORMAS_PAGAMENTO,
                index=FORMAS_PAGAMENTO.index(reg["forma_pagamento"])
                if reg["forma_pagamento"] in FORMAS_PAGAMENTO else 0,
            )
            descricao = st.text_input("Descrição *", value=reg["descricao"] or "")
            c4, c5 = st.columns(2)
            valor = c4.number_input(
                "Valor (R$) *", min_value=0.0,
                value=float(reg["valor"]) if pd.notna(reg["valor"]) else None,
                step=10.0, format="%.2f",
            )
            op = {"— Não vincular —": None}
            op.update({f"{r['nome']} — {r['tutor']}": r["id"] for _, r in pets.iterrows()})
            labels = list(op.keys())
            atual = None
            pet_ref = reg["pet_id"] if pd.notna(reg["pet_id"]) else None
            for lbl, vid_ in op.items():
                if vid_ == pet_ref:
                    atual = lbl
            pet_lbl = c5.selectbox("Vincular a um pet (opcional)", labels,
                                   index=labels.index(atual) if atual else 0)
            if st.form_submit_button("💾 Salvar alterações", type="primary"):
                if valor is None or valor <= 0:
                    st.error("Informe um valor maior que zero.")
                elif not descricao.strip():
                    st.error("A descrição é obrigatória.")
                else:
                    run(
                        """UPDATE lancamentos SET data=?, tipo=?, categoria=?, descricao=?,
                           valor=?, forma_pagamento=?, pet_id=? WHERE id=?""",
                        (data.isoformat(), tipo_e, categoria, descricao.strip(),
                         float(valor), pagamento, op[pet_lbl], lid),
                    )
                    st.success("Lançamento atualizado!")
                    st.rerun()

        st.markdown("**🗑️ Excluir lançamento**")
        confirma = st.checkbox("Confirmo que desejo excluir", key=f"conf_lanc_{lid}")
        if st.button("Excluir lançamento", disabled=not confirma, key=f"del_lanc_{lid}"):
            run("DELETE FROM lancamentos WHERE id = ?", (lid,))
            st.success("Lançamento excluído.")
            st.rerun()


# --------------------------------------------------------------------------- #
#  Relatórios em PDF
# --------------------------------------------------------------------------- #

def novo_pdf(titulo: str, subtitulo: str = "") -> FPDF:
    pdf = FPDF(format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    if os.path.exists("assets/logo.png"):
        try:
            pdf.image("assets/logo.png", x=168, y=12, w=27)
        except Exception:
            pass  # se a imagem falhar, o PDF sai sem logo
        pdf.set_y(42)
    pdf.set_font("helvetica", "B", 17)
    pdf.set_text_color(22, 101, 96)
    pdf.cell(0, 10, "CARDIOEVET - Clínica Veterinária", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 13)
    pdf.set_text_color(30)
    pdf.cell(0, 8, pdf_san(titulo), align="C", new_x="LMARGIN", new_y="NEXT")
    if subtitulo:
        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 6, pdf_san(subtitulo), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(120)
    pdf.cell(0, 5, f"Emitido em {datetime.now().strftime('%d/%m/%Y %H:%M')}",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30)
    pdf.set_draw_color(22, 101, 96)
    pdf.set_line_width(0.5)
    pdf.ln(2)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(6)
    return pdf


def pdf_tabela(pdf: FPDF, cabecalho, linhas, larguras, aligns=None):
    pdf.set_font("helvetica", "B", 9)
    pdf.set_fill_color(22, 101, 96)
    pdf.set_text_color(255)
    pdf.set_draw_color(160)
    for cab, larg in zip(cabecalho, larguras):
        pdf.cell(larg, 7, pdf_san(cab), border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(30)
    fill = False
    for linha in linhas:
        pdf.set_fill_color(233, 245, 243)
        for i, (val, larg) in enumerate(zip(linha, larguras)):
            pdf.cell(larg, 6, pdf_san(val), border=1,
                     align=aligns[i] if aligns else "L", fill=fill)
        pdf.ln()
        fill = not fill


def pdf_campo(pdf: FPDF, rotulo: str, valor: str):
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(34, 6, pdf_san(rotulo))
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, pdf_san(valor), new_x="LMARGIN", new_y="NEXT")


def pdf_vazio(pdf: FPDF, texto: str):
    pdf.set_font("helvetica", "I", 10)
    pdf.cell(0, 8, pdf_san(texto), new_x="LMARGIN", new_y="NEXT")


def botao_imprimir_pdf(pdf_bytes: bytes, chave: str, altura: int = 620):
    """Botão '🖨️ Visualizar / imprimir': mostra o PDF na tela no visualizador do
    próprio navegador — basta clicar no ícone de impressora (ou Ctrl+P).

    `chave` deve ser única por documento/tela.
    """
    k_view = f"_view_{chave}"
    if st.button("🖨️ Visualizar / imprimir", key=f"btn_view_{chave}"):
        st.session_state[k_view] = not st.session_state.get(k_view, False)
    if st.session_state.get(k_view):
        b64 = base64.b64encode(pdf_bytes).decode()
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="{altura}" '
            f'style="border:1px solid #cfd8d3; border-radius:8px; background:#f8faf9;"></iframe>',
            unsafe_allow_html=True,
        )
        st.caption("🖨️ **Para imprimir:** clique no **ícone de impressora** no canto superior "
                   "direito do visualizador acima — ou pressione **Ctrl+P** (Windows) / "
                   "**Cmd+P** (Mac). O documento sai idêntico ao PDF.")
        if st.button("✖ Fechar visualização", key=f"btn_close_{chave}"):
            st.session_state[k_view] = False
            st.rerun()


def trunc(s, n: int) -> str:
    s = str(s if s is not None else "").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


# --------------------------------------------------------------------------- #
#  Valor por extenso (usado em recibos)
# --------------------------------------------------------------------------- #

_UNID = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"]
_11_19 = ["", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis",
          "dezessete", "dezoito", "dezenove"]
_DEZ = ["", "dez", "vinte", "trinta", "quarenta", "cinquenta", "sessenta",
        "setenta", "oitenta", "noventa"]
_CENT = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
         "seiscentos", "setecentos", "oitocentos", "novecentos"]


def _ext_ate_99(n: int) -> str:
    if n < 10:
        return _UNID[n]
    if n == 10:
        return "dez"
    if n < 20:
        return _11_19[n - 10]
    d, u = divmod(n, 10)
    return _DEZ[d] if u == 0 else f"{_DEZ[d]} e {_UNID[u]}"


def _ext_ate_999(n: int) -> str:
    if n < 100:
        return _ext_ate_99(n)
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    return _CENT[c] if r == 0 else f"{_CENT[c]} e {_ext_ate_99(r)}"


def valor_por_extenso(valor: float) -> str:
    """Converte R$ para texto por extenso em pt-BR (até < 1 bilhão)."""
    valor = abs(float(valor))
    centavos = int(round((valor - int(valor)) * 100))
    if centavos == 100:
        valor += 1
        centavos = 0
    reais = int(valor)

    partes = []
    milhoes, resto = divmod(reais, 1_000_000)
    milhares, unidades = divmod(resto, 1000)
    if milhoes:
        partes.append(f"{_ext_ate_999(milhoes)} {'milhão' if milhoes == 1 else 'milhões'}")
    if milhares:
        if milhares == 1:
            partes.append("mil")
        else:
            partes.append(f"{_ext_ate_999(milhares)} mil")
    if unidades:
        partes.append(_ext_ate_999(unidades))

    if not reais and not centavos:
        return "Zero reais"
    txt = ""
    if reais:
        txt = " e ".join(partes) + (" real" if reais == 1 else " reais")
    if centavos:
        ext_c = _ext_ate_99(centavos) + (" centavo" if centavos == 1 else " centavos")
        txt = ext_c if not txt else f"{txt} e {ext_c}"
    return txt[0].upper() + txt[1:]


def proximo_numero(chave: str) -> int:
    n = int(get_config(chave, "0") or 0) + 1
    set_config(chave, str(n))
    return n


def assinatura(pdf: FPDF):
    pdf.ln(14)
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 5, "________________________________________", align="C", new_x="LMARGIN", new_y="NEXT")
    nome = (get_config("carimbo_nome", "") or "").strip()
    crmv = (get_config("carimbo_crmv", "") or "").strip()
    if nome or crmv:
        rotulo = ("  —  ".join(p for p in (nome, crmv) if p))
    else:
        rotulo = "Veterinário(a) responsável"
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, pdf_san(rotulo), align="C", new_x="LMARGIN", new_y="NEXT")
    if assinatura_ativa():
        pdf.set_font("helvetica", "I", 7.5)
        pdf.set_text_color(100)
        pdf.cell(0, 4, pdf_san("Documento assinado digitalmente (ICP-Brasil) — verificável no painel de "
                               "assinaturas do leitor de PDF ou em verificador.iti.br"),
                 align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30)


def dados_pet(pdf: FPDF, pet):
    extra = f" - {pet['raca']}" if pet["raca"] else ""
    pdf_campo(pdf, "Pet:", f"{pet['nome']}  ({pet['especie'] or '-'}{extra})")
    pdf_campo(pdf, "Sexo / Idade:", f"{pet['sexo'] or '-'} / {idade_str(pet['nascimento'])}")
    pdf_campo(pdf, "Tutor:", f"{pet['tutor']}   Tel: {pet['telefone'] or '-'}")
    pdf.ln(4)


def gerar_pdf_carteirinha(pid: int) -> bytes:
    pet = qdf(
        """SELECT p.*, t.nome AS tutor, t.telefone FROM pets p
           JOIN tutores t ON t.id = p.tutor_id WHERE p.id = ?""",
        (pid,),
    ).iloc[0]
    vacs = qdf("SELECT * FROM vacinas WHERE pet_id = ? ORDER BY data_aplicacao", (pid,))
    pdf = novo_pdf(pdf_san("Carteirinha de Vacinação"))
    dados_pet(pdf, pet)
    if vacs.empty:
        pdf_vazio(pdf, "Nenhuma vacina registrada para este pet.")
    else:
        linhas = [
            [
                trunc(v["vacina"], 30),
                fmt_data(v["data_aplicacao"]),
                fmt_data(v["proxima_dose"]) if v["proxima_dose"] else "Dose unica",
                trunc(v["veterinario"] or "-", 26),
                situacao_vacina(v["proxima_dose"])[0],
            ]
            for _, v in vacs.iterrows()
        ]
        pdf_tabela(pdf, ["Vacina", "Aplicação", "Reforço", "Veterinário", "Situação"],
                   linhas, [44, 24, 24, 48, 40], ["L", "C", "C", "L", "L"])
    assinatura(pdf)
    return bytes(pdf.output())


def gerar_pdf_historico(pid: int) -> bytes:
    pet = qdf(
        """SELECT p.*, t.nome AS tutor, t.telefone FROM pets p
           JOIN tutores t ON t.id = p.tutor_id WHERE p.id = ?""",
        (pid,),
    ).iloc[0]
    hist = qdf("SELECT * FROM historico WHERE pet_id = ? ORDER BY data DESC, id DESC", (pid,))
    pdf = novo_pdf(pdf_san("Histórico de Atendimentos"))
    dados_pet(pdf, pet)
    if hist.empty:
        pdf_vazio(pdf, "Nenhum atendimento registrado para este pet.")
    else:
        linhas = [
            [
                fmt_data(h["data"]),
                trunc(h["tipo"], 14),
                trunc(h["veterinario"] or "-", 22),
                f"{h['peso_kg']:.1f}" if pd.notna(h["peso_kg"]) and h["peso_kg"] is not None else "-",
                trunc(h["descricao"], 62) or "-",
            ]
            for _, h in hist.iterrows()
        ]
        pdf_tabela(pdf, ["Data", "Tipo", "Veterinário", "Peso(kg)", "Descrição"],
                   linhas, [20, 22, 38, 18, 82], ["C", "L", "L", "C", "L"])
    assinatura(pdf)
    return bytes(pdf.output())


def gerar_pdf_financeiro(mes: str) -> bytes:
    rec = float(qdf(
        "SELECT COALESCE(SUM(valor),0) s FROM lancamentos WHERE tipo='Receita' AND substr(data,1,7)=?",
        (mes,),
    ).iloc[0]["s"])
    desp = float(qdf(
        "SELECT COALESCE(SUM(valor),0) s FROM lancamentos WHERE tipo='Despesa' AND substr(data,1,7)=?",
        (mes,),
    ).iloc[0]["s"])
    df = qdf(
        """SELECT l.*, p.nome AS pet FROM lancamentos l
           LEFT JOIN pets p ON p.id = l.pet_id
           WHERE substr(l.data, 1, 7) = ? ORDER BY l.data, l.id""",
        (mes,),
    )
    rotulo = datetime.strptime(mes, "%Y-%m").strftime("%m/%Y")
    pdf = novo_pdf(f"Relatório Financeiro - {rotulo}")
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(
        0, 7,
        pdf_san(f"Receitas: {fmt_moeda(rec)}    Despesas: {fmt_moeda(desp)}    Saldo: {fmt_moeda(rec - desp)}"),
        align="C", new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(4)
    if df.empty:
        pdf_vazio(pdf, "Nenhum lançamento neste mês.")
    else:
        linhas = [
            [
                fmt_data(x["data"]), x["tipo"], trunc(x["categoria"], 16), trunc(x["descricao"], 44),
                trunc(x["forma_pagamento"] or "-", 12), fmt_moeda(x["valor"]),
            ]
            for _, x in df.iterrows()
        ]
        pdf_tabela(pdf, ["Data", "Tipo", "Categoria", "Descrição", "Pagam.", "Valor"],
                   linhas, [20, 18, 28, 72, 20, 22], ["C", "L", "L", "L", "L", "R"])
    return bytes(pdf.output())


def gerar_pdf_agenda(dia_iso: str) -> bytes:
    df = qdf(
        """SELECT a.*, p.nome AS pet, t.nome AS tutor FROM agendamentos a
           JOIN pets p ON p.id = a.pet_id
           JOIN tutores t ON t.id = p.tutor_id
           WHERE a.data = ? ORDER BY a.hora""",
        (dia_iso,),
    )
    pdf = novo_pdf(f"Agenda do dia {fmt_data(dia_iso)}")
    if df.empty:
        pdf_vazio(pdf, "Nenhum compromisso agendado para este dia.")
    else:
        linhas = [
            [
                x["hora"], trunc(x["pet"], 20), trunc(x["tutor"], 20), trunc(x["tipo"], 14),
                trunc(x["veterinario"] or "-", 22), x["status"],
            ]
            for _, x in df.iterrows()
        ]
        pdf_tabela(pdf, ["Hora", "Pet", "Tutor", "Tipo", "Veterinário", "Status"],
                   linhas, [15, 33, 35, 22, 38, 37], ["C", "L", "L", "L", "L", "L"])
    return bytes(pdf.output())


# --------------------------------------------------------------------------- #
#  Assinatura digital A1 (e-CNPJ / ICP-Brasil)
# --------------------------------------------------------------------------- #

def assinatura_ativa() -> bool:
    return get_config("cert_ativo", "0") == "1" and get_config("cert_pfx") is not None


def _carregar_signer(pfx_dados: bytes, senha: str):
    from pyhanko.sign import signers
    return signers.SimpleSigner.load_pkcs12_data(pfx_dados, (), passphrase=senha.encode("utf-8"))


def _extrair_info_cert(pfx_dados: bytes, senha: str):
    """Lê titular, CNPJ/CPF e validade do certificado A1 (sem gravar a senha)."""
    signer = _carregar_signer(pfx_dados, senha)
    cert = signer.signing_cert
    subj = cert.subject.native  # dict: {'common_name': ..., 'organization_name': ..., 'serial_number': ...}
    titular = str(subj.get("common_name") or "")
    cnpj = ""
    for chave in ("2.16.76.1.3.4", "serial_number"):
        val = str(subj.get(chave) or "")
        digitos = "".join(c for c in val if c.isdigit())
        if len(digitos) in (11, 14) and not cnpj:
            cnpj = digitos
    if ":" in titular:
        base, doc = titular.rsplit(":", 1)
        digitos = "".join(c for c in doc if c.isdigit())
        if len(digitos) in (11, 14):
            titular = base.strip()
            cnpj = cnpj or digitos
    if len(cnpj) == 14:
        cnpj = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    titular = titular or str(subj.get("organization_name") or "Certificado digital")
    return titular, cnpj, cert.not_valid_after.replace(tzinfo=None)


def carimbo_texto() -> str:
    nome = (get_config("carimbo_nome", "") or "").strip()
    crmv = (get_config("carimbo_crmv", "") or "").strip()
    titular = (get_config("cert_titular", "") or "").strip() or "CARDIOEVET"
    linha1 = "  |  ".join(p for p in (nome, crmv) if p) or "Veterinário(a) responsável"
    texto = f"{linha1}\nAssinado digitalmente por {titular} — ICP-Brasil"
    return texto.encode("latin-1", "replace").decode("latin-1")


def carimbo_preview(nome: str, crmv: str) -> str:
    titular = (get_config("cert_titular", "") or "").strip() or "<titular do certificado>"
    linha1 = "  |  ".join(p for p in (nome.strip(), crmv.strip()) if p) or "Veterinário(a) responsável"
    return f"{linha1}\nAssinado digitalmente por {titular} — ICP-Brasil"


def assinar_pdf_icp(pdf_dados: bytes, pfx_dados: bytes, senha: str, texto: str) -> bytes:
    """Aplica assinatura PAdES (ICP-Brasil) no PDF e devolve os bytes assinados."""
    import io
    from pyhanko import stamp
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    signer = _carregar_signer(pfx_dados, senha)
    entrada = io.BytesIO(pdf_dados)
    escritor = IncrementalPdfFileWriter(entrada)
    saida = io.BytesIO()
    assinador = signers.PdfSigner(
        signers.PdfSignatureMetadata(field_name="AssinaturaDigital"),
        signer=signer,
        stamp_style=stamp.TextStampStyle(stamp_text=texto),
        new_field_spec=fields.SigFieldSpec(
            "AssinaturaDigital", box=(285, 24, 570, 78), on_page=-1
        ),
    )
    assinador.sign_pdf(escritor, output=saida)
    return saida.getvalue()


def finalizar_pdf(pdf_dados: bytes) -> bytes:
    """Assina o PDF se a assinatura estiver ativa e desbloqueada na sessão."""
    if assinatura_ativa() and st.session_state.get("cert_senha"):
        try:
            return assinar_pdf_icp(pdf_dados, get_config("cert_pfx"),
                                   st.session_state["cert_senha"], carimbo_texto())
        except Exception as e:
            st.warning(f"⚠️ Não foi possível assinar digitalmente ({e}). Gerando o PDF sem assinatura.")
    return pdf_dados


def relatorios_gate_assinatura():
    """Bloco de desbloqueio da assinatura exibido no topo da página de relatórios."""
    if not assinatura_ativa():
        return
    if st.session_state.get("cert_senha"):
        titular = get_config("cert_titular", "") or "titular do certificado"
        st.caption(f"🔏 **Assinatura digital ATIVA** — os PDFs saem assinados com o certificado "
                   f"ICP-Brasil de **{titular}**.")
        return
    with st.container(border=True):
        st.markdown("##### 🔏 Assinatura digital (ICP-Brasil) disponível")
        st.caption("Informe a senha do certificado A1 **uma vez por sessão** para assinar os PDFs.")
        senha = st.text_input("Senha do certificado", type="password", key="unlock_cert")
        if senha:
            try:
                _carregar_signer(get_config("cert_pfx"), senha)
            except Exception:
                st.error("❌ Senha incorreta (ou arquivo de certificado inválido).")
            else:
                st.session_state["cert_senha"] = senha
                st.success("✅ Certificado desbloqueado — os PDFs desta sessão sairão assinados!")
                st.rerun()


def pagina_assinatura():
    st.header("🔏 Assinatura digital A1 (e-CNPJ)")
    st.caption(
        "Use seu certificado digital A1 para assinar automaticamente **todos os PDFs** gerados "
        "pelo sistema — receituários, atestados e relatórios saem com validade jurídica "
        "(assim como em plataformas como Memed), verificáveis em qualquer leitor de PDF."
    )

    tem_cert = get_config("cert_pfx") is not None

    if tem_cert:
        titular = get_config("cert_titular", "") or "—"
        cnpj = get_config("cert_cnpj", "") or "—"
        val_str = get_config("cert_validade", "") or "—"
        nome_arq = get_config("cert_arquivo", "") or "certificado.pfx"
        try:
            dias = (datetime.strptime(val_str, "%d/%m/%Y").date() - date.today()).days
        except Exception:
            dias = None
        c1, c2, c3 = st.columns(3)
        c1.metric("Titular", titular[:28])
        c2.metric("CNPJ", cnpj or "—")
        c3.metric("Válido até", val_str)
        if dias is not None and dias < 0:
            st.error("⛔ **Certificado VENCIDO!** Renove com a certificadora e reenvie o arquivo abaixo.")
        elif dias is not None and dias <= 30:
            st.warning(f"⚠️ Atenção: seu certificado vence em **{dias} dias** — providencie a renovação.")
        else:
            st.success(f"✅ Certificado instalado: `{nome_arq}`  ·  válido por mais **{dias} dias**")
    else:
        st.info("Nenhum certificado cadastrado. Envie seu arquivo **.pfx** (ou **.p12**) abaixo ⬇️")

    with st.expander("📤 " + ("Reenviar / trocar certificado" if tem_cert else "Enviar certificado"),
                     expanded=not tem_cert):
        with st.form("form_cert", clear_on_submit=True):
            arq = st.file_uploader("Arquivo do certificado *", type=["pfx", "p12"])
            senha = st.text_input("Senha do certificado *", type="password",
                                  help="A senha NUNCA é salva — só fica na memória da sua sessão no navegador.")
            enviado = st.form_submit_button("💾 Validar e salvar certificado", type="primary")
        if enviado:
            if not arq or not senha:
                st.error("Selecione o arquivo do certificado e informe a senha.")
            else:
                dados = arq.getvalue()
                try:
                    t_tit, t_cnpj, t_val = _extrair_info_cert(dados, senha)
                except Exception:
                    st.error("❌ Não foi possível abrir o certificado. Verifique se é um arquivo "
                             "**.pfx/.p12** válido e se a senha está correta.")
                else:
                    set_config("cert_pfx", dados)
                    set_config("cert_arquivo", arq.name or "certificado.pfx")
                    set_config("cert_titular", t_tit)
                    set_config("cert_cnpj", t_cnpj)
                    set_config("cert_validade", t_val.strftime("%d/%m/%Y"))
                    set_config("cert_ativo", "1")
                    st.session_state["cert_senha"] = senha
                    st.success(f"✅ Certificado de **{t_tit}** instalado e assinatura ativada!")
                    st.rerun()

    if tem_cert:
        st.divider()
        ativo = assinatura_ativa()
        novo = st.toggle("🔏 Assinar automaticamente **todos os PDFs** do sistema", value=ativo)
        if novo != ativo:
            set_config("cert_ativo", "1" if novo else "0")
            st.success("✅ Assinatura automática ATIVADA." if novo else "Assinatura automática desativada.")
            st.rerun()

        st.subheader("✍️ Carimbo visual da assinatura")
        st.caption("Este texto aparece carimbado no rodapé dos PDFs, junto da assinatura criptográfica.")
        with st.form("form_carimbo"):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome do(a) veterinário(a)",
                                 value=get_config("carimbo_nome", "") or "",
                                 placeholder="Ex.: Dr. João Alves")
            crmv = c2.text_input("CRMV", value=get_config("carimbo_crmv", "") or "",
                                 placeholder="Ex.: CRMV-SC 00000")
            if nome.strip() or crmv.strip():
                st.caption("**Prévia do carimbo:**")
                st.code(carimbo_preview(nome, crmv), language=None)
            salvar_txt = st.form_submit_button("💾 Salvar carimbo", type="primary")
        if salvar_txt:
            set_config("carimbo_nome", nome.strip())
            set_config("carimbo_crmv", crmv.strip())
            st.success("✅ Carimbo atualizado!")
            st.rerun()

        with st.expander("ℹ️ Perguntas frequentes"):
            st.markdown(
                """
**A senha do certificado fica salva no sistema?**
Não. Por segurança, a senha fica apenas na memória do seu navegador enquanto a aba está
aberta. A cada nova sessão, você a informa **uma única vez** na página 📄 Relatórios e
todos os PDFs gerados em seguida já saem assinados.

**Onde o certificado fica guardado?**
O arquivo do certificado fica no seu próprio banco de dados (Turso), junto dos demais
dados da clínica. Guarde também uma cópia de segurança do arquivo original fora do sistema.

**A assinatura tem validade jurídica?**
Sim — usa o padrão **ICP-Brasil (PAdES)**. Verifique qualquer PDF em
[verificador.iti.br](https://verificador.iti.br/) ou no painel de assinaturas do
Adobe Acrobat Reader.

**Certificado A1 vence em 1 ano. E depois?**
O app avisa quando faltar 30 dias. É só renovar com a certificadora (Serasa, Soluti,
Certisign, Valid...) e reenviar o novo arquivo aqui. Os PDFs já assinados continuam válidos.

**Posso desligar sem remover o certificado?**
Sim — use o botão liga/desliga *"Assinar automaticamente todos os PDFs"* acima.
"""
            )

        st.divider()
        with st.expander("🗑️ Remover certificado"):
            st.caption("Remove o arquivo do certificado do banco de dados. "
                       "Os PDFs voltam a sair sem assinatura digital.")
            conf = st.checkbox("Confirmo a remoção do certificado", key="conf_rm_cert")
            if st.button("Remover certificado definitivamente", disabled=not conf):
                for k in ("cert_pfx", "cert_arquivo", "cert_titular", "cert_cnpj", "cert_validade"):
                    run("DELETE FROM config WHERE chave = ?", (k,))
                set_config("cert_ativo", "0")
                st.session_state.pop("cert_senha", None)
                st.success("Certificado removido.")
                st.rerun()


# --------------------------------------------------------------------------- #
#  Página: Relatórios
# --------------------------------------------------------------------------- #

def pagina_relatorios():
    st.header("📄 Relatórios em PDF")
    relatorios_gate_assinatura()
    tipo = st.radio(
        "Tipo de relatório",
        ["Carteirinha de vacinação (pet)", "Histórico de atendimentos (pet)",
         "Financeiro do mês", "Agenda do dia"],
        horizontal=True,
    )
    st.divider()

    pets = qdf(
        """SELECT p.id, p.nome, t.nome AS tutor FROM pets p
           JOIN tutores t ON t.id = p.tutor_id ORDER BY p.nome"""
    )

    if tipo in ("Carteirinha de vacinação (pet)", "Histórico de atendimentos (pet)"):
        if pets.empty:
            st.info("Cadastre primeiro um tutor e um pet para gerar relatórios.")
            return
        op = {f"{r['nome']} — {r['tutor']} (#{r['id']})": r["id"] for _, r in pets.iterrows()}
        sel = st.selectbox("Selecione o pet", list(op.keys()))
        pid = op[sel]
        nome = pets[pets["id"] == pid].iloc[0]["nome"].lower().replace(" ", "_")

        if tipo == "Carteirinha de vacinação (pet)":
            n = qdf("SELECT COUNT(*) c FROM vacinas WHERE pet_id = ?", (pid,)).iloc[0]["c"]
            st.caption(f"{n} vacina(s) registrada(s) para este pet.")
            dados = finalizar_pdf(gerar_pdf_carteirinha(pid))
            st.download_button("⬇️ Baixar carteirinha em PDF", dados,
                               f"carteirinha_{nome}.pdf", "application/pdf", type="primary")
            botao_imprimir_pdf(dados, f"carteirinha_{pid}")
        else:
            n = qdf("SELECT COUNT(*) c FROM historico WHERE pet_id = ?", (pid,)).iloc[0]["c"]
            st.caption(f"{n} atendimento(s) registrado(s) para este pet.")
            dados = finalizar_pdf(gerar_pdf_historico(pid))
            st.download_button("⬇️ Baixar histórico em PDF", dados,
                               f"historico_{nome}.pdf", "application/pdf", type="primary")
            botao_imprimir_pdf(dados, f"histrel_{pid}")

    elif tipo == "Financeiro do mês":
        meses_db = qdf("SELECT DISTINCT substr(data, 1, 7) AS m FROM lancamentos")["m"].tolist()
        opcoes = sorted({date.today().strftime("%Y-%m"), *meses_db}, reverse=True)
        mes = st.selectbox(
            "Mês de referência", opcoes,
            format_func=lambda m: datetime.strptime(m, "%Y-%m").strftime("%m/%Y"),
        )
        dados = finalizar_pdf(gerar_pdf_financeiro(mes))
        st.download_button("⬇️ Baixar relatório financeiro", dados,
                           f"financeiro_{mes}.pdf", "application/pdf", type="primary")
        botao_imprimir_pdf(dados, f"fin_{mes}")

    else:  # Agenda do dia
        dia = st.date_input("Dia", value=date.today(), format="DD/MM/YYYY")
        dados = finalizar_pdf(gerar_pdf_agenda(dia.isoformat()))
        st.download_button("⬇️ Baixar agenda em PDF", dados,
                           f"agenda_{dia.isoformat()}.pdf", "application/pdf", type="primary")
        botao_imprimir_pdf(dados, f"agenda_{dia.isoformat()}")


# --------------------------------------------------------------------------- #
#  Página: Recibos e Nota Fiscal (modelo)
# --------------------------------------------------------------------------- #

FORMAS_PAGAMENTO = ["Dinheiro", "PIX", "Cartão de débito", "Cartão de crédito",
                    "Transferência bancária", "Boleto", "Outro"]


def gerar_pdf_recibo(num: int, recebido_de: str, valor: float, servico: str,
                     forma: str, data_iso: str, obs: str, cidade: str) -> bytes:
    """Recibo profissional com valor por extenso, caixa de valor e assinatura."""
    ano = datetime.strptime(data_iso, "%Y-%m-%d").year
    pdf = novo_pdf("RECIBO", subtitulo=f"Nº {num:04d}/{ano}")
    pdf.set_font("helvetica", "", 11)

    pdf_campo(pdf, "Recebido de:", recebido_de or "—")
    pdf_campo(pdf, "Referente a:", servico or "—")
    pdf_campo(pdf, "Forma pagto.:", forma or "—")
    pdf_campo(pdf, "Data:", fmt_data(data_iso))
    if obs.strip():
        pdf_campo(pdf, "Observações:", obs.strip())
    pdf.ln(6)

    # caixa de destaque do valor
    y = pdf.get_y()
    pdf.set_draw_color(22, 101, 96)
    pdf.set_fill_color(233, 245, 243)
    pdf.set_line_width(0.6)
    pdf.rect(45, y, 120, 16, style="DF")
    pdf.set_xy(45, y + 3.5)
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(22, 101, 96)
    pdf.cell(120, 9, pdf_san(fmt_moeda(valor)), align="C")
    pdf.set_y(y + 20)
    pdf.set_text_color(60)
    pdf.set_font("helvetica", "I", 9.5)
    pdf.multi_cell(0, 5, pdf_san(f"Correspondente a: {valor_por_extenso(valor)}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    d = datetime.strptime(data_iso, "%Y-%m-%d")
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]
    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(30)
    pdf.cell(0, 6, pdf_san(f"{(cidade or 'Penha/SC')}, {d.day} de {meses[d.month - 1]} de {d.year}."),
             new_x="LMARGIN", new_y="NEXT")
    assinatura(pdf)
    return bytes(pdf.output())


def gerar_pdf_nota_modelo(num: int, emitente: str, cnpj_emi: str, tomador: str,
                          doc_tom: str, servicos, data_iso: str, obs: str) -> bytes:
    """Nota de serviço 'modelo' (SEM valor fiscal) com dados prontos p/ prefeitura."""
    ano = datetime.strptime(data_iso, "%Y-%m-%d").year
    pdf = novo_pdf("NOTA FISCAL DE SERVIÇO — MODELO", subtitulo=f"Nº {num:04d}/{ano} · Série A")

    pdf.set_font("helvetica", "B", 10)
    pdf.set_text_color(22, 101, 96)
    pdf.cell(0, 6, "EMITENTE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30)
    pdf_campo(pdf, "Nome/Razão:", emitente or "—")
    pdf_campo(pdf, "CNPJ:", cnpj_emi or "—")
    pdf.ln(3)

    pdf.set_font("helvetica", "B", 10)
    pdf.set_text_color(22, 101, 96)
    pdf.cell(0, 6, "TOMADOR DO SERVIÇO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30)
    pdf_campo(pdf, "Nome:", tomador or "—")
    if doc_tom.strip():
        pdf_campo(pdf, "CPF/CNPJ:", doc_tom.strip())
    pdf.ln(3)

    pdf.set_font("helvetica", "B", 10)
    pdf.set_text_color(22, 101, 96)
    pdf.cell(0, 6, "DISCRIMINAÇÃO DOS SERVIÇOS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30)
    linhas = [[trunc(d, 60), f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")]
              for d, v in servicos]
    pdf_tabela(pdf, ["Descrição dos serviços", "Valor (R$)"], linhas, [150, 30], ["L", "R"])
    total = sum(v for _, v in servicos)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(150, 7, pdf_san("TOTAL"), border=1)
    pdf.cell(30, 7, pdf_san(fmt_moeda(total).replace("R$ ", "")), border=1, align="R")
    pdf.ln(8)
    pdf_campo(pdf, "Data emissão:", fmt_data(data_iso))
    if obs.strip():
        pdf_campo(pdf, "Observações:", obs.strip())
    pdf.ln(2)

    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(150, 40, 40)
    pdf.multi_cell(0, 5, pdf_san(
        "AVISO: documento gerado por modelo interno — SEM VALOR FISCAL. "
        "A NFS-e oficial (com validade junto à Receita Federal) deve ser emitida no "
        "portal de notas da Prefeitura do seu município, usando os dados acima."
    ), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30)
    assinatura(pdf)
    return bytes(pdf.output())


def pagina_recibos():
    st.header("🧾 Recibos e Nota de Serviço")
    relatorios_gate_assinatura()
    aba = st.radio("Documento", ["🧾 Recibo de pagamento", "📄 Nota de serviço (modelo)"],
                   horizontal=True)
    st.divider()

    if aba == "🧾 Recibo de pagamento":
        origem = st.radio("Gerar recibo a partir de:", ["💰 Lançamento do financeiro", "✏️ Formulário livre"],
                          horizontal=True)

        nome = servico = forma = ""
        valor = 0.0
        if origem == "💰 Lançamento do financeiro":
            recs = qdf(
                """SELECT l.*, p.nome AS pet, t.nome AS tutor FROM lancamentos l
                   LEFT JOIN pets p ON p.id = l.pet_id
                   LEFT JOIN tutores t ON t.id = p.tutor_id
                   WHERE l.tipo = 'Receita' ORDER BY l.id DESC LIMIT 100"""
            )
            if recs.empty:
                st.info("Nenhuma receita no financeiro ainda. Use o formulário livre ou lance uma receita em 💰 Financeiro.")
                return
            op = {
                f"#{int(r['id'])} · {fmt_data(r['data'])} · {fmt_moeda(r['valor'])} · "
                f"{trunc(r['descricao'], 30)} · {r['pet'] or '-'} ({r['tutor'] or 'sem tutor'})": int(r["id"])
                for _, r in recs.iterrows()
            }
            sel = st.selectbox("Selecione a receita", list(op.keys()))
            lid = op[sel]
            r = recs[recs["id"] == lid].iloc[0]
            nome = r["tutor"] or ""
            servico = r["descricao"] or "Serviços veterinários"
            if r.get("pet"):
                servico = f"{servico} — Pet: {r['pet']}"
            valor = float(r["valor"])
            forma = r["forma_pagamento"] if r["forma_pagamento"] in FORMAS_PAGAMENTO else "PIX"
            sufixo = str(lid)
        else:
            sufixo = "livre"

        def_i = FORMAS_PAGAMENTO.index(forma) if forma in FORMAS_PAGAMENTO else 1
        with st.form(f"form_recibo_{sufixo}"):
            c1, c2 = st.columns(2)
            f_nome = c1.text_input("Recebido de (tutor/cliente) *", value=nome)
            f_valor = c2.number_input("Valor (R$) *", min_value=0.0, value=valor,
                                      step=10.0, format="%.2f")
            f_serv = st.text_input("Referente a (serviço/pet) *", value=servico)
            c3, c4 = st.columns(2)
            f_forma = c3.selectbox("Forma de pagamento", FORMAS_PAGAMENTO, index=def_i)
            f_data = c4.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            f_obs = st.text_input("Observações (opcional)")
            f_cid = st.text_input("Local (cidade/UF)", value=get_config("rec_cidade", "Penha/SC") or "Penha/SC")
            gerar = st.form_submit_button("🧾 Gerar recibo", type="primary")

        if gerar:
            if not f_nome.strip() or f_valor <= 0 or not f_serv.strip():
                st.error("Preencha: recebido de, valor (maior que zero) e referente a.")
            else:
                num = proximo_numero("recibo_seq")
                set_config("rec_cidade", f_cid.strip() or "Penha/SC")
                pdf_bytes = finalizar_pdf(gerar_pdf_recibo(
                    num, f_nome.strip(), f_valor, f_serv.strip(), f_forma,
                    f_data.isoformat(), f_obs, f_cid.strip()))
                st.session_state["recibo_pdf"] = pdf_bytes
                st.session_state["recibo_nome"] = f"recibo_{num:04d}_{f_nome.strip().lower().replace(' ', '_')[:20]}.pdf"
        if st.session_state.get("recibo_pdf"):
            st.download_button("⬇️ Baixar recibo em PDF", st.session_state["recibo_pdf"],
                               st.session_state["recibo_nome"], "application/pdf", type="primary")
            botao_imprimir_pdf(st.session_state["recibo_pdf"], "recibo_atual")

    else:  # Nota modelo
        st.caption("📌 Documento **visual** para referência interna — a NFS-e oficial (valor fiscal) "
                   "você emite no portal da prefeitura **copiando os dados** que o app monta aqui.")

        c1, c2 = st.columns(2)
        emi = c1.text_input("Emitente (sua clínica)",
                            value=get_config("cert_titular", "") or "")
        cnpj = c2.text_input("CNPJ do emitente",
                             value=get_config("cert_cnpj", "") or "")

        tuts = qdf("SELECT nome, cpf FROM tutores ORDER BY nome")
        lista_t = ["(digitar outro)"] + tuts["nome"].tolist()
        tom_sel = st.selectbox("Tomador (seu cliente)", lista_t)
        if tom_sel == "(digitar outro)":
            c3, c4 = st.columns(2)
            tom = c3.text_input("Nome do tomador")
            doc_t = c4.text_input("CPF/CNPJ do tomador (opcional)")
        else:
            tom = tom_sel
            doc_t = (tuts[tuts["nome"] == tom_sel].iloc[0]["cpf"] or "") if not tuts.empty else ""
            st.caption(f"Doc. do tomador: {doc_t or 'não informado'}")

        st.markdown("**Serviços** (descrição + valor)")
        svcs = []
        for i in range(4):
            c5, c6 = st.columns([5, 2])
            d = c5.text_input(f"Serviço {i + 1}", key=f"nf_d{i}",
                              placeholder="Ex.: Consulta clínica — Pet Juma" if i == 0 else "", label_visibility="visible")
            v = c6.number_input(f"Valor R$ {i + 1}", min_value=0.0, step=10.0, format="%.2f", key=f"nf_v{i}")
            if d.strip() and v > 0:
                svcs.append((d.strip(), v))
        total = sum(v for _, v in svcs)
        st.metric("Total da nota", fmt_moeda(total))

        c7, c8 = st.columns(2)
        nf_data = c7.date_input("Data de emissão", value=date.today(), format="DD/MM/YYYY")
        nf_obs = c8.text_input("Observações (opcional)")

        if st.button("📄 Gerar nota (modelo) + dados p/ prefeitura", type="primary"):
            if not emi.strip() or not tom.strip() or not svcs:
                st.error("Preencha emitente, tomador e pelo menos 1 serviço com valor.")
            else:
                num = proximo_numero("nf_seq")
                pdf_bytes = finalizar_pdf(gerar_pdf_nota_modelo(
                    num, emi.strip(), cnpj.strip(), tom.strip(), doc_t.strip(),
                    svcs, nf_data.isoformat(), nf_obs))
                st.session_state["nf_pdf"] = pdf_bytes
                st.session_state["nf_num"] = num
                resumo = (
                    f"PREFEITURA DE PENHA — EMISSÃO NFS-e (dados prontos)\n"
                    f"===============================================\n"
                    f"Emitente: {emi.strip()}\n"
                    f"CNPJ: {cnpj.strip() or '-'}\n"
                    f"Tomador: {tom.strip()}\n"
                    f"Doc. tomador: {doc_t.strip() or '-'}\n"
                    f"Data: {fmt_data(nf_data.isoformat())}\n"
                    f"-----------------------------------------------\n"
                    + "\n".join(f"• {d} — {fmt_moeda(v)}" for d, v in svcs) +
                    f"\n-----------------------------------------------\n"
                    f"TOTAL: {fmt_moeda(total)}\n"
                    f"Obs.: {nf_obs.strip() or '-'}"
                )
                st.session_state["nf_resumo"] = resumo

        if st.session_state.get("nf_pdf"):
            ano = datetime.strptime(nf_data.isoformat(), "%Y-%m-%d").year
            st.download_button("⬇️ Baixar nota (modelo) em PDF", st.session_state["nf_pdf"],
                               f"nota_{st.session_state['nf_num']:04d}_{ano}.pdf", "application/pdf",
                               type="primary")
            botao_imprimir_pdf(st.session_state["nf_pdf"],
                               f"nota_{st.session_state['nf_num']:04d}")
            with st.expander("📋 Copie estes dados no portal da prefeitura", expanded=True):
                st.code(st.session_state.get("nf_resumo", ""), language=None)


# --------------------------------------------------------------------------- #
#  Página: Login e Usuários
# --------------------------------------------------------------------------- #

PAPEIS = {"admin": "Administrador", "veterinario": "Veterinário(a)", "recepcao": "Recepção"}
PAPEIS_ORDEM = ["recepcao", "veterinario", "admin"]


def tela_login():
    col_img, _ = st.columns([1, 2])
    if os.path.exists("assets/logo_login.png"):
        with col_img:
            st.image("assets/logo_login.png", use_container_width=True)
    st.title("❤️ CARDIOEVET")
    st.subheader("Gestão de clínica veterinária")
    st.divider()
    col, _ = st.columns([1, 2])
    with col:
        with st.form("form_login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar 🔑", type="primary", use_container_width=True):
                df = qdf("SELECT * FROM usuarios WHERE usuario = ?", (usuario.strip().lower(),))
                if not df.empty and verificar_senha(senha, df.iloc[0]["senha_hash"]):
                    r = df.iloc[0]
                    st.session_state.usuario = {
                        "id": int(r["id"]), "usuario": r["usuario"],
                        "nome": r["nome"] or r["usuario"], "papel": r["papel"],
                    }
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")
        st.info("🔑 **Primeiro acesso?** Entre com **admin / admin123** e troque a senha depois "
                "em **🔑 Trocar minha senha** (na barra lateral).")


def trocar_minha_senha():
    with st.sidebar.expander("🔑 Trocar minha senha"):
        with st.form("form_minha_senha", clear_on_submit=True):
            atual = st.text_input("Senha atual", type="password")
            nova = st.text_input("Nova senha (mín. 4 caracteres)", type="password")
            if st.form_submit_button("Salvar nova senha"):
                eu = st.session_state.usuario
                reg = qdf("SELECT senha_hash FROM usuarios WHERE id = ?", (eu["id"],)).iloc[0]
                if not verificar_senha(atual, reg["senha_hash"]):
                    st.error("Senha atual incorreta.")
                elif len(nova) < 4:
                    st.error("A nova senha deve ter pelo menos 4 caracteres.")
                else:
                    run("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (hash_senha(nova), eu["id"]))
                    st.success("Senha alterada! ✅")


def pagina_usuarios():
    st.header("🔐 Usuários do sistema")
    eu = st.session_state.usuario

    df = qdf("SELECT id, usuario, nome, papel, criado_em FROM usuarios ORDER BY usuario")
    view = df.copy()
    view["papel"] = view["papel"].map(lambda p: PAPEIS.get(p, p))
    st.dataframe(
        view, hide_index=True, use_container_width=True,
        column_config={
            "id": st.column_config.NumberColumn("#", width="small"),
            "usuario": "Usuário", "nome": "Nome", "papel": "Papel", "criado_em": "Criado em",
        },
    )

    with st.expander("➕ Novo usuário"):
        with st.form("form_novo_usuario", clear_on_submit=True):
            c1, c2 = st.columns(2)
            usr = c1.text_input("Nome de usuário (login) *")
            nome = c2.text_input("Nome completo")
            c3, c4 = st.columns(2)
            senha = c3.text_input("Senha *", type="password")
            papel = c4.selectbox("Papel", PAPEIS_ORDEM, format_func=lambda p: PAPEIS[p])
            if st.form_submit_button("💾 Criar usuário", type="primary"):
                if not usr.strip() or len(senha) < 4:
                    st.error("Informe um usuário e uma senha com pelo menos 4 caracteres.")
                else:
                    try:
                        run(
                            "INSERT INTO usuarios (usuario, nome, senha_hash, papel) VALUES (?,?,?,?)",
                            (usr.strip().lower(), nome.strip(), hash_senha(senha), papel),
                        )
                        st.success(f"Usuário **{usr.strip().lower()}** criado!")
                        st.rerun()
                    except Exception as e:
                        if "UNIQUE" in str(e).upper():
                            st.error("Esse nome de usuário já existe.")
                        else:
                            st.error(f"Erro ao criar usuário: {e}")

    with st.expander("✏️ Editar, redefinir senha ou excluir"):
        op = {f"{r['usuario']} — {r['nome'] or '-'} ({PAPEIS.get(r['papel'], r['papel'])})": r["id"]
              for _, r in df.iterrows()}
        sel = st.selectbox("Selecione o usuário", list(op.keys()))
        uid = op[sel]
        reg = df[df["id"] == uid].iloc[0]

        with st.form("form_edit_usuario"):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome completo", value=reg["nome"] or "")
            papel = c2.selectbox(
                "Papel", PAPEIS_ORDEM, format_func=lambda p: PAPEIS[p],
                index=PAPEIS_ORDEM.index(reg["papel"]) if reg["papel"] in PAPEIS_ORDEM else 0,
            )
            nova_senha = st.text_input("Nova senha (deixe em branco para manter)", type="password")
            if st.form_submit_button("💾 Salvar alterações", type="primary"):
                if nova_senha and len(nova_senha) < 4:
                    st.error("A nova senha deve ter pelo menos 4 caracteres.")
                elif uid == eu["id"] and papel != "admin":
                    st.error("Você não pode remover o seu próprio papel de Administrador.")
                else:
                    if nova_senha:
                        run("UPDATE usuarios SET nome=?, papel=?, senha_hash=? WHERE id=?",
                            (nome.strip(), papel, hash_senha(nova_senha), uid))
                    else:
                        run("UPDATE usuarios SET nome=?, papel=? WHERE id=?", (nome.strip(), papel, uid))
                    st.success("Usuário atualizado!")
                    st.rerun()

        st.markdown("**🗑️ Excluir usuário**")
        if uid == eu["id"]:
            st.caption("Você não pode excluir o usuário com o qual está logado.")
        else:
            confirma = st.checkbox("Confirmo que desejo excluir este usuário", key=f"conf_user_{uid}")
            if st.button("Excluir usuário", disabled=not confirma, key=f"del_user_{uid}"):
                run("DELETE FROM usuarios WHERE id = ?", (uid,))
                st.success("Usuário excluído.")
                st.rerun()


def _ler_blob(tabela: str, rid: int) -> bytes:
    """Lê um BLOB de forma à prova de encoding (hexadecimal puro, em pedaços).

    `tabela` deve ser um nome de tabela interno/conhecido (anexos, laudo_imagens).
    """
    if nuvem_ativa():
        total = qdf(f"SELECT length(dados) AS n FROM {tabela} WHERE id = ?", (rid,)).iloc[0]["n"]
        total = int(total or 0)
        if not total:
            return b""
        CHUNK = 100_000  # bytes por query — respostas ficam pequenas e seguras
        hex_partes = []
        pos = 1
        while pos <= total:
            h = qdf(f"SELECT hex(substr(dados, ?, ?)) AS h FROM {tabela} WHERE id = ?",
                    (pos, CHUNK, rid)).iloc[0]["h"] or ""
            hex_partes.append(str(h))
            pos += CHUNK
        dados = bytes.fromhex("".join(hex_partes))
        if len(dados) != total:
            raise RuntimeError(
                f"leitura incompleta do blob ({len(dados)} de {total} bytes) — tente novamente"
            )
        return dados
    return bytes(qdf(f"SELECT dados FROM {tabela} WHERE id = ?", (rid,)).iloc[0]["dados"] or b"")


def ler_anexo_dados(aid: int) -> bytes:
    """Lê o BLOB do anexo de forma à prova de encoding (hexadecimal puro, em pedaços)."""
    return _ler_blob("anexos", aid)


def ler_laudo_imagens(laudo_id: int) -> list:
    """Retorna [(legenda, bytes), ...] das imagens JPG do laudo, na ordem."""
    rows = qdf("SELECT id, legenda FROM laudo_imagens WHERE laudo_id = ? ORDER BY ordem, id",
               (int(laudo_id),))
    imgs = []
    for _, r in rows.iterrows():
        try:
            imgs.append(((r["legenda"] or "").strip(), _ler_blob("laudo_imagens", int(r["id"]))))
        except Exception as e:
            st.warning(f"⚠️ Não foi possível ler uma das imagens do laudo ({e}). "
                       "Ela foi omitida do PDF — tente novamente ou recadastre a imagem.")
    return imgs


# --------------------------------------------------------------------------- #
#  Página: Exames e anexos
# --------------------------------------------------------------------------- #

def pagina_exames():
    st.header("📎 Exames e anexos")

    pets = qdf(
        """SELECT p.id, p.nome, t.nome AS tutor FROM pets p
           JOIN tutores t ON t.id = p.tutor_id ORDER BY p.nome"""
    )
    if pets.empty:
        st.info("Cadastre primeiro um **tutor** e um **pet** para anexar exames.")
        return

    op = {f"{r['nome']} — {r['tutor']} (#{r['id']})": r["id"] for _, r in pets.iterrows()}
    sel = st.selectbox("Selecione o pet", list(op.keys()))
    pid = op[sel]

    n_anexos = qdf("SELECT COUNT(*) c FROM anexos WHERE pet_id = ?", (pid,)).iloc[0]["c"]

    if "ex_up" not in st.session_state:
        st.session_state.ex_up = 0
    with st.expander("➕ Enviar arquivo", expanded=n_anexos == 0):
        arquivos = st.file_uploader(
            "Arquivos (PDF, PNG ou JPG — até 10 MB cada)",
            type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True,
            key=f"up_exame_{st.session_state.ex_up}",
        )
        desc = st.text_input("Descrição (opcional)", placeholder="Ex.: Hemograma completo, Raio-X de tórax…")
        if st.button("💾 Salvar anexos", type="primary", disabled=not arquivos):
            enviados = 0
            for f in arquivos:
                if f.size > 10 * 1024 * 1024:
                    st.warning(f"⚠️ **{f.name}** tem mais de 10 MB e não foi anexado.")
                    continue
                run(
                    "INSERT INTO anexos (pet_id, nome, descricao, mime, tamanho, dados) VALUES (?,?,?,?,?,?)",
                    (pid, f.name, desc.strip(), f.type or "application/octet-stream",
                     int(f.size), sqlite3.Binary(f.getvalue())),
                )
                enviados += 1
            if enviados:
                st.success(f"{enviados} arquivo(s) anexado(s)!")
                st.session_state.ex_up += 1
                st.rerun()

    df = qdf(
        "SELECT id, nome, descricao, mime, tamanho, criado_em FROM anexos WHERE pet_id = ? ORDER BY id DESC",
        (pid,),
    )
    st.divider()
    st.subheader("🗂️ Arquivos deste pet")
    if df.empty:
        st.info("Nenhum exame anexado para este pet ainda.")
        return

    view = df.copy()
    view["Tamanho"] = view["tamanho"].map(lambda t: f"{t / 1024:.0f} KB" if pd.notna(t) else "—")
    view["Enviado em"] = view["criado_em"].map(
        lambda s: f"{fmt_data(str(s)[:10])} {str(s)[11:16]}" if s else "—"
    )
    st.dataframe(
        view[["nome", "descricao", "mime", "Tamanho", "Enviado em"]],
        hide_index=True, use_container_width=True,
        column_config={"nome": "Arquivo", "descricao": "Descrição", "mime": "Tipo"},
    )

    st.divider()
    st.subheader("🔍 Visualizar, baixar ou excluir")
    op2 = {f"{r['nome']} — {r['descricao'] or 'sem descrição'} (#{r['id']})": r["id"] for _, r in df.iterrows()}
    sel2 = st.selectbox("Selecione o arquivo", list(op2.keys()))
    aid = op2[sel2]
    reg = qdf("SELECT id, nome, descricao, mime, tamanho, criado_em FROM anexos WHERE id = ?", (aid,)).iloc[0]
    try:
        dados = ler_anexo_dados(aid)
    except Exception as e:
        st.error(f"❌ Não foi possível ler o arquivo do banco em nuvem: {e}. "
                 f"Tente novamente — se o erro persistir, reenvie o arquivo.")
        return

    c1, c2 = st.columns([1, 3])
    c1.download_button("⬇️ Baixar arquivo", dados, reg["nome"],
                       reg["mime"] or "application/octet-stream", type="primary")
    if str(reg["mime"]).startswith("image"):
        st.image(dados, caption=reg["nome"], width=440)
    elif reg["mime"] == "application/pdf":
        botao_imprimir_pdf(dados, f"anexo_{aid}", altura=700)
    else:
        st.caption("A pré-visualização está disponível apenas para imagens e PDFs. "
                   "Use o botão de download para abrir o arquivo.")

    st.markdown("**🗑️ Excluir anexo**")
    confirma = st.checkbox("Confirmo que desejo excluir este arquivo", key=f"conf_anx_{aid}")
    if st.button("Excluir anexo", disabled=not confirma, key=f"del_anx_{aid}"):
        run("DELETE FROM anexos WHERE id = ?", (aid,))
        st.success("Anexo excluído.")
        st.rerun()


# --------------------------------------------------------------------------- #
#  Página: Nuvem (Turso) — configuração e migração
# --------------------------------------------------------------------------- #

TABELAS_MIGRACAO = ["tutores", "pets", "historico", "agendamentos", "vacinas", "lancamentos", "anexos"]


def migrar_local_para_nuvem() -> list:
    """Copia os dados do SQLite local para a nuvem (sem sobrescrever o que já existe lá)."""
    relatorio = []
    for tabela in TABELAS_MIGRACAO:
        try:
            local = qdf_local(f"SELECT * FROM {tabela}")
        except Exception:
            local = pd.DataFrame()
        try:
            na_nuvem = qdf(f"SELECT COUNT(*) c FROM {tabela}").iloc[0]["c"]
        except Exception as e:
            relatorio.append(f"❌ **{tabela}**: erro ao consultar a nuvem ({e})")
            continue
        if na_nuvem > 0:
            relatorio.append(f"⏭️ **{tabela}**: a nuvem já tem {na_nuvem} registro(s) — nada alterado.")
            continue
        if local.empty:
            relatorio.append(f"ℹ️ **{tabela}**: sem dados locais para migrar.")
            continue
        campos = list(local.columns)
        marcas = ",".join("?" * len(campos))
        sql = f"INSERT INTO {tabela} ({','.join(campos)}) VALUES ({marcas})"
        erros = 0
        for _, linha in local.iterrows():
            vals = [None if pd.isna(v) else v for v in linha.tolist()]
            try:
                run(sql, tuple(vals))
            except Exception:
                erros += 1
        ok = len(local) - erros
        relatorio.append(
            f"✅ **{tabela}**: {ok} registro(s) migrados" + (f" ({erros} erro(s))." if erros else ".")
        )
    return relatorio


# --------------------------------------------------------------------------- #
#  Laudos ultrassonográficos (US abdominal + ecocardiograma)
# --------------------------------------------------------------------------- #

_ACHADO_PADRAO = "Sem alterações ecográficas evidentes."

CAMPOS_US_ABDOMINAL = [
    "Fígado", "Vias biliares e vesícula biliar", "Baço",
    "Rim direito", "Rim esquerdo", "Bexiga urinária",
    "Estômago", "Alças intestinais", "Pâncreas",
    "Glândulas adrenais", "Linfonodos", "Útero e ovários / Próstata",
    "Cavidade peritoneal",
]

CAMPOS_ECO_TEXTO = [
    "Anatomia e função sistólica (modo-M / bidimensional)",
    "Valva mitral", "Valva aórtica", "Valva tricúspide", "Valva pulmonar",
    "Doppler — fluxos, refluxos e pressões estimadas", "Pericárdio",
]

MEDIDAS_ECO = [
    "AO (mm)", "AE (mm)", "Relação AE/AO",
    "DIVEd (mm)", "SIVd (mm)", "PLVEd (mm)",
    "DIVEs (mm)", "SIVs (mm)", "PLVEs (mm)",
    "FE (%)", "FS (%)", "FC (bpm)",
]


def _laudo_default_dados(tipo: str) -> dict:
    campos = CAMPOS_US_ABDOMINAL if tipo == "abdominal" else CAMPOS_ECO_TEXTO
    dados = {c: _ACHADO_PADRAO for c in campos}
    if tipo == "eco":
        dados["medidas"] = {m: "" for m in MEDIDAS_ECO}
    return dados


def gerar_pdf_laudo(tipo: str, numero: int, pet, dados: dict, conclusao: str,
                    recomendacoes: str, data_iso: str, veterinario: str,
                    cidade: str, imagens: list | None = None) -> bytes:
    """Gera o PDF do laudo ultrassonográfico (abdominal ou ecocardiográfico).

    `imagens`: lista de (legenda, bytes_jpg) exibida em grade após os achados.
    """
    if tipo == "abdominal":
        titulo = "LAUDO DE ULTRASSONOGRAFIA ABDOMINAL"
        campos = CAMPOS_US_ABDOMINAL
    else:
        titulo = "LAUDO ECOCARDIOGRÁFICO (MODO-M, BIDIMENSIONAL E DOPPLER)"
        campos = CAMPOS_ECO_TEXTO
    ano = datetime.strptime(data_iso, "%Y-%m-%d").year
    pdf = novo_pdf(titulo, subtitulo=f"Nº {numero:04d}/{ano}")
    dados_pet(pdf, pet)
    pdf_campo(pdf, "Data do exame:", fmt_data(data_iso))
    if veterinario.strip():
        pdf_campo(pdf, "Examinador:", veterinario.strip())
    pdf.ln(3)

    def _campo_secao(rotulo: str, texto: str):
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(22, 101, 96)
        pdf.cell(0, 5.5, pdf_san(rotulo), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30)
        pdf.set_font("helvetica", "", 9.5)
        pdf.multi_cell(0, 4.8, pdf_san((texto or "").strip() or "Não avaliado."),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)

    if tipo == "eco":
        medidas = dados.get("medidas", {}) or {}
        linhas, atual = [], []
        for m in MEDIDAS_ECO:
            v = str(medidas.get(m, "") or "").strip()
            if v:
                atual.append((m, v))
                if len(atual) == 3:
                    linhas.append(atual)
                    atual = []
        if atual:
            while len(atual) < 3:
                atual.append(("", ""))
            linhas.append(atual)
        if linhas:
            pdf.set_font("helvetica", "B", 11)
            pdf.set_text_color(22, 101, 96)
            pdf.cell(0, 7, "MEDIDAS", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(30)
            pdf_tabela(pdf,
                       ["Medida", "Valor", "Medida", "Valor", "Medida", "Valor"],
                       [[a, b, c, d, e, f] for (a, b), (c, d), (e, f) in linhas],
                       [30, 30, 30, 30, 30, 30], aligns=["L", "C", "L", "C", "L", "C"])
            pdf.ln(4)
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(22, 101, 96)
        pdf.cell(0, 7, "AVALIAÇÃO", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30)
        pdf.ln(1)

    if tipo == "abdominal":
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(22, 101, 96)
        pdf.cell(0, 7, "ACHADOS ULTRASSONOGRÁFICOS", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30)
        pdf.ln(1)

    for campo in campos:
        _campo_secao(campo + ":", dados.get(campo, ""))

    # ---- Grade de imagens do exame (JPG) ------------------------------------ #
    imagens = imagens or []
    if imagens:
        pdf.ln(1)
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(22, 101, 96)
        pdf.cell(0, 7, "IMAGENS DO EXAME", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30)
        pdf.ln(1)
        W_CELL, H_CELL, GAP = 85, 54, 10  # mm — grade de 2 colunas
        for base in range(0, len(imagens), 2):
            linha = imagens[base:base + 2]
            if pdf.get_y() + H_CELL + 18 > 278:  # quebra de página antes da linha
                pdf.add_page()
            y0 = pdf.get_y()
            h_leg_max = 0.0
            for col, (legenda, img_bytes) in enumerate(linha):
                x = 15 + col * (W_CELL + GAP)
                try:
                    pdf.image(io.BytesIO(img_bytes), x=x, y=y0,
                              w=W_CELL, h=H_CELL, keep_aspect_ratio=True)
                except Exception:
                    pdf.set_xy(x, y0)
                    pdf.set_font("helvetica", "I", 8)
                    pdf.cell(W_CELL, H_CELL, "imagem indisponível", border=1, align="C")
                if legenda:
                    pdf.set_xy(x, y0 + H_CELL + 1)
                    pdf.set_font("helvetica", "", 7.5)
                    pdf.set_text_color(90)
                    y_antes = pdf.get_y()
                    pdf.multi_cell(W_CELL, 3.6, pdf_san(trunc(legenda, 130)), align="C")
                    h_leg_max = max(h_leg_max, pdf.get_y() - y_antes)
                    pdf.set_text_color(30)
            pdf.set_y(y0 + H_CELL + h_leg_max + 5)
        pdf.ln(1)

    pdf.ln(2)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(22, 101, 96)
    pdf.cell(0, 7, "CONCLUSÃO / IMPRESSÃO DIAGNÓSTICA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(30)
    pdf.set_font("helvetica", "", 10)
    pdf.set_fill_color(233, 245, 243)
    pdf.multi_cell(0, 5.2, pdf_san(conclusao.strip()), fill=True,
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    if recomendacoes.strip():
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 6, "Recomendações:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 9.5)
        pdf.multi_cell(0, 4.8, pdf_san(recomendacoes.strip()),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    d = datetime.strptime(data_iso, "%Y-%m-%d")
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, pdf_san(f"{(cidade or 'Penha/SC')}, {d.day} de {meses[d.month - 1]} de {d.year}."),
             new_x="LMARGIN", new_y="NEXT")
    assinatura(pdf)
    return bytes(pdf.output())


LIMITE_IMG_LAUDO = 4_000_000   # ~4 MB por imagem (JPG)
MAX_IMG_LAUDO = 10             # imagens por laudo


def _anexar_imagens_laudo(laudo_id: int, ctx) -> int:
    """Grava no banco as imagens JPG escolhidas no uploader do contexto `ctx` (0 = novo laudo)."""
    up_files = st.session_state.get(f"ld_up_{ctx}") or []
    if not up_files:
        return 0
    base = qdf("SELECT COALESCE(MAX(ordem), 0) m FROM laudo_imagens WHERE laudo_id = ?",
               (int(laudo_id),)).iloc[0]["m"]
    n_atual = qdf("SELECT COUNT(*) c FROM laudo_imagens WHERE laudo_id = ?",
                  (int(laudo_id),)).iloc[0]["c"]
    anexadas = 0
    for i, f in enumerate(up_files):
        if int(n_atual) + anexadas >= MAX_IMG_LAUDO:
            st.warning(f"⚠️ Limite de {MAX_IMG_LAUDO} imagens por laudo — "
                       "as demais não foram anexadas.")
            break
        b = f.getvalue()
        if not b:
            continue
        if len(b) > LIMITE_IMG_LAUDO:
            st.warning(f"⚠️ **{f.name}** tem mais de 4 MB e não foi anexada. "
                       "Reduza a imagem e tente de novo.")
            continue
        leg = (st.session_state.get(f"ld_leg_{ctx}_{i}", "") or "").strip()
        run("INSERT INTO laudo_imagens (laudo_id, ordem, legenda, dados) VALUES (?,?,?,?)",
            (int(laudo_id), int(base) + i + 1, leg, sqlite3.Binary(b)))
        anexadas += 1
    if anexadas:
        # limpa o uploader na próxima renderização (antes de o widget ser recriado)
        st.session_state[f"_ldclr_{ctx}"] = True
    return anexadas


def _uploader_imagens(ctx, rotulo: str):
    """Uploader de JPGs + campos de legenda. Retorna True se há arquivos escolhidos.

    Deve ser chamado de forma consistente em todo rerun (mesmo ctx).
    """
    if st.session_state.pop(f"_ldclr_{ctx}", False):
        st.session_state.pop(f"ld_up_{ctx}", None)
        for k in [k for k in list(st.session_state) if str(k).startswith(f"ld_leg_{ctx}_")]:
            st.session_state.pop(k, None)
    files = st.file_uploader(rotulo, type=["jpg", "jpeg"], accept_multiple_files=True,
                             key=f"ld_up_{ctx}",
                             help="Somente JPG — as imagens entram em grade no PDF do laudo.")
    if files:
        st.caption(f"{len(files)} imagem(ns) — legenda opcional (sai embaixo da imagem no PDF):")
        for i, f in enumerate(files):
            c_img, c_leg = st.columns([1, 3])
            c_img.image(f.getvalue(), width=110)
            c_leg.text_input("Legenda", key=f"ld_leg_{ctx}_{i}",
                             placeholder=f"Ex.: Fig. {i + 1} — fígado",
                             label_visibility="collapsed")
            if f.size and f.size > LIMITE_IMG_LAUDO:
                c_leg.warning(f"⚠️ {f.name}: mais de 4 MB — não será anexada.")
    return bool(files)


def _secao_upload_novo_laudo(ctx):
    """Bloco de imagens exibido no formulário de novo laudo / edição (fora do st.form)."""
    st.markdown("**📷 Imagens do exame (JPG, opcional)**")
    st.caption("Escolha as imagens agora — elas são **anexadas ao salvar o laudo**. "
               "Depois de salvo, dá para adicionar/remover imagens na lista abaixo.")
    _uploader_imagens(ctx, "Adicionar imagens JPG do exame")


def _secao_imagens_laudo_salvo(laudo_id: int, numero: int):
    """Gerencia as imagens de um laudo já salvo: ver, adicionar e excluir."""
    imgs = qdf("SELECT id, legenda FROM laudo_imagens WHERE laudo_id = ? ORDER BY ordem, id",
               (int(laudo_id),))
    with st.container(border=True):
        st.markdown(f"📷 **Imagens do laudo #{numero:04d}** ({len(imgs)} de {MAX_IMG_LAUDO})")
        for _, im in imgs.iterrows():
            c1, c2, c3 = st.columns([2, 3, 1])
            try:
                c1.image(_ler_blob("laudo_imagens", int(im["id"])), width=150)
            except Exception as e:
                c1.error(f"⚠️ Erro ao ler a imagem ({e})")
            c2.caption((im["legenda"] or "").strip() or "_(sem legenda)_")
            conf = c3.checkbox("Excluir?", key=f"limg_conf_{im['id']}")
            if c3.button("🗑️ Excluir", key=f"limg_del_{im['id']}", disabled=not conf):
                run("DELETE FROM laudo_imagens WHERE id = ?", (int(im["id"]),))
                st.success("Imagem excluída.")
                st.rerun()
        if len(imgs) >= MAX_IMG_LAUDO:
            st.info(f"Limite de {MAX_IMG_LAUDO} imagens por laudo atingido.")
        else:
            st.markdown("**➕ Adicionar imagens**")
            tem = _uploader_imagens(f"s{laudo_id}",
                                    "Escolher imagens JPG para este laudo")
            if st.button("💾 Anexar imagens agora", key=f"ld_upsave_{laudo_id}",
                         type="primary", disabled=not tem):
                n = _anexar_imagens_laudo(laudo_id, f"s{laudo_id}")
                if n:
                    st.success(f"{n} imagem(ns) anexada(s) ao laudo #{numero:04d}!")
                    st.rerun()


def _render_laudo_pdf_widgets(pdf_bytes: bytes, numero: int, pet_nome: str, key_sufixo: str):
    st.download_button(
        f"⬇️ Baixar laudo nº {numero:04d} (PDF{' assinado' if assinatura_ativa() and st.session_state.get('cert_senha') else ''})",
        pdf_bytes,
        f"laudo_{numero:04d}_{pet_nome.lower().replace(' ', '_')}.pdf",
        "application/pdf", type="primary", key=f"dl_laudo_{key_sufixo}")
    botao_imprimir_pdf(pdf_bytes, f"laudo_{key_sufixo}")


def pagina_laudos():
    st.header("🔬 Laudos ultrassonográficos")
    st.caption("Modelos próprios de **ultrassom abdominal** e **ecocardiograma**. "
               "Os campos já vêm preenchidos com \"sem alterações\" — edite apenas o que encontrou "
               "no exame. Você pode **anexar imagens JPG** do exame (saem em grade no PDF). "
               "O laudo fica salvo no cadastro do pet e sai em PDF com seu carimbo "
               "(e assinatura digital ICP-Brasil, se estiver desbloqueada).")

    pets = qdf(
        """SELECT p.id, p.nome, t.nome AS tutor FROM pets p
           JOIN tutores t ON t.id = p.tutor_id ORDER BY p.nome"""
    )
    if pets.empty:
        st.info("Cadastre um tutor e um pet primeiro.")
        return

    op = {f"{r['nome']} — {r['tutor']}": r["id"] for _, r in pets.iterrows()}
    pid = op[st.selectbox("Pet", list(op.keys()), key="ld_pet")]
    pet = qdf(
        """SELECT p.*, t.nome AS tutor, t.telefone FROM pets p
           JOIN tutores t ON t.id = p.tutor_id WHERE p.id = ?""",
        (pid,),
    ).iloc[0]

    # PDF recém-gerado sobrevive ao rerun (padrão da página de receitas)
    if st.session_state.get("ld_pdf"):
        with st.container(border=True):
            st.success(f"✅ Laudo nº {st.session_state['ld_num']:04d} "
                       f"de **{st.session_state['ld_pet']}** pronto!")
            _render_laudo_pdf_widgets(st.session_state["ld_pdf"], st.session_state["ld_num"],
                                      st.session_state["ld_pet"], "novo")

    editando = st.session_state.get("ld_edit")  # dict do laudo em edição ou None

    # ---- Novo laudo / Edição ------------------------------------------------ #
    titulo_exp = "✏️ Editando laudo nº {:04d} — clique em ✖ para cancelar".format(editando["numero"]) \
        if editando else "➕ Novo laudo"
    with st.expander(titulo_exp, expanded=True):
        if editando:
            if st.button("✖ Cancelar edição", key="ld_cancel"):
                st.session_state.pop("ld_edit", None)
                st.rerun()

        edit_id = editando["id"] if editando else 0
        tipo_lbl = ["🔊 Ultrassom abdominal", "❤️ Ecocardiograma (Doppler)"]
        tipo_ix = 1 if (editando and editando["tipo"] == "eco") else 0
        tipo_sel = st.radio("Modelo do laudo", tipo_lbl, horizontal=True,
                            index=tipo_ix, key=f"ld_tipo_{edit_id}",
                            disabled=bool(editando))
        tipo = "eco" if tipo_sel.startswith("❤️") else "abdominal"

        if editando:
            dados_ant = json.loads(editando["dados"] or "{}")
            dados_ini = _laudo_default_dados(tipo)
            dados_ini.update({k: v for k, v in dados_ant.items() if k != "medidas" or tipo == "eco"})
            if tipo == "eco":
                med = dados_ini.get("medidas") or {}
                dados_ini["medidas"] = {m: str((dados_ant.get("medidas") or {}).get(m, ""))
                                        for m in MEDIDAS_ECO}
        else:
            dados_ini = _laudo_default_dados(tipo)

        with st.form(f"form_laudo_{edit_id}_{tipo}"):
            c1, c2, c3 = st.columns(3)
            data_ex = c1.date_input("Data do exame *", format="DD/MM/YYYY",
                                    value=datetime.strptime(editando["data"], "%Y-%m-%d").date()
                                    if editando else date.today())
            vet_def = editando["veterinario"] if editando else \
                (get_config("carimbo_nome", "") or st.session_state.usuario.get("nome", ""))
            veterinario = c2.text_input("Veterinário(a) examinador(a)", value=vet_def or "")
            cidade = c3.text_input("Local (cidade/UF)",
                                   value=get_config("rec_cidade", "Penha/SC") or "Penha/SC")

            if tipo == "eco":
                st.markdown("**📏 Medidas** *(preencha só as aferidas)*")
                medidas = {}
                cols = st.columns(3)
                med_ini = dados_ini.get("medidas", {})
                for i, m in enumerate(MEDIDAS_ECO):
                    medidas[m] = cols[i % 3].text_input(
                        m, value=str(med_ini.get(m, "")), key=f"ld{edit_id}_eco_med_{i}",
                        placeholder="—")
                st.markdown("**📝 Avaliação**")

            campos = CAMPOS_US_ABDOMINAL if tipo == "abdominal" else CAMPOS_ECO_TEXTO
            descricoes = {}
            for i, campo in enumerate(campos):
                descricoes[campo] = st.text_area(
                    campo, value=dados_ini.get(campo, _ACHADO_PADRAO),
                    height=52, key=f"ld{edit_id}_{tipo}_campo_{i}")

            conclusao = st.text_area(
                "Conclusão / impressão diagnóstica *",
                value=editando["conclusao"] if editando else "", height=90,
                key=f"ld{edit_id}_{tipo}_concl",
                placeholder="Ex.: Ecoconstituição e ecogenicidade preservadas de todos os órgãos avaliados…")
            recomendacoes = st.text_area(
                "Recomendações (opcional)",
                value=editando["recomendacoes"] if editando else "", height=52,
                key=f"ld{edit_id}_{tipo}_rec",
                placeholder="Ex.: Reavaliação em 30 dias; correlacionar com exames laboratoriais.")
            reg_hist = st.checkbox("Registrar também no histórico do pet",
                                   value=True, disabled=bool(editando),
                                   help="Na edição, o registro do histórico original é mantido.")
            salvar = st.form_submit_button(
                "💾 Salvar laudo e gerar PDF" if not editando else "💾 Salvar alterações e gerar PDF",
                type="primary")

        if salvar:
            if not conclusao.strip():
                st.error("A **conclusão** é obrigatória.")
            else:
                dados_json = json.dumps(descricoes | ({"medidas": medidas} if tipo == "eco" else {}),
                                        ensure_ascii=False)
                set_config("rec_cidade", cidade.strip() or "Penha/SC")
                if editando:
                    laudo_id = edit_id
                    numero = int(editando["numero"])
                    run("""UPDATE laudos SET data=?, dados=?, conclusao=?, recomendacoes=?,
                           veterinario=? WHERE id=?""",
                        (data_ex.isoformat(), dados_json, conclusao.strip(),
                         recomendacoes.strip(), veterinario.strip(), edit_id))
                else:
                    numero = proximo_numero("laudo_seq")
                    run("""INSERT INTO laudos (pet_id, numero, data, tipo, dados, conclusao,
                                               recomendacoes, veterinario)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (pid, numero, data_ex.isoformat(), tipo, dados_json,
                         conclusao.strip(), recomendacoes.strip(), veterinario.strip()))
                    laudo_id = int(qdf("SELECT id FROM laudos WHERE numero = ?",
                                       (numero,)).iloc[0]["id"])
                    if reg_hist:
                        rotulo = "Laudo US abdominal" if tipo == "abdominal" else "Laudo ecocardiograma"
                        run("""INSERT INTO historico (pet_id, data, tipo, veterinario, descricao)
                               VALUES (?,?,?,?,?)""",
                            (pid, data_ex.isoformat(), rotulo,
                             veterinario.strip() or (get_config("carimbo_nome", "") or ""),
                             f"{rotulo} nº {numero:04d}/{data_ex.year} — {trunc(conclusao, 380)}"))
                _anexar_imagens_laudo(laudo_id, edit_id)
                pdf_bytes = finalizar_pdf(gerar_pdf_laudo(
                    tipo, numero, pet,
                    json.loads(dados_json), conclusao, recomendacoes,
                    data_ex.isoformat(), veterinario, cidade.strip(),
                    imagens=ler_laudo_imagens(laudo_id)))
                st.session_state["ld_pdf"] = pdf_bytes
                st.session_state["ld_num"] = numero
                st.session_state["ld_pet"] = pet["nome"]
                st.session_state.pop("ld_edit", None)
                st.rerun()

        # ---- Imagens do exame (JPG) — fora do formulário; anexadas ao salvar --- #
        _secao_upload_novo_laudo(edit_id)

    # ---- Laudos salvos do pet ------------------------------------------------ #
    with st.expander("📂 Laudos salvos deste pet"):
        laudos = qdf(
            "SELECT id, numero, data, tipo, dados, conclusao, recomendacoes, veterinario "
            "FROM laudos WHERE pet_id = ? ORDER BY data DESC, id DESC", (pid,))
        if laudos.empty:
            st.info("Nenhum laudo salvo para este pet ainda.")
        else:
            st.caption(f"{len(laudos)} laudo(s). O PDF pode ser gerado novamente a qualquer momento "
                       "(sai sempre atualizado, com carimbo e assinatura quando ativa).")
            for _, ld in laudos.iterrows():
                rotulo = "US abdominal" if ld["tipo"] == "abdominal" else "Ecocardiograma"
                st.markdown(f"**#{int(ld['numero']):04d}/{str(ld['data'])[:4]} — {rotulo}** "
                            f"· exame em {fmt_data(ld['data'])}"
                            + (f" · Dr(a). {ld['veterinario']}" if ld["veterinario"] else ""))
                st.caption("Conclusão: " + (trunc(ld["conclusao"], 160) or "—"))
                b1, b2, b3 = st.columns([2, 2, 3])
                if b1.button("⬇️ Gerar PDF", key=f"ld_pdf_{ld['id']}", use_container_width=True):
                    pdf_bytes = finalizar_pdf(gerar_pdf_laudo(
                        ld["tipo"], int(ld["numero"]), pet, json.loads(ld["dados"] or "{}"),
                        ld["conclusao"] or "", ld["recomendacoes"] or "", ld["data"],
                        ld["veterinario"] or "", get_config("rec_cidade", "Penha/SC") or "Penha/SC",
                        imagens=ler_laudo_imagens(ld["id"])))
                    st.session_state["ld_pdf"] = pdf_bytes
                    st.session_state["ld_num"] = int(ld["numero"])
                    st.session_state["ld_pet"] = pet["nome"]
                    st.rerun()
                if b2.button("✏️ Editar", key=f"ld_editbtn_{ld['id']}", use_container_width=True):
                    st.session_state["ld_edit"] = dict(ld)
                    st.rerun()
                conf_l = st.checkbox("Confirmo excluir", key=f"ld_conf_{ld['id']}")
                if b3.button("🗑️ Excluir laudo", key=f"ld_del_{ld['id']}", disabled=not conf_l):
                    run("DELETE FROM laudo_imagens WHERE laudo_id = ?", (int(ld["id"]),))
                    run("DELETE FROM laudos WHERE id = ?", (int(ld["id"]),))
                    st.session_state.pop("ld_edit", None)
                    st.success("Laudo excluído.")
                    st.rerun()
                _secao_imagens_laudo_salvo(int(ld["id"]), int(ld["numero"]))
                st.divider()


def pagina_nuvem():
    st.header("☁️ Banco de dados em nuvem")
    url, token = config_nuvem()
    ativo = nuvem_ativa()

    if ativo:
        st.success(
            f"☁️ **Modo nuvem ativo** — os dados ficam no Turso e são compartilhados "
            f"entre todos os acessos.\n\nServidor: `{url}`"
        )
    else:
        st.info("💾 **Modo local ativo** — os dados ficam apenas no arquivo `vetclinic.db` deste servidor.")

    with st.expander("ℹ️ Como configurar (passo a passo)", expanded=not ativo):
        st.markdown(
            """
O app usa o **Turso** — um SQLite na nuvem com plano gratuito — que fala a mesma
linguagem do banco local. Nada muda no sistema: ao conectar, todas as telas passam a
ler e gravar na nuvem automaticamente.

**Passo a passo (5 minutos):**

1. Crie uma conta grátis em **[turso.tech](https://turso.tech)** (pode entrar com GitHub/Google);
2. No painel do Turso, crie um banco (ex.: `vetclinic`);
3. Copie a **Database URL** (formato `libsql://vetclinic-xxxx.turso.io`);
4. Gere um **token de acesso** (Create Token);
5. Cole os dois nos campos abaixo, clique em **🔎 Testar conexão** e depois em **💾 Salvar e conectar**;
6. Se quiser levar os dados locais junto, use a **migração** mais abaixo. 🎉

> 💡 Usuários avançados também podem configurar por variáveis de ambiente
> (`TURSO_DATABASE_URL` e `TURSO_AUTH_TOKEN`) ou `.streamlit/secrets.toml` —
> nesse caso eles têm prioridade sobre o salvo aqui.
"""
        )

    url_sugerida = "" if (url and os.environ.get("TURSO_DATABASE_URL")) else url
    with st.form("form_nuvem"):
        nova_url = st.text_input("URL do banco *", value=url_sugerida,
                                 placeholder="libsql://seu-banco-xxxx.turso.io")
        novo_token = st.text_input("Token de acesso *", value="", type="password",
                                   placeholder="Cole aqui o token gerado no Turso")
        c1, c2 = st.columns(2)
        testar = c1.form_submit_button("🔎 Testar conexão", use_container_width=True)
        salvar = c2.form_submit_button("💾 Salvar e conectar", use_container_width=True, type="primary")

    if testar:
        if not nova_url.strip() or not novo_token.strip():
            st.error("Preencha a URL e o token para testar.")
        else:
            try:
                dbcloud.executar(normalizar_url_nuvem(nova_url), novo_token.strip(), "SELECT 1 AS ok")
                st.success("✅ Conexão bem-sucedida! Pode clicar em **Salvar e conectar**.")
            except Exception as e:
                st.error(f"❌ Falha na conexão: {e}")

    if salvar:
        if not nova_url.strip() or not novo_token.strip():
            st.error("Preencha a URL e o token para conectar.")
        else:
            salvar_config_nuvem(nova_url, novo_token)
            st.success("Configuração salva! O app agora usa a nuvem. ☁️")
            st.rerun()

    st.caption("⚠️ As credenciais ficam salvas em `db_config.json`, no mesmo servidor do app. "
               "Guarde esse arquivo com cuidado e não o compartilhe. "
               "☁️ **Deploy no Streamlit Cloud?** Prefira as *Secrets* do app "
               "(⋮ → Settings → Secrets) — arquivos locais podem ser apagados a cada reinício.")

    # ---- Migração ------------------------------------------------------------ #
    st.divider()
    st.subheader("📦 Migração de dados (local → nuvem)")
    if not ativo:
        st.caption("Conecte-se a um banco em nuvem para poder migrar os dados locais.")
    else:
        st.caption(
            "Copia os dados do `vetclinic.db` local para a nuvem. "
            "Tabelas que **já tiverem dados** na nuvem são puladas — nada é sobrescrito. "
            "Os **usuários não são migrados** (a nuvem mantém o próprio admin; crie os demais em 🔐 Usuários)."
        )
        if st.button("📦 Migrar dados locais para a nuvem agora", type="primary"):
            with st.spinner("Migrando dados…"):
                linhas = migrar_local_para_nuvem()
            for linha in linhas:
                st.markdown(f"- {linha}")
            st.success("Migração finalizada!")

    # ---- Desconectar ----------------------------------------------------------- #
    if ativo and not os.environ.get("TURSO_DATABASE_URL"):
        st.divider()
        st.subheader("🔁 Voltar ao modo local")
        st.caption("Remove o arquivo `db_config.json`. Os dados permanecem guardados na nuvem — "
                   "você pode reconectar quando quiser.")
        confirma = st.checkbox("Confirmo que quero desconectar deste banco em nuvem", key="conf_disc_nuvem")
        if st.button("Desconectar da nuvem", disabled=not confirma):
            if os.path.exists(CONFIG_PATH):
                os.remove(CONFIG_PATH)
            st.success("Desconectado! O app voltou ao banco local (💾 SQLite).")
            st.rerun()


# --------------------------------------------------------------------------- #
#  Dados de exemplo
# --------------------------------------------------------------------------- #

def carregar_exemplos():
    if qdf("SELECT COUNT(*) c FROM tutores").iloc[0]["c"] > 0:
        st.sidebar.warning("Já existem dados cadastrados. Os exemplos só podem ser carregados em uma base vazia.")
        return

    tutores = [
        ("Maria Silva", "(47) 99999-1234", "maria@email.com", "123.456.789-00", "Rua das Flores, 120 — Penha/SC", ""),
        ("João Santos", "(47) 98888-5678", "joao@email.com", "987.654.321-00", "Av. Central, 450 — Penha/SC", "Prefere contato por WhatsApp"),
        ("Ana Oliveira", "(47) 97777-9012", "ana@email.com", "456.789.123-00", "Rua do Mar, 89 — Piçarras/SC", ""),
    ]
    for t in tutores:
        run("INSERT INTO tutores (nome, telefone, email, cpf, endereco, observacoes) VALUES (?,?,?,?,?,?)", t)

    hoje = date.today()
    pets = [
        (1, "Rex", "Cachorro", "Labrador", "Macho", date(hoje.year - 4, 3, 15).isoformat(), 32.5, "Caramelo", "987654321", 1, ""),
        (1, "Mimi", "Gato", "Siamês", "Fêmea", date(hoje.year - 2, 7, 2).isoformat(), 4.2, "Cinza", "", 1, "Muito arisca com estranhos"),
        (2, "Thor", "Cachorro", "Bulldog Francês", "Macho", date(hoje.year - 1, 11, 20).isoformat(), 12.8, "Branco e preto", "", 0, "Alergia a ração com frango"),
        (3, "Loro", "Ave", "Papagaio", "Macho", None, 0.9, "Verde", "", 0, ""),
    ]
    for p in pets:
        run(
            """INSERT INTO pets (tutor_id, nome, especie, raca, sexo, nascimento, peso, cor, microchip, castrado, observacoes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            p,
        )

    historico = [
        (1, hoje.isoformat(), "Consulta", "Dra. Camila", 32.5, "Check-up anual: animal saudável. Orientada dieta."),
        (1, date(hoje.year, max(1, hoje.month - 1), 10).isoformat(), "Vacina", "Dr. Rafael", None, "Vacina V10 aplicada. Próxima dose em 12 meses."),
        (2, hoje.isoformat(), "Vacina", "Dra. Camila", 4.2, "Vacina antirrábica aplicada."),
        (3, date(hoje.year, max(1, hoje.month - 2), 5).isoformat(), "Exame", "Dr. Rafael", 12.4, "Exame de sangue de rotina: resultados dentro da normalidade."),
        (3, hoje.isoformat(), "Retorno", "Dra. Camila", 12.8, "Alergia controlada com nova dieta. Retorno em 60 dias."),
    ]
    for h in historico:
        run("INSERT INTO historico (pet_id, data, tipo, veterinario, peso_kg, descricao) VALUES (?,?,?,?,?,?)", h)

    agendamentos = [
        (1, hoje.isoformat(), "09:00", "Consulta", "Dra. Camila", "Revisão pós-check-up", "Confirmado"),
        (3, hoje.isoformat(), "14:30", "Vacina", "Dr. Rafael", "Reforço anual de vacinas", "Agendado"),
        (2, (hoje + timedelta(days=1)).isoformat(), "10:00", "Retorno", "Dra. Camila", "Reavaliar vacina em atraso", "Agendado"),
        (4, (hoje + timedelta(days=2)).isoformat(), "11:00", "Exame", "Dr. Rafael", "Exame de fezes anual", "Agendado"),
    ]
    for a in agendamentos:
        run("INSERT INTO agendamentos (pet_id, data, hora, tipo, veterinario, motivo, status) VALUES (?,?,?,?,?,?,?)", a)

    vacinas = [
        (1, "V10 (múltipla)", (hoje - timedelta(days=335)).isoformat(), (hoje + timedelta(days=30)).isoformat(), "Dr. Rafael", "L10-2531", ""),
        (2, "Antirrábica", (hoje - timedelta(days=380)).isoformat(), (hoje - timedelta(days=15)).isoformat(), "Dra. Camila", "AR-0912", ""),
        (3, "Giárdia", (hoje - timedelta(days=160)).isoformat(), (hoje + timedelta(days=20)).isoformat(), "Dr. Rafael", "", ""),
        (3, "V10 (múltipla)", (hoje - timedelta(days=195)).isoformat(), (hoje + timedelta(days=170)).isoformat(), "Dra. Camila", "", ""),
    ]
    for v in vacinas:
        run("INSERT INTO vacinas (pet_id, vacina, data_aplicacao, proxima_dose, veterinario, lote, observacao) VALUES (?,?,?,?,?,?,?)", v)

    def d(dia: int) -> str:
        return date(hoje.year, hoje.month, min(dia, hoje.day)).isoformat()

    lancamentos = [
        (d(14), "Receita", "Consulta", "Consulta de rotina - Rex", 180.0, "PIX", 1),
        (d(12), "Receita", "Vacina", "Vacina antirrábica - Mimi", 95.0, "Cartão de crédito", 2),
        (d(10), "Receita", "Banho/Tosa", "Banho e tosa higiênica - Thor", 120.0, "Dinheiro", 3),
        (d(9), "Despesa", "Medicamentos", "Reposição de antipulgas e vermífugos", 320.0, "Boleto", None),
        (d(7), "Receita", "Exame", "Exame de sangue - Thor", 210.0, "Cartão de débito", 3),
        (d(5), "Despesa", "Produtos", "Rações e petiscos para revenda", 540.0, "Boleto", None),
    ]
    for l in lancamentos:
        run("INSERT INTO lancamentos (data, tipo, categoria, descricao, valor, forma_pagamento, pet_id) VALUES (?,?,?,?,?,?,?)", l)

    st.sidebar.success("Dados de exemplo carregados! 🎉")
    st.rerun()


# --------------------------------------------------------------------------- #
#  App principal
# --------------------------------------------------------------------------- #

def main():
    st.set_page_config(
        page_title="CARDIOEVET — Gestão Veterinária",
        page_icon="assets/favicon.png" if os.path.exists("assets/favicon.png") else "🐾",
        layout="wide",
    )
    init_db()

    if "usuario" not in st.session_state:
        tela_login()
        return

    eu = st.session_state.usuario

    if os.path.exists("assets/logo.png"):
        _c1, _c2, _c3 = st.sidebar.columns([1, 2, 1])
        with _c2:
            st.image("assets/logo.png", use_container_width=True)
    st.sidebar.title("❤️ CARDIOEVET")
    st.sidebar.caption(f"👤 {eu['nome']} ({PAPEIS.get(eu['papel'], eu['papel'])})  ·  "
                       f"{'☁️ Nuvem' if nuvem_ativa() else '💾 Local'}")
    if st.sidebar.button("🚪 Sair", use_container_width=True):
        del st.session_state.usuario
        st.rerun()
    trocar_minha_senha()
    st.sidebar.divider()

    opcoes = ["🏠 Início", "📅 Agenda", "💉 Vacinas", "👤 Tutores", "🐾 Pets",
              "📋 Histórico", "📎 Exames", "🔬 Laudos", "💰 Financeiro", "🧾 Recibos/NF", "📄 Relatórios"]
    if eu["papel"] == "admin":
        opcoes += ["🔐 Usuários", "🔏 Assinatura", "☁️ Nuvem"]
    pagina = st.sidebar.radio("Menu", opcoes)

    st.sidebar.divider()
    with st.sidebar.expander("⚙️ Utilidades"):
        if st.button("Carregar dados de exemplo", use_container_width=True):
            carregar_exemplos()
        st.caption("Banco de dados: `vetclinic.db` (SQLite)")
        st.divider()
        apagar = st.checkbox("⚠️ Confirmo apagar TODOS os dados (exceto usuários)", key="conf_wipe")
        if st.button("🗑️ Apagar todos os dados", use_container_width=True, disabled=not apagar):
            for tabela in ("lancamentos", "vacinas", "agendamentos", "historico", "anexos",
                           "laudo_imagens", "laudos", "pets", "tutores"):
                run(f"DELETE FROM {tabela}")
            st.sidebar.success("Banco de dados limpo! (usuários mantidos)")
            st.rerun()

    if pagina == "🏠 Início":
        pagina_inicio()
    elif pagina == "📅 Agenda":
        pagina_agenda()
    elif pagina == "💉 Vacinas":
        pagina_vacinas()
    elif pagina == "👤 Tutores":
        pagina_tutores()
    elif pagina == "🐾 Pets":
        pagina_pets()
    elif pagina == "📋 Histórico":
        pagina_historico()
    elif pagina == "📎 Exames":
        pagina_exames()
    elif pagina == "🔬 Laudos":
        pagina_laudos()
    elif pagina == "💰 Financeiro":
        pagina_financeiro()
    elif pagina == "🧾 Recibos/NF":
        pagina_recibos()
    elif pagina == "🔐 Usuários":
        pagina_usuarios()
    elif pagina == "🔏 Assinatura":
        pagina_assinatura()
    elif pagina == "☁️ Nuvem":
        pagina_nuvem()
    else:
        pagina_relatorios()


if __name__ == "__main__":
    main()
