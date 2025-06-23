import openai
import os
import json
import pandas as pd
from SPARQLWrapper import SPARQLWrapper, JSON
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(filename='.env'))

# Create the OpenAI client (reads API key from environment variable)
client = openai.OpenAI()

# Prefixes for the available target ontologies, they are removed from the prompts, to save on cost per tokens
target_prefixes = {"DOID": "http://purl.obolibrary.org/obo/",
                   "MESH": "http://purl.bioontology.org/ontology/MESH/"}

def find_equivalent_entity(model: str, prompt: str) -> str:
    """
    Given an entity ID from the source ontology, asks OpenAI to find the equivalent in the target ontology.

    :param prompt: The prompt send to OpenAI

    """

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0  # deterministic output
        )

        answer = response.choices[0].message.content.strip()
        return answer

    except Exception as e:
        print(f"Error querying OpenAI: {e}")
        return None

def create_prompt_with_candidates(source_ontology: str, target_ontology: str, source_id: str, info: dict ) -> str:
    target_id_name = target_ontology.lower() + "_id"

    prompt = f"""You are comparing the ontologies {source_ontology} and {target_ontology}.

    Given the source entity:
    - ID: {source_id}
    - Label: {info["label"]}

    Here are candidate equivalent entities in {target_ontology}:
    """
    for c in info["candidates"]:
        short_id = c[target_id_name].rsplit('/', 1)[-1]
        prompt += f"- ID: {short_id}, Label: {c['label']}, String-similarity-score: {c['score']}\n"

    prompt += "\nWhich one is the best match?"
    prompt += "\nIMPORTANT: Return only the ID, and nothing else. Do not explain."
    return prompt

def get_extended_info(ontology: str, entity_id: str) -> dict:
    """
    Retrieve alternative and parent class labels from GraphDB using SPARQL queries loaded from file.
    """
    endpoint = "http://localhost:7200/repositories/WeVerify"
    sparql = SPARQLWrapper(endpoint)
    sparql.setReturnFormat(JSON)

    # Map ontology to query file
    query_file_map = {
        "icd10cm": "../queries/extended_info_icd10cm_mesh.rq",
        "doid": "../queries/extended_info_doid.rq",
        "mesh": "../queries/extended_info_icd10cm_mesh.rq"
    }

    ontology_key = ontology.lower()
    if ontology_key not in query_file_map:
        raise ValueError(f"Unsupported ontology: {ontology}")

    # Load and inject entity ID into query
    query_file = query_file_map[ontology_key]
    with open(query_file, "r", encoding="utf-8") as f:
        query_template = f.read()
    query = query_template.replace("{{ENTITY_URI}}", entity_id)

    # Execute the SPARQL query
    sparql.setQuery(query)
    results = sparql.query().convert()

    # Parse result
    bindings = results["results"]["bindings"]
    if not bindings:
        return {"altLabels": [], "parentClassLabels": []}

    result = bindings[0]
    alt_labels = result.get("altLabels", {}).get("value", "")
    parent_labels = result.get("parentClassLabels", {}).get("value", "")

    return {
        "altLabels": [label.strip() for label in alt_labels.split(";") if label.strip()],
        "parentClassLabels": [label.strip() for label in parent_labels.split(";") if label.strip()]
    }


def create_extended_prompt(source_ontology: str, target_ontology: str, source_id: str, info: dict ) -> str:
    target_id_name = target_ontology.lower() + "_id"
    source_extended_info = get_extended_info(source_ontology, source_id)

    # Build optional label sections
    alt_labels_section = (
        f"- Alternative Labels: {'; '.join(source_extended_info['altLabels'])}"
        if source_extended_info["altLabels"] else ""
    )

    parent_labels_section = (
        f"- Parent Classes Labels: {'; '.join(source_extended_info['parentClassLabels'])}"
        if source_extended_info["parentClassLabels"] else ""
    )

    # Join only non-empty sections
    optional_sections = "\n".join(filter(None, [alt_labels_section, parent_labels_section]))

    # Construct the final prompt
    prompt = f"""You are comparing the ontologies {source_ontology} and {target_ontology}.

    Given the source entity:
    - ID: {source_id}
    - Label: {info["label"]}
    {optional_sections}

    Here are candidate equivalent entities in {target_ontology}:
    """


    for c in info["candidates"]:
        short_id = c[target_id_name].rsplit('/', 1)[-1]
        candiadate_extended_info = get_extended_info(target_ontology, c[target_id_name])
        prompt += f"- ID: {short_id}, Label: {c['label']}, String-similarity-score: {c['score']}"
        if candiadate_extended_info["altLabels"]:
            prompt+=f", Alternative Labels: {'; '.join(candiadate_extended_info['altLabels'])}"
        if candiadate_extended_info["parentClassLabels"]:
            prompt+=f", Parent Classes Labels: {'; '.join(candiadate_extended_info['parentClassLabels'])}"
        prompt+="\n"

    prompt += "\nWhich one is the best match?"
    prompt += "\nIMPORTANT: Return only the ID, and nothing else. Do not explain."
    return prompt

def classify(data, model, source, target, extended_prompt):
    num_queries = len(data)

    target_prefix = target_prefixes[target]

    correct_cnt = 0
    results = []

    for i, (source_id, info) in enumerate(data.items()):

        label = info.get("label")
        equivalent_id = info.get("equivalent_id")
        equivalent_id_label = info.get("equivalent_id_label")

        prompt = (
            create_extended_prompt(source, target, source_id, info)
            if extended_prompt
            else create_prompt_with_candidates(source, target, source_id, info)
        )
        llm_answer = target_prefix +  find_equivalent_entity(model, prompt)

        if llm_answer == equivalent_id:
            print(f"Correct answer for {source_id}: {label}!")
            correct_cnt += 1
        else:
            print(f"For {source_id}: LLM answer is {llm_answer}, but equivalent ID is {equivalent_id}")
        results.append({
            "Source ID": source_id,
            "Label": label,
            "Predicted Target ID": llm_answer,
            "Correct Target Label": equivalent_id_label,
            "Correct Target ID": equivalent_id,
        })


    df = pd.DataFrame(results)
    score = correct_cnt / num_queries if num_queries > 0 else 0.0
    return df, score


#Example usage
if __name__ == "__main__":
    # extended_info_icd = get_extended_info("icd10cm", "http://purl.bioontology.org/ontology/ICD10CM/J09.X")
    # extended_info_doid = get_extended_info("doid", "http://purl.obolibrary.org/obo/DOID_8469")
    # extended_info_mesh = get_extended_info("mesh", "http://purl.bioontology.org/ontology/MESH/D017889")

    file_path = "../data/candidates/ICD10CM-DOID_extended_mappings_doid_icd10cm.json"

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates_data = data.get("candidates", {})

    max_queries = 100
    total_queries = min(len(candidates_data), max_queries)
    source_ontology = "ICD10CM"
    target_ontology = "DOID"

    target_prefix = "http://purl.obolibrary.org/obo/"

    correct_cnt = 0
    missing_candidate_cnt = 0

    # model = "gpt-4o-mini"
    # model = "gpt-3.5-turbo"
    model = "gpt-4o-2024-11-20"

    for i, (source_id, info) in enumerate(candidates_data.items()):
        if i >= max_queries:
            break

        label = info.get("label")
        equivalent_id = info.get("equivalent_id")
        candidate_list = info.get("candidates", [])
        candidate_ids = [c["doid_id"] for c in info.get("candidates", [])]

        if (equivalent_id not in candidate_ids):
            print(f"The correct equivalent entity ID for {source_id}: {label} is not among the candidates.")
            missing_candidate_cnt += 1
            continue

        prompt = create_extended_prompt(source_ontology, target_ontology, source_id, info)
        print(prompt)
        llm_answer = target_prefix +  find_equivalent_entity(model, prompt)

        if llm_answer == equivalent_id:
            print(f"Correct answer for {source_id}: {label}!")
            correct_cnt += 1
        else:
            print(f"For {source_id}: LLM answer is {llm_answer}, but equivalent ID is {equivalent_id}")



    print(f"Correct answers: {correct_cnt} out of {total_queries} - {round(100 * (correct_cnt / total_queries), 2)}%")
    print(
        f"Correct answers when answer is in the candidates: {correct_cnt} out of {total_queries - missing_candidate_cnt} - {round(100 * (correct_cnt / (total_queries - missing_candidate_cnt)), 2)}%")
    wrong_cnt = total_queries - correct_cnt
    print(
        f"Out of {wrong_cnt} wrong answers {missing_candidate_cnt} are because of answer not in provided candidates - {round(100 * (missing_candidate_cnt / wrong_cnt), 2)}%")
