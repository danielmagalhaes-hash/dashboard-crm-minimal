import requests
import streamlit as st
from dotenv import load_dotenv
import os

load_dotenv()
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY")

BASE_URL = "https://a.klaviyo.com/api"
HEADERS = {
    "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
    "revision": "2024-10-15",
    "Accept": "application/json",
}


def _get_all_pages(url: str, params: dict = None) -> list[dict]:
    """Percorre todas as páginas cursor-based e retorna lista flat de items."""
    items = []
    next_url = url
    while next_url:
        resp = requests.get(next_url, headers=HEADERS, params=params if next_url == url else None)
        resp.raise_for_status()
        body = resp.json()
        items.extend(body.get("data", []))
        next_url = body.get("links", {}).get("next")
    return items


@st.cache_data(ttl=3600)
def get_all_flows() -> list[dict]:
    """
    GET /api/flows
    Retorna lista de flows com id e name.
    """
    items = _get_all_pages(f"{BASE_URL}/flows", params={"fields[flow]": "name"})
    return [
        {"id": f["id"], "name": f["attributes"]["name"]}
        for f in items
    ]


@st.cache_data(ttl=3600)
def get_flow_subscribers(flow_id: str) -> int:
    """
    Número de profiles que entraram no flow.
    Usa GET /api/flow-profiles com filter por flow id e conta via paginação.
    Fallback: retorna 0 se o endpoint não suportar.
    """
    try:
        url = f"{BASE_URL}/flows/{flow_id}/flow-profiles"
        # A API pode não suportar — capturamos e retornamos 0
        resp = requests.get(url, headers=HEADERS, params={"page[size]": 1})
        if resp.status_code == 404:
            return 0
        resp.raise_for_status()
        body = resp.json()
        # Tenta pegar total do meta, se disponível
        total = body.get("meta", {}).get("total", None)
        if total is not None:
            return int(total)
        # Fallback: conta contando todas as páginas (pode ser lento)
        count = len(body.get("data", []))
        next_url = body.get("links", {}).get("next")
        while next_url:
            r = requests.get(next_url, headers=HEADERS)
            r.raise_for_status()
            b = r.json()
            count += len(b.get("data", []))
            next_url = b.get("links", {}).get("next")
        return count
    except Exception:
        return 0


@st.cache_data(ttl=3600)
def get_flow_messages(flow_id: str) -> list[dict]:
    """
    Retorna emails de um flow com métricas.
    1. GET /api/flow-messages?filter=equals(flow.id,"{flow_id}")
    2. Enriquece com /api/flow-message-aggregates para cada mensagem.
    Abordagem: flow-message-aggregates com conversion_metric_id (Placed Order).
    """
    params = {
        "filter": f'equals(flow.id,"{flow_id}")',
        "fields[flow-message]": "name,position,created,updated",
        "page[size]": 50,
    }
    raw = _get_all_pages(f"{BASE_URL}/flow-messages", params=params)

    messages = []
    for item in raw:
        attrs = item.get("attributes", {})
        msg = {
            "id": item["id"],
            "name": attrs.get("name", ""),
            "position": attrs.get("position", 0),
            "sends": 0,
            "opens": 0,
            "open_rate": 0.0,
            "clicks": 0,
            "ctr": 0.0,
        }
        # Busca métricas agregadas via /api/flow-message-aggregates
        try:
            agg_url = f"{BASE_URL}/flow-message-aggregates"
            agg_params = {
                "filter": f'equals(flow_message_id,"{item["id"]}")',
                "fields[flow-message-aggregate]": "send_count,open_count,open_rate,click_count,click_rate",
            }
            r = requests.get(agg_url, headers=HEADERS, params=agg_params)
            if r.status_code == 200:
                agg_data = r.json().get("data", [])
                if agg_data:
                    a = agg_data[0].get("attributes", {})
                    msg["sends"] = int(a.get("send_count", 0) or 0)
                    msg["opens"] = int(a.get("open_count", 0) or 0)
                    msg["open_rate"] = float(a.get("open_rate", 0) or 0) * 100
                    msg["clicks"] = int(a.get("click_count", 0) or 0)
                    msg["ctr"] = float(a.get("click_rate", 0) or 0) * 100
        except Exception:
            pass

        messages.append(msg)

    messages.sort(key=lambda x: x["position"])
    return messages


@st.cache_data(ttl=3600)
def get_all_campaigns() -> list[dict]:
    """
    GET /api/campaigns?filter=equals(messages.channel,'email')
    Enriquece com /api/campaign-values-reports para métricas de envio.
    """
    params = {
        "filter": "equals(messages.channel,'email')",
        "fields[campaign]": "name,send_time,status",
        "page[size]": 50,
    }
    raw = _get_all_pages(f"{BASE_URL}/campaigns", params=params)

    campaigns = []
    for item in raw:
        attrs = item.get("attributes", {})
        camp = {
            "id": item["id"],
            "name": attrs.get("name", ""),
            "send_time": attrs.get("send_time", ""),
            "status": attrs.get("status", ""),
            "sends": 0,
            "opens": 0,
            "open_rate": 0.0,
            "clicks": 0,
            "ctr": 0.0,
        }
        campaigns.append(camp)

    # Enriquece métricas via campaign-values-reports (bulk endpoint)
    _enrich_campaign_metrics(campaigns)
    return campaigns


def _enrich_campaign_metrics(campaigns: list[dict]) -> None:
    """
    Usa POST /api/campaign-values-reports para buscar métricas em lote.
    Endpoint real: POST /api/campaign-values-reports/
    """
    if not campaigns:
        return
    try:
        campaign_ids = [c["id"] for c in campaigns]
        # Klaviyo suporta até 100 ids por request
        for i in range(0, len(campaign_ids), 100):
            batch = campaign_ids[i:i + 100]
            payload = {
                "data": {
                    "type": "campaign-values-report",
                    "attributes": {
                        "timeframe": {"key": "all_time"},
                        "conversion_metric_id": None,
                        "filter": f"any(campaign_id,[{','.join(repr(x) for x in batch)}])",
                    }
                }
            }
            headers = {**HEADERS, "Content-Type": "application/json"}
            r = requests.post(f"{BASE_URL}/campaign-values-reports/", headers=headers, json=payload)
            if r.status_code not in (200, 202):
                continue
            results = r.json().get("data", {}).get("attributes", {}).get("results", [])
            metrics_by_id = {row.get("campaign_id"): row for row in results}
            for camp in campaigns:
                if camp["id"] in metrics_by_id:
                    m = metrics_by_id[camp["id"]]
                    camp["sends"] = int(m.get("sent_count", 0) or 0)
                    camp["opens"] = int(m.get("open_count", 0) or 0)
                    delivered = int(m.get("delivered_count", camp["sends"]) or camp["sends"])
                    camp["open_rate"] = (camp["opens"] / delivered * 100) if delivered else 0.0
                    camp["clicks"] = int(m.get("click_count", 0) or 0)
                    camp["ctr"] = (camp["clicks"] / delivered * 100) if delivered else 0.0
    except Exception:
        pass


@st.cache_data(ttl=3600)
def get_all_forms() -> list[dict]:
    """
    GET /api/forms
    Retorna id, name, views, submissions, conversion_rate.
    Enriquece com /api/form-values-reports se disponível.
    """
    try:
        raw = _get_all_pages(f"{BASE_URL}/forms", params={"fields[form]": "name,status"})
    except Exception:
        return []

    forms = []
    for item in raw:
        attrs = item.get("attributes", {})
        f = {
            "id": item["id"],
            "name": attrs.get("name", ""),
            "views": 0,
            "submissions": 0,
            "conversion_rate": 0.0,
        }
        forms.append(f)

    _enrich_form_metrics(forms)
    return forms


def _enrich_form_metrics(forms: list[dict]) -> None:
    """
    POST /api/form-values-reports/ para métricas de formulários.
    """
    if not forms:
        return
    try:
        form_ids = [f["id"] for f in forms]
        payload = {
            "data": {
                "type": "form-values-report",
                "attributes": {
                    "timeframe": {"key": "all_time"},
                    "filter": f"any(form_id,[{','.join(repr(x) for x in form_ids)}])",
                }
            }
        }
        headers = {**HEADERS, "Content-Type": "application/json"}
        r = requests.post(f"{BASE_URL}/form-values-reports/", headers=headers, json=payload)
        if r.status_code not in (200, 202):
            return
        results = r.json().get("data", {}).get("attributes", {}).get("results", [])
        metrics_by_id = {row.get("form_id"): row for row in results}
        for form in forms:
            if form["id"] in metrics_by_id:
                m = metrics_by_id[form["id"]]
                form["views"] = int(m.get("view_count", 0) or 0)
                form["submissions"] = int(m.get("submit_count", 0) or 0)
                views = form["views"]
                form["conversion_rate"] = (form["submissions"] / views * 100) if views else 0.0
    except Exception:
        pass


@st.cache_data(ttl=3600)
def get_total_email_subscribers() -> int:
    """
    Total de profiles com email subscription ativa.
    Usa GET /api/profiles com filter de consent.
    Abordagem: conta via meta.total se disponível, senão percorre páginas.
    """
    try:
        url = f"{BASE_URL}/profiles"
        params = {
            "filter": "equals(subscriptions.email.marketing.can_receive_email_marketing,true)",
            "page[size]": 1,
            "fields[profile]": "id",
        }
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        body = resp.json()
        total = body.get("meta", {}).get("total", None)
        if total is not None:
            return int(total)
        # Fallback: conta contando todas as páginas
        params["page[size]"] = 100
        return len(_get_all_pages(url, params=params))
    except Exception:
        return 0
