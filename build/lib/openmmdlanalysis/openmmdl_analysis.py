"""
mmdl_simulation.py
Perform Simulations of Protein-ligand complexes with OpenMM
"""
import argparse
import sys
import warnings
warnings.filterwarnings("ignore")
import os
import argparse
import MDAnalysis as mda
import pandas as pd
import rdkit
import matplotlib
import pickle
import json
import cairosvg
from collections import Counter
from rdkit import Chem
from rdkit.Chem import AllChem, Draw
from rdkit.Chem.Draw import rdMolDraw2D

from openmmdlanalysis.preprocessing import process_pdb_file, convert_pdb_to_sdf
from openmmdlanalysis.ligand_processing import increase_ring_indices, convert_ligand_to_smiles
from openmmdlanalysis.interaction_gathering import characterize_complex, retrieve_plip_interactions, create_df_from_binding_site, process_frame, process_trajectory
from openmmdlanalysis.binding_mode_processing import gather_interactions, remove_duplicate_values, combine_subdict_values, filtering_values, unique_data_generation, df_iteration_numbering, update_values
from openmmdlanalysis.markov_state_figure_generation import min_transition_calculation, binding_site_markov_network
from openmmdlanalysis.rdkit_figure_generation import split_interaction_data, highlight_numbers, generate_interaction_dict, update_dict, create_and_merge_images, arranged_figure_generation
from openmmdlanalysis.barcode_generation import barcodegeneration,plot_barcodes,plot_waterbridge_piechart
from openmmdlanalysis.visualization_functions import interacting_water_ids, save_interacting_waters_trajectory, cloud_json_generation
from openmmdlanalysis.pml_writer import generate_md_pharmacophore_cloudcenters, generate_bindingmode_pharmacophore, generate_pharmacophore_centers_all_points, generate_point_cloud_pml


def main():
    logo = '\n'.join(["     ,-----.    .-------.     .-''-.  ,---.   .--.,---.    ,---.,---.    ,---. ______       .---.      ",
                  "   .'  .-,  '.  \  _(`)_ \  .'_ _   \ |    \  |  ||    \  /    ||    \  /    ||    _ `''.   | ,_|      ",
                  "  / ,-.|  \ _ \ | (_ o._)| / ( ` )   '|  ,  \ |  ||  ,  \/  ,  ||  ,  \/  ,  || _ | ) _  \,-./  )      ",
                  " ;  \  '_ /  | :|  (_,_) /. (_ o _)  ||  |\_ \|  ||  |\_   /|  ||  |\_   /|  ||( ''_'  ) |\  '_ '`)    ",
                  " |  _`,/ \ _/  ||   '-.-' |  (_,_)___||  _( )_\  ||  _( )_/ |  ||  _( )_/ |  || . (_) `. | > (_)  )    ",
                  " : (  '\_/ \   ;|   |     '  \   .---.| (_ o _)  || (_ o _) |  || (_ o _) |  ||(_    ._) '(  .  .-'    ",
                  "  \ `_/  \  ) / |   |      \  `-'    /|  (_,_)\  ||  (_,_)  |  ||  (_,_)  |  ||  (_.\.' /  `-'`-'|___  ",
                  "   '. \_/``'.'  /   )       \       / |  |    |  ||  |      |  ||  |      |  ||       .'    |        \ ",
                  "     '-----'    `---'        `'-..-'  '--'    '--''--'      '--''--'      '--''-----'`      `--------` ",
                  "              Prepare and Perform OpenMM Protein-Ligand MD Simulations                                 ",
                  "                                     Alpha Version                                                     "])
    
    parser = argparse.ArgumentParser(prog='openmmdl', description=logo, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-t', dest='topology', help='Topology File after MD Simulation', required=True)
    parser.add_argument('-d', dest='trajectory', help='Trajectory File in DCD Format', required=True)
    parser.add_argument('-l', dest='ligand_sdf', help='Ligand in SDF Format', required=True)       
    parser.add_argument('-n', dest='ligand_name', help='Ligand Name (3 Letter Code in PDB)', required=True)
    parser.add_argument('-b', dest='binding', help='Binding Mode Treshold for Binding Mode in %', default=40)   
    parser.add_argument('-df', dest='dataframe', help='Dataframe (use if the interactions were already calculated, default name would be "df_all.csv")', default=None)
    parser.add_argument('-m', dest='min_transition', help='Minimal Transition % for Markov State Model', default=1)
    parser.add_argument('-c', dest='cpu_count', help='CPU Count, specify how many CPUs should be used, default is half of the CPU count', default=os.cpu_count()/2 )

    input_formats = ['.pdb', '.dcd', '.sdf', '.csv'] 
    args = parser.parse_args()
    if input_formats[0] not in args.topology:
        print("PDB is missing, try the absolute path")
    if input_formats[1] not in args.trajectory:
        print("DCD is missing, try the absolute path")
    # if input_formats[2] not in args.ligand_sdf:
    #    print("SDF is missing, try the absolute path")
    if args.ligand_name == None:
        print("Ligand Name is Missing, Add Ligand Name")

    # set variables for analysis and preprocess input files
    topology = args.topology
    trajectory = args.trajectory
    ligand_sdf = args.ligand_sdf
    ligand = args.ligand_name
    if ligand == "*":
       ligand = "UNK"
    treshold = int(args.binding)
    dataframe = args.dataframe
    min_transition = args.min_transition
    cpu_count = int(args.cpu_count)
    process_pdb_file(topology)
    print("\033[1mFiles are preprocessed\033[0m")
    
    pdb_md = mda.Universe(topology, trajectory)

    # Writing out the complex of the protein and ligand with water around 10A of the ligand 
    complex = pdb_md.select_atoms(f"protein or resname {ligand} or (resname HOH and around 10 resname {ligand})")
    complex.write("complex.pdb")
    # Writing out the ligand in a separate pdb file for ring calculation
    ligand_complex = pdb_md.select_atoms(f"resname {ligand}")
    ligand_complex.write("lig.pdb")
    #convert_pdb_to_sdf("lig.pdb", "lig.sdf")
    #ligand_sdf = "ligand_unk_2.sdf"

    # getting Ring Information from the ligand pdb file
    lig_rd = rdkit.Chem.rdmolfiles.MolFromPDBFile("lig.pdb")
    lig_rd_ring = lig_rd.GetRingInfo()

    # getting the index of the first atom of the ligand from the complex pdb
    novel = mda.Universe("complex.pdb")
    novel_lig = novel.select_atoms(f"resname {ligand}")
    for atom in novel_lig:
        lig_index = atom.id
        break
    ligand_rings = []

    # Iterate through each ring, increase indices by 1, and print the updated rings
    for atom_ring in lig_rd_ring.AtomRings():
        updated_ring = increase_ring_indices(atom_ring, lig_index)
        ligand_rings.append(updated_ring)
        print(ligand_rings)
    print("\033[1mLigand ring data gathered\033[0m")
    
    convert_ligand_to_smiles(ligand_sdf,output_smi="lig.smi")
    
    interaction_list = pd.DataFrame(columns=["RESNR", "RESTYPE", "RESCHAIN", "RESNR_LIG", "RESTYPE_LIG", "RESCHAIN_LIG", "DIST", "LIGCARBONIDX", "PROTCARBONIDX", "LIGCOO", "PROTCOO"])

    interaction_list = process_trajectory(pdb_md, dataframe=dataframe, num_processes=cpu_count)

    interaction_list["Prot_partner"] = interaction_list["RESNR"].astype(str) + interaction_list["RESTYPE"] + interaction_list["RESCHAIN"]

    interaction_list = interaction_list.reset_index(drop=True)

    unique_columns_rings_grouped = gather_interactions(interaction_list, ligand_rings)

    interactions_all = interaction_list.copy()

    # Add Frames + Treshold by user
    filtered_values = filtering_values(threshold=treshold/100, frames=len(pdb_md.trajectory)-1, df=interaction_list, unique_columns_rings_grouped=unique_columns_rings_grouped)

    filtering_all = filtering_values(threshold=0.00001, frames=len(pdb_md.trajectory)-1, df=interactions_all, unique_columns_rings_grouped=unique_columns_rings_grouped)

    # Replace NaN values with 0 in the entire DataFrame
    interaction_list.fillna(0, inplace=True)
    interactions_all.fillna(0, inplace=True)

    unique_data = unique_data_generation(filtered_values)
    unique_data_all = unique_data_generation(filtering_all)

    # Iteration through the dataframe and numbering the interactions with 1 and 0, depending if the interaction exists or not
    df_iteration_numbering(interaction_list,unique_data)
    df_iteration_numbering(interactions_all,unique_data_all)
    print("\033[1mInteraction values assigned\033[0m")

    # Saving the dataframe
    interactions_all.to_csv("df_all.csv")

    # Group by 'FRAME' and transform each group to set all values to 1 if there is at least one 1 in each column
    grouped_frames_treshold = interaction_list.groupby('FRAME', as_index=False)[list(unique_data.values())].max()
    grouped_frames_treshold = grouped_frames_treshold.set_index('FRAME', drop=False)

    update_values(interaction_list, grouped_frames_treshold, unique_data)

    # Change the FRAME column value type to int
    grouped_frames_treshold['FRAME'] = grouped_frames_treshold['FRAME'].astype(int)

    # Extract all columns except 'FRAME' and the index column
    selected_columns = grouped_frames_treshold.columns[1:-1]

    # Create a list of lists with the values from selected columns for each row
    treshold_result_list = [row[selected_columns].values.tolist() for _, row in grouped_frames_treshold.iterrows()]

    # Calculate the occurrences of each list in the result_list
    treshold_occurrences = Counter(tuple(lst) for lst in treshold_result_list)

    # Create a new column 'fingerprint' in the DataFrame
    grouped_frames_treshold['fingerprint'] = None

    # Set the 'fingerprint' column values based on the corresponding index in result_list
    for index, fingerprint_value in enumerate(treshold_result_list,1):
        grouped_frames_treshold.at[index, 'fingerprint'] = fingerprint_value

    # Assuming your original DataFrame is named 'df'
    # First, we'll create a new column 'Binding_fingerprint_hbond'
    grouped_frames_treshold['Binding_fingerprint_treshold'] = ''

    # Dictionary to keep track of encountered fingerprints and their corresponding labels
    treshold_fingerprint_dict = {}

    # Counter to generate the labels (Hbond_Binding_1, Hbond_Binding_2, etc.)
    label_counter = 1

    # Iterate through the rows and process the 'fingerprint' column
    for index, row in grouped_frames_treshold.iterrows():
        fingerprint = tuple(row['fingerprint'])
    
        # Check if the fingerprint has been encountered before
        if fingerprint in treshold_fingerprint_dict:
            grouped_frames_treshold.at[index, 'Binding_fingerprint_treshold'] = treshold_fingerprint_dict[fingerprint]
        else:
            # Assign a new label if the fingerprint is new
            label = f'Binding_Mode_{label_counter}'
            treshold_fingerprint_dict[fingerprint] = label
            grouped_frames_treshold.at[index, 'Binding_fingerprint_treshold'] = label
            label_counter += 1

    # Group the DataFrame by the 'Binding_fingerprint_hbond' column and create the dictionary of the fingerprints
    fingerprint_dict = grouped_frames_treshold['Binding_fingerprint_treshold'].to_dict()
    combined_dict = {'all': []}
    for key, value in fingerprint_dict.items():
        combined_dict['all'].append(value)

    # Generate Markov state figures of the binding modes
    total_frames = len(pdb_md.trajectory) - 1
    min_transitions =  min_transition_calculation(min_transition)
    binding_site_markov_network(total_frames, min_transitions, combined_dict)
    print("\033[1mMarkov State Figure generated\033[0m")

    # Get the top 10 nodes with the most occurrences
    node_occurrences = {node: combined_dict['all'].count(node) for node in set(combined_dict['all'])}
    top_10_nodes = sorted(node_occurrences, key=node_occurrences.get, reverse=True)[:10]
    top_10_nodes_with_occurrences = {node: node_occurrences[node] for node in top_10_nodes}
    
    # Initialize an empty dictionary to store the result
    columns_with_value_1 = {}  

    for treshold, row_count in top_10_nodes_with_occurrences.items():
        for i in range(1, row_count + 1):
            # Get the row corresponding to the treshold value
            row = grouped_frames_treshold.loc[grouped_frames_treshold['Binding_fingerprint_treshold'] == treshold].iloc[i - 1]

            # Extract column names with value 1 in that row
            columns_with_1 = row[row == 1].index.tolist()

            # Convert the list to a set to remove duplicates
            columns_set = set(columns_with_1)

            # Add the columns to the dictionary under the corresponding threshold
            if treshold not in columns_with_value_1:
                columns_with_value_1[treshold] = set()
            columns_with_value_1[treshold].update(columns_set)

    # Generate an Figure for each of the binding modes with rdkit Drawer with the atoms interacting highlighted by colors
    matplotlib.use("Agg") 
    binding_site = {}
    merged_image_paths = []
    for binding_mode, values in columns_with_value_1.items():
        binding_site[binding_mode] = values
        occurrence_count = top_10_nodes_with_occurrences[binding_mode]
        occurrence_percent = 100* occurrence_count / total_frames
        with open("lig.smi", "r") as file:
            reference_smiles = file.read().strip()  # Read the SMILES from the file and remove any leading/trailing whitespace
        reference_mol = Chem.MolFromSmiles(reference_smiles)
        prepared_ligand = AllChem.AssignBondOrdersFromTemplate(reference_mol, lig_rd)
        # Generate 2D coordinates for the molecule
        AllChem.Compute2DCoords(prepared_ligand)
        split_data = split_interaction_data(values)
        # Get the highlighted atom indices based on interaction type
        highlighted_hbond_donor, highlighted_hbond_acceptor, highlighted_hbond_both, highlighted_hydrophobic, highlighted_waterbridge,highlighted_pistacking, highlighted_halogen, highlighted_ni, highlighted_pi, highlighted_pication, highlighted_metal = highlight_numbers(split_data, starting_idx=lig_index)

        # Generate a dictionary for hydrogen bond acceptors
        hbond_acceptor_dict = generate_interaction_dict('hbond_acceptor', highlighted_hbond_acceptor)
        # Generate a dictionary for hydrogen bond acceptors and donors
        hbond_both_dict = generate_interaction_dict('hbond_both', highlighted_hbond_both)
        # Generate a dictionary for hydrogen bond donors
        hbond_donor_dict = generate_interaction_dict('hbond_donor', highlighted_hbond_donor)
        # Generate a dictionary for hydrophobic features
        hydrophobic_dict = generate_interaction_dict('hydrophobic', highlighted_hydrophobic)
        # Generate a dictionary for water bridge interactions
        waterbridge_dict = generate_interaction_dict('waterbridge', highlighted_waterbridge)
        # Generate a dictionary for pistacking
        pistacking_dict = generate_interaction_dict('pistacking', highlighted_pistacking)
        # Generate a dictionary for halogen interactions
        halogen_dict = generate_interaction_dict('halogen', highlighted_halogen)
        # Generate a dictionary for negative ionizables
        ni_dict = generate_interaction_dict('ni', highlighted_ni)
        # Generate a dictionary for negative ionizables
        pi_dict = generate_interaction_dict('pi', highlighted_pi)
        # Generate a dictionary for pication
        pication_dict = generate_interaction_dict('pication', highlighted_pication)
        # Generate a dictionary for metal interactions
        metal_dict = generate_interaction_dict('metal', highlighted_metal)

        # Call the function to update hbond_donor_dict with values from other dictionaries
        update_dict(hbond_donor_dict, hbond_acceptor_dict, hydrophobic_dict, hbond_both_dict, waterbridge_dict, pistacking_dict, halogen_dict, ni_dict, pi_dict, pication_dict, metal_dict)

        # Convert the highlight_atoms to int type for rdkit drawer
        highlight_atoms = [int(x) for x in highlighted_hbond_donor + highlighted_hbond_acceptor + highlighted_hbond_both + highlighted_hydrophobic + highlighted_waterbridge + highlighted_pistacking + highlighted_halogen + highlighted_ni + highlighted_pi + highlighted_pication + highlighted_metal]
        highlight_atoms = list(set(highlight_atoms))
    
        # Convert the RDKit molecule to SVG format with atom highlights
        drawer = rdMolDraw2D.MolDraw2DSVG(600, 600)
        drawer.DrawMolecule(prepared_ligand, highlightAtoms=highlight_atoms, highlightAtomColors=hbond_donor_dict)
        drawer.FinishDrawing()
        svg = drawer.GetDrawingText().replace('svg:', '')

        # Save the SVG to a file
        with open(f'{binding_mode}.svg', 'w') as f:
            f.write(svg)

        # Convert the svg to an png
        cairosvg.svg2png(url=f'{binding_mode}.svg', write_to=f'{binding_mode}.png')

        # Generate the interactions legend and combine it with the ligand png
        merged_image_paths = create_and_merge_images(binding_mode, occurrence_percent, split_data, merged_image_paths)

    # Create Figure with all Binding modes
    arranged_figure_generation(merged_image_paths, "all_binding_modes_arranged.png")
    print("\033[1mBinding mode figure generated\033[0m")

    df_all = pd.read_csv('df_all.csv')
    
    # get the top 10 bindingmodes with the most occurrences
    binding_modes = grouped_frames_treshold['Binding_fingerprint_treshold'].str.split('\n')
    all_binding_modes = [mode.strip() for sublist in binding_modes for mode in sublist]
    binding_mode_counts = pd.Series(all_binding_modes).value_counts()
    top_10_binding_modes = binding_mode_counts.head(10)
    total_binding_modes = len(all_binding_modes)
    result_dict = {'Binding Mode': [], 'First Frame': [], 'Percentage Occurrence': []}
    for mode in top_10_binding_modes.index:
        first_frame = grouped_frames_treshold.loc[grouped_frames_treshold['Binding_fingerprint_treshold'].str.contains(mode), 'FRAME'].iloc[0]
        percent_occurrence = (top_10_binding_modes[mode] / total_binding_modes) * 100
        result_dict['Binding Mode'].append(mode)
        result_dict['First Frame'].append(first_frame)
        result_dict['Percentage Occurrence'].append(percent_occurrence)
    top_10_binding_modes_df = pd.DataFrame(result_dict)
    
    id_num = 0
    for index, row in top_10_binding_modes_df.iterrows():
        b_mode = row['Binding Mode']
        first_occurance = row['First Frame']
        filtered_df_all = df_all[df_all['FRAME'] == first_occurance]
        filtered_df_bindingmodes = grouped_frames_treshold[grouped_frames_treshold['FRAME'] == first_occurance]
        bindingmode_dict = {}
        for index, row in filtered_df_bindingmodes.iterrows():
            for column in filtered_df_bindingmodes.columns:
                if column not in ['FRAME', 'FRAME.1', 'fingerprint', 'Binding_fingerprint_treshold']:
                    if row[column] == 1:
                        if column not in bindingmode_dict:
                            bindingmode_dict[column] = {"LIGCOO": [], "PROTCOO": []}  # Initialize a nested dictionary for each key if not already present
                        for index2, row2 in filtered_df_all.iterrows():
                            if row2[column] == 1:
                                # Extract the string representation of the tuple
                                tuple_string = row2['LIGCOO']
                                # Split the string into individual values using a comma as the delimiter
                                ligcoo_values = tuple_string.strip('()').split(',')
                                # Convert the string values to float
                                ligcoo_values = [float(value.strip()) for value in ligcoo_values]

                                # Extract the string representation of the tuple for PROTCOO
                                tuple_string = row2['PROTCOO']
                                # Split the string into individual values using a comma as the delimiter
                                protcoo_values = tuple_string.strip('()').split(',')
                                # Convert the string values to float
                                protcoo_values = [float(value.strip()) for value in protcoo_values]

                                bindingmode_dict[column]["LIGCOO"].append(ligcoo_values)
                                bindingmode_dict[column]["PROTCOO"].append(protcoo_values)
        generate_bindingmode_pharmacophore(bindingmode_dict, ligand, f"{ligand}_complex", b_mode, id_num)
        
    
    hydrophobic_interactions = df_all.filter(regex='hydrophobic').columns
    acceptor_interactions = df_all.filter(regex='Acceptor_hbond').columns
    donor_interactions = df_all.filter(regex='Donor_hbond').columns
    pistacking_interactions = df_all.filter(regex='pistacking').columns
    halogen_interactions = df_all.filter(regex='halogen').columns
    waterbridge_interactions = df_all.filter(regex='waterbridge').columns
    pication_interactions = df_all.filter(regex='pication').columns
    saltbridge_ni_interactions = df_all.filter(regex='NI_saltbridge').columns
    saltbridge_pi_interactions = df_all.filter(regex='PI_saltbridge').columns

    hydrophobicinteraction_barcodes = {}
    for hydrophobic_interaction in hydrophobic_interactions:
        barcode = barcodegeneration(df_all, hydrophobic_interaction)
        hydrophobicinteraction_barcodes[hydrophobic_interaction] = barcode

    acceptor_barcodes = {}
    for acceptor_interaction in acceptor_interactions:
        barcode = barcodegeneration(df_all, acceptor_interaction)
        acceptor_barcodes[acceptor_interaction] = barcode

    donor_barcodes = {}
    for donor_interaction in donor_interactions:
        barcode = barcodegeneration(df_all, donor_interaction)
        donor_barcodes[donor_interaction] = barcode

    pistacking_barcodes = {}
    for pistacking_interaction in pistacking_interactions:
        barcode = barcodegeneration(df_all, pistacking_interaction)
        pistacking_barcodes[pistacking_interaction] = barcode

    halogen_barcodes = {}
    for halogen_interaction in halogen_interactions:
        barcode = barcodegeneration(df_all, halogen_interaction)
        halogen_barcodes[halogen_interaction] = barcode

    waterbridge_barcodes = {}
    for waterbridge_interaction in waterbridge_interactions:
        barcode = barcodegeneration(df_all, waterbridge_interaction)
        waterbridge_barcodes[waterbridge_interaction] = barcode

    pication_barcodes = {}
    for pication_interaction in pication_interactions:
        barcode = barcodegeneration(df_all, pication_interaction)
        pication_barcodes[pication_interaction] = barcode

    saltbridge_ni_barcodes = {}
    for saltbridge_ni_interaction in saltbridge_ni_interactions:
        barcode = barcodegeneration(df_all, saltbridge_ni_interactions)
        saltbridge_ni_barcodes[saltbridge_ni_interaction] = barcode

    saltbridge_pi_barcodes = {}
    for saltbridge_pi_interaction in saltbridge_pi_interactions:
        barcode = barcodegeneration(df_all, saltbridge_pi_interactions)
        saltbridge_pi_barcodes[saltbridge_pi_interaction] = barcode
    
    plot_barcodes(hydrophobicinteraction_barcodes, "hydrophobic_barcodes.png")
    plot_barcodes(acceptor_barcodes, "acceptor_barcodes.png")
    plot_barcodes(donor_barcodes, "donor_barcodes.png")
    plot_barcodes(pistacking_barcodes, "pistacking_barcodes.png")
    plot_barcodes(halogen_barcodes, "halogen_barcodes.png")
    plot_barcodes(pication_barcodes, "pication_barcodes.png")
    plot_barcodes(waterbridge_barcodes, "waterbridge_barcodes.png")
    plot_barcodes(saltbridge_ni_barcodes, "saltbridge_ni_barcodes.png")
    plot_barcodes(saltbridge_pi_barcodes, "saltbridge_pi_barcodes.png")
    plot_waterbridge_piechart(df_all, waterbridge_barcodes, waterbridge_interactions)
    print("\033[1mBarcodes generated\033[0m")

    interacting_water_id_list = interacting_water_ids(df_all, waterbridge_interactions)

    # dump interacting waters for visualization
    with open('interacting_waters.pkl', 'wb') as f:
        pickle.dump(interacting_water_id_list, f)
    save_interacting_waters_trajectory(topology, trajectory, interacting_water_id_list)

    # save clouds for visualization with NGL
    with open('clouds.json', 'w') as f:
        json.dump(cloud_json_generation(df_all), f)
        
    # generate poincloud pml for visualization    
    cloud_dict = {}
    cloud_dict["H"] = generate_pharmacophore_centers_all_points(df_all, df_all.filter(regex='hydrophobic').columns)
    cloud_dict["HBA"] = generate_pharmacophore_centers_all_points(df_all, df_all.filter(regex='Acceptor_hbond').columns)
    cloud_dict["HBD"] = generate_pharmacophore_centers_all_points(df_all, df_all.filter(regex='Donor_hbond').columns)
    cloud_dict["AR"] = generate_pharmacophore_centers_all_points(df_all, df_all.filter(regex='pistacking').columns)
    cloud_dict["PI"] = generate_pharmacophore_centers_all_points(df_all, df_all.filter(regex='PI_saltbridge').columns)
    cloud_dict["NI"] = generate_pharmacophore_centers_all_points(df_all, df_all.filter(regex='NI_saltbridge').columns)
    
    generate_point_cloud_pml(cloud_dict, f"{ligand}_complex", "point_cloud")
        
    # generate combo pharmacophore of the md with each interaction as a single pharmacophore feature
    generate_md_pharmacophore_cloudcenters(df_all, ligand, "combopharm.pml", f"{ligand}_complex")

    print("\033[1mPharmacophores generated\033[0m")
    print("\033[1mAnalysis is Finished.\033[0m")
    
    
if __name__ == "__main__":
    main()
