import streamlit as st
import pandas as pd
import sys
import os

# Add the main folder (parent of `app/`) to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from similarity.similarity_utils import search_rdf_index

st.set_page_config(page_title="Entity Alignment Demo", layout="wide")

st.title("🔎Candidates Finder")

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
        df_results = search_rdf_index(search_term, index_name, index_name.replace("_labels", "_id"), top_k=top_k)

        if df_results.empty:
            st.warning("No candidates found.")
        else:
            # Sort and limit results
            df_results = df_results.sort_values(by="score", ascending=False).head(top_k)
            df_results = df_results.reset_index(drop=True)
            df_results.index += 1
            st.success(f"Found {len(df_results)} candidates.")
            # Apply green gradient to 'score' column
            styled_df = df_results.style.background_gradient(
                subset=['score'],
                cmap='BuGn'  # You can also try 'Greens' 'YlGn' or 'BuGn'
            )
            st.dataframe(styled_df, use_container_width=True)