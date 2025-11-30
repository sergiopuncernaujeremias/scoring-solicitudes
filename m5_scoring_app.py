import os
import requests
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
from supabase import create_client, Client

# ------------------------------
# Configuración inicial
# ------------------------------
st.set_page_config(
    page_title="RentMatch · M5 Scoring de candidatos",
    layout="wide",
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
N8N_M5_WEBHOOK_URL = os.getenv("N8N_M5_WEBHOOK_URL")  # webhook específico para M5

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("⚠️ Faltan variables SUPABASE_URL o SUPABASE_KEY en el entorno.")
    st.stop()

if not N8N_M5_WEBHOOK_URL:
    st.warning("⚠️ Falta la variable N8N_M5_WEBHOOK_URL. Podrás ver la UI pero no habrá scoring.")
    
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------------------
# Helpers
# ------------------------------
def load_pisos() -> List[Dict[str, Any]]:
    """Carga todos los pisos de la tabla `pisos`."""
    res = supabase.table("pisos").select("*").execute()
    return res.data or []

def load_solicitudes_by_piso(id_piso: str) -> List[Dict[str, Any]]:
    """Carga todas las solicitudes/candidatos para un piso."""
    res = (
        supabase.table("solicitudes")
        .select("*")
        .eq("id_piso", id_piso)
        .execute()
    )
    return res.data or []

def build_piso_label(piso: Dict[str, Any]) -> str:
    """Texto amigable para el selectbox de pisos."""
    barrio = piso.get("barrio_ciudad") or "Zona desconocida"
    precio = piso.get("precio")
    m2 = piso.get("m2")
    id_corto = str(piso.get("id_piso"))[:8] if piso.get("id_piso") else "sin-id"

    partes = [f"[{id_corto}]"]
    if barrio:
        partes.append(f"{barrio}")
    if m2:
        partes.append(f"{m2} m²")
    if precio:
        partes.append(f"{precio} €/mes")

    return " · ".join(partes)


def build_candidate_label(c: Dict[str, Any]) -> str:
    """Texto amigable para mostrar el candidato en la tabla."""
    # Intenta varios nombres posibles, por si el CSV tiene distinto naming
    nombre = (
        c.get("nombre")
        or c.get("nombre_candidato")
        or c.get("full_name")
        or f"ID {str(c.get('id'))[:8]}"
    )
    return str(nombre)


def call_n8n_scoring(piso: Dict[str, Any], candidato: Dict[str, Any]) -> Dict[str, Any]:
    """
    Llama al webhook de n8n, que a su vez llama a GPT y (opcionalmente)
    actualiza Supabase. Devuelve un dict con score y explicación.
    """
    if not N8N_M5_WEBHOOK_URL:
        return {
            "score_afinidad": None,
            "explicacion": "N8N_M5_WEBHOOK_URL no está configurado.",
            "error": True,
        }

    payload = {
        "piso": piso,
        "candidato": candidato,
    }

    try:
        resp = requests.post(N8N_M5_WEBHOOK_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Esperamos que n8n devuelva algo así:
        # { "score_afinidad": 92, "explicacion": "..." }
        score = data.get("score_afinidad")
        explicacion = data.get("explicacion") or data.get("explicación")

        return {
            "score_afinidad": score,
            "explicacion": explicacion,
            "error": False,
        }
    except Exception as e:
        return {
            "score_afinidad": None,
            "explicacion": f"Error llamando a n8n: {e}",
            "error": True,
        }


# ------------------------------
# UI Streamlit
# ------------------------------
APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    color: #1f2937;
}

/* Main container adjustments */
.main .block-container {
    padding-top: 1rem;
    padding-bottom: 3rem;
    max_width: 1200px;
}

/* Cards */
.rm-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    margin-bottom: 1.5rem;
    transition: box-shadow 0.2s ease;
}
.rm-card:hover {
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.025);
}

/* Hero Section */
.rm-hero {
    background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
    border-radius: 16px;
    padding: 3rem 2rem;
    margin-bottom: 2rem;
    color: white;
    box-shadow: 0 10px 15px -3px rgba(79, 70, 229, 0.2);
    position: relative;
    overflow: hidden;
}
.rm-hero::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image: url('https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=1600&q=80');
    background-size: cover;
    background-position: center;
    opacity: 0.15;
    mix-blend-mode: overlay;
}
.rm-hero-content {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    gap: 1.5rem;
}
.rm-hero-icon {
    font-size: 3.5rem;
    background: rgba(255,255,255,0.2);
    width: 80px; height: 80px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 50%;
    backdrop-filter: blur(4px);
}
.rm-hero-text h1 {
    margin: 0;
    font-weight: 700;
    font-size: 2.25rem;
    color: white;
    letter-spacing: -0.025em;
}
.rm-hero-text p {
    margin: 0.5rem 0 0 0;
    font-size: 1.1rem;
    color: rgba(255,255,255,0.9);
}

/* Utilities */
.text-sm { font-size: 0.875rem; }
.text-muted { color: #6b7280; }
.font-bold { font-weight: 600; }
</style>
"""

st.markdown(APP_CSS, unsafe_allow_html=True)

st.markdown(
    """
    <div class="rm-hero">
      <div class="rm-hero-content">
        <div class="rm-hero-icon">🏆</div>
        <div class="rm-hero-text">
          <h1>RentMatch · Scoring</h1>
          <p>Priorización inteligente de candidatos con IA</p>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- Carga de pisos ---
st.markdown("<div class='rm-card'>", unsafe_allow_html=True)
st.subheader("1. Selección del Inmueble")
with st.spinner("Cargando pisos desde Supabase..."):
    pisos = load_pisos()

if not pisos:
    st.info("No se han encontrado pisos en la tabla `pisos`.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# Mapeamos labels para el selectbox
piso_labels = {build_piso_label(p): p for p in pisos}

selected_label = st.selectbox(
    "Elige el piso para ver sus candidatos:",
    options=list(piso_labels.keys()),
)

piso_seleccionado = piso_labels[selected_label]

# Mostrar ficha básica del piso
with st.expander("Ver detalles del piso seleccionado"):
    st.json(
        {
            "id": piso_seleccionado.get("id"),
            "id_piso": piso_seleccionado.get("id_piso"),
            "descripcion_ia": piso_seleccionado.get("descripcion_ia"),
            "precio": piso_seleccionado.get("precio"),
            "barrio_ciudad": piso_seleccionado.get("barrio_ciudad"),
            "m2": piso_seleccionado.get("m2"),
            "habitaciones": piso_seleccionado.get("habitaciones"),
            "banos": piso_seleccionado.get("banos"),
            "max_ocupantes": piso_seleccionado.get("max_ocupantes"),
            # aquí podrían ir otros campos de preferencias del arrendador:
            "ingreso_minimo": piso_seleccionado.get("ingreso_minimo"),
            "admite_mascotas_inquilino": piso_seleccionado.get("admite_mascotas_inquilino"),
        }
    )
st.markdown("</div>", unsafe_allow_html=True)

# --- Carga de solicitudes para ese piso ---
st.markdown("<div class='rm-card'>", unsafe_allow_html=True)
st.subheader("2. Candidatos y Scoring")

with st.spinner("Cargando solicitudes de candidatos..."):
    solicitudes = load_solicitudes_by_piso(piso_seleccionado["id_piso"])

if not solicitudes:
    st.warning("Este piso todavía no tiene solicitudes en la tabla `solicitudes`.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

st.write(f"Se han encontrado **{len(solicitudes)}** solicitudes.")

df_solicitudes = pd.DataFrame(solicitudes)

# Para no marear, oculta las columnas más técnicas si quieres
cols_visibles = [
    c for c in df_solicitudes.columns
    if c not in ("id_piso", "created_at")
]
st.dataframe(df_solicitudes[cols_visibles], use_container_width=True)

# --- Botón para lanzar scoring vía n8n/GPT ---
st.markdown("---")
st.write("Pulsa el botón para analizar la afinidad de cada candidato con las preferencias del piso.")

ejecutar_scoring = st.button("✨ Calcular scoring con IA (vía n8n)", type="primary")

if ejecutar_scoring:
    resultados = []
    with st.spinner("Llamando a n8n para cada candidato..."):
        for cand in solicitudes:
            resultado = call_n8n_scoring(piso_seleccionado, cand)

            fila = {
                "candidato": build_candidate_label(cand),
                "id_solicitud": cand.get("id"),
                "score_afinidad": resultado.get("score_afinidad"),
                "explicacion": resultado.get("explicacion"),
                "error": resultado.get("error"),
            }
            resultados.append(fila)

    df_resultados = pd.DataFrame(resultados)

    # Ordenamos de mayor a menor score (cuando exista)
    if "score_afinidad" in df_resultados.columns:
        df_resultados = df_resultados.sort_values(
            by="score_afinidad",
            ascending=False,
            na_position="last"
        )

    st.success("Scoring completado.")
    st.subheader("🏆 Ranking de candidatos")

    st.dataframe(df_resultados, use_container_width=True)

    # Vista tipo “cards” opcional
    st.markdown("### Vista detallada")
    for _, row in df_resultados.iterrows():
        score_txt = (
            f"{int(row['score_afinidad'])}/100"
            if pd.notnull(row["score_afinidad"])
            else "N/D"
        )
        st.markdown(
            f"""
            <div style="background:#f9fafb; padding:1rem; border-radius:8px; margin-bottom:1rem; border:1px solid #e5e7eb;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                    <h4 style="margin:0;">{row['candidato']}</h4>
                    <span style="background:#4f46e5; color:white; padding:2px 8px; border-radius:12px; font-size:0.9rem; font-weight:bold;">{score_txt}</span>
                </div>
                <p style="font-size:0.95rem; color:#4b5563; margin-bottom:0.5rem;">{row['explicacion']}</p>
                <div style="display:flex; gap:1rem; font-size:0.9rem;">
                    <label><input type="checkbox"> Contactar</label>
                    <label><input type="checkbox"> Descartar</label>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
else:
    st.info("Pulsa el botón de arriba para calcular el scoring de los candidatos.")

st.markdown("</div>", unsafe_allow_html=True)

