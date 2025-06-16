import streamlit as st
import pandas as pd
import sys
import os
import json

# Add the main folder (parent of `app/`) to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from similarity.similarity_utils import search_rdf_index, compute_hits_at_n

# Load KG pairs and their mappings from JSON file
@st.cache_data
def load_similarity_config():
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'similarity_config.json'))
    with open(config_path, 'r') as f:
        return json.load(f)

st.set_page_config(page_title="Entity Alignment Demo", layout="wide")
st.title("🧠 Entity Alignment Toolkit")

# Sidebar: Task selection
task = st.sidebar.selectbox(
    "Select Task",
    ["Candidates Finder", "Similarity Search"]
)

# Task 1: Candidates Finder
if task == "Candidates Finder":
    st.header("🔎 Candidates Finder")

    # Input: label to search
    search_term = st.text_input("Enter entity label:", "")

    # Input: index to use
    index_options = ["doid_labels", "mesh_labels"]
    index_name = st.selectbox("Choose similarity index:", index_options)

    # Optional: limit number of results
    top_k = st.slider("Number of candidates", 1, 50, 10)

    # Search button
    if st.button("Search Candidates") and search_term:
        with st.spinner("Searching GraphDB index..."):
            df_results = search_rdf_index(
                search_term,
                index_name,
                index_name.replace("_labels", "_id"),
                top_k=top_k
            )

            if df_results.empty:
                st.warning("No candidates found.")
            else:
                # Sort and style results
                df_results = df_results.sort_values(by="score", ascending=False).head(top_k)
                df_results = df_results.reset_index(drop=True)
                df_results.index += 1
                st.success(f"Found {len(df_results)} candidates.")
                styled_df = df_results.style.background_gradient(
                    subset=['score'],
                    cmap='BuGn'
                )
                st.dataframe(styled_df, use_container_width=True)

# Task 2: Similarity Search
elif task == "Similarity Search":
    st.header("📊 Similarity Search Evaluation")

    config = load_similarity_config()
    kg_pairs = list(config.keys())
    selected_pair = st.selectbox("Knowledge Graphs Pair:", kg_pairs)
    selected_mapping = st.selectbox(
        "Mappings:", config[selected_pair] if selected_pair else []
    )

    if st.button("Compute Hits@K"):
        with st.spinner("Computing Hits@K..."):
            hits_scores, mapping_size, elapsed_time = compute_hits_at_n(selected_pair, selected_mapping)

            if not hits_scores:
                st.warning("No results returned.")
            else:
                st.success("Hits@K Results:")

                # Prepare DataFrame: one row with all values
                hits_row = {f"Hits@{k}": v for k, v in hits_scores.items()}
                hits_row["Mapping size"] = mapping_size
                hits_df = pd.DataFrame([hits_row])

                # Reorder columns: 'Mapping size' first
                cols = ["Mapping size"] + [f"Hits@{k}" for k in sorted(hits_scores.keys())]
                hits_df = hits_df[cols]

                # Apply green gradient styling to Hits@K columns (vmin/vmax fixed to 0–100)
                styled_hits_df = (
                    hits_df.style.format(precision=2)
                    .background_gradient(cmap='BuGn', axis=1, subset=cols[1:], vmin=0, vmax=100)
                    .hide(axis='index')  # Hide row index
                )

                st.dataframe(styled_hits_df, use_container_width=True)
                st.caption(f"Computed in {elapsed_time:.2f} seconds.")