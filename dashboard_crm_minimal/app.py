import streamlit as st
from datetime import date
import pandas as pd
import json
import os
import re

from modules.sheets import load_dataframe, get_revenue
from modules.klaviyo import (
    get_all_flows, get_flow_subscribers, get_flow_messages,
    get_all_campaigns, get_all_forms, get_total_email_subscribers,
)
from modules.flow_config import (
    FLOW_MAPPING, MOF_FLOW_NAMES, MOF_CAMPAIGN_NAME,
    MOF_DISPLAY_NAME, get_campaign_for_flow,
)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

UTM_MAPPING_PATH = os.path.join(os.path.dirname(__file__), "data", "utm_mapping.json")


def _load_utm_mapping() -> dict:
    if os.path.exists(UTM_MAPPING_PATH):
        with open(UTM_MAPPING_PATH, "r", encoding="utf-8") as fp:
            return json.load(fp)
    return {}


def _save_utm_mapping(mapping: dict) -> None:
    os.makedirs(os.path.dirname(UTM_MAPPING_PATH), exist_ok=True)
    with open(UTM_MAPPING_PATH, "w", encoding="utf-8") as fp:
        json.dump(mapping, fp, ensure_ascii=False, indent=2)


def _fmt_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _render_messages_table(
    messages: list[dict],
    df: pd.DataFrame,
    start_date,
    end_date,
    campaign_name: str | None,
    utm_map: dict,
    flow_id_for_utm: str | None,
    show_subflow_col: bool,
) -> None:
    if not messages:
        st.info("Nenhum email encontrado para este flow.")
        return

    fid_key = str(flow_id_for_utm) if flow_id_for_utm else "unknown"
    flow_utm_map = utm_map.get(fid_key, {})

    missing_utm = [
        m for m in messages
        if not re.match(r'^em\d+$', str(flow_utm_map.get(m["id"], "")), re.IGNORECASE)
    ]

    if missing_utm:
        with st.expander("⚙️ Configurar utm_content por email"):
            st.caption("Associe cada email a um código emXXXX para cruzar receita da planilha.")
            updated = False
            for m in messages:
                current = flow_utm_map.get(m["id"], "")
                val = st.text_input(
                    f"{m['name'] or m['id']} (posição {m['position']})",
                    value=current,
                    key=f"utm_{fid_key}_{m['id']}",
                    placeholder="ex: em0042",
                )
                if val != current:
                    flow_utm_map[m["id"]] = val
                    updated = True
            if updated:
                utm_map[fid_key] = flow_utm_map
                _save_utm_mapping(utm_map)
                st.success("utm_mapping.json atualizado.")

    rows = []
    for m in messages:
        utm_val = flow_utm_map.get(m["id"], "")
        utm_norm = utm_val.lower().strip() if utm_val else None

        if utm_norm and re.match(r'^em\d+$', utm_norm) and campaign_name:
            rev = get_revenue(df, start_date, end_date, "email_fluxo",
                              campaign_name=campaign_name, utm_content=utm_norm)
            rev_display = _fmt_brl(rev)
        else:
            rev_display = "—"

        row = {
            "Email": m["name"] or m["id"],
            "Pos.": m["position"],
            "Envios": _fmt_int(m["sends"]),
            "Taxa de Abertura": f"{m['open_rate']:.1f}%",
            "CTR": f"{m['ctr']:.1f}%",
            "Receita": rev_display,
        }
        if show_subflow_col:
            row["Sub-flow"] = m.get("_subflow", "")
        rows.append(row)

    cols = (
        ["Sub-flow", "Email", "Pos.", "Envios", "Taxa de Abertura", "CTR", "Receita"]
        if show_subflow_col
        else ["Email", "Pos.", "Envios", "Taxa de Abertura", "CTR", "Receita"]
    )
    st.dataframe(pd.DataFrame(rows)[cols], use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# CABEÇALHO E SELETOR DE DATA
# ─────────────────────────────────────────────

st.set_page_config(page_title="CRM Dashboard — Minimal Club", layout="wide")
st.title("📊 CRM Dashboard — Minimal Club")

col1, col2 = st.columns(2)
start_date = col1.date_input("Data inicial", value=date(2025, 1, 1))
end_date = col2.date_input("Data final", value=date.today())

with st.spinner("Carregando dados da planilha..."):
    try:
        df = load_dataframe()
    except Exception as e:
        st.error(f"Erro ao carregar planilha: {e}")
        st.stop()

tab_flows, tab_campaigns, tab_forms = st.tabs(["📬 Flows", "📣 Campanhas", "📋 Formulários"])

# ─────────────────────────────────────────────
# ABA 1 — FLOWS
# ─────────────────────────────────────────────
with tab_flows:
    st.subheader("Visão Geral — Email Flows")

    with st.spinner("Buscando dados do Klaviyo..."):
        try:
            total_subscribers = get_total_email_subscribers()
        except Exception as e:
            st.error(f"Erro ao buscar inscritos: {e}")
            total_subscribers = 0

        try:
            all_flows_raw = get_all_flows()
        except Exception as e:
            st.error(f"Erro ao buscar flows: {e}")
            all_flows_raw = []

    total_flow_revenue = get_revenue(df, start_date, end_date, "email_fluxo")
    rpi = total_flow_revenue / total_subscribers if total_subscribers else 0.0

    m1, m2, m3 = st.columns(3)
    m1.metric("Inscritos Totais", _fmt_int(total_subscribers))
    m2.metric("Receita Total Email Fluxo", _fmt_brl(total_flow_revenue))
    m3.metric("Receita por Inscrito", _fmt_brl(rpi))

    st.divider()
    st.subheader("Tabela de Flows")

    # Constrói lista de linhas para exibição
    flow_rows = []
    mof_ids = []  # (flow_id, flow_name)

    for flow in all_flows_raw:
        fname = flow["name"]
        fid = flow["id"]
        if fname in MOF_FLOW_NAMES:
            mof_ids.append((fid, fname))
        elif fname in FLOW_MAPPING:
            flow_rows.append({
                "_display": fname,
                "_id": fid,
                "_ids": [fid],
                "_campaign": FLOW_MAPPING[fname],
                "_mof": False,
                "_mapped": True,
            })
        else:
            flow_rows.append({
                "_display": fname,
                "_id": fid,
                "_ids": [fid],
                "_campaign": None,
                "_mof": False,
                "_mapped": False,
            })

    if mof_ids:
        flow_rows.append({
            "_display": MOF_DISPLAY_NAME,
            "_id": None,
            "_ids": [fid for fid, _ in mof_ids],
            "_campaign": MOF_CAMPAIGN_NAME,
            "_mof": True,
            "_mapped": True,
        })

    table_data = []
    for row in flow_rows:
        try:
            if row["_mof"]:
                subs = sum(get_flow_subscribers(fid) for fid in row["_ids"])
            else:
                subs = get_flow_subscribers(row["_id"]) if row["_id"] else 0
        except Exception:
            subs = 0

        if row["_mapped"] and row["_campaign"]:
            rev = get_revenue(df, start_date, end_date, "email_fluxo",
                              campaign_name=row["_campaign"])
            rev_display = _fmt_brl(rev)
        else:
            rev = None
            rev_display = "—"

        rpi_flow = (rev / subs) if (rev and subs) else None
        rpi_display = _fmt_brl(rpi_flow) if rpi_flow else "—"

        label = row["_display"] if row["_mapped"] else f"{row['_display']} (não mapeado)"
        table_data.append({
            "Flow": label,
            "Inscritos": _fmt_int(subs),
            "Receita": rev_display,
            "Receita / Inscrito": rpi_display,
        })

    if table_data:
        st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum flow encontrado.")

    # ── Drill-down ────────────────────────────────────────────────
    st.divider()
    st.subheader("Drill-down por Flow")

    display_names = [r["_display"] for r in flow_rows]
    if not display_names:
        st.info("Nenhum flow disponível para detalhar.")
    else:
        selected_name = st.selectbox("Selecione um Flow para detalhar", display_names)
        selected_row = next((r for r in flow_rows if r["_display"] == selected_name), None)

        if selected_row:
            utm_map = _load_utm_mapping()

            if selected_row["_mof"]:
                all_msgs = []
                for fid, fname in mof_ids:
                    try:
                        msgs = get_flow_messages(fid)
                        for m in msgs:
                            m["_subflow"] = fname
                        all_msgs.extend(msgs)
                    except Exception as e:
                        st.warning(f"Erro ao buscar emails do sub-flow '{fname}': {e}")

                _render_messages_table(
                    all_msgs, df, start_date, end_date,
                    MOF_CAMPAIGN_NAME, utm_map,
                    flow_id_for_utm=selected_row["_ids"][0] if selected_row["_ids"] else None,
                    show_subflow_col=True,
                )
            else:
                fid = selected_row["_id"]
                if fid:
                    try:
                        msgs = get_flow_messages(fid)
                        _render_messages_table(
                            msgs, df, start_date, end_date,
                            selected_row["_campaign"], utm_map,
                            flow_id_for_utm=fid,
                            show_subflow_col=False,
                        )
                    except Exception as e:
                        st.error(f"Erro ao buscar emails do flow: {e}")


# ─────────────────────────────────────────────
# ABA 2 — CAMPANHAS
# ─────────────────────────────────────────────
with tab_campaigns:
    st.subheader("Campanhas de Email")

    with st.spinner("Buscando campanhas no Klaviyo..."):
        try:
            campaigns = get_all_campaigns()
        except Exception as e:
            st.error(f"Erro ao buscar campanhas: {e}")
            campaigns = []

    camp_rows = []
    for c in campaigns:
        match = re.search(r'\[([Ee][Mm]\d+)\]', c["name"])
        if match:
            utm = match.group(1).lower()
            rev = get_revenue(df, start_date, end_date, "email_campanha", utm_content=utm)
            rev_display = _fmt_brl(rev)
        else:
            rev_display = "—"

        send_time = c["send_time"][:10] if c.get("send_time") else "—"

        camp_rows.append({
            "Campanha": c["name"],
            "Data Envio": send_time,
            "Envios": _fmt_int(c["sends"]),
            "Taxa de Abertura": f"{c['open_rate']:.1f}%",
            "Cliques": _fmt_int(c["clicks"]),
            "CTR": f"{c['ctr']:.1f}%",
            "Receita": rev_display,
        })

    if camp_rows:
        st.dataframe(pd.DataFrame(camp_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma campanha encontrada.")


# ─────────────────────────────────────────────
# ABA 3 — FORMULÁRIOS
# ─────────────────────────────────────────────
with tab_forms:
    st.subheader("Formulários de Captação")

    with st.spinner("Buscando formulários no Klaviyo..."):
        try:
            forms = get_all_forms()
        except Exception as e:
            st.error(f"Erro ao buscar formulários: {e}")
            forms = []

    total_views = sum(f["views"] for f in forms)
    total_subs_form = sum(f["submissions"] for f in forms)
    total_conv = (total_subs_form / total_views * 100) if total_views else 0.0

    fm1, fm2, fm3 = st.columns(3)
    fm1.metric("Visualizações Totais", _fmt_int(total_views))
    fm2.metric("Inscrições Totais", _fmt_int(total_subs_form))
    fm3.metric("Taxa de Conversão Geral", f"{total_conv:.1f}%")

    st.divider()

    form_rows = [
        {
            "Formulário": f["name"],
            "Visualizações": _fmt_int(f["views"]),
            "Inscrições": _fmt_int(f["submissions"]),
            "Taxa de Conversão": f"{f['conversion_rate']:.1f}%",
        }
        for f in forms
    ]

    if form_rows:
        st.dataframe(pd.DataFrame(form_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum formulário encontrado.")
