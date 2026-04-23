import requests
import streamlit as st
from dotenv import load_dotenv, find_dotenv
import os
import time
from datetime import datetime, timedelta, timezone

load_dotenv(find_dotenv(usecwd=True), override=True)

BASE_URL = "https://a.klaviyo.com/api"

# ID da métrica "Placed Order" (obrigatório em campaign-values-reports)
_PLACED_ORDER_METRIC_ID = "Vrb6Ca"

# Timeframe máximo permitido pela API: 1 ano
def _timeframe_1y() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "start": (now - timedelta(days=364)).strftime("%Y-%m-%dT00:00:00+00:00"),
        "end": now.strftime("%Y-%m-%dT23:59:59+00:00"),
    }


def _headers():
    key = os.getenv("KLAVIYO_API_KEY")
    return {
        "Authorization": f"Klaviyo-API-Key {key}",
        "revision": "2024-10-15",
        "Accept": "application/json",
    }


def _get(url: str, params: dict = None, retries: int = 3) -> requests.Response:
    """GET com retry automático em 429."""
    for attempt in range(retries):
        resp = requests.get(url, headers=_headers(), params=params)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 5))
            time.sleep(min(wait + 1, 15))
            continue
        return resp
    return resp


def _post(url: str, payload: dict, retries: int = 3) -> requests.Response:
    """POST com retry automático em 429."""
    hdrs = {**_headers(), "Content-Type": "application/json"}
    for attempt in range(retries):
        resp = requests.post(url, headers=hdrs, json=payload)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 5))
            time.sleep(min(wait + 1, 15))
            continue
        return resp
    return resp


def _get_all_pages(url: str, params: dict = None) -> list[dict]:
    """
    Percorre todas as páginas cursor-based.
    Não usa page[size] para evitar 400 no endpoint de campanhas.
    """
    items = []
    next_url = url
    first = True
    while next_url:
        resp = _get(next_url, params=params if first else None)
        resp.raise_for_status()
        first = False
        body = resp.json()
        items.extend(body.get("data", []))
        next_url = body.get("links", {}).get("next")
    return items


# ─────────────────────────────────────────────
# FLOWS
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_all_flows() -> list[dict]:
    """GET /api/flows"""
    items = _get_all_pages(f"{BASE_URL}/flows", params={"fields[flow]": "name,status"})
    return [{"id": f["id"], "name": f["attributes"]["name"]} for f in items]


@st.cache_data(ttl=3600)
def get_flow_subscribers(flow_id: str) -> int:
    """
    Conta via GET /api/flows/{id}/profiles com meta.total.
    Retorna 0 se o endpoint não suportar.
    """
    try:
        resp = _get(
            f"{BASE_URL}/flows/{flow_id}/profiles",
            params={"page[size]": 1, "fields[profile]": "id"},
        )
        if resp.status_code == 200:
            total = resp.json().get("meta", {}).get("total")
            if total is not None:
                return int(total)
    except Exception:
        pass
    return 0


@st.cache_data(ttl=3600)
def get_flow_messages(flow_id: str) -> list[dict]:
    """
    Hierarquia: Flow → SEND_EMAIL actions → Flow Messages.
    1. GET /api/flows/{id}/flow-actions  (filtra action_type == SEND_EMAIL)
    2. GET /api/flow-actions/{id}/flow-messages
    Métricas ficam zeradas — flow-message-aggregates não existe na v3.
    utm_content pode ser extraído do nome do email se seguir padrão [EMXXXX].
    """
    resp = _get(
        f"{BASE_URL}/flows/{flow_id}/flow-actions",
        params={"fields[flow-action]": "action_type,status"},
    )
    if resp.status_code != 200:
        return []

    email_actions = [
        a for a in resp.json().get("data", [])
        if a["attributes"].get("action_type") == "SEND_EMAIL"
    ]

    messages = []
    for action in email_actions:
        action_id = action["id"]
        try:
            r = _get(
                f"{BASE_URL}/flow-actions/{action_id}/flow-messages",
                params={"fields[flow-message]": "name,content,position,created,updated"},
            )
            if r.status_code != 200:
                continue
            for m in r.json().get("data", []):
                attrs = m.get("attributes", {})
                messages.append({
                    "id": m["id"],
                    "name": attrs.get("name", ""),
                    "position": attrs.get("position", 0),
                    "sends": 0,
                    "opens": 0,
                    "open_rate": 0.0,
                    "clicks": 0,
                    "ctr": 0.0,
                })
        except Exception:
            pass

    messages.sort(key=lambda x: x["position"])
    return messages


# ─────────────────────────────────────────────
# CAMPANHAS
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_all_campaigns() -> list[dict]:
    """
    GET /api/campaigns?filter=equals(messages.channel,'email')
    Sem page[size] — obrigatório para evitar 400.
    Métricas via POST /api/campaign-values-reports/.
    Estatísticas válidas confirmadas: open_rate, click_rate, conversion_rate.
    A API retorna apenas taxas (não contagens). Sends ficam como 0.
    """
    raw = _get_all_pages(
        f"{BASE_URL}/campaigns",
        params={
            "filter": "equals(messages.channel,'email')",
            "fields[campaign]": "name,send_time,status",
        },
    )

    campaigns = []
    for item in raw:
        attrs = item.get("attributes", {})
        campaigns.append({
            "id": item["id"],
            "name": attrs.get("name", ""),
            "send_time": attrs.get("send_time", ""),
            "status": attrs.get("status", ""),
            "sends": 0,
            "open_rate": 0.0,
            "ctr": 0.0,
        })

    _enrich_campaign_metrics(campaigns)
    return campaigns


def _enrich_campaign_metrics(campaigns: list[dict]) -> None:
    """
    POST /api/campaign-values-reports/
    Estatísticas válidas (confirmado): open_rate, click_rate.
    Estrutura de resposta: results[].groupings.campaign_id + results[].statistics.{stat}
    """
    if not campaigns:
        return
    try:
        payload = {
            "data": {
                "type": "campaign-values-report",
                "attributes": {
                    "statistics": ["open_rate", "click_rate"],
                    "timeframe": _timeframe_1y(),
                    "conversion_metric_id": _PLACED_ORDER_METRIC_ID,
                },
            }
        }
        r = _post(f"{BASE_URL}/campaign-values-reports/", payload)
        if r.status_code not in (200, 202):
            return

        results = r.json().get("data", {}).get("attributes", {}).get("results", [])
        # Indexa por campaign_id (groupings.campaign_id)
        metrics_by_id: dict[str, dict] = {}
        for row in results:
            cid = row.get("groupings", {}).get("campaign_id")
            if cid:
                stats = row.get("statistics", {})
                metrics_by_id[cid] = stats

        for camp in campaigns:
            m = metrics_by_id.get(camp["id"], {})
            open_rate = float(m.get("open_rate", 0) or 0)
            click_rate = float(m.get("click_rate", 0) or 0)
            # API retorna valores entre 0-1; converte para percentual
            camp["open_rate"] = open_rate * 100 if open_rate <= 1 else open_rate
            camp["ctr"] = click_rate * 100 if click_rate <= 1 else click_rate
    except Exception:
        pass


# ─────────────────────────────────────────────
# FORMULÁRIOS
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_all_forms() -> list[dict]:
    """
    GET /api/forms
    Métricas via POST /api/form-values-reports/.
    """
    try:
        raw = _get_all_pages(
            f"{BASE_URL}/forms",
            params={"fields[form]": "name,status"},
        )
    except Exception:
        return []

    forms = [
        {
            "id": item["id"],
            "name": item.get("attributes", {}).get("name", ""),
            "views": 0,
            "submissions": 0,
            "conversion_rate": 0.0,
        }
        for item in raw
    ]

    _enrich_form_metrics(forms)
    return forms


def _enrich_form_metrics(forms: list[dict]) -> None:
    """
    POST /api/form-values-reports/
    Testa estatísticas válidas progressivamente.
    """
    if not forms:
        return

    # Tenta diferentes combinações de statistics até uma funcionar
    stat_sets = [
        ["view_count", "submit_count", "submit_rate"],
        ["views", "submits", "rate"],
        ["open_rate", "click_rate"],  # fallback genérico
    ]
    for stats in stat_sets:
        try:
            payload = {
                "data": {
                    "type": "form-values-report",
                    "attributes": {
                        "statistics": stats,
                        "timeframe": _timeframe_1y(),
                    },
                }
            }
            r = _post(f"{BASE_URL}/form-values-reports/", payload)
            if r.status_code not in (200, 202):
                continue

            results = r.json().get("data", {}).get("attributes", {}).get("results", [])
            if not results:
                return

            metrics_by_id: dict[str, dict] = {}
            for row in results:
                fid = row.get("groupings", {}).get("form_id")
                if fid:
                    metrics_by_id[fid] = row.get("statistics", {})

            for form in forms:
                m = metrics_by_id.get(form["id"], {})
                if not m:
                    continue
                views = int(m.get("view_count", m.get("views", 0)) or 0)
                subs = int(m.get("submit_count", m.get("submits", 0)) or 0)
                rate = float(m.get("submit_rate", m.get("rate", 0)) or 0)
                form["views"] = views
                form["submissions"] = subs
                form["conversion_rate"] = rate * 100 if rate <= 1 else rate
            return
        except Exception:
            continue


# ─────────────────────────────────────────────
# INSCRITOS
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_total_email_subscribers() -> int:
    """
    Total de profiles com email marketing ativo via meta.total.
    Fallback: soma meta.total de cada lista.
    """
    try:
        resp = _get(
            f"{BASE_URL}/profiles",
            params={
                "filter": "equals(subscriptions.email.marketing.can_receive_email_marketing,true)",
                "page[size]": 1,
                "fields[profile]": "id",
            },
        )
        if resp.status_code == 200:
            total = resp.json().get("meta", {}).get("total")
            if total is not None:
                return int(total)
    except Exception:
        pass
    return _count_list_subscribers()


def _count_list_subscribers() -> int:
    """Fallback: soma meta.total dos profiles em cada lista."""
    try:
        lists = _get_all_pages(f"{BASE_URL}/lists", params={"fields[list]": "name"})
        total = 0
        for lst in lists:
            resp = _get(
                f"{BASE_URL}/lists/{lst['id']}/profiles",
                params={"page[size]": 1, "fields[profile]": "id"},
            )
            if resp.status_code == 200:
                t = resp.json().get("meta", {}).get("total", 0)
                total += int(t or 0)
        return total
    except Exception:
        return 0
