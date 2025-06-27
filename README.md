# EntityAlignment

##  Environment Setup

To reproduce the development environment and run the application, follow these steps:

### 1. Install Conda

If you don’t already have Conda installed, you can install [Miniconda](https://docs.conda.io/en/latest/miniconda.html):

```bash
# On Linux or macOS
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
```
### 2. Create the Conda Environment
```bash
conda env create -f environment.yml
```

### 3. Activate the Environment
```bash
conda activate entity-alignment
```

### 3. Setup dependencies

The application requires OpenAI API key for classification with LLM
The key should be placed in a file [.env](.env)
With content:

OPENAI_API_KEY="your key"


The application requires a running GraphDB instance
The provided [docker-compose.yml](docker-compose/docker-compose.yml) can be used to start GraphDB

Docker and docker-compose are required to be installed.
The docker-compose can be started with:
```bash
/usr/bin/docker-compose -f docker-compose/docker-compose.yml -p docker-compose up -d
```
This setup also persists the ingested data into folder docker-compose/data

Alternatively GraphDB can be started as an executable, more info at https://graphdb.ontotext.com/documentation/10.8/graphdb-desktop-installation.html

The data used for the project can be provided on request.

It contains rdf files of ontologies from https://bioportal.bioontology.org/ontologies
And additionally it has two Similarity indexes created "doid_labels" and "mesh_labels", created respectively from the DOID and MESH ontologies.


### 5. Run the App
```bash
streamlit run app/demo.py
```