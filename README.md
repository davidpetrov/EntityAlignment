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

### 4. Run the App
```bash
streamlit run app/demo.py
```