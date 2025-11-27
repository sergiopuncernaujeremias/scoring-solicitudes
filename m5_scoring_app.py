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
    # Aseguramos que lo que mandamos al filtro es un string
    id_piso_str = str(id_piso)

res = (
        supabase
        .table("solicitudes")          # OJO: aquí debe ser exactamente el nombre de tu tabla
        .select("*")
        .eq("id_piso", id_piso_str)    # OJO: y aquí el nombre exacto de la columna en Supabase
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
st.title("🏠 RentMatch · M5 Scoring / priorización de candidatos")

st.markdown(
    """
Esta pantalla es para el **arrendador**.

1. Selecciona un piso.
2. Verás todas las solicitudes para ese piso.
3. Pulsa **“Calcular scoring con IA (vía n8n)”** para que GPT, desde n8n, evalúe a los candidatos.
"""
)

# --- Carga de pisos ---
with st.spinner("Cargando pisos desde Supabase..."):
    pisos = load_pisos()

if not pisos:
    st.info("No se han encontrado pisos en la tabla `pisos`.")
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

# --- Carga de solicitudes para ese piso ---
with st.spinner("Cargando solicitudes de candidatos..."):
    solicitudes = load_solicitudes_by_piso(piso_seleccionado["id_piso"])

if not solicitudes:
    st.warning("Este piso todavía no tiene solicitudes en la tabla `solicitudes`.")
    st.stop()

st.subheader("📋 Solicitudes encontradas para este piso")

df_solicitudes = pd.DataFrame(solicitudes)

# Para no marear, oculta las columnas más técnicas si quieres
cols_visibles = [
    c for c in df_solicitudes.columns
    if c not in ("id_piso", "created_at")
]
st.dataframe(df_solicitudes[cols_visibles], use_container_width=True)

# --- Botón para lanzar scoring vía n8n/GPT ---
st.markdown("---")
st.subheader("⚙️ Scoring de candidatos con IA (GPT vía n8n)")

ejecutar_scoring = st.button("Calcular scoring con IA (vía n8n)")

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
    st.markdown("### Vista resumida")
    for _, row in df_resultados.iterrows():
        score_txt = (
            f"{int(row['score_afinidad'])}/100"
            if pd.notnull(row["score_afinidad"])
            else "N/D"
        )
        st.markdown(
            f"""
**{row['candidato']}** — **{score_txt}**  
{row['explicacion']}

- [ ] Contactar  
- [ ] Descartar  

---
"""
        )
else:
    st.info("Pulsa el botón de arriba para calcular el scoring de los candidatos.")
