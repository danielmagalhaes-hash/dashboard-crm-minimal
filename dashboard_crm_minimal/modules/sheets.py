import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import os

load_dotenv()
SHEETS_URL = os.getenv("SHEETS_URL")


@st.cache_data(ttl=3600)
def load_dataframe() -> pd.DataFrame:
    df = pd.read_csv(SHEETS_URL)
    # Normaliza nomes de colunas removendo espaços extras
    df.columns = df.columns.str.strip()
    # Detecta coluna de data (pode ser 'data', 'date', 'Data', etc.)
    date_col = next((c for c in df.columns if c.lower() == 'data'), None)
    if date_col and date_col != 'data':
        df = df.rename(columns={date_col: 'data'})
    df['data'] = pd.to_datetime(df['data'], errors='coerce')
    df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce').fillna(0)
    return df


def get_revenue(df: pd.DataFrame, start_date, end_date, agrupamento: str,
                campaign_name: str = None, utm_content: str = None) -> float:
    mask = (
        (df['agrupamento_custom_minimal'] == agrupamento) &
        (df['data'] >= pd.Timestamp(start_date)) &
        (df['data'] <= pd.Timestamp(end_date))
    )
    if campaign_name:
        mask &= (df['campaign_name'] == campaign_name)
    if utm_content:
        mask &= (df['utm_content'] == utm_content)
    return float(df[mask]['revenue'].sum())


def get_distinct_campaign_names(df: pd.DataFrame, agrupamento: str) -> list[str]:
    return sorted(
        df[df['agrupamento_custom_minimal'] == agrupamento]['campaign_name']
        .dropna().unique().tolist()
    )
