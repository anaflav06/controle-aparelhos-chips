import streamlit as st
import pandas as pd
import requests
import base64
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from io import BytesIO

st.set_page_config(
    page_title="Controle de Aparelhos e Chips",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_TITLE = "Controle de Aparelhos e Chips da Empresa"
LOCAL_DB = Path(__file__).with_name("database_aparelhos_chips.json")

STATUS_APARELHO = ["EM USO", "EM ESTOQUE", "ASSISTÊNCIA", "INATIVO", "ROUBADO/PERDIDO"]
STATUS_LINHA = ["ATIVA", "INATIVA", "BLOQUEADA", "CANCELADA"]
TIPOS_CHIP = ["CHIP FÍSICO", "eSIM"]
OPERADORAS = ["", "VIVO", "TIM", "CLARO", "OI", "OUTRA"]
CLASSIFICACOES = [
    "",
    "CORPORATIVO / PAGO",
    "PRÉ-PAGO",
    "OUTRA OPERAÇÃO",
    "MANTER DISPONÍVEL",
    "CANCELAR / AVALIAR",
]
LIFE_STATUS = ["", "ATIVO", "INATIVO", "NÃO UTILIZA"]

# ==========================================================
# VISUAL
# ==========================================================
st.markdown(
    """
<style>
.block-container{
    padding-top:1.4rem;
    padding-bottom:2rem;
    max-width:100%;
}
h1,h2,h3{
    letter-spacing:-0.02em;
}
[data-testid="stSidebar"]{
    border-right:1px solid #E6EAF0;
}
[data-testid="stMetric"]{
    background:linear-gradient(145deg,#FFFFFF 0%,#F8FAFC 100%);
    border:1px solid #E3E8EF;
    padding:14px 16px;
    border-radius:16px;
    box-shadow:0 5px 18px rgba(16,24,40,.05);
}
[data-testid="stMetricValue"]{
    font-weight:800;
}
div[data-testid="stDataFrame"],
div[data-testid="stDataEditor"]{
    border:1px solid #E4E8EE;
    border-radius:14px;
    overflow:hidden;
    box-shadow:0 4px 16px rgba(16,24,40,.04);
}
.stButton>button,
.stDownloadButton>button{
    border-radius:10px!important;
    font-weight:700!important;
}
div[data-baseweb="select"]>div{
    border-radius:10px!important;
}
input{
    border-radius:9px!important;
}
.section-title{
    padding:9px 12px;
    margin:6px 0 10px 0;
    border-radius:10px;
    background:#F5F7FA;
    border-left:4px solid #667085;
    font-weight:800;
}
.helper{
    color:#667085;
    font-size:.9rem;
}
</style>
""",
    unsafe_allow_html=True,
)


# ==========================================================
# LOGIN
# ==========================================================
def get_login_users():
    """
    No Streamlit Cloud, configure em Settings > Secrets:

    [LOGIN_USERS]
    julia = "SUA_SENHA"
    jessica = "SUA_SENHA"

    Localmente, use .streamlit/secrets.toml com a mesma estrutura.
    """
    try:
        users = st.secrets.get("LOGIN_USERS", {})
        return {str(k).strip().lower(): str(v) for k, v in users.items()}
    except Exception:
        return {}

def tela_login():
    st.markdown("""
    <style>
    [data-testid="stSidebar"] {display:none;}
    .login-title {
        text-align:center;
        font-size:2rem;
        font-weight:800;
        margin-top:4rem;
        margin-bottom:.25rem;
    }
    .login-subtitle {
        text-align:center;
        color:#667085;
        margin-bottom:1.5rem;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-title">📱 Controle de Aparelhos e Chips</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">Acesso restrito</div>', unsafe_allow_html=True)

    left, center, right = st.columns([1.4, 1, 1.4])
    with center:
        with st.form("login_form"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

        if entrar:
            users = get_login_users()
            if not users:
                st.error("Usuários de acesso ainda não foram configurados nos Secrets.")
            elif usuario.strip().lower() in users and senha == users[usuario.strip().lower()]:
                st.session_state["autenticado"] = True
                st.session_state["usuario_logado"] = usuario.strip().lower()
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")

if not st.session_state.get("autenticado", False):
    tela_login()
    st.stop()


# ==========================================================
# PERSISTÊNCIA LOCAL + GITHUB
# ==========================================================
def github_config():
    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
        repo = st.secrets.get("GITHUB_REPO", "")
        branch = st.secrets.get("GITHUB_DATA_BRANCH", "main")
        path = st.secrets.get("GITHUB_DB_PATH", "database_aparelhos_chips.json")
        if token and repo:
            return token, repo, branch, path
    except Exception:
        pass
    return None

def empty_db():
    return {"version": 1, "cadastros": []}

def normalize_db(data):
    if not isinstance(data, dict):
        return empty_db()
    if "cadastros" not in data or not isinstance(data["cadastros"], list):
        data["cadastros"] = []
    data["version"] = 1
    return data

def load_local():
    if not LOCAL_DB.exists():
        return empty_db()
    try:
        return normalize_db(json.loads(LOCAL_DB.read_text(encoding="utf-8")))
    except Exception:
        return empty_db()

def save_local(data):
    LOCAL_DB.write_text(
        json.dumps(normalize_db(data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def github_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def load_github():
    cfg = github_config()
    if not cfg:
        return None
    token, repo, branch, path = cfg
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    r = requests.get(
        url,
        headers=github_headers(token),
        params={"ref": branch},
        timeout=20,
    )
    if r.status_code == 404:
        return empty_db()
    r.raise_for_status()
    payload = r.json()
    content = base64.b64decode(payload["content"]).decode("utf-8")
    return normalize_db(json.loads(content))

def save_github(data):
    cfg = github_config()
    if not cfg:
        return False, "Secrets do GitHub não configurados."

    token, repo, branch, path = cfg
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = github_headers(token)

    sha = None
    get_r = requests.get(
        url,
        headers=headers,
        params={"ref": branch},
        timeout=20,
    )
    if get_r.status_code == 200:
        sha = get_r.json().get("sha")
    elif get_r.status_code != 404:
        get_r.raise_for_status()

    raw = json.dumps(normalize_db(data), ensure_ascii=False, indent=2).encode("utf-8")
    payload = {
        "message": "Atualiza base do controle de aparelhos e chips",
        "content": base64.b64encode(raw).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    put_r = requests.put(url, headers=headers, json=payload, timeout=30)
    if put_r.status_code not in (200, 201):
        return False, f"GitHub retornou {put_r.status_code}: {put_r.text[:300]}"
    return True, ""

@st.cache_data(ttl=20, show_spinner=False)
def read_db_cached():
    cfg = github_config()
    if cfg:
        try:
            return load_github(), "github"
        except Exception:
            # Fallback local para não derrubar o app em indisponibilidade temporária.
            return load_local(), "local"
    return load_local(), "local"

def read_db():
    return read_db_cached()

def persist_db(data):
    save_local(data)
    cfg = github_config()
    if cfg:
        ok, err = save_github(data)
        if not ok:
            return False, err
    read_db_cached.clear()
    return True, ""

# ==========================================================
# HELPERS / VALIDAÇÕES
# ==========================================================
def clean(v):
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s

def digits(v):
    return re.sub(r"\D", "", clean(v))

def format_cpf(v):
    d = digits(v)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return clean(v)

def cpf_valido(v):
    d = digits(v)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    n = list(map(int, d))
    soma1 = sum(n[i] * (10 - i) for i in range(9))
    dv1 = (soma1 * 10) % 11
    dv1 = 0 if dv1 == 10 else dv1
    soma2 = sum(n[i] * (11 - i) for i in range(10))
    dv2 = (soma2 * 10) % 11
    dv2 = 0 if dv2 == 10 else dv2
    return n[9] == dv1 and n[10] == dv2

def format_phone(v):
    d = digits(v)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return clean(v)

def imei_valido(v):
    return len(digits(v)) == 15

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def situacao_registro(r):
    tem_aparelho = bool(clean(r.get("imei")))
    tem_linha = bool(clean(r.get("telefone")))
    if tem_aparelho and tem_linha:
        return "VINCULADO"
    if tem_aparelho:
        return "APARELHO DISPONÍVEL EM ESTOQUE"
    if tem_linha:
        return "CHIP DISPONÍVEL EM ESTOQUE"
    return "SEM APARELHO / CHIP"

def pendencias_registro(r):
    faltas = []
    tem_aparelho = bool(clean(r.get("imei")))
    tem_linha = bool(clean(r.get("telefone")))
    status_ap = clean(r.get("status_aparelho")).upper()
    em_uso = status_ap == "EM USO" or (tem_aparelho and tem_linha)

    if em_uso:
        if not clean(r.get("responsavel")):
            faltas.append("nome")
        if not clean(r.get("cpf")):
            faltas.append("CPF")
        elif not cpf_valido(r.get("cpf")):
            faltas.append("CPF inválido")

    if tem_linha:
        if len(digits(r.get("telefone"))) not in (10, 11):
            faltas.append("telefone")
        if not clean(r.get("operadora")):
            faltas.append("operadora")
        if not clean(r.get("tipo_chip")):
            faltas.append("tipo chip")
        if not clean(r.get("status_linha")):
            faltas.append("status linha")

    if tem_aparelho:
        if not imei_valido(r.get("imei")):
            faltas.append("IMEI")
        if clean(r.get("imei2")) and not imei_valido(r.get("imei2")):
            faltas.append("IMEI 2")
        if not clean(r.get("marca")):
            faltas.append("marca")
        if not clean(r.get("modelo")):
            faltas.append("modelo")
        if not clean(r.get("status_aparelho")):
            faltas.append("status aparelho")

    if not tem_aparelho and not tem_linha:
        faltas.append("sem aparelho/chip")

    return ", ".join(dict.fromkeys(faltas)) if faltas else "OK"

def validate_record(r, all_records, current_id=None):
    erros = []
    tem_aparelho = bool(clean(r.get("imei")))
    tem_linha = bool(clean(r.get("telefone")))
    status_ap = clean(r.get("status_aparelho")).upper()
    em_uso = status_ap == "EM USO" or (tem_aparelho and tem_linha)

    if not tem_aparelho and not tem_linha:
        erros.append("Cadastre pelo menos um aparelho ou uma linha/chip.")

    if em_uso:
        if not clean(r.get("responsavel")):
            erros.append("Nome de quem está com o aparelho/linha é obrigatório quando estiver em uso.")
        if not clean(r.get("cpf")):
            erros.append("CPF é obrigatório quando estiver em uso.")
        elif not cpf_valido(r.get("cpf")):
            erros.append("CPF inválido. Informe o CPF completo com 11 dígitos.")

    if tem_linha:
        if len(digits(r.get("telefone"))) not in (10, 11):
            erros.append("Telefone deve conter DDD + número completo.")
        if not clean(r.get("operadora")):
            erros.append("Operadora é obrigatória.")
        if not clean(r.get("tipo_chip")):
            erros.append("Tipo do chip é obrigatório.")
        if not clean(r.get("status_linha")):
            erros.append("Status da linha é obrigatório.")

    if tem_aparelho:
        if not imei_valido(r.get("imei")):
            erros.append("IMEI deve conter exatamente 15 números.")
        if clean(r.get("imei2")) and not imei_valido(r.get("imei2")):
            erros.append("IMEI 2 deve conter exatamente 15 números quando preenchido.")
        if not clean(r.get("marca")):
            erros.append("Marca do aparelho é obrigatória.")
        if not clean(r.get("modelo")):
            erros.append("Modelo do aparelho é obrigatório.")
        if not clean(r.get("status_aparelho")):
            erros.append("Status do aparelho é obrigatório.")

    tel_d = digits(r.get("telefone"))
    imei_d = digits(r.get("imei"))
    for x in all_records:
        if current_id and x.get("id") == current_id:
            continue
        if tel_d and digits(x.get("telefone")) == tel_d:
            erros.append("Este número de telefone já está cadastrado.")
            break
    for x in all_records:
        if current_id and x.get("id") == current_id:
            continue
        if imei_d and digits(x.get("imei")) == imei_d:
            erros.append("Este IMEI já está cadastrado.")
            break

    return list(dict.fromkeys(erros))

def normalize_record(r, current=None):
    current = current or {}
    return {
        "id": current.get("id") or str(uuid.uuid4()),
        "responsavel": clean(r.get("responsavel")).upper(),
        "cpf": format_cpf(r.get("cpf")),
        "cargo": clean(r.get("cargo")).upper(),
        "empresa_operacao": clean(r.get("empresa_operacao")).upper(),

        "telefone": format_phone(r.get("telefone")),
        "operadora": clean(r.get("operadora")).upper(),
        "tipo_chip": clean(r.get("tipo_chip")),
        "status_linha": clean(r.get("status_linha")),
        "classificacao_linha": clean(r.get("classificacao_linha")),

        "imei": digits(r.get("imei")) if clean(r.get("imei")) else "",
        "imei2": digits(r.get("imei2")) if clean(r.get("imei2")) else "",
        "marca": clean(r.get("marca")).upper(),
        "modelo": clean(r.get("modelo")).upper(),
        "status_aparelho": clean(r.get("status_aparelho")),

        "senha_celular": clean(r.get("senha_celular")),
        "email_celular": clean(r.get("email_celular")),
        "senha_email": clean(r.get("senha_email")),
        "life_status": clean(r.get("life_status")),
        "email_life": clean(r.get("email_life")),
        "senha_life": clean(r.get("senha_life")),

        "observacao": clean(r.get("observacao")),
        "criado_em": current.get("criado_em") or now_iso(),
        "atualizado_em": now_iso(),
    }

def records_df(records):
    if not records:
        return pd.DataFrame(columns=[
            "id","responsavel","cpf","cargo","empresa_operacao",
            "telefone","operadora","tipo_chip","status_linha","classificacao_linha",
            "imei","imei2","marca","modelo","status_aparelho",
            "senha_celular","email_celular","senha_email","life_status","email_life","senha_life",
            "observacao","criado_em","atualizado_em","situacao","pendencias"
        ])
    rows = []
    for r in records:
        x = dict(r)
        x["situacao"] = situacao_registro(r)
        x["pendencias"] = pendencias_registro(r)
        rows.append(x)
    return pd.DataFrame(rows)

def upsert_record(record_id, form_data):
    db, _ = read_db()
    records = db["cadastros"]
    current = next((x for x in records if x.get("id") == record_id), None) if record_id else None

    erros = validate_record(form_data, records, current_id=record_id)
    if erros:
        return False, erros

    novo = normalize_record(form_data, current)
    if current:
        records[records.index(current)] = novo
    else:
        records.append(novo)

    ok, err = persist_db(db)
    if not ok:
        return False, [f"Os dados foram salvos localmente, mas não consegui atualizar o banco permanente no GitHub. Detalhe: {err}"]
    return True, []

def delete_record(record_id):
    db, _ = read_db()
    db["cadastros"] = [x for x in db["cadastros"] if x.get("id") != record_id]
    return persist_db(db)

def export_excel(records, chips_only=False):
    df = records_df(records).copy()
    if chips_only:
        df = df[df["telefone"].fillna("").ne("")]

    ren = {
        "responsavel":"Responsável",
        "cpf":"CPF",
        "cargo":"Cargo",
        "empresa_operacao":"Empresa / Operação",
        "telefone":"Telefone",
        "operadora":"Operadora",
        "tipo_chip":"Tipo do chip",
        "status_linha":"Status da linha",
        "classificacao_linha":"Classificação da linha",
        "imei":"IMEI",
        "imei2":"IMEI 2",
        "marca":"Marca",
        "modelo":"Modelo",
        "status_aparelho":"Status do aparelho",
        "life_status":"Life",
        "email_life":"E-mail Life",
        "situacao":"Situação",
        "pendencias":"Pendências",
        "observacao":"Observação",
    }
    df = df.rename(columns=ren)
    cols = [c for c in [
        "Responsável","CPF","Cargo","Empresa / Operação",
        "Telefone","Operadora","Tipo do chip","Status da linha","Classificação da linha",
        "IMEI","IMEI 2","Marca","Modelo","Status do aparelho",
        "Life","E-mail Life","Situação","Pendências","Observação"
    ] if c in df.columns]

    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df[cols].to_excel(writer, index=False, sheet_name="CHIPS" if chips_only else "CONTROLE")
    return bio.getvalue()

def search_df(df, termo):
    if not termo or df.empty:
        return df
    termo = termo.lower()
    cols = [
        "responsavel","cpf","cargo","empresa_operacao","telefone","operadora",
        "imei","modelo","marca","status_aparelho","status_linha","observacao"
    ]
    mask = pd.Series(False, index=df.index)
    for c in cols:
        mask |= df[c].fillna("").astype(str).str.lower().str.contains(termo, regex=False)
    return df[mask]

# ==========================================================
# SIDEBAR
# ==========================================================
db, storage_mode = read_db()
records = db["cadastros"]
df = records_df(records)

with st.sidebar:
    st.markdown("## 📱 Gestão de ativos")
    st.caption("Aparelhos • Chips • Linhas • Apps")
    st.caption(f"👤 {st.session_state.get('usuario_logado', '').title()}")
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state["autenticado"] = False
        st.session_state.pop("usuario_logado", None)
        st.rerun()
    st.divider()
    menu = st.radio(
        "Navegação",
        [
            "🏠 Dashboard",
            "➕ Novo cadastro",
            "✏️ Editar cadastro",
            "📦 Estoque",
            "📄 Conferência",
            "💾 Backup",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    if storage_mode == "github" and github_config():
        st.success("Banco permanente conectado")
    else:
        st.info("Banco local")

st.title(APP_TITLE)

# ==========================================================
# DASHBOARD
# ==========================================================
if menu == "🏠 Dashboard":
    st.markdown("### Visão geral")

    total = len(df)
    vinculados = int((df["situacao"] == "VINCULADO").sum()) if not df.empty else 0
    aparelhos_disp = int((df["situacao"] == "APARELHO DISPONÍVEL EM ESTOQUE").sum()) if not df.empty else 0
    chips_disp = int((df["situacao"] == "CHIP DISPONÍVEL EM ESTOQUE").sum()) if not df.empty else 0
    assistencia = int((df["status_aparelho"] == "ASSISTÊNCIA").sum()) if not df.empty else 0
    linhas_ativas = int((df["status_linha"] == "ATIVA").sum()) if not df.empty else 0
    pendencias = int((df["pendencias"] != "OK").sum()) if not df.empty else 0

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("Vinculados", vinculados)
    c2.metric("Aparelhos disponíveis", aparelhos_disp)
    c3.metric("Chips disponíveis", chips_disp)
    c4.metric("Assistência", assistencia)
    c5.metric("Linhas ativas", linhas_ativas)
    c6.metric("Com pendência", pendencias)

    st.markdown("### Consulta rápida")
    a,b = st.columns([1.1,2.2])
    with a:
        filtro = st.selectbox(
            "Situação",
            [
                "TODOS",
                "VINCULADOS",
                "APARELHOS DISPONÍVEIS",
                "CHIPS DISPONÍVEIS",
                "ASSISTÊNCIA",
                "LINHAS ATIVAS",
                "COM PENDÊNCIA",
            ],
        )
    with b:
        busca = st.text_input("🔎 Buscar por nome, CPF, telefone, IMEI, modelo, marca ou operação")

    view = df.copy()
    if filtro == "VINCULADOS":
        view = view[view["situacao"] == "VINCULADO"]
    elif filtro == "APARELHOS DISPONÍVEIS":
        view = view[view["situacao"] == "APARELHO DISPONÍVEL EM ESTOQUE"]
    elif filtro == "CHIPS DISPONÍVEIS":
        view = view[view["situacao"] == "CHIP DISPONÍVEL EM ESTOQUE"]
    elif filtro == "ASSISTÊNCIA":
        view = view[view["status_aparelho"] == "ASSISTÊNCIA"]
    elif filtro == "LINHAS ATIVAS":
        view = view[view["status_linha"] == "ATIVA"]
    elif filtro == "COM PENDÊNCIA":
        view = view[view["pendencias"] != "OK"]

    view = search_df(view, busca)

    if view.empty:
        st.info("Nenhum cadastro encontrado.")
    else:
        tabela = view[[
            "responsavel","cpf","cargo","empresa_operacao",
            "telefone","operadora","status_linha",
            "imei","marca","modelo","status_aparelho",
            "life_status","situacao","pendencias"
        ]].rename(columns={
            "responsavel":"Responsável",
            "cpf":"CPF",
            "cargo":"Cargo",
            "empresa_operacao":"Empresa / Operação",
            "telefone":"Telefone",
            "operadora":"Operadora",
            "status_linha":"Status linha",
            "imei":"IMEI",
            "marca":"Marca",
            "modelo":"Modelo",
            "status_aparelho":"Status aparelho",
            "life_status":"Life",
            "situacao":"Situação",
            "pendencias":"Pendências",
        })
        st.dataframe(tabela, use_container_width=True, hide_index=True, height=560)

# ==========================================================
# FORMULÁRIO REUTILIZÁVEL
# ==========================================================
def cadastro_form(prefix, initial=None):
    initial = initial or {}

    st.markdown('<div class="section-title">👤 1. Dados do colaborador</div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    responsavel = c1.text_input("Nome / responsável", clean(initial.get("responsavel")), key=f"{prefix}_responsavel")
    cpf = c2.text_input("CPF", clean(initial.get("cpf")), placeholder="000.000.000-00", key=f"{prefix}_cpf")
    cargo = c3.text_input("Cargo", clean(initial.get("cargo")), key=f"{prefix}_cargo")
    empresa_operacao = c4.text_input("Empresa / Operação", clean(initial.get("empresa_operacao")), key=f"{prefix}_operacao")

    st.markdown('<div class="section-title">📶 2. Dados da linha / telefone</div>', unsafe_allow_html=True)
    c1,c2,c3,c4,c5 = st.columns(5)
    telefone = c1.text_input("Telefone", clean(initial.get("telefone")), placeholder="(11) 99999-9999", key=f"{prefix}_telefone")
    op_ini = clean(initial.get("operadora"))
    operadora = c2.selectbox("Operadora", OPERADORAS, index=OPERADORAS.index(op_ini) if op_ini in OPERADORAS else 0, key=f"{prefix}_operadora")
    tipo_opts = [""] + TIPOS_CHIP
    tipo_ini = clean(initial.get("tipo_chip"))
    tipo_chip = c3.selectbox("Tipo do chip", tipo_opts, index=tipo_opts.index(tipo_ini) if tipo_ini in tipo_opts else 0, key=f"{prefix}_tipo")
    linha_opts = [""] + STATUS_LINHA
    linha_ini = clean(initial.get("status_linha"))
    status_linha = c4.selectbox("Status da linha", linha_opts, index=linha_opts.index(linha_ini) if linha_ini in linha_opts else 0, key=f"{prefix}_status_linha")
    class_ini = clean(initial.get("classificacao_linha"))
    classificacao_linha = c5.selectbox("Classificação", CLASSIFICACOES, index=CLASSIFICACOES.index(class_ini) if class_ini in CLASSIFICACOES else 0, key=f"{prefix}_class")

    st.markdown('<div class="section-title">📱 3. Dados do aparelho</div>', unsafe_allow_html=True)
    c1,c2,c3,c4,c5 = st.columns(5)
    imei = c1.text_input("IMEI", clean(initial.get("imei")), placeholder="15 números", key=f"{prefix}_imei")
    imei2 = c2.text_input("IMEI 2 (opcional)", clean(initial.get("imei2")), placeholder="15 números", key=f"{prefix}_imei2")
    marca = c3.text_input("Marca", clean(initial.get("marca")), key=f"{prefix}_marca")
    modelo = c4.text_input("Modelo", clean(initial.get("modelo")), key=f"{prefix}_modelo")
    ap_opts = [""] + STATUS_APARELHO
    ap_ini = clean(initial.get("status_aparelho"))
    status_aparelho = c5.selectbox("Status do aparelho", ap_opts, index=ap_opts.index(ap_ini) if ap_ini in ap_opts else 0, key=f"{prefix}_status_ap")

    st.markdown('<div class="section-title">🔐 4. Aplicativos e acessos</div>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns(3)
    senha_celular = c1.text_input("Senha do celular", clean(initial.get("senha_celular")), key=f"{prefix}_senha_cel")
    email_celular = c2.text_input("E-mail do celular", clean(initial.get("email_celular")), key=f"{prefix}_email_cel")
    senha_email = c3.text_input("Senha do e-mail", clean(initial.get("senha_email")), key=f"{prefix}_senha_email")

    c4,c5,c6 = st.columns(3)
    life_ini = clean(initial.get("life_status"))
    life_status = c4.selectbox("Life", LIFE_STATUS, index=LIFE_STATUS.index(life_ini) if life_ini in LIFE_STATUS else 0, key=f"{prefix}_life")
    email_life = c5.text_input("E-mail Life", clean(initial.get("email_life")), key=f"{prefix}_email_life")
    senha_life = c6.text_input("Senha Life", clean(initial.get("senha_life")), key=f"{prefix}_senha_life")

    observacao = st.text_area("📝 Observação", clean(initial.get("observacao")), key=f"{prefix}_obs")

    return {
        "responsavel": responsavel,
        "cpf": cpf,
        "cargo": cargo,
        "empresa_operacao": empresa_operacao,
        "telefone": telefone,
        "operadora": operadora,
        "tipo_chip": tipo_chip,
        "status_linha": status_linha,
        "classificacao_linha": classificacao_linha,
        "imei": imei,
        "imei2": imei2,
        "marca": marca,
        "modelo": modelo,
        "status_aparelho": status_aparelho,
        "senha_celular": senha_celular,
        "email_celular": email_celular,
        "senha_email": senha_email,
        "life_status": life_status,
        "email_life": email_life,
        "senha_life": senha_life,
        "observacao": observacao,
    }

# ==========================================================
# NOVO CADASTRO
# ==========================================================
if menu == "➕ Novo cadastro":
    st.markdown("### Novo cadastro")
    st.caption("Cadastre aparelho e chip juntos quando estiverem vinculados. Se cadastrar apenas um deles, o item ficará disponível em estoque.")

    with st.form("form_novo", clear_on_submit=True):
        form_data = cadastro_form("novo")
        submit = st.form_submit_button("💾 Salvar cadastro", type="primary", use_container_width=True)

    if submit:
        ok, erros = upsert_record(None, form_data)
        if ok:
            st.success("Cadastro salvo com sucesso no banco permanente.")
            st.rerun()
        else:
            for e in erros:
                st.error(e)

# ==========================================================
# EDITAR
# ==========================================================
elif menu == "✏️ Editar cadastro":
    st.markdown("### Editar cadastro")
    if df.empty:
        st.info("Ainda não existem cadastros.")
    else:
        busca_edit = st.text_input("🔎 Localizar cadastro")
        edit_df = search_df(df, busca_edit)

        labels = {}
        for _, r in edit_df.iterrows():
            label = clean(r["responsavel"]) or "SEM RESPONSÁVEL"
            if clean(r["telefone"]):
                label += f" | {clean(r['telefone'])}"
            if clean(r["modelo"]):
                label += f" | {clean(r['modelo'])}"
            if clean(r["imei"]):
                label += f" | IMEI {clean(r['imei'])}"
            labels[label] = r["id"]

        if not labels:
            st.info("Nenhum cadastro encontrado.")
        else:
            escolhido = st.selectbox("Selecione", list(labels.keys()))
            rid = labels[escolhido]
            initial = next(x for x in records if x.get("id") == rid)

            with st.form("form_editar"):
                form_data = cadastro_form("editar", initial)
                submit_ed = st.form_submit_button("💾 Salvar alterações", type="primary", use_container_width=True)

            if submit_ed:
                ok, erros = upsert_record(rid, form_data)
                if ok:
                    st.success("Alterações salvas com sucesso.")
                    st.rerun()
                else:
                    for e in erros:
                        st.error(e)

            st.divider()
            confirmar = st.checkbox("Confirmo que desejo excluir este cadastro.")
            if st.button("🗑️ Excluir cadastro", disabled=not confirmar):
                ok, err = delete_record(rid)
                if ok:
                    st.success("Cadastro excluído.")
                    st.rerun()
                else:
                    st.error(err)

# ==========================================================
# ESTOQUE
# ==========================================================
elif menu == "📦 Estoque":
    st.markdown("### Estoque e disponibilidade")
    st.caption("Aparelho sem chip/linha e chip/linha sem aparelho aparecem automaticamente como disponíveis.")

    filtro_est = st.radio(
        "Exibir",
        ["Aparelhos disponíveis", "Chips disponíveis", "Vinculados", "Assistência", "Pendências"],
        horizontal=True,
    )

    view = df.copy()
    if filtro_est == "Aparelhos disponíveis":
        view = view[view["situacao"] == "APARELHO DISPONÍVEL EM ESTOQUE"]
    elif filtro_est == "Chips disponíveis":
        view = view[view["situacao"] == "CHIP DISPONÍVEL EM ESTOQUE"]
    elif filtro_est == "Vinculados":
        view = view[view["situacao"] == "VINCULADO"]
    elif filtro_est == "Assistência":
        view = view[view["status_aparelho"] == "ASSISTÊNCIA"]
    else:
        view = view[view["pendencias"] != "OK"]

    busca_est = st.text_input("🔎 Buscar no estoque")
    view = search_df(view, busca_est)

    if view.empty:
        st.info("Nenhum item neste filtro.")
    else:
        st.dataframe(
            view[[
                "responsavel","cpf","empresa_operacao",
                "telefone","operadora","status_linha",
                "imei","marca","modelo","status_aparelho",
                "situacao","pendencias","observacao"
            ]].rename(columns={
                "responsavel":"Responsável","cpf":"CPF","empresa_operacao":"Empresa / Operação",
                "telefone":"Telefone","operadora":"Operadora","status_linha":"Status linha",
                "imei":"IMEI","marca":"Marca","modelo":"Modelo","status_aparelho":"Status aparelho",
                "situacao":"Situação","pendencias":"Pendências","observacao":"Observação",
            }),
            use_container_width=True,
            hide_index=True,
            height=580,
        )

# ==========================================================
# CONFERÊNCIA
# ==========================================================
elif menu == "📄 Conferência":
    st.markdown("### Conferência e exportação")
    st.write("Exporte as linhas para comparar o que está no app com os planos pagos/linhas existentes na operação.")

    linhas = df[df["telefone"].fillna("").ne("")] if not df.empty else df
    aparelhos = df[df["imei"].fillna("").ne("")] if not df.empty else df

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Cadastros", len(df))
    c2.metric("Linhas", len(linhas))
    c3.metric("Aparelhos", len(aparelhos))
    c4.metric("Chips disponíveis", int((df["situacao"] == "CHIP DISPONÍVEL EM ESTOQUE").sum()) if not df.empty else 0)

    if not linhas.empty:
        st.markdown("#### Linhas / chips")
        st.dataframe(
            linhas[[
                "responsavel","empresa_operacao","telefone","operadora","tipo_chip",
                "status_linha","classificacao_linha","imei","modelo","situacao","pendencias"
            ]].rename(columns={
                "responsavel":"Responsável","empresa_operacao":"Empresa / Operação","telefone":"Telefone",
                "operadora":"Operadora","tipo_chip":"Tipo","status_linha":"Status",
                "classificacao_linha":"Classificação","imei":"IMEI vinculado","modelo":"Aparelho",
                "situacao":"Situação","pendencias":"Pendências",
            }),
            use_container_width=True,
            hide_index=True,
        )

    a,b = st.columns(2)
    a.download_button(
        "⬇️ Exportar chips / linhas",
        data=export_excel(records, chips_only=True),
        file_name=f"conferencia_chips_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )
    b.download_button(
        "⬇️ Exportar controle completo",
        data=export_excel(records, chips_only=False),
        file_name=f"controle_aparelhos_chips_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# ==========================================================
# BACKUP
# ==========================================================
elif menu == "💾 Backup":
    st.markdown("### Backup da base")
    st.write("Faça uma cópia da base sempre que desejar guardar um ponto de segurança.")

    raw = json.dumps(db, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button(
        "⬇️ Baixar backup JSON",
        data=raw,
        file_name=f"backup_aparelhos_chips_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
        type="primary",
    )

    if github_config():
        st.success("No Streamlit, cada inclusão, edição ou exclusão é gravada também no GitHub.")
    else:
        st.info("Executando localmente: a base fica salva no arquivo database_aparelhos_chips.json na mesma pasta do app.")
