import streamlit as st
import pandas as pd
import sys
import os
import json
from dotenv import load_dotenv
from pathlib import Path
import math

from llm import llm_utils

# Add the main folder (parent of `app/`) to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from similarity.similarity_utils import search_rdf_index, compute_hits_at_n

load_dotenv()

# Load KG pairs and their mappings from JSON file
@st.cache_data
def load_similarity_config():
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'similarity_config.json'))
    with open(config_path, 'r') as f:
        return json.load(f)

def load_candidate_results():
    candidates_results_folder = Path("../data/candidates/")
    files = [f.name for f in candidates_results_folder.iterdir() if f.is_file()]
    return files

st.set_page_config(page_title="Entity Alignment Demo", layout="wide")
st.title("Entity Alignment Toolkit")
# Sidebar: Task selection

task = st.sidebar.selectbox(
    "Select Task",
    ["Candidates Finder", "Similarity Search Evaluation", "LLM classification"]
)


if task == "Candidates Finder":
    st.header("🔎 Candidates Finder")

    # Input: label to search
    search_term = st.text_input("Enter entity label:", "", help="Label of an entity to search equivalent for")

    # Input: index to use
    index_options = ["doid_labels", "mesh_labels"]
    index_name = st.selectbox("Choose similarity index:", index_options,
                              help="Choose against which similarity index to search")

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
elif task == "Similarity Search Evaluation":
    st.header("📊 Similarity Search Evaluation")

    config = load_similarity_config()
    kg_pairs = list(config.keys())
    selected_pair = st.selectbox("Knowledge Graphs Pair:", kg_pairs,
                                 help="Available knowledge graph pairs for evaluation with similarity search")

    selected_mapping = st.selectbox(
        "Mappings:", config[selected_pair] if selected_pair else [],
        help="Available seed mappings for the selected kg pair"
    )

    save_candidates = st.checkbox("Save candidates data", value=True,
                                  help="Persists generated candidates data to be used by the LLM classification task")

    if st.button("Compute Hits@K"):
        with st.spinner("Computing Hits@K..."):
            hits_scores, mapping_size, elapsed_time = compute_hits_at_n(selected_pair, selected_mapping, save_candidates)

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

# Task 3 LLM classification
elif task == "LLM classification":
    st.header("LLM classification ")

    # Saved candidates results
    candidates_results = load_candidate_results()
    candidates_results_names = [f.replace(".json","") for f in candidates_results if f.endswith(".json")]
    candidates_result = st.selectbox("Choose candidates results:", candidates_results_names,
                                     help="Choose candidates results generated from the task Similarity Search.")


    # Assumes the string is always in the format source-target_mappings
    main_part = candidates_result.split("_")[0]  # 'ICD10CM-DOID'
    source, target = main_part.split("-")
    target_id_name = target.lower() + "_id"

    # Input: index to use
    model_options = ["gpt-4o-mini", "gpt-3.5-turbo","gpt-4o-2024-11-20" ]
    model = st.selectbox("Choose OpenAI model:", model_options,
                         help="Select which OpenAI model to use for classification.")

    extended_prompt = st.checkbox("Use extended prompt", value=False,
                                  help="Uses more detailed prompts with all altLabel and parent classes for the source and all the candidates.")

    current_page = 1

    file_path = f"../data/candidates/{candidates_result}.json"

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates_data = data.get("candidates", {})

    filtered_candidates_data = {
        kg1_id: entry
        for kg1_id, entry in candidates_data.items()
        if entry.get("equivalent_id") in {c[target_id_name] for c in entry.get("candidates", [])}
    }

    print(f"{candidates_result} contains {len(filtered_candidates_data)} classifiable ids.")

    page_size = 10
    total_pages = math.ceil(len(filtered_candidates_data) / page_size)

    # Session state to track page
    if "current_page" not in st.session_state:
        st.session_state.current_page = 1

    # Get current page slice
    start_idx = (st.session_state.current_page - 1) * page_size
    end_idx = start_idx + page_size
    keys = list(filtered_candidates_data.keys())
    page_keys = keys[start_idx:end_idx]
    page_data = {k: filtered_candidates_data[k] for k in page_keys}

    # Track previous selections to reset cache when inputs change
    if "last_candidates_result" not in st.session_state:
        st.session_state.last_candidates_result = candidates_result
    if "last_model" not in st.session_state:
        st.session_state.last_model = model
    if "last_extended_prompt" not in st.session_state:
        st.session_state.last_extended_prompt = extended_prompt

    # Reset classified results if inputs changed
    if (
            st.session_state.last_candidates_result != candidates_result or
            st.session_state.last_model != model or
            st.session_state.last_extended_prompt != extended_prompt
    ):
        st.session_state.classified_pages = {}  # Clear the cache
        st.session_state.current_page = 1  # Optionally reset to page 1

        # Update tracked inputs
        st.session_state.last_candidates_result = candidates_result
        st.session_state.last_model = model
        st.session_state.last_extended_prompt = extended_prompt


    # Session state to cache results
    if "classified_pages" not in st.session_state:
        st.session_state.classified_pages = {}

    # Trigger LLM classification
    if st.button("Classify"):
        with st.spinner("Sending prompts to OpenAI..."):
            if st.session_state.current_page not in st.session_state.classified_pages:
                result_df, score = llm_utils.classify(page_data, model, source, target, extended_prompt)
                st.session_state.classified_pages[st.session_state.current_page] = (result_df, score)
            else:
                result_df, score = st.session_state.classified_pages[st.session_state.current_page]


            # Highlight prediction column
            def highlight_prediction(row):
                color = "lightgreen" if row["Predicted Target ID"] == row["Correct Target ID"] else "#fdd"
                return ["background-color: " + color if col == "Predicted Target ID" else "" for col in row.index]


            styled_df = result_df.style.apply(highlight_prediction, axis=1)
            st.dataframe(styled_df, use_container_width=True)

            # Compute aggregated score
            all_scores = [s for (_, s) in st.session_state.classified_pages.values()]
            cumulative_score = sum(all_scores) / len(all_scores)

            st.success(f"Page success rate: {100 * score:.2f}%")
            st.info(f"Cumulative success rate for first {len(st.session_state.classified_pages)} pages: {100 * cumulative_score:.2f}%")

    # Navigation controls
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("⬅️ Previous") and st.session_state.current_page > 1:
            st.session_state.current_page -= 1
    with col3:
        if st.button("Next ➡️") and st.session_state.current_page < total_pages:
            st.session_state.current_page += 1

    # Show pagination info
    st.caption(f"Page {st.session_state.current_page} of {total_pages}")