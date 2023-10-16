openmmdlanalysis
==============================

Analyze your molecular dynamics simulations for receptor ligand interactions.

## Instalation
### Clone this repository
``` 
git clone https://github.com/.....
```
### Install dependencies
Openmmdlanalysis uses a multitude of different tools to analyze and visualize your receptor ligand interactions.

Please create a new conda environment to overt any issues with the instalation.
```
cd /YOUR_SAVE_PATH/openmmdlanalysis/
conda create -n openmmdlanalysis -c conda-forge --file requirements.txt
```
### Install the package
Now that the dependencies are resolved in the conda environment, we can install openmmdlanalysis (be sure you in the downloaded repository where the pyproject.toml is located).
```
conda activate openmmdlanalysis
pip install .
```
## Run openmmdlanalysis
### Analysis
The analysis of your molecular dynamics trajectorie can now be started anywhere (just activate the conda environment).
```
openmmdlanalysis -t YOUR_TOPOLOGY.pdb -d YOUR_TRAJECTORY.dcd -l YOUR_LIGAND.sdf -n 'YOUR_LIGANDS_NAME'
```
-t = your systems topology file in PDB file format

-d = your trajectory file in DCD file format

-l = your ligand as an SDF file (best directly exported from the topology file(-t))

-n = the name of your ligand in the PDB topology

### Visualization
Most of the analysis outputs are JEPG images and do not need any further preperation to be viewed.

For the visualization of trajectory with interaction pointclouds you can use the jupyter notebook prepared in the openmmdlanalysis repository.
```
jupyter notebook /YOUR_SAVE_PATH/openmmdlanalysis/visualization.ipynb
```

#### Copyright

Copyright (c) 2023, Molecular Design Lab


#### Acknowledgements
 
Project based on the 
[Computational Molecular Science Python Cookiecutter](https://github.com/molssi/cookiecutter-cms) version 1.1.
