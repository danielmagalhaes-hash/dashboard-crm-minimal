FLOW_MAPPING = {
    "[Fluxo] Recuperação de Check-out Shopify - Envio ChatFlux - Novo Modelo 2026": "abandoned_cart",
    "[Fluxo] Recuperação de Check-out [Chat Flux] - Novo Modelo 2026": "abandoned_cart",
    "[FLUXO] Welcome - Novo Modelo 2026": "welcome",
    "[Fluxo] Welcome Facebook": "welcomefacebook",
    "[Fluxo] PageView - Perpetuo - Novo Modelo 2026": "fluxo-pageview",
    "[FLUXO] [Aquisição] [Check-out Abandonado] [30 - 60 dias] - Novo modelo 2026": "check-out-30-60d",
    "[FLUXO] - [Aquisição] - Recuperação de Check-out 60-90D - Novo Modelo 2026": "check-out-60-90d",
    "[FLUXO] - [LEADS] - Recuperação de Check-out 90-120D - Novo Modelo 2026": "check-out-90-120d",
    "[FLUXO] - [Aquisição] - Recuperação de Check-out 120-150D - Novo Modelo 2026": "check-out-120-150d",
    "[FLUXO] - [Aquisição] - Recuperação de Check-out 150-180D - Novo Modelo 2026": "check-out-150-180d",
    "[FLUXO] [AQUISIÇÃO] - Pageview 30-60D - Novo Modelo 2026": "pageview-30-60d",
    "[FLUXO] [AQUISIÇÃO] - Pageview 60-90D - Novo Modelo 2026": "pageview-60-90d",
    "[FLUXO] [AQUISIÇÃO] - Pageview 90-120D - Novo Modelo 2026": "pageview-90-120d",
    "[FLUXO] [AQUISIÇÃO] - Pageview 120-150D - Novo Modelo 2026": "pageview-120-150d",
    "[FLUXO] [AQUISIÇÃO] - Pageview 150-180D - Novo Modelo 2026": "pageview-150-180d",
    "[Fluxo] [Retenção] - 21 - 60 DIAS": "retencao0-60_dias",
    "[Fluxo] [Retenção] - 60 - 90 DIAS": "60-90_dias",
    "[Fluxo] [Retenção] - 90 - 120 DIAS": "90-120_dias",
    "[Fluxo] [Retenção] 120-150D": "120-150_dias",
    "[Fluxo] [Retenção] 150-180D": "150-180_dias",
    "[Fluxo] [Retenção] 180-210D": "180+_dias",
    "[Fluxo] Desengajamento": "desengajamento",
    "[The Journey] - Boas Vindas": "thejourney",
}

MOF_FLOW_NAMES = [
    "[Fluxo] Fluxo MOF - Camiseta T - Novo Modelo 2026",
    "[Fluxo] Fluxo MOF - Compre 3 e Leve 4 - Novo Modelo 2026",
    "[Fluxo] Fluxo MOF - Compre 3 e Leve 4 + Brinde - Novo Modelo 2026",
    "[Fluxo] Fluxo MOF - Jeans Novos - Novo Modelo 2026",
    "[Fluxo] Fluxo MOF - Comfort - Novo Modelo 2026",
    "[Fluxo] Fluxo MOF - Polo - Novo Modelo 2026",
]
MOF_CAMPAIGN_NAME = "fluxotof"
MOF_DISPLAY_NAME = "Fluxo MOF"


def get_campaign_for_flow(flow_name: str) -> str | None:
    if flow_name in MOF_FLOW_NAMES:
        return MOF_CAMPAIGN_NAME
    return FLOW_MAPPING.get(flow_name)
