import openai
import os
import json
import pandas as pd

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


def classify(data, model, source, target):
    num_queries = len(data)

    target_prefix = target_prefixes[target]

    correct_cnt = 0
    results = []

    for i, (source_id, info) in enumerate(data.items()):

        label = info.get("label")
        equivalent_id = info.get("equivalent_id")

        prompt = create_prompt_with_candidates(source, target, source_id, info)
        llm_answer = target_prefix +  find_equivalent_entity(model, prompt)

        if llm_answer == equivalent_id:
            print(f"Correct answer for {source_id}: {label}!")
            correct_cnt += 1

        results.append({
            "Source ID": source_id,
            "Label": label,
            "Predicted Target ID": llm_answer,
            "Correct Target ID": equivalent_id
        })

    df = pd.DataFrame(results)
    score = correct_cnt / num_queries if num_queries > 0 else 0.0
    return df, score


#Example usage
if __name__ == "__main__":
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

    model = "gpt-4o-mini"
    model = "gpt-3.5-turbo"
    # model = "gpt-4o-2024-11-20"

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

        prompt = create_prompt_with_candidates(source_ontology, target_ontology, source_id, info)
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
