from SPARQLWrapper import SPARQLWrapper, JSON
import pandas as pd
import csv
import sys
import time
import json
import os

similarity_indices = {"DOID": "doid_labels", "MESH": "mesh_labels"}

def search_rdf_index(search_term, index_name, result_column_name, top_k=10, endpoint="http://localhost:7200/repositories/WeVerify"):
    """
    Executes a SPARQL similarity search query on the given RDF repository.

    Parameters:
    - search_term (str): The term to search for in the RDF similarity index.
    - index_name (str): The name of the similarity index.
    - top_k (int, optional): The maximum number of results to return (default: 10).
    - endpoint (str, optional): The URL of the SPARQL endpoint (default: GraphDB local instance).

    Returns:
    - pandas.DataFrame: DataFrame containing 'doid_id' and 'score' columns.
    """
    # Define the SPARQL query
    query = f"""
    PREFIX : <http://www.ontotext.com/graphdb/similarity/>
    PREFIX similarity-index: <http://www.ontotext.com/graphdb/similarity/instance/>
    PREFIX pubo: <http://ontology.ontotext.com/publishing#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?documentID ?label ?score WHERE {{
        ?search a similarity-index:{index_name} ;
                :searchTerm "{search_term}" ;
                :searchParameters "" ;
                :documentResult ?result .
        ?result :value ?documentID ;
                :score ?score.
        optional {{ ?documentID rdfs:label ?label }}
        optional {{ ?documentID skos:prefLabel ?label }}
    }} ORDER BY DESC(?score) LIMIT {top_k}
    """

    # Initialize the SPARQL endpoint
    sparql = SPARQLWrapper(endpoint)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)

    # Execute the query
    try:
        results = sparql.query().convert()
        data = [(res["documentID"]["value"], res["label"]["value"],float(res["score"]["value"])) for res in results["results"]["bindings"]]

        # Convert to Pandas DataFrame
        df = pd.DataFrame(data, columns=[result_column_name, "label", "score"])
        return df
    except Exception as e:
        print("Error executing SPARQL query:", e)
        return pd.DataFrame(columns=[result_column_name, "score"])


def read_class_id_to_pref_label(file_name):
    class_id_to_label = {}

    # Increase the maximum field size limit to handle large cells
    csv.field_size_limit(sys.maxsize)

    with open(file_name, mode='r', newline='', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file, delimiter=',')
        for row in csv_reader:
            try:
                class_id = row['Class ID']
                preferred_label = row['Preferred Label']
                # Store the class_id and preferred_label in the dictionary
                class_id_to_label[class_id] = preferred_label
            except (ValueError, KeyError, UnicodeDecodeError) as e:
                # Skip rows with errors (exceeds max length or other errors)
                print(f"Skipping row due to error: {e}")

    return class_id_to_label

def compute_hits_at_n(selected_pair, selected_mapping, save_candidates):
    start_time = time.time()

    kg_1, kg_2 = selected_pair.split("-")

    # get the selected mapping as df
    mappings_df = pd.read_csv("../data/mappings/" + selected_mapping, sep=",", dtype=str)
    print(f' Mappings has {len(mappings_df)} ids')

    kg_1_to_kg_2 = mappings_df.set_index(kg_1)[kg_2].to_dict()

    index_name = similarity_indices[kg_2]
    if not index_name:
        print("No similarity index found for {}".format(kg_2))
        return

    result_column_name = index_name.replace("_labels", "_id")


    kg_1_id_to_label = read_class_id_to_pref_label("../data/datasets/csv/" + kg_1 + ".csv")
    print(f' {kg_1} has {len(kg_1_id_to_label)} ids')

    # this is needed just for caching the correct label id from kg_2
    kg_2_id_to_label = read_class_id_to_pref_label("../data/datasets/csv/" + kg_2 + ".csv")
    print(f' {kg_2} has {len(kg_2_id_to_label)} ids')

    kg_1_label_to_kg_2 = {
        (id1, label_1): kg_1_to_kg_2[id1]
        for id1, label_1 in kg_1_id_to_label.items()
        if id1 in kg_1_to_kg_2
    }

    generated_candidates_file = None
    if save_candidates:
        generated_candidates_file = ("../data/candidates/" + selected_pair + "_" + selected_mapping).replace(".csv",
                                                                                                             ".json")

    hits_at_n_results, _ = calculate_hits_at_n(kg_1_label_to_kg_2, search_rdf_index, kg_2_id_to_label=kg_2_id_to_label,
                                               index_name=index_name,
                                               result_column_name=result_column_name,
                                               generated_candidates_file=generated_candidates_file,
                                               k_values=[1, 3, 5, 10, 20, 40])
    elapsed_time = time.time() - start_time

    return hits_at_n_results, len(mappings_df), elapsed_time


def calculate_hits_at_n(kg1_label_to_kg2, search_rdf_index, kg_2_id_to_label, index_name, result_column_name,
                        generated_candidates_file,
                        k_values=[1, 3, 5, 10]):
    """
    Computes Hits@N metric for each entry in kg1_label_to_kg2.
    Optionally it persists the generated candidates in generated_candidates_file.

    Parameters:
    - kg1_label_to_kg2 (dict): A dictionary mapping ICD-10 labels to DOID IDs.
    - search_rdf_index (function): A function that executes SPARQL search and returns a DataFrame with id, label and score columns

    Returns:
    - A dictionary with Hits@1, Hits@3, Hits@5, and Hits@10 scores.
    - A list of failed search queries (ICD-10 labels that didn't match in top 10 results).
    """
    hits_at_n = {k: 0 for k in k_values}  # Track hits
    total_queries = len(kg1_label_to_kg2)  # Total number of queries
    failed_searches = []  # List to store failed queries
    all_candidates = {}


    for (kg1_id, kg1_label), correct_kg2_id in kg1_label_to_kg2.items():
        # Call search function and get results
        search_results = search_rdf_index(kg1_label, index_name, result_column_name, top_k=100)

        # limit the score up to the 4th decimal point to save space in the persisted files
        search_results["score"] = search_results["score"].round(4)

        equivalent_id_label = None
        if generated_candidates_file:
            if correct_kg2_id not in kg_2_id_to_label:
                print("There is no label for correct target id {}".format(correct_kg2_id))
            else:
                equivalent_id_label = kg_2_id_to_label[correct_kg2_id]

            all_candidates[kg1_id] = {"label": kg1_label,
                                      "equivalent_id": correct_kg2_id,
                                      "equivalent_id_label": equivalent_id_label,
                                      "candidates": search_results.to_dict(orient="records")
                                      }

        # Extract top-N KG2 IDs from results
        retrieved_kg2_ids = search_results[result_column_name].tolist()

        # Debug print for verification
        # print(f"Search Query: '{kg1_label}'")
        # print(f"Expected {result_column_name}: {correct_kg2_id}")
        # print(f"Retrieved {result_column_name} IDs (Top 10): {retrieved_kg2_ids[:10]}")

        # Track if at least one hit was found in the top 10
        match_found = False

        # Check if correct_kg2_id appears in the top N results
        for N in k_values:
            # Ensure N doesn't exceed available results
            retrieved_subset = retrieved_kg2_ids[:min(N, len(retrieved_kg2_ids))]

            if correct_kg2_id in retrieved_subset:
                hits_at_n[N] += 1  # Increase hit count for this N
                match_found = True  # Mark match as found

        # If no match found in the top 10, add to failed searches list
        if not match_found:
            failed_searches.append(kg1_label)

    # Normalize counts into percentages
    hits_at_n = {N: round((hits_at_n[N] / total_queries) * 100, 2) for N in hits_at_n}

    if generated_candidates_file:
        # Persists candidates
        os.makedirs(os.path.dirname(generated_candidates_file), exist_ok=True)
        result_json = {"hits_at_k": hits_at_n,
                       "candidates": all_candidates
                       }
        with open(generated_candidates_file, "w", encoding="utf-8") as f:
            json.dump(result_json, f, indent=2, ensure_ascii=False)
        print("Candidates written to {}".format(generated_candidates_file))

    return hits_at_n, failed_searches