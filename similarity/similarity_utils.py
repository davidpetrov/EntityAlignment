from SPARQLWrapper import SPARQLWrapper, JSON
import pandas as pd

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