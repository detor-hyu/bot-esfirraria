"""
Bot de Fechamento Diário — Esfirraria
=======================================

ABERTURA (início do dia):
  1. Dinheiro no caixa (troco)
  2. Esfihas feitas
  3. Refrigerantes na geladeira (cada tipo)

FECHAMENTO (fim do dia):
  1. Esfihas que sobraram
  2. Dinheiro no caixa (total final)
  3. Vendas cartão
  4. Vendas Pix
  5. Vendas iFood
  6. Refrigerantes que sobraram (cada tipo)
  7. Saídas do caixa

CONFERÊNCIA:
  Esfihas vendidas   = feitas (abertura) − sobraram (fechamento)
  Refri vendidos     = geladeira (abertura) − sobraram (fechamento)
  Esperado           = esfihas vendidas × R$3,75 + refri vendidos × preço
  Recebido           = (dinheiro final − troco) + cartão + pix + iFood + saídas
  Diferença          = Recebido − Esperado

Requisitos:
  pip install python-telegram-bot==20.7
"""

import sqlite3
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIGURAÇÃO
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "COLOQUE_SEU_TOKEN_AQUI")
DB_PATH = "fechamento.db"

# ============================================================
# PREÇOS FIXOS
# ============================================================
PRECO_ESFIHA = 3.75

# Chave interna, nome exibido, preço
REFRI_LISTA = [
    ("lata",          "Lata",           6.00),
    ("ks",            "KS",             5.00),
    ("kapo_dellvale", "Kapo/Dell Vale", 4.00),
    ("dellvale_pet",  "Dell Vale Pet",  5.00),
    ("tubaina_350",   "Tubaína 350ml",  4.00),
    ("tubaina_600",   "Tubaína 600ml",  6.00),
]

# ============================================================
# ESTADOS — ABERTURA
# ============================================================
AB_DINHEIRO = 100
AB_ESFIHAS  = 101
# 102..107 = refrigerantes na geladeira (6 tipos)
AB_REFRI_BASE = 102
AB_OBS = 108

# ============================================================
# ESTADOS — FECHAMENTO
# ============================================================
FE_ESFIHAS_SOBRA = 200
FE_DINHEIRO      = 201
FE_CARTAO        = 202
FE_PIX           = 203
FE_IFOOD         = 204
# 205..210 = refrigerantes que sobraram (6 tipos)
FE_REFRI_BASE    = 205
FE_SAIDAS        = 211
FE_SAIDAS_DESC   = 212

# ============================================================
# BANCO DE DADOS
# ============================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS aberturas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            data            TEXT NOT NULL,
            hora            TEXT NOT NULL,
            dinheiro        REAL DEFAULT 0,
            esfihas         INTEGER DEFAULT 0,
            refri_lata      INTEGER DEFAULT 0,
            refri_ks        INTEGER DEFAULT 0,
            refri_kapo      INTEGER DEFAULT 0,
            refri_dellvale  INTEGER DEFAULT 0,
            refri_tub350    INTEGER DEFAULT 0,
            refri_tub600    INTEGER DEFAULT 0,
            obs             TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fechamentos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL,
            data                TEXT NOT NULL,
            hora                TEXT NOT NULL,

            ab_dinheiro         REAL DEFAULT 0,
            ab_esfihas          INTEGER DEFAULT 0,
            ab_refri_lata       INTEGER DEFAULT 0,
            ab_refri_ks         INTEGER DEFAULT 0,
            ab_refri_kapo       INTEGER DEFAULT 0,
            ab_refri_dellvale   INTEGER DEFAULT 0,
            ab_refri_tub350     INTEGER DEFAULT 0,
            ab_refri_tub600     INTEGER DEFAULT 0,

            fe_esfihas_sobra    INTEGER DEFAULT 0,
            fe_dinheiro         REAL DEFAULT 0,
            fe_cartao           REAL DEFAULT 0,
            fe_pix              REAL DEFAULT 0,
            fe_ifood            REAL DEFAULT 0,
            fe_refri_lata       INTEGER DEFAULT 0,
            fe_refri_ks         INTEGER DEFAULT 0,
            fe_refri_kapo       INTEGER DEFAULT 0,
            fe_refri_dellvale   INTEGER DEFAULT 0,
            fe_refri_tub350     INTEGER DEFAULT 0,
            fe_refri_tub600     INTEGER DEFAULT 0,
            fe_saidas           REAL DEFAULT 0,
            fe_saidas_desc      TEXT,

            esfihas_vendidas    INTEGER DEFAULT 0,
            esfihas_valor       REAL DEFAULT 0,
            refri_total_valor   REAL DEFAULT 0,
            total_esperado      REAL DEFAULT 0,
            total_recebido      REAL DEFAULT 0,
            diferenca           REAL DEFAULT 0,

            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def salvar_abertura(user_id, d):
    conn = get_db()
    # Remove abertura anterior do mesmo dia (se reabrir)
    conn.execute("DELETE FROM aberturas WHERE user_id = ? AND data = ?", (user_id, hoje()))
    conn.execute("""
        INSERT INTO aberturas (
            user_id, data, hora, dinheiro, esfihas,
            refri_lata, refri_ks, refri_kapo,
            refri_dellvale, refri_tub350, refri_tub600, obs
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, hoje(), agora(), d["dinheiro"], d["esfihas"],
        d.get("refri_lata", 0), d.get("refri_ks", 0), d.get("refri_kapo", 0),
        d.get("refri_dellvale", 0), d.get("refri_tub350", 0), d.get("refri_tub600", 0),
        d.get("obs", ""),
    ))
    conn.commit()
    conn.close()


def buscar_abertura(user_id, data=None):
    data = data or hoje()
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM aberturas WHERE user_id = ? AND data = ? ORDER BY id DESC LIMIT 1",
        (user_id, data),
    ).fetchone()
    conn.close()
    return row


def salvar_fechamento(user_id, d):
    conn = get_db()
    conn.execute("""
        INSERT INTO fechamentos (
            user_id, data, hora,
            ab_dinheiro, ab_esfihas,
            ab_refri_lata, ab_refri_ks, ab_refri_kapo,
            ab_refri_dellvale, ab_refri_tub350, ab_refri_tub600,
            fe_esfihas_sobra, fe_dinheiro, fe_cartao, fe_pix, fe_ifood,
            fe_refri_lata, fe_refri_ks, fe_refri_kapo,
            fe_refri_dellvale, fe_refri_tub350, fe_refri_tub600,
            fe_saidas, fe_saidas_desc,
            esfihas_vendidas, esfihas_valor, refri_total_valor,
            total_esperado, total_recebido, diferenca
        ) VALUES (
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?, ?
        )
    """, (
        user_id, hoje(), agora(),
        d["ab_dinheiro"], d["ab_esfihas"],
        d["ab_refri_lata"], d["ab_refri_ks"], d["ab_refri_kapo"],
        d["ab_refri_dellvale"], d["ab_refri_tub350"], d["ab_refri_tub600"],
        d["fe_esfihas_sobra"], d["fe_dinheiro"], d["fe_cartao"], d["fe_pix"], d["fe_ifood"],
        d["fe_refri_lata"], d["fe_refri_ks"], d["fe_refri_kapo"],
        d["fe_refri_dellvale"], d["fe_refri_tub350"], d["fe_refri_tub600"],
        d["fe_saidas"], d.get("fe_saidas_desc", ""),
        d["esfihas_vendidas"], d["esfihas_valor"], d["refri_total_valor"],
        d["total_esperado"], d["total_recebido"], d["diferenca"],
    ))
    conn.commit()
    conn.close()


def buscar_fechamento(user_id, data=None):
    data = data or hoje()
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM fechamentos WHERE user_id = ? AND data = ? ORDER BY id DESC LIMIT 1",
        (user_id, data),
    ).fetchone()
    conn.close()
    return row


def buscar_historico(user_id, dias=7):
    conn = get_db()
    rows = conn.execute(
        """SELECT data, esfihas_vendidas, ab_esfihas,
                  total_esperado, total_recebido, diferenca
           FROM fechamentos WHERE user_id = ?
           ORDER BY id DESC LIMIT ?""",
        (user_id, dias),
    ).fetchall()
    conn.close()
    return rows


# ============================================================
# HELPERS
# ============================================================
def hoje():
    return datetime.now().strftime("%Y-%m-%d")

def agora():
    return datetime.now().strftime("%H:%M:%S")

def brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_num(texto):
    texto = texto.strip().replace("R$", "").replace(" ", "").replace(",", ".")
    return float(texto)

def parse_int(texto):
    return int(parse_num(texto))

def teclado_principal():
    return ReplyKeyboardMarkup([
        ["☀️ Abrir Caixa", "🌙 Fechar Caixa"],
        ["📊 Ver Fechamento", "📅 Histórico"],
        ["❓ Ajuda"],
    ], resize_keyboard=True)

def teclado_cancelar():
    return ReplyKeyboardMarkup([["❌ Cancelar"]], resize_keyboard=True)

# Chaves dos refrigerantes para mapear estados
REFRI_KEYS = ["lata", "ks", "kapo", "dellvale", "tub350", "tub600"]
REFRI_DB_KEYS = ["refri_lata", "refri_ks", "refri_kapo", "refri_dellvale", "refri_tub350", "refri_tub600"]


# ============================================================
# RELATÓRIOS
# ============================================================
def relatorio_abertura(d):
    data_fmt = datetime.now().strftime("%d/%m/%Y")
    hora_fmt = datetime.now().strftime("%H:%M")

    texto = (
        f"☀️ *CAIXA ABERTO — {data_fmt} às {hora_fmt}*\n"
        f"{'━' * 30}\n\n"
        f"💵 Dinheiro no caixa: *{brl(d['dinheiro'])}*\n"
        f"🥟 Esfihas feitas: *{d['esfihas']}* un ({brl(d['esfihas'] * PRECO_ESFIHA)})\n\n"
        f"🥤 *Geladeira:*\n"
    )
    for i, (chave, nome, preco) in enumerate(REFRI_LISTA):
        qtd = d.get(REFRI_DB_KEYS[i], 0)
        if qtd > 0:
            texto += f"    {nome}: {qtd} un\n"

    total_refri = sum(d.get(REFRI_DB_KEYS[i], 0) for i in range(len(REFRI_LISTA)))
    if total_refri == 0:
        texto += "    Nenhum\n"

    if d.get("obs"):
        texto += f"\n📝 Obs: _{d['obs']}_\n"

    texto += "\nBom dia de trabalho! 💪"
    return texto


def relatorio_fechamento(d):
    data_fmt = datetime.now().strftime("%d/%m/%Y")

    # Esfihas
    esf_vendidas = d["esfihas_vendidas"]
    esf_valor = d["esfihas_valor"]

    # Refrigerantes vendidos
    refri_linhas = []
    for i, (chave, nome, preco) in enumerate(REFRI_LISTA):
        ab = d[f"ab_{REFRI_DB_KEYS[i]}"]
        fe = d[f"fe_{REFRI_DB_KEYS[i]}"]
        vendido = ab - fe
        if vendido > 0:
            sub = vendido * preco
            refri_linhas.append(f"    {nome}: {vendido} un × {brl(preco)} = {brl(sub)}")

    troco = d["ab_dinheiro"]
    din_vendas = d["fe_dinheiro"] - troco

    texto = f"""🌙 *FECHAMENTO — {data_fmt}*
{'━' * 30}

☀️ *ABERTURA DO DIA*
    💵 Troco: {brl(troco)}
    🥟 Esfihas feitas: {d['ab_esfihas']} un

🥟 *ESFIHAS*
    Feitas: {d['ab_esfihas']} un
    Sobraram: {d['fe_esfihas_sobra']} un
    Vendidas: *{esf_vendidas} un*
    Valor: {esf_vendidas} × {brl(PRECO_ESFIHA)} = *{brl(esf_valor)}*

🥤 *REFRIGERANTES VENDIDOS*
"""
    if refri_linhas:
        texto += "\n".join(refri_linhas)
        texto += f"\n    Total: *{brl(d['refri_total_valor'])}*"
    else:
        texto += "    Nenhum vendido"

    texto += f"""

{'━' * 30}
📦 *TOTAL ESPERADO (vendas)*
    Esfihas: {brl(esf_valor)}
    Refrigerantes: {brl(d['refri_total_valor'])}
    ➡️  *{brl(d['total_esperado'])}*

{'━' * 30}
💰 *O QUE ENTROU*
    💵 Dinheiro no caixa: {brl(d['fe_dinheiro'])}
    💵 (−) Troco abertura: −{brl(troco)}
    💵 = Vendas dinheiro: *{brl(din_vendas)}*
    💳 Cartão: {brl(d['fe_cartao'])}
    📲 Pix: {brl(d['fe_pix'])}
    📱 iFood: {brl(d['fe_ifood'])}
"""

    if d['fe_saidas'] > 0:
        texto += f"    📤 Saídas: +{brl(d['fe_saidas'])}"
        if d.get('fe_saidas_desc'):
            texto += f"\n        _({d['fe_saidas_desc']})_"
        texto += "\n"

    texto += f"""    ➡️  *{brl(d['total_recebido'])}*

{'━' * 30}
"""

    diff = d["diferenca"]
    if abs(diff) < 0.01:
        texto += "✅ *CAIXA BATEU CERTINHO!*"
    elif diff > 0:
        texto += f"🟢 *SOBROU {brl(diff)}*\n    (Entrou a mais do que o esperado)"
    else:
        texto += f"🔴 *FALTOU {brl(abs(diff))}*\n    (Entrou a menos do que o esperado)"

    return texto


# ============================================================
# HANDLERS — START / AJUDA
# ============================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nome = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Olá, *{nome}*!\n\n"
        "Eu sou o Bot de Fechamento da sua esfirraria.\n\n"
        "☀️ *Abrir Caixa* — registra troco, esfihas e geladeira\n"
        "🌙 *Fechar Caixa* — conta o que sobrou e confere\n\n"
        "O bot calcula automaticamente:\n"
        "  🥟 Esfihas vendidas = feitas − sobraram\n"
        "  🥤 Refri vendido = geladeira − sobraram\n"
        "  ✅ Se o dinheiro bate com as vendas",
        parse_mode="Markdown",
        reply_markup=teclado_principal(),
    )


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = f"""❓ *AJUDA*

*☀️ Abertura:* troco + esfihas feitas + geladeira
*🌙 Fechamento:* o que sobrou + dinheiro/cartão/pix/iFood

*Preços:*
🥟 Esfiha: {brl(PRECO_ESFIHA)}
"""
    for _, nome, preco in REFRI_LISTA:
        texto += f"🥤 {nome}: {brl(preco)}\n"

    texto += f"""
*Conferência:*
Vendido = Abertura − Sobra
Esperado = esfihas vendidas × {brl(PRECO_ESFIHA)} + refri vendidos
Recebido = (dinheiro − troco) + cartão + pix + iFood + saídas

*Dicas:*
• Aceita vírgula ou ponto: `49,90` ou `49.90`
• Digite `0` quando não teve / não tem
• /cancelar cancela o processo
"""
    await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=teclado_principal())


# ============================================================
# ABERTURA DO CAIXA
# ============================================================
async def iniciar_abertura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data.clear()
    context.user_data["ab"] = {}

    ab = buscar_abertura(user_id)
    aviso = ""
    if ab:
        aviso = f"\n⚠️ Caixa já foi aberto hoje com {brl(ab['dinheiro'])} — será substituído.\n"

    await update.message.reply_text(
        f"☀️ *ABERTURA DE CAIXA*{aviso}\n\n"
        "*Passo 1/3 — Dinheiro*\n\n"
        "💵 Quanto de dinheiro/troco tem no caixa?\n\n"
        "Digite o valor:",
        parse_mode="Markdown",
        reply_markup=teclado_cancelar(),
    )
    return AB_DINHEIRO


async def ab_dinheiro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        valor = parse_num(update.message.text)
        if valor < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Valor inválido (ex: `100`):", parse_mode="Markdown")
        return AB_DINHEIRO

    context.user_data["ab"]["dinheiro"] = valor

    await update.message.reply_text(
        f"✅ Dinheiro: *{brl(valor)}*\n\n"
        "━━━━━━━━━━━━━━━\n"
        "*Passo 2/3 — Esfihas*\n\n"
        "🥟 Quantas esfihas foram feitas hoje?\n\n"
        "Digite a quantidade:",
        parse_mode="Markdown",
    )
    return AB_ESFIHAS


async def ab_esfihas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        qtd = parse_int(update.message.text)
        if qtd < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Número inteiro (ex: `120`):", parse_mode="Markdown")
        return AB_ESFIHAS

    context.user_data["ab"]["esfihas"] = qtd
    valor = qtd * PRECO_ESFIHA

    # Primeiro refrigerante
    nome_r, preco_r = REFRI_LISTA[0][1], REFRI_LISTA[0][2]

    await update.message.reply_text(
        f"✅ Esfihas: *{qtd}* un ({brl(valor)})\n\n"
        "━━━━━━━━━━━━━━━\n"
        "*Passo 3/3 — Geladeira*\n\n"
        "🥤 Quantos de cada refrigerante tem na geladeira?\n"
        "Digite `0` para os que não tem.\n\n"
        f"*{nome_r}* ({brl(preco_r)}) — quantos?",
        parse_mode="Markdown",
    )
    return AB_REFRI_BASE


# --- Refrigerantes abertura (genérico) ---

async def ab_refri_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, idx: int):
    """Processa refrigerante idx (0..5) da abertura."""
    try:
        qtd = parse_int(update.message.text)
        if qtd < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Número inteiro:", parse_mode="Markdown")
        return AB_REFRI_BASE + idx

    context.user_data["ab"][REFRI_DB_KEYS[idx]] = qtd

    nome_atual = REFRI_LISTA[idx][1]
    txt = f"✅ {nome_atual}: {qtd}\n\n" if qtd else f"✅ {nome_atual}: 0\n\n"

    # Próximo refrigerante ou observação
    if idx < len(REFRI_LISTA) - 1:
        prox_nome, prox_preco = REFRI_LISTA[idx + 1][1], REFRI_LISTA[idx + 1][2]
        await update.message.reply_text(
            f"{txt}*{prox_nome}* ({brl(prox_preco)}) — quantos?",
            parse_mode="Markdown",
        )
        return AB_REFRI_BASE + idx + 1
    else:
        # Último refri, pedir obs
        await update.message.reply_text(
            f"{txt}"
            "━━━━━━━━━━━━━━━\n"
            "📝 Alguma observação?\n"
            "_(ex: faltou moeda, geladeira com defeito)_\n\n"
            "Ou /pular para abrir sem obs.",
            parse_mode="Markdown",
        )
        return AB_OBS


# Gerar handlers individuais para cada refrigerante
async def ab_refri_0(update, context): return await ab_refri_handler(update, context, 0)
async def ab_refri_1(update, context): return await ab_refri_handler(update, context, 1)
async def ab_refri_2(update, context): return await ab_refri_handler(update, context, 2)
async def ab_refri_3(update, context): return await ab_refri_handler(update, context, 3)
async def ab_refri_4(update, context): return await ab_refri_handler(update, context, 4)
async def ab_refri_5(update, context): return await ab_refri_handler(update, context, 5)

AB_REFRI_HANDLERS = [ab_refri_0, ab_refri_1, ab_refri_2, ab_refri_3, ab_refri_4, ab_refri_5]


async def ab_obs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ab"]["obs"] = update.message.text.strip()
    return await finalizar_abertura(update, context)


async def ab_pular_obs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ab"]["obs"] = ""
    return await finalizar_abertura(update, context)


async def finalizar_abertura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    d = context.user_data["ab"]
    salvar_abertura(user_id, d)
    rel = relatorio_abertura(d)
    await update.message.reply_text(rel, parse_mode="Markdown", reply_markup=teclado_principal())
    context.user_data.clear()
    return ConversationHandler.END


# ============================================================
# FECHAMENTO DO CAIXA
# ============================================================
async def iniciar_fechamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data.clear()
    context.user_data["fe"] = {}

    ab = buscar_abertura(user_id)
    if not ab:
        await update.message.reply_text(
            "⚠️ *Caixa não foi aberto hoje!*\n\n"
            "Use ☀️ *Abrir Caixa* primeiro para registrar\n"
            "o troco, esfihas e geladeira.",
            parse_mode="Markdown",
            reply_markup=teclado_principal(),
        )
        return ConversationHandler.END

    # Guardar dados da abertura
    context.user_data["fe"]["ab_dinheiro"] = ab["dinheiro"]
    context.user_data["fe"]["ab_esfihas"] = ab["esfihas"]
    for i, key in enumerate(REFRI_DB_KEYS):
        context.user_data["fe"][f"ab_{key}"] = ab[key]

    await update.message.reply_text(
        "🌙 *FECHAMENTO DE CAIXA*\n\n"
        f"☀️ Abertura: {brl(ab['dinheiro'])} troco | "
        f"{ab['esfihas']} esfihas\n\n"
        "━━━━━━━━━━━━━━━\n"
        "*Passo 1/7 — Esfihas que sobraram*\n\n"
        f"🥟 Foram feitas *{ab['esfihas']}* esfihas.\n"
        "Quantas *sobraram*?\n\n"
        "Digite a quantidade (ou `0` se vendeu tudo):",
        parse_mode="Markdown",
        reply_markup=teclado_cancelar(),
    )
    return FE_ESFIHAS_SOBRA


async def fe_esfihas_sobra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        qtd = parse_int(update.message.text)
        if qtd < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Número inteiro:", parse_mode="Markdown")
        return FE_ESFIHAS_SOBRA

    d = context.user_data["fe"]
    d["fe_esfihas_sobra"] = qtd
    vendidas = d["ab_esfihas"] - qtd
    if vendidas < 0:
        await update.message.reply_text(
            f"⚠️ Sobraram mais ({qtd}) do que foram feitas ({d['ab_esfihas']}).\n"
            "Confere e digita de novo:",
            parse_mode="Markdown",
        )
        return FE_ESFIHAS_SOBRA

    valor = vendidas * PRECO_ESFIHA

    await update.message.reply_text(
        f"✅ Sobraram: {qtd} | Vendidas: *{vendidas}* ({brl(valor)})\n\n"
        "━━━━━━━━━━━━━━━\n"
        "*Passo 2/7 — Dinheiro no caixa*\n\n"
        "💵 Quanto tem de dinheiro no caixa AGORA?\n"
        "_(total, incluindo troco)_\n\n"
        "Digite o valor:",
        parse_mode="Markdown",
    )
    return FE_DINHEIRO


async def fe_dinheiro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        valor = parse_num(update.message.text)
        if valor < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Valor inválido:", parse_mode="Markdown")
        return FE_DINHEIRO

    d = context.user_data["fe"]
    d["fe_dinheiro"] = valor
    troco = d["ab_dinheiro"]
    din_vendas = valor - troco

    await update.message.reply_text(
        f"✅ Dinheiro: *{brl(valor)}*\n"
        f"    (−) Troco: {brl(troco)} → Vendas dinheiro: *{brl(din_vendas)}*\n\n"
        "━━━━━━━━━━━━━━━\n"
        "*Passo 3/7 — Vendas Cartão*\n\n"
        "💳 Quanto vendeu no cartão?\n"
        "_(digite `0` se não teve)_",
        parse_mode="Markdown",
    )
    return FE_CARTAO


async def fe_cartao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        valor = parse_num(update.message.text)
        if valor < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Valor inválido:", parse_mode="Markdown")
        return FE_CARTAO

    context.user_data["fe"]["fe_cartao"] = valor
    await update.message.reply_text(
        f"✅ Cartão: *{brl(valor)}*\n\n"
        "━━━━━━━━━━━━━━━\n"
        "*Passo 4/7 — Vendas Pix*\n\n"
        "📲 Quanto vendeu no Pix?\n"
        "_(digite `0` se não teve)_",
        parse_mode="Markdown",
    )
    return FE_PIX


async def fe_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        valor = parse_num(update.message.text)
        if valor < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Valor inválido:", parse_mode="Markdown")
        return FE_PIX

    context.user_data["fe"]["fe_pix"] = valor
    await update.message.reply_text(
        f"✅ Pix: *{brl(valor)}*\n\n"
        "━━━━━━━━━━━━━━━\n"
        "*Passo 5/7 — Vendas iFood*\n\n"
        "📱 Quanto vendeu no iFood?\n"
        "_(digite `0` se não teve)_",
        parse_mode="Markdown",
    )
    return FE_IFOOD


async def fe_ifood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        valor = parse_num(update.message.text)
        if valor < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Valor inválido:", parse_mode="Markdown")
        return FE_IFOOD

    context.user_data["fe"]["fe_ifood"] = valor

    nome_r, preco_r = REFRI_LISTA[0][1], REFRI_LISTA[0][2]
    ab_qtd = context.user_data["fe"].get("ab_refri_lata", 0)

    await update.message.reply_text(
        f"✅ iFood: *{brl(valor)}*\n\n"
        "━━━━━━━━━━━━━━━\n"
        "*Passo 6/7 — Refrigerantes que sobraram*\n\n"
        "🥤 Quantos de cada refrigerante *sobraram* na geladeira?\n"
        "Digite `0` para os que acabaram.\n\n"
        f"*{nome_r}* (tinha {ab_qtd} na abertura) — sobraram quantos?",
        parse_mode="Markdown",
    )
    return FE_REFRI_BASE


# --- Refrigerantes fechamento (genérico) ---

async def fe_refri_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, idx: int):
    try:
        qtd = parse_int(update.message.text)
        if qtd < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Número inteiro:", parse_mode="Markdown")
        return FE_REFRI_BASE + idx

    d = context.user_data["fe"]
    d[f"fe_{REFRI_DB_KEYS[idx]}"] = qtd

    ab_qtd = d.get(f"ab_{REFRI_DB_KEYS[idx]}", 0)
    vendido = ab_qtd - qtd
    nome_atual = REFRI_LISTA[idx][1]

    if vendido < 0:
        await update.message.reply_text(
            f"⚠️ Sobraram mais ({qtd}) do que tinha na abertura ({ab_qtd}).\n"
            "Confere e digita de novo:",
            parse_mode="Markdown",
        )
        return FE_REFRI_BASE + idx

    txt = f"✅ {nome_atual}: sobrou {qtd} (vendeu {vendido})\n\n"

    if idx < len(REFRI_LISTA) - 1:
        prox_nome = REFRI_LISTA[idx + 1][1]
        prox_ab = d.get(f"ab_{REFRI_DB_KEYS[idx + 1]}", 0)
        await update.message.reply_text(
            f"{txt}*{prox_nome}* (tinha {prox_ab} na abertura) — sobraram quantos?",
            parse_mode="Markdown",
        )
        return FE_REFRI_BASE + idx + 1
    else:
        # Último refri, ir pra saídas
        await update.message.reply_text(
            f"{txt}"
            "━━━━━━━━━━━━━━━\n"
            "*Passo 7/7 — Saídas do caixa*\n\n"
            "📤 Teve saída de dinheiro hoje?\n"
            "_(troco pra banco, compra de insumo, etc.)_\n\n"
            "Digite o valor total, ou `0` se não teve:",
            parse_mode="Markdown",
        )
        return FE_SAIDAS


async def fe_refri_0(update, context): return await fe_refri_handler(update, context, 0)
async def fe_refri_1(update, context): return await fe_refri_handler(update, context, 1)
async def fe_refri_2(update, context): return await fe_refri_handler(update, context, 2)
async def fe_refri_3(update, context): return await fe_refri_handler(update, context, 3)
async def fe_refri_4(update, context): return await fe_refri_handler(update, context, 4)
async def fe_refri_5(update, context): return await fe_refri_handler(update, context, 5)

FE_REFRI_HANDLERS = [fe_refri_0, fe_refri_1, fe_refri_2, fe_refri_3, fe_refri_4, fe_refri_5]


async def fe_saidas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        valor = parse_num(update.message.text)
        if valor < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Valor inválido:", parse_mode="Markdown")
        return FE_SAIDAS

    context.user_data["fe"]["fe_saidas"] = valor

    if valor > 0:
        await update.message.reply_text(
            f"Saída: *{brl(valor)}*\n\n"
            "Descreva em uma linha:\n"
            "_(ex: troco banco, compra massa)_\n\n"
            "Ou /pular para não descrever.",
            parse_mode="Markdown",
        )
        return FE_SAIDAS_DESC

    context.user_data["fe"]["fe_saidas_desc"] = ""
    return await calcular_e_fechar(update, context)


async def fe_saidas_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fe"]["fe_saidas_desc"] = update.message.text.strip()
    return await calcular_e_fechar(update, context)


async def fe_pular_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fe"]["fe_saidas_desc"] = ""
    return await calcular_e_fechar(update, context)


# ============================================================
# CÁLCULO FINAL
# ============================================================
async def calcular_e_fechar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = context.user_data["fe"]
    user_id = update.effective_user.id

    # Esfihas vendidas
    esf_vendidas = d["ab_esfihas"] - d["fe_esfihas_sobra"]
    esf_valor = esf_vendidas * PRECO_ESFIHA
    d["esfihas_vendidas"] = esf_vendidas
    d["esfihas_valor"] = esf_valor

    # Refrigerantes vendidos
    refri_total = 0.0
    for i, (chave, nome, preco) in enumerate(REFRI_LISTA):
        ab = d.get(f"ab_{REFRI_DB_KEYS[i]}", 0)
        fe = d.get(f"fe_{REFRI_DB_KEYS[i]}", 0)
        vendido = ab - fe
        refri_total += vendido * preco
    d["refri_total_valor"] = refri_total

    # ESPERADO
    total_esperado = esf_valor + refri_total
    d["total_esperado"] = total_esperado

    # RECEBIDO
    troco = d["ab_dinheiro"]
    total_recebido = (
        (d["fe_dinheiro"] - troco)
        + d["fe_cartao"]
        + d["fe_pix"]
        + d["fe_ifood"]
        + d["fe_saidas"]
    )
    d["total_recebido"] = total_recebido

    # DIFERENÇA
    d["diferenca"] = total_recebido - total_esperado

    # Salvar
    salvar_fechamento(user_id, d)

    # Relatório
    rel = relatorio_fechamento(d)
    await update.message.reply_text(rel, parse_mode="Markdown", reply_markup=teclado_principal())

    context.user_data.clear()
    return ConversationHandler.END


# ============================================================
# CONSULTAS
# ============================================================
async def ver_fechamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    row = buscar_fechamento(user_id)
    if not row:
        await update.message.reply_text(
            "Nenhum fechamento hoje. Use 🌙 *Fechar Caixa*.",
            parse_mode="Markdown", reply_markup=teclado_principal(),
        )
        return

    d = {col: row[col] for col in row.keys() if col not in ("id", "user_id", "data", "hora", "created_at")}
    rel = relatorio_fechamento(d)
    await update.message.reply_text(rel, parse_mode="Markdown", reply_markup=teclado_principal())


async def ver_historico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = buscar_historico(user_id, 7)
    if not rows:
        await update.message.reply_text("📅 Nenhum histórico.", reply_markup=teclado_principal())
        return

    linhas = ["📅 *HISTÓRICO*\n"]
    for r in rows:
        data_fmt = datetime.strptime(r["data"], "%Y-%m-%d").strftime("%d/%m")
        diff = r["diferenca"]
        if abs(diff) < 0.01:
            emoji, diff_txt = "✅", "bateu"
        elif diff > 0:
            emoji, diff_txt = "🟢", f"+{brl(diff)}"
        else:
            emoji, diff_txt = "🔴", f"{brl(diff)}"
        linhas.append(
            f"{emoji} *{data_fmt}* — {r['ab_esfihas']} feitas / {r['esfihas_vendidas']} vendidas — "
            f"Esp {brl(r['total_esperado'])} / Rec {brl(r['total_recebido'])} → {diff_txt}"
        )

    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown", reply_markup=teclado_principal())


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado.", reply_markup=teclado_principal())
    return ConversationHandler.END


# ============================================================
# MAIN
# ============================================================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # --- ABERTURA ---
    ab_states = {
        AB_DINHEIRO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ab_dinheiro)],
        AB_ESFIHAS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ab_esfihas)],
        AB_OBS: [
            CommandHandler("pular", ab_pular_obs),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ab_obs),
        ],
    }
    # Adicionar estados dos refrigerantes da abertura
    for i, handler in enumerate(AB_REFRI_HANDLERS):
        ab_states[AB_REFRI_BASE + i] = [MessageHandler(filters.TEXT & ~filters.COMMAND, handler)]

    abertura_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^☀️ Abrir Caixa$"), iniciar_abertura),
            CommandHandler("abrir", iniciar_abertura),
        ],
        states=ab_states,
        fallbacks=[
            CommandHandler("cancelar", cancelar),
            MessageHandler(filters.Regex("^❌ Cancelar$"), cancelar),
        ],
    )

    # --- FECHAMENTO ---
    fe_states = {
        FE_ESFIHAS_SOBRA: [MessageHandler(filters.TEXT & ~filters.COMMAND, fe_esfihas_sobra)],
        FE_DINHEIRO:      [MessageHandler(filters.TEXT & ~filters.COMMAND, fe_dinheiro)],
        FE_CARTAO:        [MessageHandler(filters.TEXT & ~filters.COMMAND, fe_cartao)],
        FE_PIX:           [MessageHandler(filters.TEXT & ~filters.COMMAND, fe_pix)],
        FE_IFOOD:         [MessageHandler(filters.TEXT & ~filters.COMMAND, fe_ifood)],
        FE_SAIDAS:        [MessageHandler(filters.TEXT & ~filters.COMMAND, fe_saidas)],
        FE_SAIDAS_DESC: [
            CommandHandler("pular", fe_pular_desc),
            MessageHandler(filters.TEXT & ~filters.COMMAND, fe_saidas_desc),
        ],
    }
    for i, handler in enumerate(FE_REFRI_HANDLERS):
        fe_states[FE_REFRI_BASE + i] = [MessageHandler(filters.TEXT & ~filters.COMMAND, handler)]

    fechamento_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🌙 Fechar Caixa$"), iniciar_fechamento),
            CommandHandler("fechar", iniciar_fechamento),
        ],
        states=fe_states,
        fallbacks=[
            CommandHandler("cancelar", cancelar),
            MessageHandler(filters.Regex("^❌ Cancelar$"), cancelar),
        ],
    )

    app.add_handler(abertura_conv)
    app.add_handler(fechamento_conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ajuda", cmd_ajuda))
    app.add_handler(CommandHandler("help", cmd_ajuda))
    app.add_handler(MessageHandler(filters.Regex("^📊 Ver Fechamento$"), ver_fechamento))
    app.add_handler(MessageHandler(filters.Regex("^📅 Histórico$"), ver_historico))
    app.add_handler(MessageHandler(filters.Regex("^❓ Ajuda$"), cmd_ajuda))

    print("🤖 Bot rodando...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
