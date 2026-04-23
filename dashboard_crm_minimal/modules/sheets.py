import pandas as pd
import streamlit as st
from dotenv import load_dotenv, find_dotenv
import os

load_dotenv(find_dotenv(usecwd=True), override=True)

# Mapeamento dos nomes reais das colunas → nomes esperados pelo código
_COL_RENAME = {
    "event_date": "data",
    "campaign": "campaign_name",
    "content": "utm_content",
}

# Normaliza valores de agrupamento para o padrão do código
_AGRUP_RENAME = {
    "email fluxo": "email_fluxo",
    "email campanha": "email_campanha",
}


@st.cache_data(ttl=3600)
def load_dataframe() -> pd.DataFrame:
    sheets_url = os.getenv("SHEETS_URL")
    if not sheets_url:
        raise ValueError("SHEETS_URL não definida no .env")

    df = pd.read_csv(sheets_url)

    # Normaliza nomes de colunas: strip + lowercase
    df.columns = df.columns.str.strip().str.lower()

    # Renomeia colunas para os nomes esperados pelo código
    df = df.rename(columns=_COL_RENAME)

    # Normaliza valores de agrupamento_custom_minimal
    if "agrupamento_custom_minimal" in df.columns:
        df["agrupamento_custom_minimal"] = (
            df["agrupamento_custom_minimal"]
            .str.strip()
            .str.lower()
            .map(lambda v: _AGRUP_RENAME.get(v, v))
        )

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0)
    return df


def get_revenue(df: pd.DataFrame, start_date, end_date, agrupamento: str,
                campaign_name: str = None, utm_content: str = None) -> float:
    mask = (
        (df["agrupamento_custom_minimal"] == agrupamento) &
        (df["data"] >= pd.Timestamp(start_date)) &
        (df["data"] <= pd.Timestamp(end_date))
    )
    if campaign_name:
        mask &= (df["campaign_name"] == campaign_name)
    if utm_content:
        mask &= (df["utm_content"] == utm_content)
    return float(df[mask]["revenue"].sum())


def get_distinct_campaign_names(df: pd.DataFrame, agrupamento: str) -> list[str]:
    return sorted(
        df[df["agrupamento_custom_minimal"] == agrupamento]["campaign_name"]
        .dropna().unique().tolist()
    )
